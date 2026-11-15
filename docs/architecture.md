# Lipok — flat multi-agent development, v6

> Renamed 2026-11-15: the harness used to be called **Archon** (the name is taken by another AI project), now it is **Lipok** — skills `lipok` and `lipok-task`, script `lipok.py`, state `~/.lipok`, lane branches `lipok-<tid>-l<N>`. References of the form "v5, section N" point to the previous design, which is not part of the repository.

Date: 2026-11-11. Basis — v5 (`multi_agent_architecture_v5.md`); this document covers only what changes.
Everything v6 does not name works as in v5: platform constraints (section 4), item statuses
(section 11; `READY` is still set only by the Manager — after `verify-pr`), failures and
recovery (section 19), project profile (section 16), the rules of section 23 — except 5 (in v6, one
open PR per lane), 7 (the chunk is led by the worker, section 5) and 17 (the disposable contexts are now those of
item executors, not workers; state still lives in files).

## 0. What changed versus v5

| In v5 | In v6 | Why |
|---|---|---|
| Two schemes: flat and three-level | **One — flat.** Three-level is deferred (section 12) | The Supervisor relies on platform workarounds: the "start" phrase (v5 §4, 1a), the ban on clearing (3b), a "grandchild" does not wake the "grandparent" (3a); option "b" reduces it to a line relay |
| The lane lead is the Manager: a brief and a clear for every item, CI triage, reconciliations | **The worker leads the chunk itself.** The Manager assigns the chunk and receives reports on the result | The Manager's context grew at the pace of the steps (under the old scheme three items produced a huge history of logs and reconciliations); the Manager did not survive to the end of the task |
| Clean context per item — the worker's `clear_session` | **Clean context per item — a fresh subagent inside the worker** | Clearing is unreliable: on 2026-11-10 the classifier rejected clearing its own idle worker (v5 §4, row 2; session-clearing probes). A subagent starts on any turn (v5 §4, row 11) |
| CI and merge are watched by the Manager (`wait-pr.sh`) | **The worker keeps its own PR watch**; the Manager checks the result with one script line (`verify-pr`) | CI logs, reruns and `SYNC` are execution details; they do not belong in the Manager's context |
| A watch over the worker's transcript catches a dead turn | **Manager supervision** (section 3a): the same watch, plus a stall without a failure, an attempt loop, a silent idle, a report that does not match reality | When the worker leads the chunk itself, the Manager would otherwise not see a failure inside it |
| The Manager is a planner and an assembler | **The Manager is the interface and the lead**: the big picture, the course, decisions, the merge queue | A worker with a clean context sees its chunk; only the Manager sees where it is heading relative to the whole project |

## 1. Model

```text
User ⇄ Manager — one window for the whole task; knows the project, the plan, the decisions, the lanes' progress
                  │
                  │  "Chat integration" → cut (approved by the user):
                  │     K0  contract: chat API, message types          → first, merged before the rest
                  │     K1  backend: storage, API, notifications (N items) → Worker A
                  │     K2  frontend: screen, list, input (M items)      → Worker B
                  │     K3  assembly: wire up, e2e, enable the feature   → whichever worker is free
                  │
                  ├── Worker A — its own worktree, leads chunk K1 itself
                  │      item 1 → fresh subagent: measure, edit, tests, review, PR
                  │      item 2 → fresh subagent …
                  │      itself: PR watch, CI, conflicts with the base, gate
                  │      upward: chunk plan · a line per item · PR ready · decision · block · chunk done
                  │
                  └── Worker B — the same for K2
```

The Manager as in real life: does not stand over your shoulder, but sees the big picture, reads short reports and
says "wrong way, do it differently" in time. A worker works from its own vantage point — well, but
narrowly; course corrections are the Manager's job.

## 2. Roles

