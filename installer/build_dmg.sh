#!/bin/bash
# Builds MemoryHub.dmg on macOS. Run from the repo's installer/ folder (or anywhere in the repo).
# Produces MemoryHub.dmg containing memory_hub.py + Install.command.
set -e
cd "$(dirname "$0")"

# memory_hub.py lives at the repo root; this script lives in installer/.
SERVER=../memory_hub.py
if [ ! -f "$SERVER" ]; then SERVER=memory_hub.py; fi
if [ ! -f "$SERVER" ]; then
  echo "error: memory_hub.py not found next to or one level above this script" >&2
  exit 1
fi

STAGING=$(mktemp -d)
cp "$SERVER" "$STAGING/"
cp Install.command "$STAGING/"
chmod +x "$STAGING/Install.command"
ln -s /Applications "$STAGING/Applications" 2>/dev/null || true

hdiutil create -volname "memory-hub" \
  -srcfolder "$STAGING" \
  -ov -format UDZO \
  MemoryHub.dmg

rm -rf "$STAGING"
echo "Done: $(pwd)/MemoryHub.dmg"
echo "Attach it to a GitHub Release, then every Download button on the site serves it."
