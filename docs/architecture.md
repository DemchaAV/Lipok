# Lipok architecture

How Lipok works now. The skills (`lipok`, `lipok-task`) are the operational instructions; this
document is the map.

## What Lipok is

Lipok is a multi-agent development harness for Claude Code. It takes a task too big for one
session — a plan of many items — and runs it as **chunks** on parallel **lanes**. Each lane is a
worker session in its own git worktree; every item ends as a pull request that a human merged.
Lipok is two skills and a few scripts: no server, no daemon, no database. State is plain files
under `~/.lipok`; sessions coordinate through one-line messages and background watches.

The human keeps three things: approving the cut, answering decisions, and merging. **Nothing
auto-merges.** No role merges, enables auto-merge or force-pushes, and a PR is called "ready to
merge" only after a script has checked it against GitHub.

## The overall flow

```text
User ── /lipok-task <plan> ──▶ Manager session (the only one the user talks to)
                                 │  scout ─▶ cut ─▶ cut-check ─▶ user says "yes"
                                 │  task-new, deploy lanes
                                 │
          CHUNK / GO / REDIRECT / NOTE / DECISION / SYNC / PING / PAUSE / RESUME / STOP
                                 │                                   ▲
                                 ▼                                   │ LANE / PLAN / READY / MERGED /
                ┌──────── Worker, lane 1 (own worktree) ─────────┐   │ DECISION / BLOCKED / PAUSED /
                │  chunk plan ─▶ for each item:                  │   │ ALIVE / CHUNK_DONE
                │     executor subagent (fresh context):         │───┘
                │       measure, fix, tests, sabotages,          │
                │       cold review, commit, draft PR            │
                │     worker: gate, CI, out of draft, verify-pr  │
                │     wait-pr.sh ─▶ MERGED ─▶ next item          │
                └────────────────────────────────────────────────┘
                ┌──────── Worker, lane 2 ... (same shape) ───────┐
                └────────────────────────────────────────────────┘

Manager's watches per lane: watch-session.sh (transcript), stall-check --watch (progress)
User: approves the cut and answers decisions in the Manager session, merges PRs on GitHub
```

## Roles

| Role | What it is | Owns | Never does |
|---|---|---|---|
| **User** | a human | the task, approval of the cut, decisions outside a chunk's scope, every merge | — |
| **Manager** | the session where the user typed `/lipok-task` | the cut; handing chunks to lanes; checking chunk plans against the whole picture; course corrections; carrying facts between lanes; decisions with the user; verifying what workers call ready; the merge queue; supervision; phone notifications | item work; reading diffs, CI logs, whole reports or worker transcripts; merging |
| **Worker** | a session the Manager starts, one per lane, in its own worktree, kept for the whole task | one chunk at a time: its plan, its items, the gate, the PR watch, CI triage, `SYNC`, taking PRs out of draft | leaving its chunk's area; deciding for the user; changing a contract outside a contract chunk; talking to other workers |
| **Executor** | a subagent of the worker, one per item attempt, fresh context | one item from its brief to a reviewed draft PR, and the item report | the next item; waiting for CI; `gh pr ready`; messaging any session; asking the user |
| **Scout** | a read-only `Explore` subagent of the Manager | mapping the code for the cut | deciding the cut |
| **Chunk reviewer** | a `general-purpose` subagent of the Manager | an independent review of contract and assembly chunks, and any chunk the user names, from the brief, `done.md` and the PRs' diffs; verdict in `reviews/GR-NNN.md` | editing code; seeing the worker's reasoning |

One principle drives the split: **the Manager sees outcomes, not steps.** It must hold the whole
task in one context, so it reads only short artifacts — a chunk plan once, one note line per PR,
one script line, a watch's last line. Whatever grows with the work stays with the worker, which in
turn gives every item to a fresh executor that starts from a brief, not from history.

## Units of work

```text
task ──▶ chunks (contract | foundation | impl | assembly) ──▶ items ──▶ one PR per item
```

