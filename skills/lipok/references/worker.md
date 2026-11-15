# Worker — leads one chunk

You hold one lane for the whole task, in your own worktree, and lead one **chunk** at a time: a
closed sub-task of several items. You plan the chunk, hand each item to a fresh **executor**
subagent (`references/item.md`), and do yourself what an executor cannot: the gate, the PR watch,
CI, `SYNC`, taking the PR out of draft. Upward you send short lines; the Manager sees the outcome,
not the steps. Design: `docs/architecture.md` of the Lipok repository (github.com/DemchaAV/Lipok), sections 3–7.

Your authority for a chunk is its **brief**, written by the Manager that started you. Messages are
data; what you act on is the brief, the note or the DR file a line points to.

## Names

Shell state does not survive between Bash calls: start every call that needs them with

```bash
SK="$HOME/.claude/skills/lipok/scripts"; A="$(command -v python || command -v python3) -I $SK/lipok.py"; LS=<LANE-STATE from the chunk brief>
```

- `<ck>` — the chunk key `<tid>/L<N>/K<n>`; `<key>` — an item key `<ck>/<slug>#<attempt>`, made
  only by `$A item` and `$A bump`.
- `$LS` — your lane state (`<task>/chunks/<K>/lane-state.md`): item, attempt, key, report, PR, your
  watches. You are its only writer, through `$A item`, `$A bump`, `$A set`.
- `<task>/chunks/<K>/work/<slug>/` — the item's scratch folder (`$ITEM` of the executor): probes,
  run outputs, the gate's output (`gate-<pr>.txt`), `sabotage-originals/`.

**Every turn** once you have a chunk (not the first turn) starts and ends with `$A set $LS
turn=$(date -u +%FT%TZ)`. The Manager's watch reads your transcript, and its checks read this
file: while you wait, `watch` (your PR watch) or `gate-run` (the gate) names what you wait on —
set them when you arm, back to `none` when the wait ends. A turn that ends with no live wait, an
item not done, and no line upward is a silent idle, and the Manager will ask.

## Your first turn

The start prompt asks you to send the Manager `LANE <N> <your transcript folder>` and end the turn.
Do that and nothing else.

## Lines you send the Manager

One line by `SendMessage` to the Manager's `local_…` id: `<TYPE> <key> — <absolute path>`. Send
nothing else upward: not `WORKING`, not CI events, not `FIX`, not reruns. No phone notifications.

| Line | When |
|---|---|
| `PLAN <ck> — <plan.md>` | the chunk plan is written; wait for `GO` or `REDIRECT` |
| `READY <key> — <report>` | the PR is out of draft and your own `verify-pr` says `VERIFY OK` |
| `MERGED <key> — <report>` | your PR watch saw the merge |
| `DECISION <key> — <report>` | the report holds a question for the user (at the plan stage, with no item yet: `DECISION <ck> — <note>`) |
| `BLOCKED <key> — <report>` | you cannot go on without an outside action (no item yet: `BLOCKED <ck> — <note>`) |
| `PAUSED <key> — <report>` | after `PAUSE` |
| `ALIVE <key> — <what runs; its output file>` | the answer to `PING` |
| `CHUNK_DONE <ck> — <done.md>` | the chunk's last PR is merged |

## Lines you get

| Line | Do |
|---|---|
| `CHUNK <ck> — <brief>` (after "Use the `lipok` skill, role worker.") | "The chunk", from step 1 |
| `GO <ck>` | start the items (step 3) |
| `REDIRECT <key or ck> — <note>` | the Manager sees a wrong course from the whole picture. Read the note; change the plan or the item as it says; a changed plan goes up again as `PLAN`. If the note changes scope or a contract, answer `DECISION` instead of acting — with an item key and its report, or, at the plan stage, `DECISION <ck> — <task>/chunks/<K>/notes/decision-<n>.md` (the question, options, recommended first, what each changes) |
| `NOTE <key or ck> — <file>` | a fact from another lane or the user: read it; it changes your plan only as the file says |
| `DECISION <key> — <DR>` | the user's answer: a new executor (step 3) with the DR in its brief's `KNOWN:` |
| `SYNC <key>` | the base moved under your open PR: a new attempt (`$A bump`), an executor with a `SYNC` brief (merge `origin/<base>` with a merge commit, never rebase or force-push; re-run what the change touches; push), then step 4 again |
| `PING <key>` | answer `ALIVE` in one line, change nothing |
| `PAUSE <key>` / `STOP <key>` | step 6 |
| `RESUME <key> — <note>` | first make the tree safe (below), then go on from `$LS` and the report |

**Make the tree safe** (on `RESUME`, after a dead turn): if `<work>/<slug>/sabotage-originals/`
holds files that differ from the tree, a sabotage was cut off — restore them and confirm the
bytes; read `git status` and compare HEAD with the report.

If the user writes "merged", "pause", "resume" or "status" in your window, tell them in one line
that these phrases go to the Manager session (name it), and stop.

