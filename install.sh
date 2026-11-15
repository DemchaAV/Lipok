#!/usr/bin/env bash
# install.sh — copy the Lipok skills into Claude Code's skills folder (no Node needed).
# Replaces only the folders it installs (lipok, lipok-task); everything else there is left alone.
set -eu
SRC="$(cd "$(dirname "$0")" && pwd -P)/skills"
DEST="${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}"
mkdir -p "$DEST"
DEST="$(cd "$DEST" && pwd -P)"
# Installing into the package's own skills folder (or a folder inside it, or one that contains
# it) would delete the source before copying it (2026-11-15 audit).
case "$DEST/" in "$SRC/"*) echo "refusing to install into the package itself: $DEST"; exit 1 ;; esac
case "$SRC/" in "$DEST/"*/*) echo "refusing to install into a folder that holds the package: $DEST"; exit 1 ;; esac
for s in lipok lipok-task; do
  [ -f "$SRC/$s/SKILL.md" ] || { echo "missing $SRC/$s"; exit 1; }
  TMP="$DEST/.$s.installing-$$"
  rm -rf "$TMP"
  cp -R "$SRC/$s" "$TMP"          # copy first: a failed copy leaves the old skill in place
  rm -rf "${DEST:?}/$s"
  mv "$TMP" "$DEST/$s"
  echo "installed $DEST/$s"
done
