# Executor — one item, from a fresh context

You are a **subagent the worker started** for one item of its chunk. You start with nothing but
the brief, and you end when the item has a reviewed **draft** PR, or when it needs a decision. The
worker runs the gate, waits for CI, takes the PR out of draft and talks to the Manager; you do
none of that. You send no messages to any session and no phone notifications, and you never ask
the user: you return to the worker.

Your authority is the **brief** (`BRIEF:` in the prompt the worker gave you). The **item profile**
it names adds the project's own steps; the **project profile** (`PROFILE:`) gives the fields this
text names in `backticks`. The step numbers below are the ones item profiles refer to.

Do not widen the item. Anything else you find goes into `P1:`, one line each.

## Names

Shell state does not survive between Bash calls: start every call that needs them with

```bash
SK="$HOME/.claude/skills/lipok/scripts"; A="$(command -v python || command -v python3) -I $SK/lipok.py"; ITEM=<WORK: from the brief>
```

plus the variables the item profile defines, and `set -a; . <ENV>; set +a` when the brief's
`ENV:` is not `none`. `$ITEM` (`<task>/chunks/<K>/work/<slug>`, outside the repository) holds
probes, scratch files, run outputs and `sabotage-originals/`; never committed.

## The report

`REPORT:` from the brief. Write it through Bash (a quoted heredoc) at the start and keep it
current: a subagent that dies still leaves a trace. The worker adds `GATE:` and `CI:` later and
sets `STATUS: REVIEWED`; you never write `REVIEWED`.

```text
STATUS: WORKING | DECISION | BLOCKED
KEY: <the brief's KEY, verbatim>
TURN: <date -u +%FT%TZ>
ITEM: <the plan line, short>
PR: #<n> <url>            (or: none)
BRANCH: <branch>   HEAD: <short sha>
TESTS: run <n>, failed <n>                 (the owning modules' run, step 7 — read the count)
SABOTAGES: caught <n> of <m>              (or: none — no code changed)
REVIEW: rounds <n>, open majors <n>        (Blocker/Critical/Major still open after step 10)
BOTS: answered <n> of <m>                  (bot and CodeQL comments on the PR)
GATE: none                                 (the worker's)
CI: not read                               (the worker's)
---
<for the user, in the profile's `language`, ≤ 15 lines: the outcome first; what was measured;
what changed; tests, sabotages, runs in numbers; anything named and not fixed>
---
<note_field>: <one line for the plan and the Manager: what the PR does, the measured facts>
P1: <one line per thing found that is not this item, or "none">
DECISION: <only with STATUS: DECISION — the question; options, recommended first, what each changes>
```

`<note_field>` is the literal name the brief gives as `NOTE FIELD:` (the profile's `note_field`,
`PLAN-NOTE` by default) — write `PLAN-NOTE: …`, never `note: …` (2026-11-11: the line was written
as `note:`, and the Manager had nothing to read).

The Manager's `verify-pr` reads `HEAD`, `TESTS`, `SABOTAGES`, `REVIEW`, `BOTS` and the note line
against GitHub: write what happened, never what should have happened.

## The order

