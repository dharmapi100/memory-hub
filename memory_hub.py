#!/usr/bin/env python3
"""
memory-hub: local-first shared memory for all your AI agents.

One SQLite file (~/.memory-hub/memory.db). Every MCP-capable agent
(Claude Code, opencode, Hermes, ...) connects and reads/writes the
same memory store. v0.2: conflict flags recomputed on every write,
so they can never go stale.

Tools exposed over MCP:
  remember(content, source, category, tags, pinned)  - source is REQUIRED
  recall(query, limit)         - search active memories
  brief(limit)                 - session-start brief (pinned + recent)
  update(memory_id, content)   - correct a memory (supersedes old)
  forget(memory_id | query)    - archive by id or text match
  consolidate()                - merge near-duplicates (never merges conflicts)
  stats()                      - store health: counts, dup estimate, pulse
"""

import os
import re
import sqlite3
import time
from difflib import SequenceMatcher

from mcp.server.fastmcp import FastMCP

DB_PATH = os.environ.get(
    "MEMORY_HUB_DB", os.path.expanduser("~/.memory-hub/memory.db")
)

SIMILARITY = 0.55
CONFLICT_OVERLAP = 0.60

SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  content TEXT NOT NULL,
  category TEXT DEFAULT 'general',
  tags TEXT DEFAULT '',
  source TEXT DEFAULT '',
  status TEXT DEFAULT 'active',
  pinned INTEGER DEFAULT 0,
  conflict INTEGER DEFAULT 0,
  supersedes INTEGER,
  created_at REAL,
  updated_at REAL
);
CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
  content, tags, content='memories', content_rowid='id'
);
CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
  INSERT INTO memories_fts(rowid, content, tags)
  VALUES (new.id, new.content, new.tags);
END;
CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
  INSERT INTO memories_fts(memories_fts, rowid, content, tags)
  VALUES ('delete', old.id, old.content, old.tags);
  INSERT INTO memories_fts(rowid, content, tags)
  VALUES (new.id, new.content, new.tags);
END;
CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
  INSERT INTO memories_fts(memories_fts, rowid, content, tags)
  VALUES ('delete', old.id, old.content, old.tags);