| Role | What it is | Does | Does not |
|---|---|---|---|
| **User** | a human | sets the task, approves the cut and the contracts, answers decisions, merges | — |
| **Manager** | the `/lipok-task` session | the cut; approving chunk plans; course corrections; supervision of the lanes' liveness and progress (section 3a); carrying facts between lanes; decisions with the user; checking ready PRs; the merge queue; chunk reviews; push to the phone; starts workers on the user's turn | does not write code; does not read CI logs, diffs or the worker's work in progress; does not merge |
| **Worker** | a session in its own worktree, bound to a lane; leads one chunk at a time | the chunk plan; the loop over items via subagents; the watch of its own PR; CI triage; `SYNC`; the gate; reports | does not step outside its chunk and its code area; does not decide for the user; does not change the contract outside a contract chunk |
| **Item executor** | the worker's subagent, one per item | the whole item from a clean context: measure, edit, tests, sabotages, cold review, commit, PR; writes the item report | does not take the next item; does not wait for CI for hours (that is the worker's job) |
| **The scout** | the Manager's subagent | during the cut, reads the code: modules, layers, seams, shared files | does not decide the cut |
| **Chunk reviewer** | the Manager's subagent | independent review of a contract chunk before the merge and of the assembly before the feature is enabled; optionally — of any chunk at the end | does not edit code |

## 3. How the Manager sees that a worker is heading the wrong way

The Manager does not follow the steps, but has five points where it sees the course, and each costs a line or two
of context.

1. **The chunk plan before the first item.** The worker has received a chunk, read the code of its area and writes
   the chunk plan: items, order, what each changes, which contracts it reads. It sends `PLAN`. The Manager
   checks it against the big picture — other chunks, contracts, `DR` decisions, acceptance criteria — and answers
   `GO` or `REDIRECT` with a note. The cheapest course correction is the one made before code is written.
2. **A line per item.** Every merged or ready item gives one `<note_field>:` line (by default `PLAN-NOTE:`) — what the PR does
   and what was measured. The Manager reads only that line and notices a mismatch: "the frontend expects a `sentAt` field,
   but the backend named it `createdAt` in item 4".
3. **Checking the result with a script.** The "PR ready" line is checked with one command
   (`lipok.py verify-pr`): not a draft, the report's HEAD is the PR head, CI is green on that SHA, review
   has no open Blocker/Critical/Major. The script prints one line. "Ready to merge" stays
   true and does not clutter the context. Past cycles showed why this cannot be skipped: false
   claims in green code (2026-10: four review rounds, eight Majors), a refuted root cause
   that survived into the CHANGELOG (2026-10-30).
4. **Chunk review.** At the end of the contract chunk (before the merge) and of the assembly (before the feature is enabled) the Manager
   launches an independent reviewer; for the other chunks — at the user's wish. The worker
   looks at its own code for twenty items — a fresh look has to come from outside.
5. **Carrying between lanes.** A fact from lane A that concerns lane B (the contract changed,
   a shared bug was found, a user decision), the Manager passes on as a `NOTE <key> — <file>` line.
   Workers do not know about each other; only the Manager connects them.

A course correction is `REDIRECT <key> — <note>`: what is wrong relative to the big picture and how it
should be. If the correction changes the scope or a contract, it is not a `REDIRECT` but a user decision
(v5, section 13).

## 3a. Supervision: is the worker alive and is the work moving

The Manager does not read *how* the worker works, but always knows *that* it is alive, moving and not lying
about the result. All of this is done by scripts with a one-line outcome; only the outcome gets into the Manager's
context. A worker's silence is also an event: it is caught by a watch, not by the Manager waiting.

### What is caught and by what