- A **task** is one plan run through Lipok; a project has at most one active task.
- A **chunk** is a closed sub-task of 2–6 items: after its last PR merges, the base builds and
  works (a new feature may still be switched off). It has an `AREA` (the files it may change) and
  an `AFTER` (chunks whose last PR must merge before it is handed out). Kinds:
  `contract` fixes the seams between parallel chunks (the contract file, generated types, mocks,
  stubs, the feature flag, and every hot-file edit the wave will need); `foundation` lays shared
  groundwork that is not a seam; `impl` builds one side of a seam inside its own area;
  `assembly` wires the sides together, switches the feature on, and owns docs and `CHANGELOG`.
- An **item** is one plan line and becomes one PR.
- A **wave** is a set of chunks with no `AFTER` path between them; they run at the same time.

**Keys** name every unit so a late message can be recognised. The chunk key `<ck>` is
`<tid>/L<N>/<K>` (task id, lane, chunk), made by `lipok.py chunk`; the item key `<key>` is
`<ck>/<slug>#<attempt>`, made by `lipok.py item` and `lipok.py bump`, never by hand. The attempt grows with every new
executor brief for the same item — a fix, a `SYNC`, a resume after a dead turn — so a line or
report carrying an older key is late and is ignored.

## The cut

Parallel lanes break at the seams between chunks, never inside one, and a bad seam surfaces only
at assembly, where no worker can save it. The cut is therefore the Manager's most valuable work.

**The hard rule: two chunks of one wave never change the same file.** Chunks may share files only
when one comes `AFTER` the other. This removes merge conflicts between lanes by construction
rather than by care.

1. A **scout** maps the main checkout: the modules the plan touches, existing seams, **hot files**
   (central registries, route tables, `index` re-exports, schemas and migrations, `package.json`
   and lockfiles, i18n files, `CHANGELOG`, snapshots, CI config), shared resources, and the files
   each item will likely change.
2. Each seam between parallel parts gets a **contract**: a file in the repository that CI checks
   from both sides — a schema with a test, a shared types module, a migration run from scratch. A
   seam described only in a brief is not a contract, and its two sides may not run in parallel.
3. **Each hot file has one owner**, normally the contract chunk (before the wave) or the assembly
   (after it). A dependency an `impl` chunk discovers later is a decision that lands through the
   owner, never a quiet lockfile edit.
4. The cut is written to `cut-draft.md`, one `## K<n> <kind> — <title>` heading per chunk with
   `AREA`, `AFTER`, `ITEMS`, `RESOURCES`, `DONE WHEN` and, for contracts, `SEAMS`.