END;
"""

NEGATION_RE = re.compile(
    r"\bnot\b|\bnever\b|\bwithout\b|\bno\b|\bdon'?t\b|\bdoesn'?t\b"
    r"|\bisn'?t\b|\baren'?t\b|\bwon'?t\b|\bcan'?t\b|\bcannot\b"
    r"|\bneither\b|\bnor\b|\bshouldn'?t\b|\bexcept\b"
)


def db() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    try:
        conn.execute("ALTER TABLE memories ADD COLUMN conflict INTEGER DEFAULT 0")
        conn.commit()
    except sqlite3.OperationalError:
        pass
    return conn


def norm(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]", " ", text.lower()).strip()


def similar(a: str, b: str) -> float:
    na, nb = norm(a), norm(b)
    seq = SequenceMatcher(None, na, nb).ratio()
    ta, tb = set(na.split()), set(nb.split())
    jac = len(ta & tb) / len(ta | tb) if ta and tb else 0.0
    return max(seq, jac)


def has_negation(text: str) -> bool:
    return bool(NEGATION_RE.search(text.lower()))


def fts_safe(query: str) -> str:
    words = re.findall(r"[a-zA-Z0-9_]+", query)
    return " OR ".join(f'"{w}"' for w in words)


def row_to_dict(row) -> dict:
    return {
        "id": row["id"],
        "content": row["content"],
        "category": row["category"],
        "tags": row["tags"],
        "source": row["source"],
        "pinned": bool(row["pinned"]),
        "conflict": bool(row["conflict"]),
        "updated": time.strftime(
            "%Y-%m-%d %H:%M", time.localtime(row["updated_at"])
        ),
    }


def _recompute_conflicts(conn):
    """Rebuild conflict flags for all active memories from scratch.
    A conflict = token overlap >= CONFLICT_OVERLAP with opposite polarity
    (one side negated, the other not). Flags can never go stale because
    every write path calls this."""
    conn.execute("UPDATE memories SET conflict=0 WHERE status='active'")
    rows = conn.execute(
        "SELECT id, content FROM memories WHERE status='active' ORDER BY id"
    ).fetchall()
    flagged = set()
    for i, a in enumerate(rows):
        for b in rows[i + 1:]:
            if similar(a["content"], b["content"]) >= CONFLICT_OVERLAP:
                if has_negation(a["content"]) != has_negation(b["content"]):
                    flagged.add(a["id"])
                    flagged.add(b["id"])
    for mid in flagged:
        conn.execute("UPDATE memories SET conflict=1 WHERE id=?", (mid,))
    conn.commit()
    return len(flagged)


# ---------- core logic (plain functions, testable without MCP) ----------

def _remember(content, category, tags, source, pinned):
    if not source or not source.strip():
        return {"error": "source is required - which agent is writing? (e.g. 'hermes')"}
    content = content.strip()
    conn = db()
    now = time.time()
    result = {"status": "remembered"}
    near_dups = []
    for r in conn.execute("SELECT * FROM memories WHERE status='active'").fetchall():
        if similar(content, r["content"]) >= SIMILARITY:
            near_dups.append(r["id"])
    if pinned:
        clash = conn.execute(
            "SELECT id FROM memories WHERE status='active' AND pinned=1"
            " AND source=? AND category=?", (source, category),
        ).fetchone()
        if clash:
            result["pin_key_warning"] = (
                f"active pinned memory #{clash['id']} already has source='{source}',"
                f" category='{category}' - use source:key convention for distinct pins"
            )
    cur = conn.execute(
        "INSERT INTO memories (content, category, tags, source, pinned, created_at, updated_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (content, category.strip(), tags.strip(), source.strip(), int(pinned), now, now),
    )
    conn.commit()
    mid = cur.lastrowid
    result["id"] = mid
    if near_dups:
        result["near_duplicates"] = near_dups
        result["note"] = "possible duplicates on record - consider update() instead next time"
    flagged = _recompute_conflicts(conn)
    if conn.execute("SELECT conflict FROM memories WHERE id=?", (mid,)).fetchone()["conflict"]:
        result["conflict"] = True
        result["note"] = ("possible contradiction: overlaps an active memory with opposite"
                          " polarity. recall() will flag these. resolve with update() or forget().")
    elif flagged:
        result["note"] = f"conflict flags refreshed on {flagged} active memories"
    return result


def _recall(query, limit=8):
    conn = db()
    if query.strip():
        rows = conn.execute(
            "SELECT m.* FROM memories_fts f JOIN memories m ON m.id = f.rowid"
            " WHERE memories_fts MATCH ? AND m.status = 'active'"
            " ORDER BY m.pinned DESC, rank, m.updated_at DESC LIMIT ?",
            (fts_safe(query), limit),
        ).fetchall()
        if not rows:
            like = f"%{query.strip()}%"
            rows = conn.execute(
                "SELECT * FROM memories WHERE status='active' AND (content LIKE ? OR tags LIKE ?)"
                " ORDER BY pinned DESC, updated_at DESC LIMIT ?",
                (like, like, limit),
            ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM memories WHERE status='active'"
            " ORDER BY pinned DESC, updated_at DESC LIMIT ?", (limit,),
        ).fetchall()
    results = [row_to_dict(r) for r in rows]
    out = {"results": results}
    if any(r["conflict"] for r in results):
        out["warning"] = ("results include conflict-flagged memories:"
                          " contradicting versions are both active. verify before use.")
    return out


def _brief(limit=15):
    conn = db()
    pinned = conn.execute(
        "SELECT * FROM memories WHERE status='active' AND pinned=1 ORDER BY updated_at DESC"
    ).fetchall()
    recent = conn.execute(
        "SELECT * FROM memories WHERE status='active' AND pinned=0"
        " ORDER BY updated_at DESC LIMIT ?", (max(limit - len(pinned), 0),),
    ).fetchall()
    return {
        "pinned": [row_to_dict(r) for r in pinned],
        "recent": [row_to_dict(r) for r in recent],
        "hint": "recall(query) for specifics; update() to correct; consolidate() when this brief gets bloated",
    }


def _update(memory_id, new_content):
    now = time.time()
    conn = db()
    old = conn.execute("SELECT * FROM memories WHERE id=?", (memory_id,)).fetchone()
    if not old:
        return {"error": f"no memory with id {memory_id}"}
    conn.execute(
        "UPDATE memories SET status='superseded', updated_at=? WHERE id=?",
        (now, memory_id),
    )
    cur = conn.execute(
        "INSERT INTO memories (content, category, tags, source, pinned, supersedes, created_at, updated_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (new_content.strip(), old["category"], old["tags"], old["source"],
         old["pinned"], old["id"], now, now),
    )
    conn.commit()
    _recompute_conflicts(conn)
    new_id = cur.lastrowid
    out = {"new_id": new_id, "superseded_id": memory_id}
    if conn.execute("SELECT conflict FROM memories WHERE id=?", (new_id,)).fetchone()["conflict"]:
        out["conflict"] = True
        out["note"] = "the corrected memory still contradicts another active memory"
    return out


def _forget(memory_id=None, query=None):
    conn = db()
    now = time.time()
    if memory_id:
        cur = conn.execute(
            "UPDATE memories SET status='archived', updated_at=? WHERE id=?",
            (now, memory_id),
        )
    elif query:
        cur = conn.execute(
            "UPDATE memories SET status='archived', updated_at=? WHERE status='active'"
            " AND content LIKE ?",
            (now, f"%{query}%"),
        )
    else:
        return {"error": "give memory_id or query"}
    conn.commit()
    _recompute_conflicts(conn)
    return {"archived": cur.rowcount}


def _consolidate(similarity=SIMILARITY):
    conn = db()
    rows = conn.execute(
        "SELECT * FROM memories WHERE status='active' ORDER BY id"
    ).fetchall()
    used, merges = set(), []
    for i, a in enumerate(rows):
        if a["id"] in used:
            continue
        used.add(a["id"])
        for b in rows[i + 1:]:
            if b["id"] in used or b["category"] != a["category"]:
                continue
            if a["conflict"] or b["conflict"]:
                continue
            if similar(a["content"], b["content"]) >= similarity:
                used.add(b["id"])
                merges.append((b, a))
    now = time.time()
    for dup, keeper in merges:
        conn.execute(
            "UPDATE memories SET status='superseded', supersedes=?, updated_at=? WHERE id=?",
            (keeper["id"], now, dup["id"]),
        )
    conn.commit()
    _recompute_conflicts(conn)
    return {
        "merged": len(merges),
        "active_left": conn.execute(
            "SELECT COUNT(*) c FROM memories WHERE status='active'"
        ).fetchone()["c"],
        "detail": [
            f"dup #{d['id']} -> keeper #{k['id']} ({k['category']})" for d, k in merges
        ],
    }


def _stats():
    conn = db()
    counts = conn.execute(
        "SELECT status, COUNT(*) c FROM memories GROUP BY status"
    ).fetchall()
    active = conn.execute(
        "SELECT id, content, updated_at, pinned, conflict FROM memories WHERE status='active'"
    ).fetchall()
    dup_pairs = 0
    for i, a in enumerate(active):
        if a["conflict"]:
            continue
        for b in active[i + 1:]:
            if b["conflict"]:
                continue
            if has_negation(a["content"]) != has_negation(b["content"]):
                continue
            if similar(a["content"], b["content"]) >= 0.70:
                dup_pairs += 1
    unpinned = [r["updated_at"] for r in active if not r["pinned"]]
    return {
        "db": DB_PATH,
        "counts": {r["status"]: r["c"] for r in counts},
        "store_health": {
            "active": len(active),
            "estimated_duplicate_pairs": dup_pairs,
            "conflict_flagged": sum(1 for r in active if r["conflict"]),
            "oldest_unpinned_days": (
                round((time.time() - min(unpinned)) / 86400, 1) if unpinned else None
            ),
        },
    }


# ---------- MCP surface ----------

mcp = FastMCP("memory-hub")


@mcp.tool()
def remember(content: str, source: str, category: str = "general",
             tags: str = "", pinned: bool = False) -> dict:
    """Store a fact, decision, or preference in the shared hub.
    source is REQUIRED: which agent is writing (e.g. 'claude-code', 'hermes')."""
    return _remember(content, category, tags, source, pinned)


@mcp.tool()
def recall(query: str, limit: int = 8) -> dict:
    """Search active memories by keyword. Empty query = most recent.
    Flags a warning when conflict-flagged (contradicting) memories are returned."""
    return _recall(query, limit)


@mcp.tool()
def brief(limit: int = 15) -> dict:
    """Session-start brief: pinned memories first, then recent."""
    return _brief(limit)


@mcp.tool()
def update(memory_id: int, new_content: str) -> dict:
    """Correct or replace a memory. Old version is kept as superseded;
    conflict flags are recomputed against the corrected content."""
    return _update(memory_id, new_content)


@mcp.tool()
def forget(memory_id: int = None, query: str = None) -> dict:
    """Archive memories by id, or all active memories matching text."""
    return _forget(memory_id, query)


@mcp.tool()
def consolidate(similarity: float = SIMILARITY) -> dict:
    """Merge near-duplicate memories (lexical match; keeps newest, archives rest).
    Never merges conflict-flagged pairs - contradictions need a human."""
    return _consolidate(similarity)


@mcp.tool()
def stats() -> dict:
    """Store health: db path, per-status counts, duplicate estimate,
    conflict count, age of oldest unpinned memory."""
    return _stats()


if __name__ == "__main__":
    mcp.run(transport="stdio")