| What happened | How we notice | Manager's response |
|---|---|---|
| **The turn died** on an API or model error | the `watch-session.sh` watch over the worker's transcript → `SESSION ERROR` | `RESUME` "continue from the report" (a new attempt, if needed, is made by the worker), a line to the user. A second death on the same item with no line from the worker in between (`death-turn` = item key) → switch the model; push |
| **Usage limit** | `SESSION LIMIT` | not a dead turn: a timer until the reset + 5 minutes, one push with the time, then `RESUME` |
| **Silence**: nothing is written for longer than the window (`quiet_window_min`) | `SESSION QUIET` — counts subagent transcripts too, so an item executor at work does not cause a false silence | looks at facts, not words: the turn is running; `lane-state` names a live wait — the PR watch (`watch`: CI or merge) or the gate (`gate-run`, its output is growing); the worker is waiting on a lock. If so → re-arm silently. Otherwise → `PING`, answered with one `ALIVE` line; no answer within the window → treat as a dead turn |
| **Silent idle**: the turn ended, but there is no line upward | `SESSION QUIET`: no turn is running, `lane-state` names no wait (`watch`, `gate-run` — `none`), the item is neither merged nor ready, and there has been no line upward since the last `turn` | `RESUME` "report and a line upward"; twice in a row → a line to the user: the worker is losing the protocol |
| **The session is gone** (closed, archived, deleted) | `SESSION GONE` or `get_session` → not found | push and a card: a new session can only be started on the user's turn. The new worker continues from the report, the branch and the PR; uncommitted work is lost — say so |
| **Stall without a failure**: the worker is alive, but the chunk is not moving | the progress timer (`lipok.py stall-check`): more than the profile's `progress_window_h` has passed since the last progress line (`PLAN`, `READY`, `MERGED`, `CHUNK_DONE` — the `progress-line` field; an `ALIVE` answer does not count as progress); waiting for a READY PR to be merged and for a user decision is not a stall (`STALL IDLE`) | an `ALIVE` request; the answer shows where it stands. Fixing the same thing over and over → a course correction (`REDIRECT`) or a user decision |
| **Loop**: the item goes in circles, the attempt count grows | `lipok.py stall-check`: the item's attempt exceeds `max_attempts` (3 by default) beyond the acknowledged one (`loop-ack`) | `PAUSE` the item, to the user — a report and what was tried, push. The user said to continue → `loop-ack=<key>`, the next alarm — after `max_attempts` attempts |
| **Report does not match reality**: "done", but the PR is a draft, CI is red, there was no review | `lipok.py verify-pr` (below) | not `READY`; `REDIRECT` with the mismatch, one line per check item |
| **Out of bounds**: the PR touches someone else's area, a push to the base branch, force-push, auto-merge | `verify-pr`: the PR's files against the chunk area; branch, history, auto-merge setting | stop the item; `REDIRECT` or `BLOCKED`, to the user |

### What `verify-pr` confirms — before the words "ready to merge"

It checks GitHub and files, not the words of the report; it prints `VERIFY OK <pr> <sha>` or
`VERIFY FAIL <pr> <what is wrong>`.

- The PR is not a draft, the base is the project's base branch, the report's HEAD is the PR head.
- **CI**: all checks for this SHA have finished, none has failed.
- **Review**: the item report names the cold review rounds and the outcome of the last one — without
  Blocker/Critical/Major; the PR has no unresolved review threads; bot and CodeQL comments
  have been read (an answer or a fix for each).
- **Gate**: the report names the gate file; its last line is `GATE PASS`, and it is newer than the HEAD commit.
- **Tests and sabotages**: the report names the number of tests (not zero) and of sabotages, and how many were caught
  by real test failures; the code changed but there are zero sabotages → not ready.
- **Area**: all the PR's files are within the chunk area from the brief.

### Manager watches

Per worker — one `watch-session.sh` watch (the transcript and its subagents) and one progress
timer. The PR watch is kept by the worker; if the worker dies, its watch dies too, so on `RESUME` or
replacement the Manager first reconciles the PR with GitHub (as in v5 "Reconciliation after a restart"). After sleep
or a reboot all watches are gone — "resume" re-arms them.

**Push to the user** from supervision: the session is gone; a second dead turn on the same step; the limit (with
the reset time); a loop or `BLOCKED`; the chunk is stuck and the worker does not answer `ALIVE`.

**"status"** for each lane: alive / turn running / idle and since when; the last line
upward and its time; chunk, item, attempt; the PR and its CI; what is waiting on the user.

## 4. Cut

As in v5 (section 7), with two refinements.

- **We cut by code areas, not by item numbers.** Each chunk has its own area of files;
  two lanes do not edit the same file. A shared seam (API, types, data schema) is a separate small
  contract chunk, merged first; the others only read it.
