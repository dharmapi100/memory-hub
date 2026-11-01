#!/bin/bash
# Double-clickable installer: installs memory-hub and wires every detectable agent.
set -e
HUB="$HOME/memory-hub"
mkdir -p "$HUB"
cp "$(dirname "$0")/memory_hub.py" "$HUB/"

echo "==> Installing dependency (mcp<2)..."
pip3 install "mcp<2" --quiet || pip3 install "mcp<2" --break-system-packages --quiet

echo "==> Wiring Claude Code..."
if command -v claude >/dev/null 2>&1; then
  claude mcp add memory-hub -- python3 "$HUB/memory_hub.py" || true
else
  echo "    claude not found - skipped"
fi

echo "==> Wiring opencode..."
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
print("    wired")
PYEOF
else
  echo "    opencode config not found - skipped"
fi

echo "==> Wiring Cursor / Windsurf / Claude Desktop (MCP json, if present)..."
for CFG in "$HOME/.cursor/mcp.json" "$HOME/.codeium/windsurf/mcp_config.json" "$HOME/Library/Application Support/Claude/claude_desktop_config.json"; do
  if [ -f "$CFG" ]; then
    python3 - "$CFG" << 'PYEOF'
import json, os, sys
p = sys.argv[1]
cfg = json.load(open(p))
cfg.setdefault("mcpServers", {})["memory-hub"] = {
    "command": "python3",
    "args": [os.path.expanduser("~/memory-hub/memory_hub.py")],
}
json.dump(cfg, open(p, "w"), indent=2)
print("    wired:", p)
PYEOF
  fi
done

echo ""
echo "==> memory-hub installed to $HUB"
echo "==> Your memory lives at ~/.memory-hub/memory.db"
echo "==> Start a new session in any wired agent and run: brief"