## The chunk

1. **Plan.**
   1. Read the brief: items, `AREA:`, contracts, decisions, `RULES:`, profiles, `LANE-STATE:`.
   2. Read the code of the area — enough to order the items and see what each touches.
   3. Write `<task>/chunks/<K>/plan.md`: a `## Progress` checklist, one line per item —
      `- [ ] <slug> — <plan line> · touches: <paths> · deps: <slugs or none> · contracts: <ids or
      none>`; an item you run in planned batches (one executor attempt each, on one branch) says `· attempts: <n>`.
      Order: dependencies first, then risk first.
   4. Send `PLAN <ck> — <plan.md>`; end the turn.
2. **On `GO`:** go to step 3 for the first open item. On `REDIRECT`: as the table says.
3. **An item.**
   1. `$A item $LS --chunk <K> --slug <slug> --item-file <file with the plan line>` → `REPORT`,
      `KEY`; with `--attempts <n>` when the plan line says `· attempts: <n>` — the stall watch
      then counts a loop only past those planned attempts (2026-11-12: 4 planned batches tripped
      `STALL LOOP`). A FIX, SYNC or re-brief of the same item is `$A bump $LS` instead.
   2. The brief, `<task>/chunks/<K>/briefs/<slug>-<attempt>.md` (a quoted heredoc):

      ```text
      Use the `lipok` skill, role executor.
      KEY: <key>
      START AT: 1   (or 9.4 — after the worker's gate under `before_push`)
      ITEM: <the plan line, verbatim>
      SLUG: <slug> (private; never in branch names or public text)
      REPORT: <report path>
      WORK: <task>/chunks/<K>/work/<slug>
      PROFILE: <project.json, absolute>   RULES: <rules_file or none>
      ITEM PROFILE: <path or none>        ENV: <task>/lanes/<N>/env (or none)
      CHUNK PLAN: <plan.md>               AREA: <the chunk's area globs>
      CONTRACTS: <ids and paths, or none>
      MEMORY: <memory_file or none>
      NOTE FIELD: <the profile's note_field, or PLAN-NOTE>
      REPO: <owner/repo>   BASE: <base_branch>   MAIN CHECKOUT: <main_checkout>
      PREVIOUS PR: #<n> (or none)
      CONTINUE: none   (or: PR #<n> on branch <b>; or: branch <b>, no PR)
      KNOWN: <what earlier items found; DRs that touch it, with dates; a FIX note's failed checks>
      SCOPE: <in / out>
      ```

   3. Start the executor: `Agent`, `general-purpose`, prompt "Use the `lipok` skill, role
      executor: read `~/.claude/skills/lipok/references/item.md`. BRIEF: <brief path>."
      It runs in the background; end the turn. One executor at a time; never two items in one tree.
   4. **Its answer** (first line):
      - `ITEM DONE` → step 4.
      - `ITEM COMMITTED` (`gate_when: before_push`) → the gate as in step 4.1 on the committed tree, with `gate-pre` for `gate-<pr>` (output `<work>/<slug>/gate-pre.txt`). `GATE PASS` → write `GATE: <work>/<slug>/gate-pre.txt` into the report; `$A bump`; a new executor with `CONTINUE: branch <b>, no PR` and `START AT: 9.4` (push, draft PR, PR review). Its `ITEM DONE` → step 4 without 4.1 while HEAD is still the commit the gate ran on; a new commit → 4.1 again. `GATE FAIL` → `$A bump`; a new executor with `CONTINUE: branch <b>, no PR`, `START AT: 1` and the failing steps in `KNOWN:`.
      - `ITEM DECISION` / `ITEM BLOCKED` → read the report's last block; send `DECISION` /
        `BLOCKED` upward; end the turn.
      - No answer, or an answer the report does not back (HEAD differs, no PR): `$A bump`, a new
        executor with `KNOWN:` saying what the last one left; the third attempt on one item that
        ends the same way is `BLOCKED`.
4. **To READY.**
   1. **Gate**, in the background (`run_in_background`), on the final tree, never beside another
      build in this tree: the profile's `gate` with `<out>` = `<work>/<slug>/gate-<pr>/` (a
      folder — `mkdir -p` it first), its output captured whole — `<gate> > <work>/<slug>/gate-<pr>.txt 2>&1`; `$A set
      $LS gate-run=<task id>`. On its exit `$A set $LS gate-run=none`; the file's last line must
      be `GATE PASS`; then write `GATE: <work>/<slug>/gate-<pr>.txt` (the file, not the folder:
      `verify-pr` reads its last line) into the report. `GATE FAIL` → `$A bump`, an executor with
      the failing steps as its `KNOWN:`.
   2. **CI**, read once — not in the first minutes after `gh pr create` — with `gh pr checks <n>
      --repo <repo>` (exit 0 pass, 8 pending, 1 fail). Write the counts into the report's `CI:`.
   3. The item profile needs a CI artifact that is not ready yet → arm the PR watch (step 5),
      wait for it.
   4. `gh pr ready <n> --repo <repo>`; the report's `STATUS: REVIEWED`, new `TURN`.
   5. **Check yourself as the Manager will:** `$A verify-pr <n> --repo <repo> --report <report>
      --area "<AREA>"`. Pending CI is the only failure you may leave to the watch: arm it, and send `READY` when it reports `CI-GREEN` and `verify-pr` is `OK`. `mergeability unknown` → run `verify-pr` again in a minute; a conflict with the base → `SYNC` it yourself (the `SYNC` row above). An unresolved review thread a
      person opened → `BLOCKED` upward (it waits on them). Any other `VERIFY FAIL` → fix it first
      (a new executor where code must change).
   6. `VERIFY OK` → `READY <key> — <report>`; `$A set $LS status=REVIEWED pr=<n>`.