- **A chunk is a closed subtask**: after its last PR the base builds and works, the feature may
  be disabled. Size — from a few to ~20 items.

The cut is proposed by the Manager (with the scout) and approved by the user. It is the most valuable work of the
Manager: a bad seam will surface at the assembly, and no worker will save it.

## 5. The worker's loop over a chunk

```text
The worker receives CHUNK <chunk key> — <chunk brief>
   1. reads the brief, the code area, the contracts; writes the chunk plan chunks/<K>/plan.md
   2. PLAN <chunk key> — <plan.md>; waits for GO or REDIRECT
   3. for each item of the chunk plan:
        a. item brief -> chunks/<K>/briefs/<slug>-<attempt>.md
        b. executor subagent (fresh context) per the brief: measure -> edit -> tests -> sabotages
           -> cold review -> commit -> draft PR -> item report
        c. the worker itself: reconciles the report with GitHub; gate (in the background); PR watch (wait-pr.sh, in the background);
           CI failed because of the change -> a new subagent with a note (FIX); infrastructure ->
           rerun once
        d. all green -> remove draft status -> READY <key> — <report> to the Manager
        e. MERGED (its own watch) -> mark it in the chunk plan -> next item
           the base moved under an open PR -> SYNC itself (merge commit, no rebase)
   4. last item merged -> CHUNK_DONE <chunk key> — <summary report>
```

- **One open PR per lane**, until it has been measured that the pipeline pays off (v5, section 10,
  "Pipeline").
- **Chunk summary report** (`chunks/<K>/done.md`): what was done, PRs with links, decisions, what remains
  or was found outside the chunk (`P1:`), what changed in the contracts. The Manager retells it to the user
  in three to five lines.
- **Decision** — as in v5: the worker writes `DECISION` with options, the recommended one first, and waits.
  A subagent does not make decisions: it stops and returns the question to the worker.

## 6. Messages

One line `<TYPE> <key> — <path>` by `local_…` id, as in v5 (section 12). Item key —
`<task>/<lane>/<chunk>/<slug>#<attempt>`, chunk key — `<task>/<lane>/<chunk>`.

| From → To | Type | Meaning |
|---|---|---|
| Manager → worker | `CHUNK` | a new chunk; path of the chunk brief |
| | `GO` / `REDIRECT` | chunk plan accepted / course correction with a note |
| | `NOTE` | a fact from another lane or from the user; path of the note |
| | `DECISION` | a user decision; `DR` path |
| | `SYNC` | the base moved under an open PR, files overlap with someone else's merge |
| | `PING` | supervision: answer with one `ALIVE` line |
| | `PAUSE`, `RESUME`, `STOP` | as in v5 |
| Worker → Manager | `LANE` | first turn: the transcript folder |
| | `PLAN` | the chunk plan for approval |
| | `READY` | the item's PR is out of draft, the worker's own `verify-pr` is OK; path of the report |
| | `MERGED` | the worker's own watch saw the merge; path of the report |
| | `DECISION`, `BLOCKED` | the user is needed; path of the report |
| | `PAUSED` | stopped on `PAUSE` |
| | `CHUNK_DONE` | the chunk is closed; path of the summary report |
| | `ALIVE` | answer to `PING`: one line, what is running and where its output is |
| Worker ↔ executor | — | the executor is a subagent: a brief on input, an `ITEM DONE / COMMITTED / DECISION / BLOCKED` answer on output |

What does **not** go upward: `WORKING` on every turn, CI events, `FIX`, `SYNC`, reruns — these are the
worker's internal business. Every event upward is an explicit line (v5 §4, row 3c).

## 7. State

As in v5 (section 16) with the step 1 amendments (`lipok.py`, `task.json`). Writers:

