#!/bin/bash
# Double-clickable installer: installs memory-hub and wires every detectable agent.
set -e

HUB="$HOME/memory-hub"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo ""
echo "  memory-hub installer"
echo "  one memory. every agent. yours."
echo ""

mkdir -p "$HUB"
cp "$SCRIPT_DIR/memory_hub.py" "$HUB/"

echo "==> Installing dependency (mcp<2)..."
pip3 install "mcp<2" --quiet 2>/dev/null || pip3 install "mcp<2" --break-system-packages --quiet

WIRED=()
TODO=()

echo "==> Claude Code..."
if command -v claude >/dev/null 2>&1; then
  if claude mcp add memory-hub -- python3 "$HUB/memory_hub.py" >/dev/null 2>&1; then
    WIRED+=("Claude Code")
  else
    TODO+=("Claude Code (wiring command failed)")
  fi
else
  TODO+=("Claude Code (not installed)")
fi

echo "==> opencode..."
OC_CONFIG="$HOME/.config/opencode/opencode.json"
if [ -f "$OC_CONFIG" ]; then
  python3 - "$OC_CONFIG" << 'PYEOF'
import json, os, sys
p = sys.argv[1]
cfg = json.load(open(p))
cfg.setdefault("mcp", {})["memory-hub"] = {
    "type": "local",
    "command": ["python3", os.path.expanduser("~/memory-hub/memory_hub.py")],
}
json.dump(cfg, open(p, "w"), indent=2)
PYEOF
  WIRED+=("opencode")
else
  TODO+=("opencode (config not found)")
fi

echo "==> Cursor / Windsurf / Claude Desktop..."
for CFG in "$HOME/.cursor/mcp.json:Cursor" "$HOME/.codeium/windsurf/mcp_config.json:Windsurf" "$HOME/Library/Application Support/Claude/claude_desktop_config.json:Claude Desktop"; do
  P=${CFG%%:*}
  NAME=${CFG##*:}
  if [ -f "$P" ]; then
    python3 - "$P" << 'PYEOF'
import json, os, sys
p = sys.argv[1]
cfg = json.load(open(p))
cfg.setdefault("mcpServers", {})["memory-hub"] = {
    "command": "python3",
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
  if "$HERMES_BIN" mcp add memory-hub --command python3 --args "$HUB/memory_hub.py" >/dev/null 2>&1; then
    WIRED+=("Hermes")
  else
    TODO+=("Hermes (run: hermes mcp add, point it at python3 $HUB/memory_hub.py)")
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
