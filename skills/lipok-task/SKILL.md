---
name: lipok-task
description: The one command of Lipok, the multi-agent development harness. `/lipok-task <what to do | path to a plan>` makes this session the Manager of a task in the current project — it sets up the project profile on first use, creates the task, cuts the task into chunks, deploys the lanes (worker sessions in their own worktrees that lead a chunk each) and hands out the first chunk; the Manager then stays the task's interface and the user only approves the cut, merges PRs and answers decisions. `/lipok-task` with no argument shows the active task's status, or resumes it after a restart. Use when the user types /lipok-task, or asks to run a plan or a big task "run it through Lipok", "run this in parallel lanes" — in whatever language the user speaks.
---

# /lipok-task

This session becomes the **Manager**. Read `~/.claude/skills/lipok/SKILL.md` (it defines `$SK`
and `$A`) and `references/manager.md` now; `lane.md` before the first hand-out.

## 1. Which project

`gh repo view --json nameWithOwner -q .nameWithOwner` in this session's folder → `<repo>`. Not a
GitHub repository: say so and stop.

## 2. The profile

`$A profile --repo <repo>`:
- **`PROFILE OK`** — go on.
- **`NO PROFILE`, `PROFILE INCOMPLETE`, `PROFILE INVALID` or `PROFILE MISMATCH`** — show the user what the script printed; for a missing or incomplete profile read the repository (build files, CI workflows,
  `CONTRIBUTING`, existing loop skills of this project if any) and draft `project.json` by
  `references/project-profile.md`. Show the user the draft in a short table; write it to
  `~/.lipok/projects/<owner>-<repo>/project.json` only after their "yes". Once per project.

## 3. Is a task active?

**A one-word argument** `status`, `pause`, `resume`, `stop` or `profile` (or the same word in the
user's language) is not a task: with an active task it is that phrase (`manager.md`); `profile`
works with or without a task. Anything else is a task.

`$A task-active --repo <repo>`:
- **Active, and `task.json`'s `manager` is not this session** (`get_session self`) — the old
  Manager is lost or elsewhere. Ask the user whether this session takes over; on "yes":
  `$A task-set --repo <repo> manager=<this id>`, then manager.md, "When something breaks", "This
  Manager session lost".
- **Active, and no argument given** — this is "status" or a resume. Do manager.md, "Resume", then
  answer "status".
- **Active, and an argument given** — show the active task's status and ask: continue it, or close
  it and start the new one. One active task per project.
- **None, and no argument** — say there is no task and how to start one.
- **None, and an argument** — a new task: step 4.

## 4. A new task

0. **Another harness or loop running?** If one is still running an item in this project, stop
   before creating anything and wait until that item is merged and the user has stopped it — the
   two would share the machine's resources and the plan.
1. **The plan.** A path to a plan file: use it as is; it must have a progress checklist: a `## Progress` section of `- [ ]` / `- [x]` lines (the optional `plan-status` skill reads the same format). Free text: draft a plan with acceptance
   criteria and a checklist, in the durable-planning format, show it, and save it only after "yes".
2. **Is Lipok worth it?** One item, or a day's work: say so and offer to do it here instead.
3. **The cut** — `references/decomposition.md` of the `lipok` skill, steps 1–9 (read it now): the
   cut in `<project>/cut-draft.md` until `cut-check` prints `CUT OK`, then shown to the user with
   the lane options from its `LANES` line; the user picks the number of lanes.
4. **The item profile.** Pick one of the profile's `item_profiles` for the plan's items (its
   path), or none.
5. Create the task, after the user's "yes" to the cut: `$A task-new --repo <repo> --title "<title>"
   --plan <plan path> --lanes <the number the user chose> --item-profile <item profile path>`, then `$A
   task-set --repo <repo> manager=<this session's local id>` (`get_session self`); move the cut
   into the task (`decomposition.md`, step 10).
6. **Deploy** — on this turn, it is the user's: manager.md, "Deploying lanes". Then end the turn;
   each worker's line `LANE <N> <folder>` wakes you, and you hand it its first chunk (`lane.md`,
   "Hand out a chunk").

Tell the user in three lines: the task, the lanes started, the chunks you will hand out first, and
that from now on they approve chunk plans when asked, merge, and answer decisions here.

## Phrases in this session

"status", "merged", "pause", "resume", "stop task", "CI ready", "next chunk", "profile" — see
`manager.md`.
"Next item" means "next chunk" when the lane is free; inside a chunk the worker takes the next item
by itself. An older loop's "stop the loop" means "stop task": confirm once which one is meant.