| File | Writer |
|---|---|
| `task.json`, the overall plan, `decisions/DR-NNN.md`, `chunks/<K>/brief.md`, `reviews/` | Manager |
| `lanes/<N>/state.md` — chunk level: worker, chunk, chunk status, open PR, pause | Manager |
| `chunks/<K>/plan.md`, `briefs/`, `done.md`, `chunks/<K>/lane-state.md` — item level: key, attempt, watches, `last-turn`, `booked`, `rerun` | worker |
| `chunks/<K>/reports/<slug>.md` | executor subagent (via the worker) |

Item state moves from the Manager's file to the worker's file: this is exactly "not following the steps".

## 8. The Manager's context — what it reads

| Reads | Does not read |
|---|---|
| the chunk brief and summary report; the chunk plan (once); the item's `<note_field>:` line; one `verify-pr` line; the outcome lines of watches and `stall-check`; `DECISION` questions; the chunk reviewer's verdict | diffs; CI logs; the full item report (only on `DECISION`/`BLOCKED` or if the line raised a doubt); worker transcripts |

Budget: a task of 120 items in 6 chunks — about 6 chunk plans, 6 summary reports and 120 lines. The Manager
survives to the end without context compaction or survives it without losses: every event starts by reading
`task.json` and `lanes/*/state.md` (v5, rule 17).

## 9. The bottleneck — merges

Two lanes with a PR per item produce a stream of merges; the task's pace is set by the user.

- The Manager sends ready PRs **in a batch**, in order: dependencies first, then PRs with overlapping
  files back to back.
- A worker may bundle two or three small related items into one PR, if the chunk plan was
  approved that way (`GO`).
- The profile's `max_ready_prs`: once the limit is reached, workers bring the current item to READY and wait.

## 10. Unverified assumptions — probes before building

| # | Assumption | How to check | If not so |
|---|---|---|---|
| P1 | The worker's subagent carries an item through entirely: edit, tests, commit, `gh pr create` | one pilot item | **verified 2026-11-11 (partial pilot): yes** — the executor carried a real item (nine findings) to a draft PR on its own: 51 minutes, two review rounds, 153 tests, 26 of 26 sabotages |
| P2 | A subagent can launch its own subagent (cold review) | **verified 2026-11-11: yes** — the subagent called `Agent` and got an answer; its background `Bash` also returned a result | — |
| P3 | A long run (gate, waiting for CI) is awaited by the worker with its watch, not by the subagent | pilot: a gate longer than 10 minutes | — (that is the design; what is checked is that the worker wakes up from the watch) |
| P4 | The worker's context holds a chunk of ~20 items: reports, PR events, compaction | pilot, metric: transcript size per item, quality after compaction | a smaller chunk; or worker-per-chunk: a new worker for each chunk (on the user's turn) |
| P5 | Clearing the worker between chunks | session-clearing probes, if needed | a new worker per chunk |

## 11. Rollout plan

**Implementation of step A (2026-11-11):** the `lipok` skill was rewritten for v6 — `references/item.md`
(executor), `worker.md` (the worker leads the chunk), `lane.md` and `manager.md` (the Manager side, supervision),
`lipok.py` (`chunk`, item state kept by the worker in `chunks/<K>/lane-state.md`, `verify-pr`,
`stall-check`; 47 tests; a cold consistency review — 11 findings fixed).

**Partial pilot (2026-11-11).** The Manager and worker roles were played by one session (the turn came from the phone, and sessions cannot be started from such a turn), while a real item was carried out by an executor subagent in a separate worktree. Outcome: a PR, gate `GATE PASS`, CI green, `verify-pr` OK for both the worker and the Manager. Verified: P1, P2, the report format, `verify-pr` on a real PR, the READY path. Found and fixed: a note line of the wrong form (the brief did not name `note_field`) — now the brief carries `NOTE FIELD:`, and `verify-pr` requires that line; the reviewer left a service folder in the tree — a rule in `item.md`; a heredoc with slashes and quotes breaks in Bash — a rule in `SKILL.md`. Not verified: separate sessions, watches and supervision, wake-ups, the worker's context over a chunk (P3, P4) — that is the full pilot.

