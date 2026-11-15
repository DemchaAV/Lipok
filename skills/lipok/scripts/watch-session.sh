#!/usr/bin/env bash
# watch-session.sh — the runner's watch on a SESSION it leads (a worker), for the gap the PR watch
# cannot see: a turn that dies (API error, crashed app) leaves no line and no report, and the lane
# then stands still unnoticed (2026-10-29). Run it with run_in_background; its exit wakes the runner.
#
#   watch-session.sh <dir-or-file> [--quiet-min N] [--hours H] [--delay S] [--wait-dir S]
#
# <dir-or-file> is the worker's transcript folder under ~/.claude/projects/ (a folder NAME, or a
# path), or ONE transcript file (*.jsonl) in it. Windows paths are accepted. All numbers are whole.
# It watches that file (or the newest *.jsonl in the folder) and exits on the first event:
#   SESSION LIMIT <minutes>m <text>  the last record is a usage-limit message (not a dead turn)
#   SESSION ERROR <minutes>m <text>  the last record is another API/model error (rate limit,
#                                    overload, context overflow …), and the transcript has been
#                                    still for 2+ minutes
#   SESSION QUIET <minutes>m <file>  still for the whole quiet window — the transcript AND its
#                                    subagents' transcripts (<file without .jsonl>/subagents/*.jsonl):
#                                    a worker waiting on a background review agent is not quiet
#                                    (2026-11-09: a 25-minute cold review left the main file still).
#                                    Quiet counts from the later of the last write and the moment
#                                    the watch was armed (after --delay): a re-arm during a legit
#                                    wait gets a full window (2026-11-12: it fired at once)
#   SESSION GONE <file>              a watched FILE vanished and no file of that name turned up in
#                                    any project folder (exit 2): re-arm, never read as OK
#   SESSION OK after <H>h            nothing happened in the time given
#   ERROR no such transcript folder: <dir>   the folder did not appear within --wait-dir (exit 2)
#   ERROR no transcript in <dir>     the folder holds no *.jsonl (exit 2)
# Origin: an earlier single-loop harness (2026-10-29 … 2026-10-30).
set -u

DIR=""; QUIET_MIN=20; HOURS=12; DELAY=0; WAIT_DIR=1800
need() { if [ $# -lt 2 ] || [ -z "$2" ]; then echo "usage: $1 needs a value"; exit 2; fi; }
int() { case "$2" in ''|*[!0-9]*) echo "usage: $1 needs a whole number, got '$2'"; exit 2 ;; esac; }
while [ $# -gt 0 ]; do
  case "$1" in
    --quiet-min) need "$1" "${2:-}"; int "$1" "$2"; QUIET_MIN="$2"; shift 2 ;;
    --hours)     need "$1" "${2:-}"; int "$1" "$2"; HOURS="$2";     shift 2 ;;
    --delay)     need "$1" "${2:-}"; int "$1" "$2"; DELAY="$2";     shift 2 ;;
    --wait-dir)  need "$1" "${2:-}"; int "$1" "$2"; WAIT_DIR="$2";  shift 2 ;;
    -*)          echo "unknown argument: $1"; exit 2 ;;
    *)           if [ -z "$DIR" ]; then DIR="$1"; else echo "unexpected argument: $1"; exit 2; fi; shift ;;
  esac
done
if [ -z "$DIR" ]; then
  echo "usage: watch-session.sh <transcript-folder-or-file> [--quiet-min N] [--hours H] [--delay S] [--wait-dir S]"
  exit 2
fi

BASE="${LIPOK_PROJECTS_DIR:-$HOME/.claude/projects}"
case "$DIR" in
  [A-Za-z]:*) command -v cygpath >/dev/null 2>&1 && DIR=$(cygpath -u "$DIR") ;;
