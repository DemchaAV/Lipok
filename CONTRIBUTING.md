# Contributing

## Run the tests

```bash
bash tests/run.sh "$PWD/skills/lipok/scripts/lipok.py" /tmp/lipok-tests
```

On Windows (Git Bash) pass Windows-form paths, as CI does:

```bash
bash tests/run.sh "$(cygpath -w "$PWD/skills/lipok/scripts/lipok.py")" "$(cygpath -m "$TEMP/lipok-tests")"
```

The last line must read `FAIL=0`. CI runs the same on Ubuntu and Windows
([.github/workflows/test.yml](.github/workflows/test.yml)). The tests need GNU `touch -d`,
`sed -i` and `timeout`; on macOS install coreutils and gnu-sed first.

Install your working copy into Claude Code with `bash install.sh` (or
`node bin/lipok.js install`) after the tests pass.

## Rules for changes

- **A fix comes with a test that fails on the code before it.** Run the new tests against the
  previous commit (`git archive HEAD | tar -x -C <dir>`) to see them fail.
- **The skills are instructions for language models.** Each rule lives in one place, in the file
  every role that needs it reads (`skills/lipok/SKILL.md` for rules shared by all roles). Prefer a
  script check over a sentence: a check cannot be misread.
- **Instructions and scripts agree.** A command, flag, field or output line named in a `.md` file
  must exist in the scripts, spelled the same.
- **Generic.** No project names, personal paths or machine-specific assumptions; everything in
  English.
- **Scripts run concurrently** in several sessions. Write state only through `lipok.py` (atomic,
  locked); never assume a file is not being replaced while you read it.
- Commits follow `type(scope): summary` (`fix`, `feat`, `docs`, `test`, `chore`). Record
  user-visible changes in [CHANGELOG.md](CHANGELOG.md).
