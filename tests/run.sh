#!/usr/bin/env bash
# Tests for lipok.py and the watch scripts. Usage: bash tests/run.sh <path to lipok.py> <empty test dir>
set -u
PY="$1"; T="$2"
export LIPOK_HOME="$T/home"; rm -rf "$LIPOK_HOME"; mkdir -p "$LIPOK_HOME/projects/o-r"
cat > "$LIPOK_HOME/projects/o-r/project.json" <<'J'
{"repo":"o/r","main_checkout":"C:/x","base_branch":"main","gate":"g","quiet_window_min":30,
 "author":{"name":"n","email":"e@x"},"progress_window_h":2,"max_attempts":3}
J
A="python -I $PY"
PASS=0; FAIL=0
t() { # t <name> <expected exit> <expected substring> -- cmd...
  local name="$1" ex="$2" sub="$3"; shift 4
  out=$("$@" 2>&1); rc=$?
  if [ "$rc" = "$ex" ] && { [ -z "$sub" ] || printf '%s' "$out" | grep -qF -- "$sub"; }; then PASS=$((PASS+1)); else FAIL=$((FAIL+1)); echo "FAIL $name: rc=$rc out=$out"; fi
}
t profile 0 "PROFILE OK" -- $A profile --repo o/r
t hier-refused 4 "only the flat" -- $A task-new --repo o/r --title x --scheme hierarchical
t task-new 0 "TASK t1" -- $A task-new --repo o/r --title "Café chat" --lanes 2
TD="$LIPOK_HOME/projects/o-r/tasks/t1"; L="$TD/lanes/1/state.md"
t lane-fields 0 "chunk-status: none" -- $A show "$L"
t chunk 0 "CHUNK-KEY t1/L1/K1" -- $A chunk "$L" --chunk K1
LS="$TD/chunks/K1/lane-state.md"
t chunk-again 4 "REFUSED lane chunk" -- $A chunk "$L" --chunk K2
t chunk-on-item 2 "Manager's lanes" -- $A chunk "$LS" --chunk K3
t item-on-lane 2 "lane-state.md" -- $A item "$L" --chunk K1 --slug a --item "x"
t item-wrong-chunk 4 "not K2" -- $A item "$LS" --chunk K2 --slug a --item "x"
t item 0 "KEY t1/L1/K1/a#1" -- $A item "$LS" --chunk K1 --slug a --item "1 Item"
t item-busy 4 "REFUSED lane item" -- $A item "$LS" --chunk K1 --slug b --item "y"
t bump 0 "KEY t1/L1/K1/a#2" -- $A bump "$LS"
t set-item-unknown 4 "unknown keys: chunk-status" -- $A set "$LS" chunk-status=WORKING
t set-item-turn 0 "SET turn=" -- $A set "$LS" turn=2026-11-11T00:00:00Z
t set-lane-unknown 4 "unknown keys: turn" -- $A set "$L" turn=x
t set-lane-legacy 0 "SET status=" -- $A set "$L" status=x
t set-lane-status 0 "SET chunk-status=WORKING" -- $A set "$L" chunk-status=WORKING
t stall-ok 0 "STALL OK" -- $A stall-check "$L" --repo o/r
$A set "$L" progress-line=2026-01-01T00:00:00Z >/dev/null
t stall-quiet 0 "STALL QUIET" -- $A stall-check "$L" --repo o/r
$A set "$L" "progress-line=$(date -u +%FT%TZ)" >/dev/null
$A bump "$LS" >/dev/null; $A bump "$LS" >/dev/null
t stall-loop 0 "STALL LOOP t1/L1/K1/a#4" -- $A stall-check "$L" --repo o/r
t stall-loop-flag 0 "STALL OK" -- $A stall-check "$L" --max-attempts 9
$A set "$L" paused=yes >/dev/null
t stall-idle 0 "STALL IDLE" -- $A stall-check "$L" --repo o/r
$A set "$L" paused=no >/dev/null
t stall-watch-trips 0 "STALL LOOP" -- $A stall-check "$L" --repo o/r --watch --every 1 --hours 0.01
t stall-watch-times-out 0 "STALL OK after" -- $A stall-check "$L" --max-attempts 9 --watch --every 1 --hours 0.0005
$A set "$L" chunk-status=DONE >/dev/null
t chunk-after-done 0 "CHUNK-KEY t1/L1/K2" -- $A chunk "$L" --chunk K2
LS2="$TD/chunks/K2/lane-state.md"
$A set "$L" chunk-status=WORKING >/dev/null
$A item "$LS2" --chunk K2 --slug b --item "2 Item" >/dev/null
t item-no-manager-fields 0 "absent" -- bash -c "grep -q 'death-turn\|pending' '$LS2' && echo present || echo absent"
for i in 1 2 3; do $A bump "$LS2" >/dev/null; done
t loop-k2 0 "STALL LOOP t1/L1/K2/b#4" -- $A stall-check "$L" --repo o/r
$A set "$L" "loop-ack=t1/L1/K2/b#4" >/dev/null
t loop-acked 0 "STALL OK" -- $A stall-check "$L" --repo o/r
$A set "$L" "loop-ack=t1/L1/K1/a#9" >/dev/null
t loop-ack-other-item 0 "STALL LOOP" -- $A stall-check "$L" --repo o/r
$A set "$L" "loop-ack=t1/L1/K2/b#4" >/dev/null
$A set "$L" progress-line=2026-01-01T00:00:00Z "last-line=$(date -u +%FT%TZ)" >/dev/null
t progress-not-last-line 0 "STALL QUIET" -- $A stall-check "$L" --repo o/r
$A set "$L" pr=5 pr-status=READY >/dev/null
t idle-ready 0 "STALL IDLE PR #5 READY" -- $A stall-check "$L" --repo o/r
$A set "$L" pr-status=none chunk-status=PLAN >/dev/null
t idle-plan 0 "STALL IDLE chunk-status=PLAN" -- $A stall-check "$L" --repo o/r