esac
case "$DIR" in
  */*) ;;                       # a path was given
  *)   DIR="$BASE/$DIR" ;;      # a folder name was given
esac

FIXED_FILE=""
case "$DIR" in
  *.jsonl) FIXED_FILE="$DIR"; DIR=$(dirname "$DIR") ;;
esac

# The folder, its first transcript, or the given file may not exist yet: they appear with the
# worker's first turn (a folder holding only memory/ is not a transcript yet; 2026-11-15 audit).
has_transcript() { compgen -G "$DIR/*.jsonl" >/dev/null 2>&1; }
WAITED=0
not_ready() {
  [ ! -d "$DIR" ] && return 0
  if [ -n "$FIXED_FILE" ]; then [ ! -f "$FIXED_FILE" ]; else ! has_transcript; fi
}
while not_ready && [ "$WAITED" -lt "$WAIT_DIR" ]; do
  sleep 10
  WAITED=$(( WAITED + 10 ))
done
if [ ! -d "$DIR" ]; then
  echo "ERROR no such transcript folder: $DIR"
  exit 2
fi

[ "$DELAY" -gt 0 ] && sleep "$DELAY"
ARMED=$(date +%s)

# File times: GNU stat (Linux, Git Bash) or BSD stat (macOS).
mtime() { stat -c %Y "$1" 2>/dev/null || stat -f %m "$1" 2>/dev/null; }
PYBIN=""
for P in python python3; do "$P" -c '' >/dev/null 2>&1 && { PYBIN=$P; break; }; done
DEADLINE=$(( ARMED + HOURS * 3600 ))

# Prints "LIMIT <text>" or "ERROR <text>" when the LAST user/assistant record of the transcript is
# an assistant record the app marked as an API error; nothing otherwise. Only the last record
# counts: a brief or a message that merely quotes an error must not trip the watch. Reads the last
# 4 MB, so trailing system records cannot hide the error.
last_error() {
  [ -n "$PYBIN" ] || return 0
  "$PYBIN" -I -c '
import sys, json, os, re
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
path = sys.argv[1]
size = os.path.getsize(path)
with open(path, "rb") as fh:
    fh.seek(max(0, size - 4 * 1024 * 1024))
    data = fh.read().decode("utf-8", errors="replace")
lines = data.split("\n")
if size > 4 * 1024 * 1024:
    lines = lines[1:]          # the first line is cut
last = None
for line in lines:
    try:
        d = json.loads(line)
    except Exception:
        continue
    if isinstance(d, dict) and d.get("type") in ("user", "assistant"):
        last = d
if last and last.get("type") == "assistant" and last.get("isApiErrorMessage"):
    c = (last.get("message") or {}).get("content")
    if isinstance(c, list):
        text = " ".join(x.get("text", "") for x in c if isinstance(x, dict))
    else:
        text = str(c)
    low = text.lower()
    usage = re.search(r"usage limit|hit your [\w-]+ limit|(session|weekly|daily|monthly|5-hour|opus|sonnet) limit|limit reached|limit will reset|resets? at", low)
    other = re.search(r"rate.?limit|context|max_tokens|too long|\b429\b", low)
    kind = "LIMIT" if usage and not other else "ERROR"
    print(kind + " " + re.sub(r"\s+", " ", text).strip()[:200])
' "$1" 2>/dev/null
}

while [ "$(date +%s)" -lt "$DEADLINE" ]; do
  if [ -n "$FIXED_FILE" ]; then
    FILE="$FIXED_FILE"
    if [ ! -f "$FILE" ]; then
      MOVED=$(ls -t "$BASE"/*/"$(basename "$FILE")" 2>/dev/null | head -1)
      if [ -n "$MOVED" ]; then
        echo "note: watched file moved to $MOVED"
        FIXED_FILE="$MOVED"; FILE="$MOVED"
      else
        echo "SESSION GONE $FILE"
        exit 2
      fi
    fi
  else
    FILE=$(ls -t "$DIR"/*.jsonl 2>/dev/null | head -1)
  fi
  if [ -z "$FILE" ]; then
    echo "ERROR no transcript in $DIR"
    exit 2
  fi

  MTIME=$(mtime "$FILE" || true)
  if [ -z "$MTIME" ]; then
    echo "SESSION GONE $FILE (cannot read its time)"
    exit 2
  fi
  STILL=$(( ( $(date +%s) - MTIME ) / 60 ))

  # Activity also counts in the session's subagents: their transcripts live beside the main one.
  ACTIVE="$MTIME"
  SUB=$(ls -t "${FILE%.jsonl}"/subagents/*.jsonl 2>/dev/null | head -1)
  if [ -n "$SUB" ]; then
    SUBTIME=$(mtime "$SUB" || echo 0)
    [ "$SUBTIME" -gt "$ACTIVE" ] && ACTIVE="$SUBTIME"
  fi
  [ "$ARMED" -gt "$ACTIVE" ] && ACTIVE="$ARMED"
  IDLE=$(( ( $(date +%s) - ACTIVE ) / 60 ))

  if [ "$STILL" -ge 2 ]; then
    ERR=$(last_error "$FILE")
    if [ -n "$ERR" ]; then
      echo "SESSION ${ERR%% *} ${STILL}m ${ERR#* }"
      exit 0
    fi
  fi

  if [ "$IDLE" -ge "$QUIET_MIN" ]; then
    echo "SESSION QUIET ${IDLE}m $FILE"
    exit 0
  fi

  sleep 60
done

echo "SESSION OK after ${HOURS}h"
