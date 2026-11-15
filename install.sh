#!/usr/bin/env bash
# install.sh — copy the Lipok skills into Claude Code's skills folder.
# Replaces only the folders it installs (lipok, lipok-task); everything else there is left alone.
set -eu
SRC="$(cd "$(dirname "$0")" && pwd)/skills"
DEST="${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}"
mkdir -p "$DEST"
for s in lipok lipok-task; do
  [ -d "$SRC/$s" ] || { echo "missing $SRC/$s"; exit 1; }
  rm -rf "${DEST:?}/$s"
  cp -r "$SRC/$s" "$DEST/$s"
  echo "installed $DEST/$s"
done