# verify-pr with a fake gh
HERE=$(cd "$(dirname "$0")" && (pwd -W 2>/dev/null || pwd))   # Windows python needs C:/… not /c/…
export LIPOK_GH="python -I $HERE/fakegh.py"
G="$T/gate.txt"; printf 'step ok\nGATE PASS\n' > "$G"
R="$T/report.md"
mk() { cat > "$R" <<EOF
STATUS: ${1:-REVIEWED}
KEY: t1/L1/K1/a#1
BRANCH: feat/x   HEAD: ${2:-abc1234}
TESTS: run ${3:-12}, failed 0
SABOTAGES: caught ${4:-3} of 3
REVIEW: rounds 2, open majors ${5:-0}
BOTS: answered 1 of 1
GATE: ${6:-$G}
---
user block
---
${7:-PLAN-NOTE}: what the PR does
EOF
}
mk; t vp-good 0 "VERIFY OK 7 abc1234" -- env FAKE_GH_CASE=good $A verify-pr 7 --repo o/r --report "$R" --area "src/*,docs/*"
t vp-draft 4 "PR is a draft" -- env FAKE_GH_CASE=draft $A verify-pr 7 --repo o/r --report "$R"
t vp-cifail 4 "CI failing: build" -- env FAKE_GH_CASE=cifail $A verify-pr 7 --repo o/r --report "$R"
t vp-pending 4 "CI pending: lint" -- env FAKE_GH_CASE=pending $A verify-pr 7 --repo o/r --report "$R"
t vp-nochecks 4 "no CI checks" -- env FAKE_GH_CASE=nochecks $A verify-pr 7 --repo o/r --report "$R"
t vp-threads 4 "1 unresolved review thread" -- env FAKE_GH_CASE=threads $A verify-pr 7 --repo o/r --report "$R"
t vp-outside 4 "outside the chunk's area: other/y.js" -- env FAKE_GH_CASE=outside $A verify-pr 7 --repo o/r --report "$R" --area "src/*,docs/*"
mk REVIEWED 9999999; t vp-head 4 "report HEAD 9999999 is not the PR head" -- $A verify-pr 7 --repo o/r --report "$R"
mk WORKING; t vp-status 4 "not REVIEWED" -- $A verify-pr 7 --repo o/r --report "$R"
mk REVIEWED abc1234 0; t vp-zero-tests 4 "tests run 0" -- $A verify-pr 7 --repo o/r --report "$R"
mk REVIEWED abc1234 12 2; t vp-sabotage 4 "sabotages caught 2 of 3" -- $A verify-pr 7 --repo o/r --report "$R"
mk REVIEWED abc1234 12 3 1; t vp-majors 4 "open Blocker/Critical/Major 1" -- $A verify-pr 7 --repo o/r --report "$R"
mk REVIEWED abc1234 12 3 0 "$T/nope.txt"; t vp-gate-missing 4 "does not exist" -- $A verify-pr 7 --repo o/r --report "$R"
printf 'GATE FAIL: tests\n' > "$T/gf.txt"; mk REVIEWED abc1234 12 3 0 "$T/gf.txt"; t vp-gate-fail 4 "not GATE PASS" -- $A verify-pr 7 --repo o/r --report "$R"
mk REVIEWED abc1234 12 3 0 "$G" note; t vp-note-missing 4 "report has no 'PLAN-NOTE:" -- $A verify-pr 7 --repo o/r --report "$R"
mk; touch -d '2025-01-01' "$G"; t vp-gate-stale 4 "before the head commit" -- $A verify-pr 7 --repo o/r --report "$R"
touch "$G"