5. `lipok.py cut-check` enforces the rule: chunks not ordered by `AFTER` may not share a file (from
   the main checkout's `git ls-files`) nor overlapping `AREA` globs; `AFTER` must name real chunks
   with no cycle; each item sits in one chunk. It prints a `LANES` line — how many rounds each
   number of lanes takes, a round being one chunk's run on one lane — then `CUT OK lanes=<n>` (the
   widest wave capped by the profile's `max_lanes`, a default) or `CUT FAIL <reasons>`. A failing
   cut is never handed out.
6. The user sees the chunks, waves, areas, seams with their CI checks and what stays sequential,
   and chooses the number of lanes from the `LANES` options — the fastest first, with what more
   lanes cost (the usage limit burns faster; more pull requests wait on the user at once). The
   task starts only after their "yes".

**One lane is often the right answer**: when the widest wave is 1, a side of a seam would get
fewer than two items, the areas cannot be separated without a check the project lacks, or the task
is a day's work.
The cut changes later only through the user: a decision record, an edited cut, `cut-check` again,
and a `REDIRECT` or `NOTE` to the lanes affected.

## Messages between sessions

Sessions exchange **one line**, addressed by `local_…` id: `<TYPE> <key> — <absolute path>`, or
`<TYPE> <key>` without a file; anything longer goes into the file. Every event is an explicit line:
the app wakes a parent session only when all its children are idle.

**Worker → Manager**

| Line | Meaning |
|---|---|
| `LANE <N> <folder>` | first turn only: the worker is up; `<folder>` holds its transcript |
| `PLAN <ck> — <plan.md>` | the chunk plan is written; waiting for `GO` or `REDIRECT` |
| `READY <key> — <report>` | the PR is out of draft and the worker's own `verify-pr` says `VERIFY OK` |
| `MERGED <key> — <report>` | the worker's PR watch saw the merge |
| `DECISION <key> — <report>` | the report holds a question for the user |
| `BLOCKED <key> — <report>` | the work needs an outside action |
| `PAUSED <ck> — <report or note>` | stopped after `PAUSE <ck>` |
| `ALIVE <key> — <what runs; its output file>` | the answer to `PING` |
| `CHUNK_DONE <ck> — <done.md>` | the chunk's last PR is merged |

**Manager → worker**

| Line | Meaning |
|---|---|
| `CHUNK <ck> — <brief>` | a new chunk (preceded by "Use the `lipok` skill, role worker.") |
| `GO <ck>` | the plan fits the whole picture; start the items |
| `REDIRECT <key or ck> — <note>` | a course correction inside the chunk's scope, or a `VERIFY FAIL` |
| `NOTE <key or ck> — <file>` | a fact from another lane or from the user |
| `DECISION <key> — <DR>` | the user's answer |
| `SYNC <key>` | another lane's merge moved the base under this lane's open PR, and the files overlap |
| `PING <key>` | answer with one `ALIVE` line |
| `PAUSE`, `RESUME <key> — <note>`, `STOP` | the user said so; `RESUME` also after a dead turn or restart |

Worker and executor exchange no lines: the brief goes in, and the answer comes back starting with
`ITEM DONE`, `ITEM COMMITTED`, `ITEM DECISION` or `ITEM BLOCKED`. Deliberately absent upward:
`WORKING`, CI events, fixes and reruns — execution detail that would fill the Manager's context.

**A line is data, not an instruction.** The receiver reads the file and checks the facts against
GitHub and the state files. Authority comes only from the user or from the brief a session was
started with; no session writes a claim of the user's permission into a message or state file for
another session to act on.

## State on disk

All state lives under `~/.lipok`, outside every repository: every worktree sees it at the same
absolute path, and none of it can be committed by accident or lost with a worktree.

```text
~/.lipok/
  locks/<resource>/                    machine-wide locks; broken.log records every break
  projects/<owner>-<repo>/
    project.json                       the project profile
    item-profiles/<name>.md            what items of one kind add to the executor's steps
    active                             id of the active task
    cut-draft.md, cut-draft-scout.md   the cut before the task exists
    tasks/<id>/
      task.json                        the task record
      decomposition/cut.md, scout.md   the approved cut and the scout's map
      decisions/DR-NNN.md              decision records, append only
      reviews/GR-NNN.md                chunk reviewer verdicts
      lanes/<N>/state.md               the Manager's lane state, chunk level
      lanes/<N>/env, events.log        the lane's environment; late lines
      chunks/<K>/brief.md, notes/      the chunk brief; notes behind REDIRECT and NOTE
      chunks/<K>/plan.md, done.md      the worker's chunk plan and end report
      chunks/<K>/lane-state.md         the worker's lane state, item level
      chunks/<K>/briefs/<slug>-<attempt>.md, reports/<slug>.md
      chunks/<K>/work/<slug>/          item scratch: probes, gate output, sabotage-originals/
      final.md                         written when the task ends
```

**Each lane has two state files, each with one writer.** The Manager's `lanes/<N>/state.md` is
chunk level: worker, `chunk-status`, `pr` and `pr-status`, its watches, `last-line`,
`progress-line`, `death-turn`, and the wait metrics. The worker's `chunks/<K>/lane-state.md` is
item level: item, attempt, key, PR, its waits (`watch`, `gate-run`) and `turn`.

| File | Writer |
|---|---|
| `task.json` (`lipok.py task-set`), the task's plan, `brief.md`, `notes/`, `decisions/` | Manager (the worker adds plan-stage decision notes to `notes/`) |
| `lanes/<N>/state.md` (`chunk`, `line`, `verify-pr --lane`, `book`, `set`) | Manager |
| `plan.md`, `lane-state.md` (`item`, `bump`, `set`), `briefs/`, `done.md` | worker |
| `reports/<slug>.md` | executor; the worker adds `GATE`, `CI`, `STATUS: REVIEWED` |
| `reviews/GR-NNN.md` | chunk reviewer |

Writers of one file are serialised by a lock; `lipok.py set` refuses unknown keys. Every event
starts by reading these files, so a compacted context loses nothing.

## Lifecycle of a chunk

1. **Hand-out.** A free lane (`chunk-status` `none`, `DONE` or `DROPPED`) takes the lowest-numbered
   chunk not yet handed out whose `AFTER` chunks are all done. `lipok.py chunk` makes the chunk
   key, its folders and the worker's `lane-state.md`, and sets `chunk-status` to `BRIEFED`. The Manager
   marks the items `[~]` in the task's plan, writes the brief (items verbatim, the cut's `AREA:`,
   `CONTRACTS:`, `KNOWN:` facts and decisions, `DONE WHEN:`), sends `CHUNK` and arms its watches.
