# Changelog

## Unreleased

### Fixed
- `cut-check` no longer passes overlapping chunks: repeated or wrapped `AREA` lines are added,
  unknown headings and lines inside a chunk are refused, brace/`./`/trailing-slash globs are
  refused, and overlap is compared without case.
- `verify-pr` fails a PR that conflicts with the base, has changes requested, has 100+ files, or a
  file outside the area by case; a PR with no checks is `VERIFY FAIL`, not an error.
- `wait-pr.sh` reports `ERROR` instead of `CI-GREEN` when the profile's required checks cannot be
  read; numbers with leading zeros are decimal; `--require none`.
- `watch-session.sh` waits for the first transcript and works with BSD `stat` and `python3`.
- `book` refuses when the lane holds another PR; lock holders carry their repository (`--repo`);
  `set --expect` checks every pair; stamps without a time zone are UTC.
- Windows: reads and lock files retry while another process replaces them.
- Installers refuse to install into the package itself and copy before replacing.
- Instructions: `BLOCKED` has a way back to work; a later executor attempt keeps its report; a
  waiting lane is not reported as quiet; the `before_push` gate path is complete.

### Changed
- One pull request per item (the unused `pr-with:` grouping is gone).
- Reports to the user are in the user's language; `max_lanes` defaults to 1 and says so.
- Shorter instructions without duplicated rules; standalone `docs/architecture.md`, the old design
  notes moved to `docs/design-history.md`; CI on Ubuntu and Windows.

## 1.0.0 — 2026-11-15

First release: the `lipok` and `lipok-task` skills (Manager, worker, executor roles; cutting a task
into parallel chunks), `lipok.py` (state, `verify-pr`, `stall-check`, `cut-check`, `usage`, locks),
`wait-pr.sh`, `watch-session.sh`, and the `npx github:DemchaAV/Lipok install` installer.
