# Manager

The one session the user talks to, and the task's interface: it knows the project, the plan, the
decisions and where every lane stands, and it keeps that picture for the whole task by reading
outcomes, not steps. It cuts the task into chunks, hands them to workers, checks each chunk plan
against the whole picture, corrects a lane's course, verifies what workers call ready, carries
decisions, keeps the merge queue, watches that workers are alive, and is the only sender of phone
notifications. It never does item work. Lanes: `references/lane.md`.

**Every event starts with reading state**: `task.json` and every `lanes/*/state.md` of the active
task. Your context may have been compacted; the files have not.

## What the Manager writes

| File | Writer |
|---|---|
| `task.json` (`lipok.py task-set`) | Manager |
| `lanes/<N>/state.md` (`lipok.py chunk`, `set`) | Manager |
| the task's plan (`crlf-replace.py` when it has CRLF line ends) | Manager |
| `chunks/<K>/brief.md`, `chunks/<K>/notes/*` | Manager (the worker adds `notes/decision-<n>.md` at the plan stage) |
| `decisions/DR-NNN.md` | Manager, append only |
| `reviews/GR-NNN.md` | the chunk reviewer the Manager starts |
| `chunks/<K>/plan.md`, `lane-state.md`, `briefs/`, `done.md` | the worker |
| `chunks/<K>/reports/*` | the executor, then the worker |

## The cut

How to cut, the cut file and the waves: `references/decomposition.md` — read it before cutting.
Chunks of one wave never share a file; run as many lanes as `cut-check` prints.

## Deploying lanes

On the user's turn only (`lane.md`, "Start the worker"). For each lane `N` of
`task.json`'s `lanes`:
1. If the profile has `lane_env`: `lipok.py lane-env --repo <repo> --lane <N>`; if it has
   `lane_setup`, run it with `{N}`.
2. Start the worker (`lane.md`, "Start the worker").
3. On its line `LANE <N> <folder>`, hand out its first chunk (`lane.md`).

## Decisions

From a worker's `DECISION` (its report holds the question, the options, the recommended one first,
and what each changes), or from your own reading of a plan or a line that needs the user:
1. `PushNotification` "Decision needed: <item or chunk> — answer in the main session".
2. Ask the user here with `AskUserQuestion`, the options, the recommended one first.
3. **Write the decision before sending it**: `decisions/DR-NNN.md` with the date, the question,
   the key and report, the options, the user's words verbatim, what it changes in the plan. A plan
   change bumps `plan_version` (`task-set`).
4. The answer picks among options inside the chunk's scope → `DECISION <key> — <DR path>`, the
   user's words quoted in the DR: "<user>: "…"". It changes the scope or the cut → a new chunk
   brief (or a `REDIRECT` with a note naming the DR) and, if other lanes are touched, a `NOTE` to
   each. Either way: `set chunk-status=WORKING`, `$A line $L ANSWERED` (closes the decision wait), re-arm the stall watch (it stopped at `STALL IDLE`), record the decision and its date in the plan.

Not the worker's and not yours: the list in SKILL.md, "Rules". Yours alone: `GO` on a plan that fits, `REDIRECT` that keeps a lane
inside its scope, the order of chunks when the plan does not fix it, handing the next chunk to a
free lane.

## Telling the user

- `PushNotification` only for: a PR READY (verified); a decision needed; something blocked; a
  supervision alarm (`lane.md`, "Supervision"); the system stopped (a session to replace, a limit).
- A chunk plan accepted, a chunk done: three to five lines in the chat; no notification.

## The merge queue

READY PRs in the order to merge: dependencies first, then PRs that touch the same files back to
back (`gh pr view <n> --json files`). With one lane the queue is the one PR. Over `max_ready_prs` READY at once (default: `max_lanes`): tell the user the queue is full; nothing changes for the workers — each lane already waits for its own PR's merge before its next item.

## The chunk reviewer

For a contract chunk (before its PR merges), the assembly chunk (before the PR that switches the
feature on), and any chunk the user asks for: an `Agent` (`general-purpose`) held to the
`review_skill` bar, given the chunk brief, the chunk's `done.md` when there is one, and the diff of the PRs under review (`gh pr diff <n>` — open or merged), never the worker's reasoning. When: a contract chunk's PR and the assembly PR that switches the feature on are reviewed at their `READY`, before you call them ready to merge; any other chunk the user asks for, at its `CHUNK_DONE`. Its verdict goes to `reviews/GR-NNN.md`;
a finding that needs work becomes a new item only after the user's yes.