2. **Plan.** The worker reads the brief and its area's code and writes `plan.md`: a `## Progress`
   checklist, one line per item with the paths it touches, its dependencies, its contracts and,
   for an item run in planned batches, `· attempts: <n>`. It sends `PLAN`.
3. **Plan check.** The Manager reads the plan once against the other chunks, the contracts, the
   decisions and the task's acceptance, and answers `GO` or `REDIRECT`; a fix that needs a change
   of scope, a contract or the cut goes to the user. It is the cheapest correction: no code exists
   yet.
4. **Items**, one at a time, one open PR per lane.
5. **End.** With every item `[x]`, the worker writes `done.md` — PRs with merge shas, decisions,
   contract changes, `P1:` findings outside the chunk, numbers — and sends `CHUNK_DONE`. The
   Manager sets `chunk-status=DONE`, tells the user in a few lines, and hands out the next chunk or
   ends the task.

## Lifecycle of an item

1. **Brief.** `lipok.py item` starts the item at attempt 1 and prints its `KEY` and `REPORT`. The
   worker writes `briefs/<slug>-<attempt>.md` and starts the executor in the background.
2. **Executor.** It **measures** the item's premise first (a refuted premise is a decision);
   **fixes** by one general rule inside `AREA:`; writes positive and negative **tests**; runs
   **sabotages** (a script breaks each rule once; a real test must fail; files must be
   byte-identical afterwards); runs the owning modules' tests (`module_tests`); gets a **cold
   review** from a fresh subagent at the `review_skill` bar; commits as the profile's `author`;
   opens a **draft** PR; and reviews the PR again until a round finds no Blocker, Critical or
   Major. It answers bot comments, keeps the report current, and returns `ITEM DONE`.
3. **Gate.** The worker runs the profile's `gate` in the background on the final tree; the output's
   last line must be `GATE PASS`, and the file goes into the report's `GATE:`. With
   `gate_when: before_push`, the executor commits without pushing (`ITEM COMMITTED`), the worker
   gates that commit, and a new executor (`START AT: 9.4`) pushes and opens the PR.
4. **CI**, read once with `gh pr checks`; pending CI is left to the PR watch.
5. **Out of draft**: `gh pr ready`, report `STATUS: REVIEWED`.
6. **Self-check**: the worker runs `verify-pr` as the Manager will, and sends `READY` on `VERIFY OK`.
7. **Verification.** The Manager runs `verify-pr --lane`. `VERIFY OK` sets `pr-status=READY`, marks
   the item `[>]`, queues the PR and notifies the user — only now is it "ready to merge".
   `VERIFY FAIL` sets `pr-status=REDIRECTED` and returns as a `REDIRECT` with every failing point.
8. **Merge.** The user merges. The worker's `wait-pr.sh` prints `MERGED <sha>`; the worker marks
   the item `[x]` and sends `MERGED`. The Manager's `lipok.py book` confirms the merge on GitHub
   (`BOOKED <pr> <sha> <date>`, `ALREADY BOOKED` or `NOT MERGED`), marks the task's plan, and sends
   `SYNC` to any other lane whose open PR touches the same files.

A red gate, a CI failure caused by the change, or a `SYNC` loops back as a new attempt
(`lipok.py bump`) and a new executor. A CI failure matching the profile's `infra_failures` is
re-run once; a second on the same head is `BLOCKED`. An executor that gives no answer, or one its
report does not back, gets a new attempt; the third that ends the same way is `BLOCKED`. A `SYNC`
merges `origin/<base>` with a merge commit, never a rebase.

## Verification