**Full pilot (2026-11-12).** One chunk of a real project (five items and a defect the user found in production during the chunk): a separate worker session in its own worktree, executors in the background, 6 PRs, all merged by a human; the task was closed with `final.md`. Verified: lines in both directions, `GO`/`READY`/`MERGED`/`DECISION`/`BLOCKED`/`NOTE`/`CHUNK_DONE`, two decisions via DR, the production defect as a `NOTE` → a new item, the Manager read neither diffs nor CI logs. Findings and fixes (2026-11-13): (1) `stall-check` counted planned batches as a loop — now `item --attempts N` and the plan line `· attempts: N`; (2) `verify-pr` did not know about required checks — the profile field `required_checks`; (3) `wait-pr.sh` reported `CI-GREEN` before the deploy check had appeared — now it waits for the required ones and says `CI-MISSING`; (4) `watch-session.sh` fired immediately on re-arming — silence is now counted from arming; (5) sessions cannot be started from a turn that came from the phone (Remote Control has nothing to do with it); (6) the Manager forgot the `progress-line` mark on `MERGED` → a false `STALL QUIET` — marks are set by `lipok.py line`, booking by `lipok.py book`, READY by `verify-pr --lane`; (7) merge wait time was not recorded — the fields `merge-wait-min`, `decision-wait-min` in the lane state. Pilot overhead (`lipok.py usage` over the transcripts, relative cost): Manager 8%, the worker's own turns 7%, executors and review 85% — coordination ≈15%; every task's `final.md` records this breakdown.

**Step A — a pilot on one lane.** The remaining items of a real task form one chunk; the worker leads
them itself via subagents per section 5; the Manager acts per sections 3 and 8. Needed: the worker-lead role
(`references/worker.md` → the chunk loop + `references/item.md` for the executor), `lipok.py verify-pr`
and `lipok.py stall-check`, the profile fields `progress_window_h` and `max_attempts`, the supervision of section 3a,
the messages of section 6, a chunk-level `lanes/state.md`.
**Done when:** the chunk is closed; over the whole chunk the Manager read not a single CI log or diff; at least one
course correction or `verify-pr` check fired for a real reason; every worker failure during the pilot (dead
turn, silence, limit — whatever happens) was noticed by supervision, not by the user; P1–P4 got an answer.

**Step B, the cut — written 2026-11-14:** `references/decomposition.md` (the scout, seams and contracts, chunks `contract`/`foundation`/`impl`/`assembly`, hot files have a single owner, a cut file with `AREA`/`AFTER`, handing out by waves) and `lipok.py cut-check` — mechanically checks that chunks of one wave share no file (via `git ls-files` and via globs), that `AFTER` has no cycles and that an item is in one chunk; prints `CUT OK lanes=<n>` (the width of the widest wave, no more than `max_lanes`). The "one lane for now" ban was lifted in `manager.md` and `/lipok-task`. Not yet verified live.

**Step B — two lanes.** A real "contract + two sides" pair (for example, the backend and frontend of one
feature): `references/decomposition.md`, the scout, `lane_env` per lane, the merge queue in batches,
`NOTE` between lanes, review of the contract chunk and of the assembly.
**Done when:** the contract was merged first; two lanes closed their chunks in parallel; the assembly wired them together,
the feature is enabled; the three v5 metrics (section 22) are in `final.md`.

**Step C — tuning by metrics:** chunk size, number of lanes (up to three), PR grouping.

## 12. Deferred

- **The three-level scheme (v5, sections 3, 9, 10, 27).** Return to it only if at step B
  the Manager cannot hold three lanes even with per-chunk reports. At that point also choose between the
  "start" phrase and option "b".
- **A pipeline inside a lane (v5, section 10).** Return to it if at step B lanes noticeably wait for merges.
- **The "Hierarchy" mod (v5, section 25)** — after step B; in the flat scheme it is a list of lanes and chunks.

## 13. Open questions

- How many items in a chunk a worker can hold (P4) — this determines whether a new worker is needed for
  each chunk.
- Whether a `REDIRECT` is needed in the middle of an item (currently — only between items and on the chunk plan).
- Confirm or reject the Manager's autonomy (v5, section 13): in v6 it matters more, because
  the Manager corrects the course more often.
