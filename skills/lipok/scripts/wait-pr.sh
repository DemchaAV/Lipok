#!/bin/bash
# wait-pr.sh <pr> --repo <owner/name> [--hours H] [--delay S] [--skip "<head> <EVENT>"] [--merge-only] [--once]
#            [--require "<name>;<name>"] [--missing-min M] [--every S]
# The lane runner's watch on one PR: its merge and its CI. Run it with run_in_background; it costs
# nothing while it waits, and its exit wakes the session that started it.
# Every 3 minutes it reads the PR's state and checks, and exits with one line at the first event:
#   MERGED <sha>                     merged (by the human)
#   CLOSED                           closed without a merge
#   CI-FAIL <head> <runs> <checks>   every check of the head has finished, one or more failed;
#                                    <runs> = failed Actions run ids joined by "," ("-" when none
#                                    is an Actions run); <checks> = the rest of the line, the failed
#                                    checks' names joined by "; "
#   CI-GREEN <head>                  every check of the head has finished, none failed, and every
#                                    required check is among them
#   CI-MISSING <head> <names>        nothing failed, nothing is running, but these required checks
#                                    have not registered for M minutes (default 20): they never
#                                    started (2026-11-12: a deploy check that never started)
#   OPEN after <H>h                  nothing happened within H hours (default 12)
#   ERROR <message>                  the PR does not exist (at once), or 10 failed reads in a row
#                                    (30 minutes); exit 1
# --skip "<head> CI-GREEN" (or CI-FAIL) ignores that event for that head, so the runner can re-arm
# after acting on it. The head is 7-40 lower-case hex characters and matches by prefix.
# --delay waits before the first read (after a rerun, until it registers).
# --merge-only reports only MERGED/CLOSED (for a PR whose CI the app's Auto-fix already watches).
# --once prints what it reads and exits (exit 1 if the read fails). --repo falls back to $LIPOK_REPO.
# Required checks: --require "<name>;<name>", or else the profile's required_checks (read with
# lipok.py beside this script; none when the repo has no profile). --every: seconds between reads
# (default 180). All numbers are whole.
# Origin: an earlier single-loop harness (2026-10-25), with the repository made a parameter.
set -u
USAGE='usage: wait-pr.sh <pr> --repo <owner/name> [--hours H] [--delay S] [--skip "<head> <EVENT>"] [--merge-only] [--once]'
if [ $# -lt 1 ]; then echo "$USAGE"; exit 2; fi
N=$1
shift
case "$N" in ''|*[!0-9]*) echo "usage: the PR number must be a whole number, got '$N'"; exit 2 ;; esac
REPO="${LIPOK_REPO:-}"
H=12
DELAY=0
SKIP=""
ONCE=0
MERGE_ONLY=0
REQUIRE=""
REQUIRE_SET=0
MISSING_MIN=20
EVERY=180
need() { if [ $# -lt 2 ] || [ -z "$2" ]; then echo "usage: $1 needs a value"; exit 2; fi; }
int() { case "$2" in ''|*[!0-9]*) echo "usage: $1 needs a whole number, got '$2'"; exit 2 ;; esac; }
while [ $# -gt 0 ]; do
  case "$1" in
    --repo) need "$1" "${2:-}"; REPO=$2; shift 2 ;;
    --hours) need "$1" "${2:-}"; int "$1" "$2"; H=$2; shift 2 ;;
    --delay) need "$1" "${2:-}"; int "$1" "$2"; DELAY=$2; shift 2 ;;
    --skip) need "$1" "${2:-}"; SKIP=$2; shift 2 ;;
    --once) ONCE=1; shift ;;
    --merge-only) MERGE_ONLY=1; shift ;;
    --require) need "$1" "${2:-}"; REQUIRE=$2; REQUIRE_SET=1; shift 2 ;;
    --missing-min) need "$1" "${2:-}"; int "$1" "$2"; MISSING_MIN=$2; shift 2 ;;
    --every) need "$1" "${2:-}"; int "$1" "$2"; EVERY=$2; shift 2 ;;
    *) echo "unknown argument: $1"; exit 2 ;;
  esac
done
if [ -z "$REPO" ]; then echo "ERROR no --repo and no LIPOK_REPO"; exit 2; fi
if [ "$REQUIRE_SET" -eq 0 ]; then
  HERE=$(dirname "$0")
  if RC=$(python -I "$HERE/lipok.py" required-checks --repo "$REPO" 2>/dev/null); then
    REQUIRE=$(printf '%s\n' "$RC" | tr -d '\r' | sed -e '/^$/d' -e 's/;/,/g' | paste -sd ';' -)
  fi
fi
# The required names, one per element; a name's own ";" or "|" cannot be told apart, so both
# sides turn them into "," and "/".
REQ=()
if [ -n "$REQUIRE" ]; then
  IFS=';' read -r -a REQ <<< "$(printf '%s' "$REQUIRE" | tr '|' '/')"
