# Decomposition — the cut into parallel chunks

The Manager's most valuable work. Parallel lanes break at the seams between chunks, never inside
one: a bad seam surfaces at assembly and no worker can save it. So the cut runs as many lanes as
the task truly has independent parts — and no more: when the parts overlap, one lane is the right
answer, not a failure.

**The hard rule:** two chunks that may run at the same time never change one file. Chunks may share
files only when one comes `AFTER` the other (its last PR merged first). `lipok.py cut-check`
enforces it mechanically; `verify-pr --area` enforces each chunk's area on every PR.

## Steps

1. **Read** the plan: the items, the acceptance, the constraints, what the plan records.
2. **The scout** — an `Agent` (`Explore`, read-only) on the main checkout. Its report goes to
   `<project>/cut-draft-scout.md` (`<project>` = `$A root --repo <repo>`), under 600 words:
   - modules and layers the plan touches; the seams between them that exist already;
   - **hot files** — the ones several items would touch: central registries (router, route table,
     DI/registration, `index` re-exports, menus), schemas and migrations, `package.json` and
     lockfiles, i18n files, `CHANGELOG`, generated code, snapshots, CI config;
   - shared resources: a database, a port, an emulator, an external account;
   - for each plan item: the files or folders it will likely change.
3. **The seams** between parts that would run in parallel: where they meet (an endpoint, a
   request/response shape, a table, a shared type, an event, a component's props, a route). Each
   seam gets a **contract**: a file in the repository that CI checks from both sides — a schema
   with a test, a types module both sides import, a migration run from scratch. A seam described
   only in a brief is not a contract; without a machine check the two sides may not run in
   parallel. A project with no such check gets it from the first contract chunk.
4. **The chunks**, each one kind:
   - `contract` — fixes the wave's seams: the contract file, generated types or clients, mocks,
     stub endpoints, empty routes, the feature flag; **and every hot-file edit the parallel chunks
     would need** (router entries, registrations, menu items, new dependencies). 1–2 PRs.
   - `foundation` — shared groundwork that is not a seam (a table, a shared component, config).
   - `impl` — one side of one or more seams; changes only its area; reads the contract, works
     against mocks.
   - `assembly` — wires the sides: real backend for the mock, end-to-end tests of the acceptance,
     the flag switched on, docs, the `CHANGELOG`.
   A task with no seams (independent fixes in separate areas) is `impl` chunks with no `AFTER`.
5. **Hot files have one owner.** Each hot file belongs to one chunk — normally the contract (before)
   or the assembly (after); never to two chunks of the same wave. A new dependency an `impl` chunk
   discovers later is a `DECISION` (it lands through the owner), never a quiet lockfile edit — its
   PR would fail `verify-pr --area` anyway.
6. **Write the cut file** (below) to `<project>/cut-draft.md`.
7. **Check it:** `$A cut-check <project>/cut-draft.md --repo <repo>`. It compares the areas against
   the main checkout's files (`git ls-files`) and against each other as globs. `CUT FAIL` → fix the
   cut (narrow an area, move a hot file to its owner, add an `AFTER`) and check again; never hand
   out a cut that fails. Its `LANES` line says what each number of lanes buys — `1 lane: 7 rounds | 3 lanes: 4 rounds |
   5 lanes: 3 rounds (fastest: 5)`: a round is one chunk's run on one lane, and lanes past the
   widest wave buy nothing. `CUT OK lanes=<n>` is that width capped by the profile's `max_lanes`
   (1 when the profile has none); it is a default, not the answer — the user chooses (step 9).
8. **Aim for parallel lanes** — the point of Lipok. A widest wave of 1 or 2 on a task with many
   items means look again: split by module, screen, endpoint or layer, move the shared edits into a
   contract chunk, and check again. **One lane is right only when** the widest wave stays 1; a side of a seam would get fewer than two items
   (too fine — one lane does both); the areas cannot be separated without a contract the project
   cannot check; or the task is a day's work. Say why in one line when you show the cut.
9. **Show the user** and hand out only after their "yes":
   - a table: chunk, kind, wave, `AFTER`, area, items, acceptance;
   - each seam: the contract file and the CI check that holds it;
      - **the lanes — the user's choice.** Ask with `AskUserQuestion`: the fastest option first (the
     `LANES` width), then one or two between, then 1 lane, each with its rounds from the `LANES`
     line. Say what more lanes cost: the total tokens stay about the same, but the usage limit
     burns that many times faster, and every lane brings PRs to merge — past about five lanes the
     user's merging is the limit. Shared `RESOURCES` queue on their lock whatever the number. A
     choice above the profile's `max_lanes` is fine for this task; offer to raise the profile's
     too (`$A profile-set --repo <repo> max_lanes=<n>`);
   - the first wave's hand-out (chunk → lane);
   - what stays sequential and why (the hot files and their owners).