`lipok.py verify-pr <pr> --repo R --report F --area "<globs>"` checks GitHub and files, not the
report's words, and prints `VERIFY OK <pr> <sha>` or `VERIFY FAIL <pr>: <every failing point>`:

- the PR is open, not a draft, on `base_branch`, with no auto-merge, no conflict with the base and
  no review requesting changes (`mergeability unknown`: run it again in a minute);
- the report's `HEAD` is the PR's head;
- all CI checks finished, none failed, and every `required_checks` name registered — a check that
  never started does not pass as green;
- no unresolved review thread;
- the report holds up: `STATUS: REVIEWED`; `TESTS` non-zero with none failed; `REVIEW` with at
  least one round and no open Blocker, Critical or Major; `BOTS` all answered; `SABOTAGES` all
  caught, at least one, when code changed (unless the profile sets `sabotages` to `false`); the
  `note_field` line (default `PLAN-NOTE`);
- `GATE` names a file ending `GATE PASS` and newer than the PR's last commit;
- every file of the PR is inside the area (under 100 files, so the list is complete).

A report can be wrong in good faith; the script checks what it claims. The worker runs the same
check before `READY`, so a `VERIFY FAIL` at the Manager is rare and meaningful.

## Supervision

Nothing a worker does inside a chunk reaches the Manager except its lines, so silence must be
caught by a watch, not by waiting. Three watches run with `run_in_background`, so their exit wakes
the session that armed them; each prints one line.

| Watch | Whose | Detects |
|---|---|---|
| `wait-pr.sh <pr> --repo R` | the worker's, per open PR | `MERGED <sha>`, `CLOSED`, `CI-GREEN <head>` (once every required check reported), `CI-FAIL <head> <runs> <checks>`, `CI-MISSING <head> <names>`, `OPEN after <H>h`, `ERROR` |
| `watch-session.sh <worker-dir> --quiet-min N` | the Manager's, per lane | over the worker's transcript and its subagents': `SESSION LIMIT`, `SESSION ERROR`, `SESSION QUIET`, `SESSION GONE`, `SESSION OK` |
| `lipok.py stall-check --watch` | the Manager's, per lane | `STALL QUIET` (no progress line — `PLAN`, `READY`, `MERGED`, `CHUNK_DONE` — for `progress_window_h`), `STALL LOOP <key>` (past the planned attempts plus `max_attempts - 1` retries), `STALL IDLE` (paused, done, or waiting on the Manager or the user) |

The PR watch is the only CI poller; nobody else reads CI repeatedly or turns on the app's CI monitor.

**Waiting is not idling.** A worker waiting on its PR watch or gate names the wait in its lane
state (`watch`, `gate-run`); a lane waiting on the user (a plan, a decision, a READY PR) is waiting
too. The Manager checks these facts and `get_session` before reacting. What it must catch is the
**silent idle**: the worker is not running, names no wait, holds an unfinished item, and has sent
nothing.

| Signal | Manager's response |
|---|---|
| `SESSION LIMIT` | a usage limit, not a failure: a timer until the reset, then `RESUME` |
| `SESSION ERROR` | the turn died on the model: `RESUME` with a note; a second death on the same item (`death-turn`) switches the worker's model (`set_session_model`) and tells the user |
| `SESSION QUIET` with a running turn or a live wait | re-arm silently |
| `SESSION QUIET`, silent idle | `RESUME` asking for the report and a line; twice in a row, tell the user |
| `SESSION QUIET` otherwise; `STALL QUIET` | `PING`; no `ALIVE` before the next stall line → a dead turn |
| `SESSION GONE` | replace the worker |
| `STALL LOOP` | `PAUSE <ck>` and tell the user; if they say go on, `loop-ack=<key>` and `RESUME` |
| `ALIVE` | read against the facts; the same fix over and over, or work outside the chunk → `REDIRECT` or a decision |

A gone worker is **replaced**, on the user's turn, by a new session (`lipok-<tid>-l<N>-r<k>`) that
continues from `lane-state.md`, `plan.md` and the open PR; uncommitted work is lost. After a restart
all watches are gone: the user's "resume" makes the Manager re-read the state, re-verify READY PRs,
re-arm the watches, send `RESUME` to each worker, and break locks of workers that no longer run.