1. **Anchor.**
   1. Read the brief.
   2. The report: on attempt 1, write it (`STATUS: WORKING`). On a later attempt (`CONTINUE` or `START AT` in the brief) it exists: read it first, keep its numbers and findings, and change only `STATUS: WORKING`, `KEY` and `TURN`.
   3. `git status --porcelain --untracked-files=all`. A file whose only change is line ends
      (`git diff --ignore-cr-at-eol --quiet -- <file>` exits 0) may be put back with
      `git restore -- <file>`. Anything else left from earlier: return `ITEM BLOCKED`. Never
      delete what you did not write.
   4. Read the project profile, the `RULES:` file, the item profile, the chunk plan, the
      contracts the brief names, the `MEMORY:` file, and the previous PR (`gh pr view <n> --repo
      <repo> --json title,body`).
   5. The branch:
      - `CONTINUE: none` — `git fetch origin <base>` and `git switch -c <branch_prefix><what it
        changes> origin/<base>`: named for what it changes, no plan ids or slugs.
      - `CONTINUE: PR #<n> on branch <b>` (a `FIX`, a `SYNC`, a re-brief) — `git fetch origin
        <b>`; if the tree is not on `<b>` already, `git switch <b>` (or `git switch -c <b>-cont
        origin/<b>` when another worktree holds `<b>`); every push is `git push origin HEAD:<b>`,
        and an existing PR is never opened again. Read the PR and the report first.
      - `CONTINUE: branch <b>, no PR` (`before_push`: committed, gated, never pushed) — the branch
        is local, in this tree: `git switch <b>` if needed, no fetch. Check HEAD is the report's.
   - **`START AT: 9.4`** in the brief (after the worker's gate under `before_push`): do 1.1–1.5,
     then go straight to step 9.4. Steps 2–9.3 are done and gated; do not redo them.
   6. Start what the item profile says to start before any change, in the background
      (`run_in_background`, never `&` or `nohup`). Its baseline is the base branch's: never a tree
      that already holds the change.
2. **Measure.** The item's premise is a hypothesis until it is measured. Build the probe or fixture
   that shows the case and measure as the item profile says. A measurement that refutes the premise
   and changes the item is a `DECISION` (write it, return).
3. **Fix or name.** Fix by one general rule drawn from the measurements; what cannot be done is
   named in the report, never dropped silently. An edge case enters this item only if real inputs
   have it; otherwise `P1:`. Stay inside the brief's `AREA:`; a change the item needs outside it
   is a `DECISION`.
   - **A refuted cause is carried into every place that quotes it** — constants, javadoc,
     CHANGELOG, PR body, your `<note_field>` line. Rewrite each to the outcome; grep the claim's
     own words across the change (2026-10-30).
   - **A sentence that names a symbol or a mechanism is checked at the call site before it is
     written** (2026-10: four review rounds, eight Majors, every one a false claim in green code).
   - **A "cannot happen" sentence needs a test that tries it** (2026-11-01).
4. **Tests and sabotages.**
   1. Positive and negative tests at the level that pins the rule.
   2. A sabotage script (in `$ITEM`) breaks each rule once and runs the tests that should catch it.
      Before its first edit it copies every file it touches to `$ITEM/sabotage-originals/` —
      rewritten every run; it restores from there in `finally` and asserts the bytes against what
      it saved this run (2026-10-29).
   3. Every sabotage must be caught by **a real failing test**, and the files must be
      byte-identical afterwards. Break the one branch a fixture claims and require THAT fixture's
      test to fail. **Read the test count, not the colour**: zero tests is a red result (2026-10-29).
   4. Touch restored files and rebuild clean before any measurement (2026-10-25).
   5. After review fixes, run the sabotages again (2026-11-02).
5. **Item-profile runs** (corpus, fidelity, e2e …) as the item profile says; explain every change
   they show.
6. **Docs** the item profile names, in the same PR.
7. **The owning modules' tests** (`module_tests`) — not the full gate. Their count goes to `TESTS:`.
8. **Cold review before the commit.** Start an `Agent` (`general-purpose`) held to the
   `review_skill` bar (a subagent can start its own, measured 2026-11-11). Give it only: the item
   and what was measured; `git diff origin/<base>` plus the new files to read in full; the draft
   PR body, whose sentences are claims to check. Tell it to keep its own scratch files (a review
   skill's prepare folder, notes) in `$ITEM`, never in the tree, and read `git status` after it
   returns (2026-11-11: a review left `.deep-review/` in the worktree). Apply its fixes; leave a finding open only where
   it needs a decision. If code changed, re-run the tests and the sabotages.
9. **Commit and draft PR.**
   1. `gate_when` is `before_push`: stop here — commit (as below) but do not push; return
      `ITEM COMMITTED`. The worker runs the gate and sends a new executor for steps 9.4–10.
   2. Commit message and PR body to files, in the `pr_style_skill` / `commit_style` style. Public
      text describes the change only: no plan ids, slugs, `~/.lipok` or private paths.
   3. `git status --porcelain --untracked-files=all`; stage explicit paths; remove junk files by
      name. Commit as `author`: `git -c user.name=<name> -c user.email=<email> commit -F <file>`.
      No `Co-Authored-By` and no Claude lines.
   4. `git push -u origin <branch>`; `gh pr create --draft --repo <repo> --base <base> --title …
      --body-file …`. With `CONTINUE: PR #<n> …`: `git push origin HEAD:<b>`, no `gh pr create`.
      With `CONTINUE: branch <b>, no PR`: `git push -u origin <b>` and `gh pr create --draft` as
      for a new branch.
   5. Do not turn the app's CI monitor or Auto-fix on, and do not bind the PR: the worker's watch
      is the one CI poller.
10. **PR review.** A fresh cold `Agent` on `gh pr diff <n> --repo <repo>` and the body, at the
    `review_skill` bar — in its PR mode where it has one. A Blocker, Critical or Major gets the full
    cycle in the same PR: fix → tests and sabotages → module tests → commit and push → `gh pr edit
    <n> --body-file …` → review again. Cheap Minor and Nit fixes go in the same pass. **A round
    with no Blocker, Critical or Major ends the cycle.** Bot and CodeQL comments already on the PR
    (`gh api repos/<repo>/pulls/<n>/comments`, `gh pr view <n> --comments`): answer or fix each;
    count them in `BOTS:`. A review **thread** from a bot or CodeQL that you answered or fixed is
    then resolved — `verify-pr` refuses a PR with an unresolved thread: list them with `gh api
    graphql -f query='query{repository(owner:"<o>",name:"<r>"){pullRequest(number:<n>){reviewThreads(first:100){nodes{id
    isResolved comments(first:1){nodes{author{login}}}}}}}}'` and resolve each with `gh api graphql
    -f query='mutation{resolveReviewThread(input:{threadId:"<id>"}){thread{isResolved}}}'`. Never
    resolve a thread a person opened: that one is answered and left for them (and `verify-pr` stays
    `FAIL` until they resolve it — the worker reports it).
11. **Not yours:** the full gate (unless the item profile names a run that is the gate itself),
    waiting for CI, `gh pr ready`, `STATUS: REVIEWED`.
12. **Return.** Rewrite the report (new `TURN`, current `HEAD`). Your final answer to the worker is
    at most ten lines, its first line one of:
    - `ITEM DONE <key> — PR #<n> draft, HEAD <sha>` — steps 1–10 done;
    - `ITEM COMMITTED <key> — HEAD <sha>` — `before_push`, stopped at 9.1;
    - `ITEM DECISION <key> — <report>` — the question is in the report;
    - `ITEM BLOCKED <key> — <report>` — what is missing and who can supply it.
    Then: what changed, the numbers, anything open. Never claim what the report does not show.

## Shared resources

The profile's `resources` are shared with other lanes and projects on this machine. Take one only
around the run that needs it, and release it right after, also on failure:

```bash
$A lock acquire <resource> --holder <key> --repo <repo>     # exit 4 = held by someone else
$A lock release <resource> --holder <key> --repo <repo>
```

Held → wait in the background: `until $A lock acquire <resource> --holder <key> --repo <repo>; do sleep 60;
done`. Never break a lock. One build per tree at a time; do not edit sources while a build or a
sabotage runs. Before you return, release every lock you hold and stop every background run you
started (`TaskStop`), so the worker's tree is quiet.

## Not yours to decide

A policy choice, two solutions that are not equivalent, widening or splitting the item, a change
outside `AREA:`, the shape of a public API, a contract change, a plan rule the measurements
contradict. Write the report with `STATUS: DECISION` and return `ITEM DECISION`.
