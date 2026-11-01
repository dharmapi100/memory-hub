#!/bin/bash
# Builds MemoryHub.dmg on macOS. Run from the repo's installer/ folder.
# Produces MemoryHub.dmg containing memory_hub.py + Install.command.
set -e
cd "$(dirname "$0")"

STAGING=$(mktemp -d)
cp memory_hub.py "$STAGING/"
cp Install.command "$STAGING/"
chmod +x "$STAGING/Install.command"
ln -s /Applications "$STAGING/Applications" 2>/dev/null || true

hdiutil create -volname "memory-hub" \
  -srcfolder "$STAGING" \
  -ov -format UDZO \
  MemoryHub.dmg

rm -rf "$STAGING"
echo "Done: $(pwd)/MemoryHub.dmg"
echo "Attach it to a GitHub Release, then point the website Download button at it."