## Decisions and blocking

No agent decides a refuted premise, a choice between non-equivalent solutions, widening or
splitting an item or chunk, a change outside the area, the shape of a public API, a contract
change, or a plan rule the measurements contradict. The Manager alone may `GO` a fitting plan,
`REDIRECT` within scope, order chunks the plan leaves open, and hand a chunk to a free lane.

1. The executor writes the question in its report (`STATUS: DECISION`; options, recommended first,
   and what each changes) and returns `ITEM DECISION`. At the plan stage the worker writes a note.
2. The worker sends `DECISION <key> — <report>`. The Manager's `lipok.py line` opens the decision
   wait; `chunk-status=DECISION`.
3. The Manager notifies and asks the user, then **writes the record before answering**:
   `decisions/DR-NNN.md` with the question, the options, the user's words verbatim, and what it
   changes in the plan.
4. Inside the chunk's scope the answer goes down as `DECISION <key> — <DR>`, and a new executor
   gets it in `KNOWN:`. An answer that changes scope or the cut becomes a new brief or a `REDIRECT`
   naming the DR, plus a `NOTE` to each lane it touches.
5. `lipok.py line … ANSWERED` closes the wait and adds its minutes to `decision-wait-min`.

`BLOCKED` takes the same path for things needing an outside action: a closed PR, a review thread a
person opened, a required check that never started, a repeated infrastructure failure. The answer
returns as `RESUME <key> — <note>` or `DECISION`, or as a drop: a `REDIRECT` dropping the item, or
`STOP` and `chunk-status=DROPPED` for the chunk.

## Parallel lanes and collisions

- **The cut** gives chunks of one wave disjoint files.
- **AREA enforcement**: each brief carries the cut's `AREA` verbatim; `verify-pr --area` refuses a
  PR with any file outside it.
- **SYNC after merges**: the Manager compares each merge's files with other lanes' open PRs
  (`gh pr view <n> --json files`) and sends `SYNC` on overlap. With a clean cut this happens only
  across `AFTER`.
- **The merge queue**: READY PRs go to the user in order — dependencies first, then PRs touching
  the same files back to back. Over `max_ready_prs`, the Manager tells the user.
- **Machine-wide locks** for indivisible resources (`resources` in the profile, `RESOURCES` in the
  cut): `lipok.py lock acquire|release <resource> --holder <key> --repo R`, held only around the
  run that needs it. A holder is the repository plus the item key without its attempt, so a retry
  keeps its lock. Only the Manager breaks a dead holder's lock (`lock break <resource> --by manager`), logged.
- **Per-lane environment**: `lane_env` gives each lane its own values (a port) via
  `lipok.py lane-env`; `lane_setup` and `lane_teardown` run per lane.

## Cost

The Manager wakes only on events — a worker's line or a watch's exit — and reads a few lines each
time; watches cost nothing while they wait. Workers spend their turns on coordination. Executors
do the bulk of the tokens.

`lipok.py usage <task> --manager <the Manager's working directory>` measures the split from the
transcripts on disk, with no model call: manager, worker (own turns) and executors, each with a
share of relative cost, and a `COORDINATION` percentage. Its lines go into `final.md` with the
task's metrics: time from deployment to the last merge, PRs merged, and minutes lanes waited on
merges and decisions.

## Limits and assumptions

- **Only the human merges**, and each lane has one open PR at a time: the task moves at the
  user's merge pace.
- **One level of coordination**: lanes are flat under one Manager, with no tier in between.
- **The Claude Code desktop app is required** for its session tools (`start_session`,
  `get_session`, `list_sessions`, `SendMessage`, `PushNotification`). It starts sessions only on a
  turn the user began, so lanes are deployed and replaced on the user's turn.
- **GitHub only**, through `gh`.
- **Developed on Windows with Git Bash.** The scripts are bash and Python; other platforms should
  work but are less exercised.
- **Multi-lane runs are not yet exercised live.** A single lane has run end to end on a real
  project; the cut, `cut-check` and parallel lanes are implemented and script-tested only.
- **A worker's context over a long chunk** is kept small by short chunks and fresh executors; how
  many items one worker holds well is still being measured.