## "status"

Read the state and answer in a few lines, one per lane, then what waits on the user:
- lane `N`: alive / turn running / idle since <time> (`get_session`, the lane-state's `turn`);
  the last line from the worker and its time; chunk, item, attempt; PR and `pr-status`;
- waiting on the user: READY PRs in queue order, open decisions;
- the plan's position, if the optional `plan-status` skill is installed (`$(command -v python || command -v python3) ~/.claude/skills/plan-status/plan_status.py <plan>`); otherwise count the plan's `[x]` and `[ ]` lines.

## Pause, resume, stop

- **"pause"** — for each lane: `PAUSE <ck>`; stop both watches (`lane.md`, "Stopping a
  watch") once `PAUSED` comes; `set paused=yes`. A merge that lands while paused is booked on
  "resume".
- **"resume" — Resume.** Also the answer after a restart or sleep, when every watch is gone:
  1. Read `task.json` and every lane's state, and each worker's `lane-state.md`.
  2. `list_sessions` (linked): is each lane's worker still there? A missing one is replaced now —
     this is the user's turn (`lane.md`, "Replace a worker").
  3. For each lane with `pr-status: READY`: `gh pr view` — merged → "When a PR is merged";
     closed → ask; open → `verify-pr` again.
  4. For each lane whose chunk is not `DONE`/`DROPPED`: re-arm the worker watch and the stall
     watch; send `RESUME <key>` with a note "restart: re-arm your watches, check the PR against GitHub, continue from lane-state". `pending` names a timer that is gone → act as on its exit.
  5. `lipok.py lock show`: a lock held by a key of this task whose worker is not running →
     `lock break <resource> --by manager`.
  6. `set paused=no`. Every step is safe to repeat (`booked`, `last-line`).
- **"stop task"** — what "pause" does, and `STOP <key>` to every worker; `lane_teardown` for
  each lane if the profile has it; write `<task>/final.md` (what was merged, what is open,
  decisions, and the three metrics: time from deployment to the last merge, PRs merged, time lanes
  waited on merges or decisions — each lane's `merge-wait-min` and `decision-wait-min`, summed;
  and the token split: `$A usage <task> --manager "$PWD"` — paste its lines as they are);
  `lipok.py task-close`; offer to archive the lane sessions. The task's end after its last
  `CHUNK_DONE` is the same, without the `STOP` lines.
  Archive only on the user's yes. Open PRs stay as they are.
- **"CI ready"** (the user, for an item waiting on a CI artifact) — `RESUME <key>` to its worker
  with the note "CI ready".
- **"next chunk"** — a lane with nothing on it (`chunk-status` `DONE`, `DROPPED` or `none`)
  → hand out the next chunk; otherwise say what each lane is doing.

## "profile"

`$A profile --repo <repo>`: show the fields as a short table. A change the user asks for: say what
it changes, and after their "yes" `$A profile-set --repo <repo> <key>=<value> …` (a number, a list
or an object as JSON: `max_lanes=5`, `required_checks='["test","deploy"]'`). It refuses a change
that would leave the profile invalid. A running task picks up `max_attempts`, `progress_window_h`
and `quiet_window_min` at the next re-arm of its watches; `max_lanes` matters at the next cut.

## When something breaks

| Failure | What to do |
|---|---|
| Worker's turn died, quiet, stalled, looping | `lane.md`, "Supervision" |
| Worker session gone | on the user's turn: `lane.md`, "Replace a worker"; the chunk continues from its files and PR |
| Usage limit (`SESSION LIMIT`) | `lane.md`, "Supervision" — a timer until the reset, then `RESUME`; tell the user "resume" after the reset does the same if the timer is lost |
| A dead worker holds a lock | `lipok.py lock break <resource> --by manager` (logged in `~/.lipok/locks/broken.log`) |
| PR closed without merge | the worker reports `BLOCKED`; ask: reopen, redo, drop |
| Base branch red after a merge | hand out nothing new; tell the user with the failing run; a fix is a new item after their yes |
| This Manager session lost | the user types `/lipok-task` in a new session, which takes the task over (`lipok-task`, step 3). The old workers answer to the old Manager's id from their briefs, and a new session can neither clear them nor claim their trust: tell the user, offer to archive the old lane sessions, and — on their yes, on this user turn — replace every lane's worker (`lane.md`, "Replace a worker") |
