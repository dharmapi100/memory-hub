#!/bin/bash
# Double-clickable installer: installs memory-hub and wires every detectable agent.
set -e

HUB="$HOME/memory-hub"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo ""
echo "  memory-hub installer"
echo "  one memory. every agent. yours."
echo ""

# mcp requires Python >= 3.10. macOS's stock /usr/bin/python3 (Xcode CLT) is
# often 3.9.x, so probe for a newer interpreter instead of assuming "python3".
find_python() {
  for candidate in python3.13 python3.12 python3.11 python3.10 python3; do
    PYBIN="$(command -v "$candidate" 2>/dev/null)" || continue
    if "$PYBIN" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
      echo "$PYBIN"
      return 0
    fi
  done
  return 1
}

PY="$(find_python)" || {
  echo "  memory-hub needs Python 3.10 or newer. This Mac's python3 is:"
  python3 --version 2>&1 | sed 's/^/    /'
  echo ""
  echo "  Install a newer one, then re-run this installer:"
  echo "    brew install python@3.12"
  echo ""
  exit 1
}
echo "==> Using $PY ($("$PY" --version 2>&1))"

mkdir -p "$HUB"
cp "$SCRIPT_DIR/memory_hub.py" "$HUB/"

echo "==> Installing dependency (mcp<2)..."
"$PY" -m pip install "mcp<2" --quiet 2>/dev/null || "$PY" -m pip install "mcp<2" --user --break-system-packages --quiet

WIRED=()
TODO=()

echo "==> Claude Code..."
if command -v claude >/dev/null 2>&1; then
  if claude mcp add memory-hub -- "$PY" "$HUB/memory_hub.py" >/dev/null 2>&1; then
    WIRED+=("Claude Code")
  else
    TODO+=("Claude Code (wiring command failed)")
  fi
else
  TODO+=("Claude Code (not installed)")
fi

echo "==> opencode..."
# opencode's current default config filename is opencode.jsonc (JSON with
# // comments allowed); older setups may still have opencode.json. Check both.
OC_CONFIG=""
for CANDIDATE in "$HOME/.config/opencode/opencode.jsonc" "$HOME/.config/opencode/opencode.json"; do
  if [ -f "$CANDIDATE" ]; then
    OC_CONFIG="$CANDIDATE"
    break
  fi
done
if [ -n "$OC_CONFIG" ]; then
  if "$PY" - "$OC_CONFIG" "$PY" << 'PYEOF'
import json, os, re, sys
p, py = sys.argv[1], sys.argv[2]
raw = open(p).read()

def strip_jsonc(text):
    # Remove // and /* */ comments while respecting string literals.
    out, i, in_str, n = [], 0, False, len(text)
    while i < n:
        c = text[i]
        if in_str:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(text[i + 1]); i += 2; continue
            if c == '"':
                in_str = False
            i += 1; continue
        if c == '"':
            in_str = True; out.append(c); i += 1; continue
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            j = text.find("\n", i)
            i = n if j == -1 else j
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "*":
            j = text.find("*/", i + 2)
            i = n if j == -1 else j + 2
            continue
        out.append(c); i += 1
    return "".join(out)

try:
    cfg = json.loads(raw)
except json.JSONDecodeError:
    cfg = json.loads(strip_jsonc(raw))

cfg.setdefault("mcp", {})["memory-hub"] = {
    "type": "local",
    "command": [py, os.path.expanduser("~/memory-hub/memory_hub.py")],
}
json.dump(cfg, open(p, "w"), indent=2)
PYEOF
  then
    WIRED+=("opencode")
  else
    TODO+=("opencode (found $OC_CONFIG but it could not be parsed/updated - edit it by hand)")
  fi
else
  TODO+=("opencode (config not found)")
fi

echo "==> Cursor / Windsurf / Claude Desktop..."
for CFG in "$HOME/.cursor/mcp.json:Cursor" "$HOME/.codeium/windsurf/mcp_config.json:Windsurf" "$HOME/Library/Application Support/Claude/claude_desktop_config.json:Claude Desktop"; do
  P=${CFG%%:*}
  NAME=${CFG##*:}
  if [ -f "$P" ]; then
    "$PY" - "$P" "$PY" << 'PYEOF'
import json, os, sys
p, py = sys.argv[1], sys.argv[2]
cfg = json.load(open(p))
cfg.setdefault("mcpServers", {})["memory-hub"] = {
    "command": py,
    "args": [os.path.expanduser("~/memory-hub/memory_hub.py")],
}
json.dump(cfg, open(p, "w"), indent=2)
PYEOF
    WIRED+=("$NAME")
  else
    TODO+=("$NAME (not installed)")
  fi
done

echo "==> Hermes..."
HERMES_BIN=""
if command -v hermes >/dev/null 2>&1; then
  HERMES_BIN="$(command -v hermes)"
elif [ -x "$HOME/.hermes/hermes-agent/venv/bin/hermes" ]; then
  HERMES_BIN="$HOME/.hermes/hermes-agent/venv/bin/hermes"
fi
if [ -n "$HERMES_BIN" ]; then
  if echo "y" | "$HERMES_BIN" mcp add memory-hub --command "$PY" --args "$HUB/memory_hub.py" >/dev/null 2>&1; then
    WIRED+=("Hermes")
  else
    TODO+=("Hermes (run: hermes mcp add, point it at $PY $HUB/memory_hub.py)")
  fi
else
  TODO+=("Hermes (not installed)")
fi

echo ""
echo "  ----------------------------------------"
echo "  Installed. Your memory lives at:"
echo "    ~/.memory-hub/memory.db"
echo ""
if [ ${#WIRED[@]} -gt 0 ]; then
  echo "  Wired automatically:"
  for w in "${WIRED[@]}"; do echo "    + $w"; done
fi
if [ ${#TODO[@]} -gt 0 ]; then
  echo ""
  echo "  Needs one step (or not installed):"
  for t in "${TODO[@]}"; do echo "    - $t"; done
fi
echo ""
echo "  Start a NEW session in any wired agent and run: brief"
echo "  ----------------------------------------"
echo ""
