# Lane — the Manager's side

The Manager leads each lane at the level of **chunks**: it starts the worker, hands it a chunk,
checks its plan against the whole picture, verifies what it calls ready, carries decisions and
watches that it is alive and moving. The items inside the chunk are the worker's
(`references/worker.md`). Design: `docs/architecture.md` of the Lipok repository (github.com/DemchaAV/Lipok), sections 3, 3a, 5–8.

## Names

Shell state does not survive between Bash calls: start every call that needs them with

```bash
SK="$HOME/.claude/skills/lipok/scripts"; A="$(command -v python || command -v python3) -I $SK/lipok.py"; L=<task>/lanes/<N>/state.md
```

- `<task>` — the task folder (`$A task-active --repo <repo>`); `<tid>` its id; `<N>` the lane.
- `<ck>` — the chunk key `<tid>/L<N>/K<n>`; `<key>` — an item key `<ck>/<slug>#<attempt>`.
- `$L` — **your** lane state, chunk level: `worker`, `worker-dir`, `branch-name`, `chunk`,
  `chunk-key`, `chunk-status` (`none`, `BRIEFED`, `PLAN`, `WORKING`, `DECISION`, `BLOCKED`,
  `PAUSED`, `DONE`, `DROPPED`), `lane-state` (the worker's file), `pr`, `pr-status`, `booked`,
  `worker-watch`, `stall-watch`, `pending`, `last-line` (any line from the worker),
  `progress-line` (the last `PLAN`, `READY`, `MERGED` or `CHUNK_DONE` — what the stall watch
  measures), `loop-ack` (`<item key>` whose loop the user let go on), `death-turn` (the item key
  of the last dead turn), `paused`, `wait-since` / `wait-kind` (`merge` from `VERIFY OK` to the
  merge, `decision` from a `DECISION`/`BLOCKED` to your answer), `merge-wait-min`,
  `decision-wait-min` (the minutes the lane has waited, summed — the task's metrics). Write it
  only with `$A chunk`, `$A line`, `$A verify-pr --lane`, `$A book` and `$A set`, with `--expect`
  where another event could have moved the field. Never stamp `last-line` or `progress-line` by
  hand: `$A line` does it (2026-11-12: a hand-typed stamp was forgotten on a `MERGED`, and the
  stall watch raised a false `STALL QUIET`).
- The worker's `lane-state.md` is **its** file: you read fields from it (`$A get`), never write it.
- **Timer** — a background `sleep <seconds>` (`run_in_background`) whose exit wakes you.

## What you read — and what you don't

| Read | Don't |
|---|---|
| chunk brief and `done.md`; the chunk `plan.md` once per `PLAN`; a report's `<note_field>` line; one line of `verify-pr`; the last line of a watch; the report's `DECISION:` block | diffs, CI logs, whole reports (unless a line raises a doubt or the item is `DECISION`/`BLOCKED`), the worker's transcript |

## Lines to the worker

One line by `local_…` id: `<TYPE> <key> — <path>`. Anything more goes into a note file,
`<task>/chunks/<K>/notes/<name>.md`, and the line points at it.

| Type | When | Path |
|---|---|---|
| `CHUNK <ck>` | a new chunk (preceded by "Use the `lipok` skill, role worker.") | the chunk brief |
| `GO <ck>` | the plan fits the whole picture | — |
| `REDIRECT <key or ck>` | the plan or an item goes the wrong way; a `VERIFY FAIL` | a note: what is wrong against the whole picture, how it should go |
| `NOTE <key or ck>` | a fact from another lane or from the user that touches this chunk | a note |
| `DECISION <key>` | the user's answer inside the chunk's scope | the DR |
| `SYNC <key>` | the base moved under its open PR and the files overlap (another lane's merge) | — |
| `PING <key>` | quiet or stalled: one line `ALIVE`, please | — |
| `PAUSE`, `RESUME`, `STOP` | the user said so; after a dead turn (`RESUME`) | a note for `RESUME` |

## Start the worker (deployment only — on a turn the user began)

The app refuses to start a session on a turn an automated event began, so workers are started
when the task is deployed and kept for the whole task. A worker missing later can only be
replaced on the user's turn: propose a card and send a `PushNotification`.

`start_session` with:
- `initiation: "user_asked"`, `context: "fresh"`, `use_worktree: true`,
  `source_branch: <base_branch>`;
- `branch_name: lipok-<tid>-l<N>` (a replacement: `lipok-<tid>-l<N>-r<k>`) — the worktree
  folder becomes `<branch_name>-<6 hex>`, known only after the worker's first turn (2026-11-01);
- `cwd` only when the project is not this session's folder: Windows form; the app may show a
  **Trust repository** button the user must click (2026-11-02, 2026-11-11);
- `name` = the branch name, `title: "<task title> — lane <N>"`;
- `prompt`: "You are the worker of lane <N> of Lipok task <tid> (project <repo>). Use the
  `lipok` skill, role worker. The Manager is `<Manager local id>`. First turn: send the Manager
  the line `LANE <N> <folder>`, where folder is `(pwd -W 2>/dev/null || pwd) | sed 's/[^A-Za-z0-9]/-/g'` (check that
  `~/.claude/projects/<folder>` exists), and end the turn. Chunks then arrive as messages
  `CHUNK <key> — <brief path>`.";
- `background`: the task's goal in two sentences and the decisions it rests on, with dates.

Do not pass a permission mode: the worker inherits yours, and sessions in one mode get each
other's messages without approval. Then `$A set $L worker=<id> branch-name=<branch_name>`; on
`LANE <N> <folder>`, check `ls -d ~/.claude/projects/<folder>` and `$A set $L worker-dir=<folder>`.

## Hand out a chunk

1. **Pick it** from the task's cut (`<task>/decomposition/cut.md`; `decomposition.md`, "Handing out by waves"): the lowest chunk not yet handed out whose `AFTER` chunks are all `DONE`. A chunk is handed out when `<task>/chunks/<K>/brief.md` exists, and `DONE` when `<task>/chunks/<K>/done.md` exists. None → the lane waits. `paused: yes` — hand nothing out.
2. `$A chunk $L --chunk K<n>` → `BRIEF`, `PLAN`, `LANE-STATE`, `CHUNK-KEY`.
3. **Mark** the chunk's items `[~]` in the task's plan with `crlf-replace.py`; rebuild the
   dashboard if the profile has one.
4. **The brief** to `BRIEF` (a quoted heredoc):

   ```text
   Use the `lipok` skill, role worker.
   CHUNK: <ck>
   TITLE: <what the chunk delivers, one line>
   ITEMS:
   <the plan lines, verbatim, one per line>
   AREA: <the cut's AREA for this chunk, verbatim>
   CONTRACTS: <ids and paths it reads; or none>
   LANE-STATE: <LANE-STATE path>
   MANAGER: <your local id>
   PROFILE: <project.json, absolute>   RULES: <rules_file or none>
   ITEM PROFILE: <path or none>        ENV: <task>/lanes/<N>/env (or none)
   PLAN: <the task's plan> — read: <the sections that hold these items>
   MEMORY: <memory_file or none>
   REPO: <owner/repo>   BASE: <base_branch>   MAIN CHECKOUT: <main_checkout>
   PREVIOUS PR: #<n> (or none)
   KNOWN: <decisions with dates; facts from other chunks; what the plan records>
   DONE WHEN: <the chunk's acceptance, from the plan>
   ```

   The brief is the worker's authority for the chunk. Never put into it a claim that the user
   allowed something they did not say in chat.
5. **A fresh context for a later chunk** (not for the first: the session is new). Optional: the
   worker keeps its state in files and its items run in fresh executors. To clear it anyway, stop
   your worker watch first, then `clear_session`. A reply "classifier gave no verdict … a hook
   changed this call's input" is not a refusal: repeat the call once with exactly the quoted input,
   alone in that response (2026-11-10, 2026-11-11). Refused after that (2026-11-10, a worktree
   worker) — go on without the clear and add to the brief, before `CHUNK:`, "The previous chunk
   is closed; work only on this one."
6. **Send** "Use the `lipok` skill, role worker. CHUNK <ck> — <brief path>" (`$A chunk` has
   already stamped `last-line` and `progress-line`).
7. **Arm the watches** ("Supervision" below): the worker watch and the stall watch.

## When the worker sends a line

Every line, first: `$A line $L <TYPE> <key or ck>`. It stamps `last-line` (and `progress-line` for
a `PLAN`, `READY`, `MERGED` or `CHUNK_DONE`), clears `death-turn`, opens the decision wait on a
`DECISION` or `BLOCKED`, and does the late check. `LATE …` (exit 4) — the line is already in
`<task>/lanes/<N>/events.log`; do nothing else with it. The late check it does:
- a chunk line (`PLAN`, `CHUNK_DONE`, a `DECISION` or `BLOCKED` with a chunk key): its key must be
  `chunk-key`;
- `MERGED`: its chunk must be `chunk-key` only — the worker moves to the next item in the same turn, so the lane-state's `key` has already changed; `$A book` then confirms the merge on GitHub;
- any other item line (`READY`, `DECISION`, `BLOCKED`, `ALIVE`, `PAUSED`): its key must be the
  lane-state's `key`.

- **`LANE <N> <folder>`** — "Start the worker".
- **`PLAN <ck> — <plan.md>`** — `$A set $L chunk-status=PLAN`; read the plan once. Check it against the whole picture: the other
  chunks' areas and plans, the contracts, the DRs, the task's acceptance, what the plan records.
  - It fits → `GO <ck>`; `$A set $L chunk-status=WORKING`; tell the user in two or three lines
    what the chunk will do, in what order.
  - It goes the wrong way and the fix stays inside the chunk's scope → a note, `REDIRECT <ck> —
    <note>`. It needs a change of scope, a contract or the cut → `manager.md`, "Decisions".
- **`READY <key> — <report>`** — `$A verify-pr <n> --repo <repo> --report <report> --area
  "<the brief's AREA>" --lane $L` (it sets `pr`, `pr-status` and the merge wait itself).
  - `VERIFY OK` → plan: `[>]` with `= #<n> OPEN
    \`<sha>\`` and the report's `<note_field>` line; read that line against the whole picture (a
    name another chunk expects, a contract, a DR) and send `NOTE`/`REDIRECT` where it clashes;
    the merge queue (`manager.md`); chat: the `<note_field>` line and the PR link;
    `PushNotification` "PR #<n> ready to merge: <one line>; CI green".
  - `VERIFY FAIL` → a note with every failing point; `REDIRECT <key> — <note>`. Never "ready to
    merge" on a `FAIL`. A `required check not registered` point is CI that never started (the
    worker's watch says `CI-MISSING`): the note says so, not "fix the code".
- **`MERGED <key> — <report>`** or the user's "merged" — "When a PR is merged".
- **`DECISION <key> — <report>`** — read the report's `DECISION:` block (a chunk-level
  `DECISION <ck> — <note>` from the plan stage: the note holds it); `$A set $L
  chunk-status=DECISION`; `manager.md`, "Decisions".
- **`BLOCKED <key> — <report>`** — read the report's user block (or the chunk note); `$A set $L chunk-status=BLOCKED`; post it; `PushNotification` "Blocked: <item>"; ask the user. **The answer** goes back the way a decision does (`manager.md`, "Decisions", step 3–4): a DR when it decides something; `RESUME <key> — <note with the answer>` (or `DECISION <key> — <DR>`); `$A set $L chunk-status=WORKING`; `$A line $L ANSWERED`; re-arm the stall watch. The answer is to drop it: for an item, `REDIRECT <key> — <note: drop this item, mark it dropped in plan.md, go on with the next>`; for the chunk, `STOP <ck>` and `$A set $L chunk-status=DROPPED`.
- **`PAUSED`** — one chat line with what it stopped.
- **`ALIVE <key> — <text>`** — the answer to `PING`: "Supervision".
- **`CHUNK_DONE <ck> — <done.md>`** — read `done.md`; `$A set $L chunk-status=DONE`; stop the
  stall watch, and the worker watch too unless the next chunk goes out now; tell the user in three to five lines (what was done, PRs, decisions, `P1:` found);
  a contract or assembly chunk, or a chunk the user asked to review: the chunk reviewer
  (`manager.md`); then the next chunk, or the task's end.

## When a PR is merged

On the worker's `MERGED` line, or the user's "merged".

1. `$A book $L <n> --repo <repo>` — it confirms the merge on GitHub and books it in `$L` (`booked`,
   `pr=none`, `pr-status=none`, the merge wait). `ALREADY BOOKED` → stop. `NOT MERGED` → the line
   was wrong; check GitHub, tell the user, stop.
2. Plan: the item's `[>]` — or `[~]`, if the user merged before READY — → `[x]` with `MERGED <date>
   \`<merge sha>\`` from the `BOOKED` line; a stage whose last step is done → `[x]`.
3. Memory: the `memory_file` and its line in `MEMORY.md` beside it.
4. Dashboard: rebuild and send; one chat line "#<n> merged".
5. On "merged" before the worker's line: send nothing — its own watch sees the merge. If the worker
   is gone or its watch is gone (after a restart), `RESUME <key>` with a note "#<n> merged".
6. Other lanes with an open PR whose files overlap this one's (`gh pr view <m> --json files`) →
   `SYNC <their key>` to each.

## Supervision

Nothing the worker does inside a chunk reaches you except its lines, so you watch that it is alive
and moving. Two watches per lane, both `run_in_background`; before arming one into a field, stop
the one the field names ("Stopping a watch").

- **Worker watch:** `bash $SK/watch-session.sh <worker-dir> --quiet-min <quiet_window_min>` →
  `$A set $L worker-watch=<task id>`. It counts the transcripts of the worker's subagents, so an
  executor at work is not quiet.
- **Stall watch:** `$A stall-check $L --repo <repo> --watch` → `$A set $L stall-watch=<task id>`.
  Its line: `STALL QUIET <h>h since <t>` (no progress line — `PLAN`, `READY`, `MERGED`,
  `CHUNK_DONE` — for `progress_window_h`; an `ALIVE` answer is not progress), `STALL LOOP <key>
  attempt=<n>` (an item past its planned attempts plus `max_attempts - 1` retries, or past
  `max_attempts` above `loop-ack`; planned attempts are the batches the chunk plan declares with
  `· attempts: <n>` — check them at `PLAN`), `STALL IDLE` (paused, done, waiting
  on you or the user: `PLAN`, `DECISION`, `BLOCKED`, or a READY PR waiting on the merge),
  `STALL OK after <H>h`.

Check the worker (`get_session`) and its `lane-state.md` before saying anything.

**Waiting is not idling.** The worker is legitimately waiting, and sends nothing upward, while its
lane-state names a live wait: `watch` (its PR watch — CI or the merge; `wait-pr.sh` writes nothing
until it exits) or `gate-run` (the gate, whose output file grows). A worker that is not running, names no wait, holds an item that is not `MERGED`/`REVIEWED`, while its chunk is `WORKING`, has stopped without telling anyone: that is the **silent idle**. A lane that waits on you or the user (`chunk-status` `PLAN`, `DECISION`, `BLOCKED`, or `pr-status: READY`) is waiting, not idle.

| Watch line | What to do |
|---|---|
| `SESSION LIMIT <m>m <text>` | a usage limit, not a dead turn; you are limited too. A **timer** until the reset the text names plus 5 minutes (60 minutes if none), `$A set $L pending="limit <timer id>"`, one `PushNotification` with the reset time. On the timer: `RESUME <key>` with a note "limit lifted, continue"; re-arm; `pending=none` |
| `SESSION ERROR <m>m <text>` | the turn died on the model. `death-turn` equals the lane-state's `key` (it died on this item before, with no line from the worker since — every line resets `death-turn`) → the second death: switch the worker's model (`set_session_model`) and tell the user. Otherwise `$A set $L death-turn=<key>`; `RESUME <key>` with a note: what killed the turn, that it was the model, not the content; re-arm; one chat line |
| `SESSION QUIET <m>m <file>` | facts, not words. `get_session` running → re-arm silently. The lane waits on you or the user (`chunk-status` `PLAN`, `DECISION`, `BLOCKED`, or `pr-status: READY`) → re-arm silently. The lane-state names a live wait (`watch`, or `gate-run` whose output still grows), or a lock it waits for (`$A lock show`) → re-arm silently. A **silent idle** (above) → `RESUME <key>` "report and a line up, please"; the second in a row → tell the user the worker is losing the protocol. Anything else → `PING <key>`; re-arm |
| `SESSION OK after 12h` | re-arm silently |
| `SESSION GONE`, `ERROR no such transcript folder`, `ERROR no transcript in` | `get_session`. Gone → "Replace a worker". There → `RESUME` with a note asking for one line `LANE <N> <folder>`, set `worker-dir` from the answer, re-arm |
| `STALL QUIET` | `PING <key>`; re-arm the stall watch. No `ALIVE` before the next stall line → as a dead turn (`RESUME`), and tell the user |
| `ALIVE` answer | read it against the facts above. Moving → re-arm. The same fix again and again, or work outside the chunk → `REDIRECT` or a decision for the user |
| `STALL LOOP <key> attempt=<n>` | the item goes round in circles: `PAUSE <key>`, read the report, tell the user what was tried, `PushNotification`; the next step is the user's. If they say go on: `$A set $L loop-ack=<key>` (the key with its attempt), `RESUME`, re-arm — the next alarm comes `max_attempts` attempts later |
| `STALL IDLE` | `$A set $L stall-watch=none`; re-arm when the chunk is `WORKING` again or the READY PR is merged (after `$A book`) |
| `STALL OK after <H>h` | re-arm silently |

`PushNotification` from supervision only for: a worker gone; a second death at one step; a usage
limit; a loop; a worker that does not answer `PING`.

## Stopping a watch

`TaskStop` the task id the state field names. Then `ps -ef | grep 'skills/lipok/scripts/'` and
kill a survivor **by its own PID**, only one whose arguments are this lane's (`worker-dir`, or
`$L` for the stall watch): other lanes and projects run the same scripts (2026-11-02). Set the
field to `none`.

## Replace a worker

When the worker session is gone, or was archived. On the user's turn only.

1. `start_session` as in "Start the worker", with `branch_name: lipok-<tid>-l<N>-r<k>`.
2. On its `LANE` line: `$A set $L worker=… worker-dir=… branch-name=…`.
3. Send the chunk's brief again with a line before `CHUNK:` — "You replace a worker that is gone.
   The chunk's state is in LANE-STATE and plan.md; the open PR is #<n> on branch <b> (or: none).
   Continue from there." The worker's open item continues with `$A bump` and an executor with
   `CONTINUE`. Uncommitted work in the old worktree is lost: tell the user.
4. Arm both watches. Offer to archive the old worker; archive only on the user's yes.