fi
MISSING_SINCE=""; MISSING_HEAD=""
SKIP_HEAD=""; SKIP_EVENT=""
if [ -n "$SKIP" ]; then
  if ! [[ "$SKIP" =~ ^([0-9a-f]{7,40})\ (CI-GREEN|CI-FAIL)$ ]]; then
    echo "usage: --skip must be \"<7-40 lower-case hex> CI-GREEN|CI-FAIL\", got '$SKIP'"; exit 2
  fi
  SKIP_HEAD="${BASH_REMATCH[1]}"; SKIP_EVENT="${BASH_REMATCH[2]}"
fi
# state|merge sha|head|checks|pending|failed names|failed Actions run ids|all check names
QUERY='.state + "|" + (if .mergeCommit then .mergeCommit.oid else "" end) + "|" + .headRefOid + "|"
  + (.statusCheckRollup | length | tostring) + "|"
  + ([.statusCheckRollup[] | select(((.status // "COMPLETED") != "COMPLETED") or ((.state // "") == "PENDING") or ((.state // "") == "EXPECTED"))] | length | tostring) + "|"
  + ([.statusCheckRollup[] | select(((.conclusion // "") as $c | ["FAILURE","TIMED_OUT","CANCELLED","ACTION_REQUIRED","STARTUP_FAILURE"] | index($c)) or ((.state // "") == "FAILURE") or ((.state // "") == "ERROR")) | (.name // .context) | gsub("\\|"; "/")] | join("; ")) + "|"
  + ([.statusCheckRollup[] | select(((.conclusion // "") as $c | ["FAILURE","TIMED_OUT","CANCELLED","ACTION_REQUIRED","STARTUP_FAILURE"] | index($c))) | (.detailsUrl // "") | select(test("/actions/runs/[0-9]+")) | capture("/actions/runs/(?<id>[0-9]+)") | .id] | unique | join(",")) + "|"
  + ([.statusCheckRollup[] | (.name // .context // "") | gsub("\\|"; "/") | gsub(";"; ",")] | join(";"))'
[ "$DELAY" -gt 0 ] && sleep "$DELAY"
END=$(( $(date +%s) + H * 3600 ))
FAILS=0
while [ "$(date +%s)" -lt "$END" ]; do
  if LINE=$(gh pr view "$N" --repo "$REPO" --json state,mergeCommit,headRefOid,statusCheckRollup -q "$QUERY" 2>&1); then
    FAILS=0
    IFS='|' read -r STATE SHA HEAD CHECKS PENDING FAILED RUNS NAMES <<< "$LINE"
    [ -z "$RUNS" ] && RUNS="-"
    MISSING=""
    for R in "${REQ[@]+"${REQ[@]}"}"; do
      [ -z "$R" ] && continue
      case ";$NAMES;" in *";$R;"*) ;; *) MISSING="${MISSING:+$MISSING; }$R" ;; esac
    done
    if [ "$ONCE" -eq 1 ]; then
      echo "state=$STATE head=${HEAD:0:9} checks=$CHECKS pending=$PENDING failed=[$FAILED] runs=[$RUNS] missing=[$MISSING]"
      exit 0
    fi
    case "$STATE" in
      MERGED) echo "MERGED $SHA"; exit 0 ;;
      CLOSED) echo "CLOSED"; exit 0 ;;
    esac
    # Nothing failed, nothing runs, a required check is absent: wait M minutes for it to register,
    # then say so (CI-MISSING) instead of calling the head green.
    if [ "$MERGE_ONLY" -eq 0 ] && [ -n "$MISSING" ] && [ -z "$FAILED" ] && [ "$PENDING" -eq 0 ]; then
      NOWS=$(date +%s)
      if [ -z "$MISSING_SINCE" ] || [ "$MISSING_HEAD" != "$HEAD" ]; then MISSING_SINCE=$NOWS; MISSING_HEAD=$HEAD; fi
      if [ $(( NOWS - MISSING_SINCE )) -ge $(( MISSING_MIN * 60 )) ]; then
        echo "CI-MISSING ${HEAD:0:9} $MISSING"; exit 0
      fi
      sleep "$EVERY"; continue
    fi
    MISSING_SINCE=""
    if [ "$MERGE_ONLY" -eq 0 ] && [ "$CHECKS" -gt 0 ] && [ "$PENDING" -eq 0 ]; then
      if [ -n "$FAILED" ]; then EVENT="CI-FAIL"; else EVENT="CI-GREEN"; fi
      if [ -n "$SKIP_HEAD" ] && [ "$SKIP_EVENT" = "$EVENT" ] && [ "${HEAD#"$SKIP_HEAD"}" != "$HEAD" ]; then
        :
      else
        if [ "$EVENT" = "CI-FAIL" ]; then echo "CI-FAIL ${HEAD:0:9} $RUNS $FAILED"; else echo "CI-GREEN ${HEAD:0:9}"; fi
        exit 0
      fi
    fi
  else
    if [ "$ONCE" -eq 1 ]; then echo "ERROR $LINE"; exit 1; fi
    case "$LINE" in
      *"Could not resolve to a PullRequest"*|*"Could not resolve to a Repository"*) echo "ERROR $LINE"; exit 1 ;;
    esac
    FAILS=$((FAILS + 1))
    if [ "$FAILS" -ge 10 ]; then echo "ERROR $LINE"; exit 1; fi
  fi
  sleep "$EVERY"
done
echo "OPEN after ${H}h"