# --- pilot fixes (2026-11-12) ---
# required checks: a registered-but-absent required check fails verify-pr (finding 2)
P="$LIPOK_HOME/projects/o-r/project.json"; cp "$P" "$T/profile.bak"
python -I -c "import json,sys;p=sys.argv[1];d=json.load(open(p));d['required_checks']=['build','deploy'];json.dump(d,open(p,'w'))" "$P"
t rc-list 0 "deploy" -- $A required-checks --repo o/r
mk; t vp-required-missing 4 "required check not registered: deploy" -- env FAKE_GH_CASE=good $A verify-pr 7 --repo o/r --report "$R"
python -I -c "import json,sys;p=sys.argv[1];d=json.load(open(p));d['required_checks']='build';json.dump(d,open(p,'w'))" "$P"
t rc-bad-profile 4 "required_checks (a list" -- $A profile --repo o/r
cp "$T/profile.bak" "$P"
t rc-none 0 "lines=0" -- bash -c "echo lines=\$($A required-checks --repo o/r | wc -l)"
# verify-pr --lane: OK opens the merge wait, FAIL marks REDIRECTED
$A set "$L" chunk-status=WORKING pr=none pr-status=none >/dev/null
t vp-lane-fail 4 "VERIFY FAIL" -- env FAKE_GH_CASE=draft $A verify-pr 7 --repo o/r --report "$R" --lane "$L"
t vp-lane-fail-state 0 "REDIRECTED" -- $A get "$L" pr-status
t vp-lane-ok 0 "VERIFY OK 7" -- env FAKE_GH_CASE=good $A verify-pr 7 --repo o/r --report "$R" --lane "$L"
t vp-lane-ok-state 0 "merge" -- $A get "$L" wait-kind
t vp-lane-ok-pr 0 "READY" -- $A get "$L" pr-status
t vp-lane-on-item 2 "Manager's lanes" -- $A verify-pr 7 --repo o/r --report "$R" --lane "$LS2"
# book: refuses an open PR, books a merged one with its merge wait, then says already booked
t book-open 4 "NOT MERGED 7 OPEN" -- env FAKE_GH_CASE=good $A book "$L" 7 --repo o/r
$A set "$L" wait-since=2026-01-01T00:00:00Z >/dev/null
t book-merged 0 "BOOKED 7 fedcba9 2026-01-01 waited 150m" -- env FAKE_GH_CASE=merged $A book "$L" 7 --repo o/r
t book-wait-sum 0 "150" -- $A get "$L" merge-wait-min
t book-cleared 0 "none" -- $A get "$L" wait-kind
t book-again 0 "ALREADY BOOKED 7" -- env FAKE_GH_CASE=merged $A book "$L" 7 --repo o/r
# line: stamps progress-line on progress lines only, catches late lines, times decisions (findings 6, 7)
$A set "$L" progress-line=2026-01-01T00:00:00Z last-line=2026-01-01T00:00:00Z death-turn=x >/dev/null
CUR=$($A get "$LS2" key)
t line-alive 0 "LINE ALIVE" -- $A line "$L" ALIVE "$CUR"
t line-alive-no-progress 0 "2026-01-01T00:00:00Z" -- $A get "$L" progress-line
t line-alive-death 0 "none" -- $A get "$L" death-turn
t line-merged 0 "LINE MERGED" -- $A line "$L" MERGED "t1/L1/K2/b#1"
t line-merged-progress 0 "$(date -u +%Y-%m-%d)" -- $A get "$L" progress-line
t line-late-chunk 4 "LATE PLAN t1/L1/K1" -- $A line "$L" PLAN t1/L1/K1
t line-late-item 4 "LATE READY t1/L1/K2/b#1" -- $A line "$L" READY "t1/L1/K2/b#1"
t line-late-logged 0 "LATE  READY" -- cat "$TD/lanes/1/events.log"
t line-bad-type 2 "TYPE must be" -- $A line "$L" HELLO
t line-decision 0 "LINE DECISION" -- $A line "$L" DECISION "$CUR"
t line-decision-wait 0 "decision" -- $A get "$L" wait-kind
$A set "$L" wait-since=2026-01-01T00:00:00Z >/dev/null
t line-answered 0 "ANSWERED after" -- $A line "$L" ANSWERED
t line-answered-sum 0 "decision-wait-min" -- bash -c "grep -E '^decision-wait-min: [1-9][0-9]*$' '$L'"
t line-answered-none 0 "no decision wait open" -- $A line "$L" ANSWERED
# planned attempts: batches the plan declares are not a loop (finding 1)
$A set "$L" loop-ack=none chunk-status=WORKING pr-status=none "progress-line=$(date -u +%FT%TZ)" >/dev/null
$A set "$LS2" status=DROPPED >/dev/null
t item-attempts-bad 2 "--attempts must be" -- $A item "$LS2" --chunk K2 --slug c --item "3 Item" --attempts 0
t item-attempts 0 "KEY t1/L1/K2/c#1" -- $A item "$LS2" --chunk K2 --slug c --item "3 Item" --attempts 4
for i in 1 2 3 4 5; do $A bump "$LS2" >/dev/null; done   # attempt 6 = 4 planned + 2 retries
t planned-not-loop 0 "STALL OK" -- $A stall-check "$L" --repo o/r
$A bump "$LS2" >/dev/null                                 # attempt 7 > 3 + 4 - 1
t planned-loop 0 "STALL LOOP t1/L1/K2/c#7 attempt=7 planned=4" -- $A stall-check "$L" --repo o/r
$A set "$L" "loop-ack=t1/L1/K2/c#7" >/dev/null
for i in 1 2 3; do $A bump "$LS2" >/dev/null; done
t planned-acked-ok 0 "STALL OK" -- $A stall-check "$L" --repo o/r
$A bump "$LS2" >/dev/null
t planned-acked-loop 0 "STALL LOOP t1/L1/K2/c#11" -- $A stall-check "$L" --repo o/r
$A set "$LS2" status=DROPPED >/dev/null
$A item "$LS2" --chunk K2 --slug d --item "4 Item" >/dev/null
t item-attempts-default 0 "1" -- $A get "$LS2" planned-attempts