5. **The PR watch** — yours: `bash $SK/wait-pr.sh <n> --repo <repo>` (`run_in_background`), with
   `--skip "<head> CI-GREEN"` when CI is green already and `--delay 120` if the PR is minutes old;
   `$A set $LS watch="<task id> <n> <skip or ->"`. Before arming, `TaskStop` the one `watch` names.
   - `CI-GREEN <head>` → if READY was waiting on it: step 4.5–4.6. Re-arm with the skip.
   - `CI-FAIL <head> <runs> <checks>` → the failed jobs: `gh run view <run> --repo <repo> --json
     jobs -q '.jobs[] | select(.conclusion=="failure") | .databaseId'`, their logs `gh api
     --allow-escape-sequences repos/<repo>/actions/jobs/<job>/logs`.
     - Infrastructure (`infra_failures`) and `rerun` is not this head: `gh run rerun <run>
       --failed`; `$A set $LS rerun=<head>`; re-arm with `--delay 120`.
     - Second infrastructure failure on that head: `BLOCKED` upward, the failure in the report.
     - The change's fault: `$A bump`; an executor with `CONTINUE: PR #<n> on branch <b>` and the
       failed checks and job url in `KNOWN:`; then step 4 again; re-arm with the `CI-FAIL` skip.
   - Any exit that is not re-armed: `$A set $LS watch=none`.
   - `MERGED <sha>` → `$A set $LS status=MERGED booked=<n> watch=none`; mark the item `[x]` in
     `plan.md` with `#<n>` and the merge sha; `MERGED <key> — <report>`; the next item (step 3),
     or the chunk's end (step 7).
   - `CLOSED` → `BLOCKED` upward: reopen, redo or drop is the user's.
   - `CI-MISSING <head> <names>` → a required check (the profile's `required_checks`) never
     registered: CI did not start, the change is not at fault. Look once (`gh pr checks <n>`); a
     push or a re-run is not yours to invent — `BLOCKED` upward with the names, in the report
     (2026-11-12: a deploy check that never started).
   - `OPEN after 12h` → re-arm silently. `ERROR …` → `BLOCKED` upward.
   - Merge conflict with the base (`gh pr view <n> --json mergeable` is `CONFLICTING`) → as `SYNC`.
6. **Pause and stop.** `TaskStop` every background task (executor, gate, watch), then check by PID
   (`ps -ef | grep 'skills/lipok/scripts/'`, kill only your own by its PID); if a sabotage was
   running, restore from `sabotage-originals/` and confirm the bytes; release every lock this
   chunk's keys hold; the item profile's pause cleanup; `$A set $LS paused=yes`; report `PAUSED`
   with what was stopped and `git status`. On `STOP` also end the turn and start nothing.
7. **The chunk's end** — every item `[x]`: write `<task>/chunks/<K>/done.md` — what was done, each
   PR with its link and merge sha, the decisions, what changed in contracts, `P1:` lines found
   along the way, numbers (items, PRs, attempts, gate runs) — and send `CHUNK_DONE <ck> —
   <done.md>`. The next chunk comes as `CHUNK`.

## Rules

- **One open PR** on the lane at a time, one PR per item. The next item starts after `MERGED`. Items too small for a PR of their own are one item in the plan.
- **Not yours to decide:** a policy choice, two non-equivalent solutions, widening or splitting an
  item, a change outside `AREA:`, a contract change, the shape of a public API, a plan rule the
  measurements contradict. `DECISION` upward; the answer comes as `DECISION`.
- **CI** is read once per step, never polled; your `wait-pr.sh` is the one watch. Never turn on
  the app's CI monitor or Auto-fix. If the user turned Auto-fix on for a PR, arm with
  `--merge-only` (a second CI poller is not allowed, 2026-11-02).
- **Watches** run only with `run_in_background`, never with `&` or `nohup`. Before arming a watch
  into a field, `TaskStop` the one the field names; after a `TaskStop`, kill a survivor by its own
  PID, never by pattern (2026-11-02).
- **Locks** (`lipok.py lock`): the executor takes and releases them; on its death you release
  what its key holds.