10. **After "yes"** and `task-new … --lanes <the user's number>`, move the files into the task:
    `<project>/cut-draft.md` → `<task>/decomposition/cut.md`, the scout's report →
    `<task>/decomposition/scout.md`. The cut file is the Manager's from now on.

## The cut file

```markdown
# Cut — <task title>

## K1 contract — <what it fixes>
AREA: <globs, comma-separated — exactly what goes into the brief's AREA>
AFTER: none
ITEMS: <plan item numbers or slugs>
RESOURCES: none
DONE WHEN: <acceptance>
SEAMS: <contract file> — checked by <CI check>

## K2 impl — <one side>
AREA: src/server/**
AFTER: K1
ITEMS: 2, 3
RESOURCES: db
DONE WHEN: …
```

- The heading is `## K<n> <contract|foundation|impl|assembly> — <title>`; `cut-check` refuses any
  other `##` heading.
- `AREA` globs are read as `verify-pr` reads them (`fnmatch`: `*` crosses `/`, so `src/*.ts` also
  covers `src/a/b.ts`). Name folders with `/**`, single files exactly.
- `AFTER` names chunks whose **last PR is merged** before this one is handed out; chunks with no
  `AFTER` path between them run in parallel.
- `RESOURCES`: shared machine resources (`db`, `emulator`, `port-3000` …). Chunks of one wave may
  share one; their items then queue on its lock (`lipok.py lock`), which `cut-check` notes.

## Handing out by waves

- A free lane (its `chunk-status` `none`, `DONE` or `DROPPED`) takes the lowest-numbered chunk not
  yet handed out whose `AFTER` chunks are all `DONE`. No such chunk → the lane waits; say so in
  "status".
- Every brief's `AREA:` is the cut's `AREA` verbatim; `KNOWN:` names the contracts it reads and the
  chunks running beside it with their areas.
- A `SYNC` after a merge (`lane.md`, "When a PR is merged") happens, with a clean cut, only across
  `AFTER`, never inside a wave.

## When the cut has to change

A worker's `DECISION` on a contract change, a missed seam found at assembly, an area that
turns out too narrow: the cut changes only through the user. Write the DR, edit
`<task>/decomposition/cut.md`, run `cut-check` on it again — a running chunk's area may grow only
where no running chunk's area is — and send the affected lanes a `REDIRECT` or `NOTE` naming the
DR. A seam found at assembly is a cut miss: record it in `final.md`.

## A good chunk, and the usual mistakes

A good chunk is coherent (its items share code or one meaning), delivers a finished step, leaves the
base building and green after each PR (the feature switched off), sits on one side of a seam, and
has 2–6 items, an area, inputs and acceptance.

- **Too fine** — a button and one endpoint are one chunk of one lane; split by layers only when each
  side gets at least two items.
- **A contract in words** — a seam described in a brief instead of a checked file.
- **A central registry every chunk appends to** — its edits go to the contract or the assembly.
- **Numbered migrations in parallel chunks** — the wave's migrations go to the foundation, or the
  numbering is by time.
- **`CHANGELOG` in every chunk** — it belongs to the assembly (or one entry file per chunk if the
  project has that).
- **A broad area "to be safe"** (`src/**`) — it serialises everything; `cut-check` will refuse it
  beside any other chunk of its wave.