# wait-pr.sh with a fake gh on PATH: required checks (finding 3)
SKD=$(dirname "$PY")
FB="$T/fakebin"; mkdir -p "$FB"
cat > "$FB/gh" <<'EOF'
#!/bin/bash
echo "$FAKE_WAIT_LINE"
EOF
chmod +x "$FB/gh"
FB=$(cygpath -u "$FB" 2>/dev/null || echo "$FB")   # a C:/ path breaks PATH at its colon
W() { PATH="$FB:$PATH" bash "$SKD/wait-pr.sh" "$@"; }
export FAKE_WAIT_LINE="OPEN||abc1234def|1|0|||test"
t wp-green-no-req 0 "CI-GREEN abc1234de" -- W 7 --repo o/r --hours 1 --every 1
t wp-missing 0 "CI-MISSING abc1234de deploy: x" -- W 7 --repo o/r --require "test;deploy: x" --missing-min 0 --hours 1 --every 1
t wp-missing-waits 124 "" -- timeout 4 bash -c "PATH='$FB:'\"\$PATH\" bash '$SKD/wait-pr.sh' 7 --repo o/r --require 'deploy: x' --missing-min 5 --every 1"
export FAKE_WAIT_LINE="OPEN||abc1234def|2|0|||test;deploy: x"
t wp-green-req 0 "CI-GREEN abc1234de" -- W 7 --repo o/r --require "test;deploy: x" --hours 1 --every 1
export FAKE_WAIT_LINE="OPEN||abc1234def|1|0|test||test"
t wp-fail-beats-missing 0 "CI-FAIL abc1234de - test" -- W 7 --repo o/r --require "test;deploy: x" --hours 1 --every 1
t wp-once-missing 0 "missing=[deploy: x]" -- W 7 --repo o/r --require "test;deploy: x" --once
python -I -c "import json,sys;p=sys.argv[1];d=json.load(open(p));d['required_checks']=['test','deploy'];json.dump(d,open(p,'w'))" "$P"
t wp-profile-req 0 "missing=[deploy]" -- env LIPOK_HOME="$LIPOK_HOME" bash -c "PATH='$FB:'\"\$PATH\" bash '$SKD/wait-pr.sh' 7 --repo o/r --once"
cp "$T/profile.bak" "$P"
unset FAKE_WAIT_LINE

