# Project profile

`~/.lipok/projects/<owner>-<repo>/project.json` tells the core everything project-specific. The
core's texts never name a stack; they name these fields. `lipok.py profile --repo <owner/repo>`
prints and checks it: required fields, `author` with name and email, and whole positive numbers
for `quiet_window_min`, `gate_minutes`, `max_lanes`, `max_ready_prs`, and `required_checks` as a
list of names.

## Fields

| Field | Required | Meaning |
|---|---|---|
| `repo` | yes | `owner/name` on GitHub |
| `main_checkout` | yes | the main checkout's absolute path |
| `base_branch` | yes | where every PR goes |
| `gate` | yes | the full local gate command; its last line is `GATE PASS` or `GATE FAIL: <steps>`; `<out>` is the output folder |
| `quiet_window_min` | yes | the worker watch's quiet window, above the longest run (the gate) |
| `gate_minutes` | | how long the gate takes, for the user and the quiet window |
| `gate_when` | | `before_ready` (default: once, on the final tree, before the PR leaves draft) or `before_push` (when CI minutes are capped) |
| `module_tests` | | the owning modules' test commands, by area |
| `author` | yes | `{ "name": …, "email": … }` — the only commit identity |
| `rules_file` | | a markdown file of rules every role reads (hooks, files never staged, folders only the main checkout has); briefs name it as `RULES:` |
| `branch_prefix` | | e.g. `fix/`; the worker adds what the change does |
| `commit_style` | | how commit titles look (e.g. `TASK-NNN: <what>`), or the `pr_style_skill` |
| `review_skill` | | the bar for cold reviews (e.g. a project review skill, or `deep-review:standard`) |
| `pr_style_skill` | | the skill for PR titles and bodies |
| `language` | | the language of reports to the user (default: the language the user writes in) |
| `note_field` | | the report's plan-note field name (default `PLAN-NOTE`) |
| `memory_file` | | the project memory file the Manager updates on a merge |
| `dashboard_html` | | where `plan_status.py --html` writes the plan's dashboard |
| `ask_first` | | kinds of items the Manager asks about before handing out |
| `infra_failures` | | CI failure signs that are not the change's fault (re-run once) |
| `required_checks` | | names of the CI checks every PR must show (e.g. `["test", "deploy-preview"]`); `verify-pr` fails while one is not registered, `wait-pr.sh` says `CI-MISSING` instead of `CI-GREEN` |
| `resources` | | shared, indivisible resources (e.g. `word`); workers lock them with `lipok.py lock` |
| `long_run_process` | | a hint for finding a long run's process, e.g. `ps -W \| grep java`; it may match other projects, so the run's own output file decides |
| `lane_env` | | per-lane environment templates, `{N}` = the lane number; `"3100+{N}"` adds |
| `lane_setup` / `lane_teardown` | | commands run per lane at deployment / at the end, with `{N}` |
| `item_profiles` | | `{ "<name>": "<path to the item profile>" }` |
| `max_lanes`, `max_ready_prs` | | how many lanes at once; how many READY PRs may wait on the user. `max_lanes` defaults to 1 and `max_ready_prs` to `max_lanes`: without `max_lanes`, `cut-check` caps every cut at one lane (it prints a `NOTE`) |
| `progress_window_h` | | the stall watch: hours without a progress line from the worker (`PLAN`, `READY`, `MERGED`, `CHUNK_DONE`; an `ALIVE` does not count) before the Manager asks (default 3) |
| `max_attempts` | | the stall watch: attempts on one item before it counts as a loop (default 3) |
| `sabotages` | | `false` turns off `verify-pr`'s demand for caught sabotages on code changes (default `true`) |

## Item profile

A markdown file that tells the executor (and, for CI and pauses, the worker) what an item *of this
kind* adds to `item.md` and `worker.md`. Sections, each optional; the step numbers are
`item.md`'s unless named otherwise:

- **Scripts** — what exists, where, its CLI and its last-line contract.
- **Before any change** (step 1.6) — baseline runs to start.
- **Measure** (step 2) — how the premise is measured.
- **Fix** (step 3) — the project's rules that bind a fix.
- **Runs** (step 5) — runs after the fix and how to read their diff.
- **Docs** (step 6) — what documentation the same PR updates.
- **Before ready** (worker step 4.3) — artifacts to take from CI before the PR leaves draft.
- **Pause cleanup** (worker step 6) — what to remove or restore on a pause.
- **Rules** — hard-won rules for items of this kind, with their dates. Rules for every item go in
  the profile's `rules_file`.

Keep the core's rules out of it: an item profile adds, it never repeats or overrides `item.md` or
`worker.md`.
