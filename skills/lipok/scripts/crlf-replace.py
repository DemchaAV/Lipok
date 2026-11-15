"""crlf-replace.py <file> <edits.json>

Applies edits to a text file whose line endings must survive (the plan is CRLF). edits.json is a list
of {"old": "...", "new": "..."}; each "old" must occur exactly once in the file as it stands when its
turn comes, written with plain \\n line ends. An "old" is matched with the file's own line ends
(as CRLF or as LF), and its "new" gets the line end of the place it lands, so untouched lines are
never rewritten, also in a file with mixed line ends. Nothing is written unless every edit applies;
the file is replaced atomically.
"""
import json
import os
import pathlib
import sys
import tempfile


def line_end_at(text, i):
    """The line end of the line that holds position i: CRLF or LF (LF at the file's end)."""
    j = text.find("\n", i)
    if j == -1:
        return "\r\n" if "\r\n" in text else "\n"
    return "\r\n" if j > 0 and text[j - 1] == "\r" else "\n"


def main(argv):
    # Windows consoles default to cp1252, and a failed edit prints the Cyrillic text it looked for:
    # without this the diagnostic itself dies with UnicodeEncodeError and hides which edit missed.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass
    if len(argv) != 3:
        print(__doc__)
        return 2
    path = pathlib.Path(argv[1])
    try:
        edits = json.loads(pathlib.Path(argv[2]).read_text(encoding="utf-8-sig"))
        text = path.read_bytes().decode("utf-8")
    except (OSError, ValueError) as e:
        print(f"ERROR {type(e).__name__}: {e}")
        return 1
    if not isinstance(edits, list) or not all(
            isinstance(e, dict) and isinstance(e.get("old"), str) and isinstance(e.get("new"), str)
            for e in edits):
        print('ERROR edits.json must be a list of {"old": "...", "new": "..."}')
        return 2
    for number, edit in enumerate(edits, 1):
        old, new = edit["old"].replace("\r\n", "\n"), edit["new"].replace("\r\n", "\n")
        if not old:
            print(f"edit {number}: 'old' is empty, nothing written")
            return 1
        forms = [old] if "\n" not in old else [old.replace("\n", "\r\n"), old]
        found = [(f, text.count(f)) for f in forms]
        total = sum(c for _, c in found)
        if total != 1:
            print(f"edit {number}: 'old' occurs {total} times, nothing written: {old[:80]!r}")
            return 1
        form = next(f for f, c in found if c == 1)
        i = text.index(form)
        eol = "\r\n" if "\r\n" in form else ("\n" if "\n" in form else line_end_at(text, i))
        text = text[:i] + new.replace("\n", eol) + text[i + len(form):]
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(text.encode("utf-8"))
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    print(f"applied {len(edits)} edits to {path} (line ends kept)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