# watch-session.sh: an old transcript does not fire at once on arming (finding 4)
WS="$T/proj/sess"; mkdir -p "$WS"; echo '{"type":"user"}' > "$WS/a.jsonl"; touch -d '-40 minutes' "$WS/a.jsonl"
t ws-armed-window 124 "" -- timeout 5 bash "$SKD/watch-session.sh" "$WS" --quiet-min 30 --wait-dir 0
# usage: who spent the tokens, from transcripts on disk
CP="$T/cp"; rm -rf "$CP"; export LIPOK_PROJECTS_DIR="$CP"
rec() { # rec <file> <id> <out> [<ts>] [<extra text>]
  mkdir -p "$(dirname "$1")"
  printf '{"timestamp":"%s","note":"%s","message":{"id":"%s","usage":{"input_tokens":0,"output_tokens":%s}}}\n' "${4:-2026-11-12T13:00:00Z}" "${5:-}" "$2" "$3" >> "$1"
}
W1="C--x--claude-worktrees-lipok-t1-l1-r1-aaaaaa"
rec "$CP/C--m/m1.jsonl" m1a 100 "" 'o-r\\tasks\\t1'; rec "$CP/C--m/m1.jsonl" m1a 100
rec "$CP/C--m/m1/subagents/r.jsonl" ra 100
rec "$CP/C--m/m2.jsonl" m2a 1000
rec "$CP/C--m/m3.jsonl" m3a 1000 "" "o-r/tasks/t10"
rec "$CP/$W1/w.jsonl" wa 100
rec "$CP/C--x--claude-worktrees-lipok-t1-l1-bbbbbb/o.jsonl" oa 100
rec "$CP/C--x--claude-worktrees-lipok-t10-l1-cccccc/d.jsonl" da 10000
rec "$CP/$W1/w/subagents/e.jsonl" ea 400
rec "$CP/$W1/w/subagents/e.jsonl" eb 9999 2020-01-01T00:00:00Z
$A set "$L" worker-dir=$W1 >/dev/null
U() { $A usage "$TD" --since 2026-11-12T00:00:00Z --until 2026-11-13T00:00:00Z "$@"; }
t usage-manager 0 "manager    turns=2 out=200" -- U --manager 'C:\m'
t usage-worker 0 "worker     turns=2 out=200" -- U --manager 'C:\m'
t usage-exec 0 "executors  turns=1 out=400" -- U --manager 'C:\m'
t usage-coord 0 "COORDINATION 50%" -- U --manager 'C:\m'
t usage-folders 0 "worker folders=2 manager transcripts=1" -- U --manager C--m
t usage-no-manager 0 "manager    not counted" -- U
t usage-no-manager-share 0 "executors  turns=1 out=400 cache-read=0 cache-write=0 in=0 weight=2.0k share=67%" -- U
t usage-file 0 "manager transcripts=1" -- U --manager "$CP/C--m/m2.jsonl"
t usage-missing-file 3 "NO TRANSCRIPT" -- U --manager "$CP/C--m/zz.jsonl"
t usage-no-task 3 "NO TASK" -- $A usage "$T/nowhere"
t usage-args 2 "usage <task folder>" -- $A usage
unset LIPOK_PROJECTS_DIR
# cut-check: parallel chunks must not share files
CUTD="$T/cut"; mkdir -p "$CUTD"
printf '%s\n' src/api/schema.ts src/server/a.ts src/server/b.ts src/web/app.tsx src/web/menu.tsx src/router.ts package.json > "$CUTD/files"
cut() { cat > "$CUTD/c.md"; }
C() { $A cut-check "$CUTD/c.md" --files "$CUTD/files" "$@"; }
cut <<'M'
# Cut
## K1 contract — schema
AREA: src/api/**, src/router.ts
ITEMS: 1
## K2 impl — server
AREA: src/server/**
AFTER: K1
ITEMS: 2, 3
## K3 impl — web
AREA: src/web/**
AFTER: K1
ITEMS: 4
## K4 assembly — switch on
AREA: src/router.ts, src/web/menu.tsx
AFTER: K2, K3
ITEMS: 5
M
t cut-ok 0 "CUT OK lanes=2 (width 2" -- C --max-lanes 3
t cut-waves 0 "WAVES 1: K1 | 2: K2,K3 | 3: K4 — parallel width 2" -- C --max-lanes 3
t cut-capped 0 "CUT OK lanes=1" -- C --max-lanes 1
t cut-files 0 "CHUNK K2 impl wave=2 after=K1 area=src/server/** files=2" -- C --max-lanes 3
sed -i 's|^AREA: src/web/\*\*$|AREA: src/web/**, src/server/b.ts|' "$CUTD/c.md"
t cut-shared-file 4 "K2 and K3 run in parallel and both may change src/server/b.ts" -- C --max-lanes 3
cut <<'M'
## K1 impl — a
AREA: src/new/**
## K2 impl — b
AREA: src/new/x.ts
M
t cut-glob-overlap 4 "areas may overlap: src/new/** ~ src/new/x.ts" -- C
cut <<'M'
## K1 impl — a
AREA: src/server/*.ts
## K2 impl — b
AREA: src/*.css
M
t cut-star-crosses-slash 4 "areas may overlap" -- C
cut <<'M'
## K1 impl — a
AREA: src/one/**
AFTER: K2
ITEMS: 1
## K2 impl — b
AREA: src/two/**
AFTER: K1
ITEMS: 1
## K3 impl — c
AREA: src/three/**
AFTER: K9
## K5 thing — bad kind
M
t cut-cycle 4 "AFTER cycle" -- C
t cut-dup-item 4 "item 1 in K1 and K2" -- C
t cut-bad-after 4 "K3 AFTER K9: no such chunk" -- C
t cut-bad-kind 4 "a chunk heading is" -- C
cut <<'M'
## K1 impl — a
AREA: src/one/**
RESOURCES: emulator
## K2 impl — b
AREA: src/two/**
RESOURCES: emulator
M
t cut-resource-note 0 "NOTE K1 and K2 share emulator" -- C --max-lanes 2
printf '## K1 impl — a
' > "$CUTD/c.md"
t cut-no-area 4 "K1 has no AREA" -- C
printf 'nothing
' > "$CUTD/c.md"
t cut-empty 4 "no chunks" -- C
t cut-args 2 "cut-check <cut.md>" -- $A cut-check
# --- audit fixes (2026-11-15) ---
# cut-check: every way an overlap used to slip through
cut <<'M'
## K1 impl — a
AREA: src/web/**
AREA: src/server/**
## K2 impl — b
AREA: src/web/menu.tsx
M
t cut-two-area-lines 4 "both may change src/web/menu.tsx" -- C --max-lanes 3
cut <<'M'
## K1 impl — a
AREA: src/server/**,
  src/web/**
## K2 impl — b
AREA: src/web/menu.tsx
M
t cut-wrapped-area 4 "both may change src/web/menu.tsx" -- C --max-lanes 3
cut <<'M'
## K1 impl — a
AREA: src/server/**
## K2 impl web part
AREA: src/web/**
M
t cut-bad-heading 4 "a chunk heading is" -- C --max-lanes 3
cut <<'M'
## K1 impl — a
AREA: src/server/**
### K2 impl — b
AREA: src/web/**
M
t cut-h3-heading 4 "a chunk heading is" -- C --max-lanes 3
cut <<'M'
## K1 impl — a
AREA: src/server/**
Some prose about the chunk
DONE WHEN: it works
SEAMS: none
M
t cut-prose-line 4 "not a field of chunk K1" -- C
cut <<'M'
## K1 impl — a
AREA: src/server/
## K2 impl — b
AREA: ./src/web/**
M
t cut-bad-globs 4 "a folder is <folder>/**" -- C
t cut-bad-globs-dot 4 "without ./ or /" -- C
cut <<'M'
## K1 impl — a
AREA: Src/Server/*.ts
## K2 impl — b
AREA: src/server/n*
M
t cut-case-overlap 4 "areas may overlap" -- C --max-lanes 3
cut <<'M'
## K1 impl — a
AREA: src/server/**
DONE WHEN: done
## K2 impl — b
AREA: src/web/**
M
t cut-fields-ok 0 "CUT OK lanes=2" -- C --max-lanes 3
t cut-no-max-lanes-note 0 "NOTE no max_lanes in the profile" -- C

# verify-pr: conflicts, changes requested, case, too many files, a PR with no checks at all
mk
t vp-conflict 4 "conflicts with the base branch" -- env FAKE_GH_CASE=conflict $A verify-pr 7 --repo o/r --report "$R"
t vp-unknown 4 "mergeability unknown" -- env FAKE_GH_CASE=unknown $A verify-pr 7 --repo o/r --report "$R"
t vp-changes 4 "a reviewer requested changes" -- env FAKE_GH_CASE=changes $A verify-pr 7 --repo o/r --report "$R"
t vp-case 4 "outside the chunk's area: SRC/App.js" -- env FAKE_GH_CASE=upper $A verify-pr 7 --repo o/r --report "$R" --area "src/*,docs/*"
t vp-many-files 4 "100+ files" -- env FAKE_GH_CASE=manyfiles $A verify-pr 7 --repo o/r --report "$R"
t vp-no-checks-real 4 "no CI checks registered" -- env FAKE_GH_CASE=nochecks-real $A verify-pr 7 --repo o/r --report "$R"

# book: a lane holding another PR refuses; booked keeps every PR
$A set "$L" pr=9 pr-status=READY >/dev/null
t book-other-pr 4 "the lane holds PR #9" -- env FAKE_GH_CASE=merged $A book "$L" 8 --repo o/r
t book-other-pr-kept 0 "READY" -- $A get "$L" pr-status
$A set "$L" pr=none pr-status=none >/dev/null
t book-second 0 "BOOKED 8" -- env FAKE_GH_CASE=merged $A book "$L" 8 --repo o/r
t book-list 0 "7,8" -- $A get "$L" booked
t book-old-again 0 "ALREADY BOOKED 7" -- env FAKE_GH_CASE=merged $A book "$L" 7 --repo o/r

# set --expect: every pair after it is a condition
$A set "$L" chunk-status=WORKING paused=no >/dev/null
t expect-multi 0 "SET paused=no" -- $A set "$L" paused=no --expect chunk-status=WORKING lane=1
t expect-multi-not-set 0 "1" -- $A get "$L" lane
t expect-multi-refused 4 "expected lane=2" -- $A set "$L" paused=no --expect chunk-status=WORKING lane=2

# times: a stamp without a zone is UTC; an unreadable one does not crash the watch
$A set "$L" chunk-status=WORKING pr-status=none paused=no progress-line=2026-01-01T00:00:00 >/dev/null
t stall-naive-time 0 "STALL QUIET" -- $A stall-check "$L" --repo o/r
$A set "$L" progress-line=yesterday >/dev/null
t stall-bad-time 0 "unreadable stamp" -- $A stall-check "$L" --repo o/r
$A set "$L" wait-kind=decision wait-since=2026-01-01T00:00:00 >/dev/null
t answered-naive-time 0 "ANSWERED after" -- $A line "$L" ANSWERED
$A set "$L" "progress-line=$(date -u +%FT%TZ)" >/dev/null

# locks: the holder carries its repository
t lock-acquire 0 "ACQUIRED db o/r:t1/L1/K1/a#1" -- $A lock acquire db --holder t1/L1/K1/a#1 --repo o/r
t lock-same-holder 0 "already held by this holder" -- $A lock acquire db --holder t1/L1/K1/a#2 --repo o/r
t lock-other-repo 4 "HELD db" -- $A lock acquire db --holder t1/L1/K1/a#1 --repo o/q
t lock-release-other-repo 4 "REFUSED db is held by" -- $A lock release db --holder t1/L1/K1/a#1 --repo o/q
t lock-no-repo 2 "--holder H --repo R" -- $A lock acquire db --holder t1/L1/K1/a#1
t lock-release 0 "RELEASED db" -- $A lock release db --holder t1/L1/K1/a#3 --repo o/r
t lock-free 0 "db: free" -- $A lock show db

# wait-pr.sh: an unreadable profile or no python is an ERROR, never green; decimal numbers
NOPY="$T/nopy"; mkdir -p "$NOPY"
printf '#!/bin/sh\nexit 1\n' > "$NOPY/python"; cp "$NOPY/python" "$NOPY/python3"; chmod +x "$NOPY/python" "$NOPY/python3"
NOPY=$(cygpath -u "$NOPY" 2>/dev/null || echo "$NOPY")
export FAKE_WAIT_LINE="OPEN||abc1234def|1|0|||test"
t wp-no-python 1 "ERROR no python" -- bash -c "PATH='$NOPY:$FB:'\"\$PATH\" bash '$SKD/wait-pr.sh' 7 --repo o/r --once"
printf '{ broken' > "$P"
t wp-broken-profile 1 "ERROR cannot read the required checks" -- W 7 --repo o/r --once
cp "$T/profile.bak" "$P"
t wp-require-none 0 "missing=[]" -- W 7 --repo o/r --require none --once
t wp-every-zero 2 "at least 1" -- W 7 --repo o/r --every 0
export FAKE_WAIT_LINE="MERGED|fedcba98|abc1234def|1|0|||test"
t wp-leading-zero 0 "MERGED fedcba98" -- W 7 --repo o/r --hours 08 --missing-min 09 --every 1
unset FAKE_WAIT_LINE

# watch-session.sh: a folder with no transcript yet is waited for, not an error at once
WS2="$T/proj/sess2"; mkdir -p "$WS2/memory"
t ws-no-transcript 2 "ERROR no transcript" -- timeout 20 bash "$SKD/watch-session.sh" "$WS2" --wait-dir 0
( sleep 2; echo '{"type":"user"}' > "$WS2/a.jsonl" ) &
t ws-waits-for-transcript 124 "" -- timeout 8 bash "$SKD/watch-session.sh" "$WS2" --wait-dir 30 --quiet-min 30
wait

# usage: a worker-dir with a trailing slash still counts
export LIPOK_PROJECTS_DIR="$CP"
W2="C--y--claude-worktrees-other-cccccc"; rec "$CP/$W2/w.jsonl" ya 10
$A set "$L" "worker-dir=$W2/" >/dev/null
t usage-trailing-slash 0 "worker folders=1" -- U --manager C--m
unset LIPOK_PROJECTS_DIR

# installers: never into the package itself; a normal install copies both skills
ROOT=$(cd "$(cygpath -u "$SKD" 2>/dev/null || echo "$SKD")/../../.." && pwd)
PKG="$T/pkg"; rm -rf "$PKG"; mkdir -p "$PKG"
cp -R "$ROOT/bin" "$ROOT/skills" "$ROOT/package.json" "$ROOT/install.sh" "$PKG/"
t inst-node-self 1 "refusing to install into the package itself" -- node "$PKG/bin/lipok.js" install --dir "$PKG/skills"
t inst-node-inside 1 "refusing to install into the package itself" -- node "$PKG/bin/lipok.js" install --dir "$PKG/skills/lipok"
t inst-node-dash 1 "--dir needs a folder" -- node "$PKG/bin/lipok.js" install --dir --force
t inst-sh-self 1 "refusing to install into the package itself" -- env CLAUDE_SKILLS_DIR="$PKG/skills" bash "$PKG/install.sh"
t inst-source-kept 0 "" -- test -f "$PKG/skills/lipok/SKILL.md"
t inst-node-ok 0 "installed" -- node "$PKG/bin/lipok.js" install --dir "$T/dest-node"
t inst-node-copy 0 "" -- diff -rq "$PKG/skills/lipok" "$T/dest-node/lipok"
t inst-sh-ok 0 "installed" -- env CLAUDE_SKILLS_DIR="$T/dest-sh" bash "$PKG/install.sh"
t inst-sh-copy 0 "" -- diff -rq "$PKG/skills/lipok-task" "$T/dest-sh/lipok-task"
t inst-uninstall 0 "removed" -- node "$PKG/bin/lipok.js" uninstall --dir "$T/dest-node"
echo "PASS=$PASS FAIL=$FAIL"
