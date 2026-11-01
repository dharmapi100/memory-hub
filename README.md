# memory-hub

**One memory. Every agent.** Local-first shared memory for AI agents, built on MCP.

You use Claude Code to build, Hermes to orchestrate, opencode to refactor. Each one forgets what the others know. memory-hub gives them all one memory - a single SQLite file that lives on your Mac, that every agent reads and writes, and that no vendor can take away.

## Install

```
pip3 install "mcp<2"
```

Save `memory_hub.py` to `~/memory-hub/`. Your memory lives at `~/.memory-hub/memory.db`. Back it up like a dotfile; it is yours and it is portable.

Or use the packaged installer (see `installer/`) - it wires Claude Code, Cursor, Windsurf, Claude Desktop and opencode automatically.

## Wire up your agents

### Claude Code

```
claude mcp add memory-hub -- python3 ~/memory-hub/memory_hub.py
```

### opencode

```json
{
  "mcp": {
    "memory-hub": {
      "type": "local",
      "command": ["python3", "~/memory-hub/memory_hub.py"]
    }
  }
}
```

### Anything else

Point it at `python3 ~/memory-hub/memory_hub.py` over stdio. If it speaks MCP, it can share your memory.

## The 7 tools

| tool | what it does |
|---|---|
| `remember` | store a fact/decision/preference. `source` is REQUIRED - which agent is writing |
| `recall` | keyword search over active memories; warns when conflict-flagged results are served |
| `brief` | session-start load: pinned first, then recent |
| `update` | correct a memory (old version kept as superseded) |
| `forget` | archive by id or text match (archive, not delete) |
| `consolidate` | merge near-duplicates. never merges conflict-flagged pairs |
| `stats` | store health: counts, duplicate estimate, conflicts, oldest unpinned |

## House rules for agents

- Session start: call `brief`
- New durable fact: `remember` with your agent name as `source`
- Wrong fact on record: `update`, never re-remember (that is how dupes happen)
- `pinned=true` only for identity-level facts and standing rules

## Design principles

- **Memory is claims with provenance, not truth.** Every memory records which agent wrote it and when
- **Conflicts are surfaced, never silently resolved.** When two agents contradict each other, both stay active, flagged, and every `recall` warns. The human settles it once
- **Nothing is ever hard-deleted.** Corrections supersede; removals archive. Every version stays auditable
- **Local-first, permanently.** No cloud, no account, no telemetry. Memory you rent improves the vendor. Memory you own compounds

## Known limits (v0.2)

- Consolidation is lexical (sequence + token overlap). Semantic dedup via embeddings is v1
- Single-machine. Cross-machine sync via plain file sync is untested

## License

MIT