"""lipok.py - state helper for the Lipok skills. Run with `python -I`.

Paths: everything lives under ~/.lipok (outside any repository, visible from every worktree).
Every path this script prints is in forward-slash form (C:/Users/...), which Git Bash accepts.
  ~/.lipok/locks/<resource>/                     machine-wide locks
  ~/.lipok/projects/<owner>-<repo>/project.json  the project profile
  ~/.lipok/projects/<owner>-<repo>/active        id of the active task
  ~/.lipok/projects/<owner>-<repo>/tasks/<id>/   the task's state (task.json, lanes/, chunks/, ...)

Two state files per lane (v6):
  <task>/lanes/<N>/state.md            the Manager's, chunk level (which chunk, worker, watches)
  <task>/chunks/<K>/lane-state.md      the worker's, item level (item, attempt, key, PR, its watches)

Commands (each prints its result; the last line is the one to read):
  root        --repo R                         the project folder
  profile     --repo R                         project.json after checking it
  profile-set --repo R key=value ...           change profile fields (a value that parses as JSON
                                               is JSON); writes nothing unless still valid
  task-new    --repo R --title T [--plan PATH] [--lanes N] [--item-profile PATH]
                                               create a task, make it active, print its folder
                                               (flat scheme only; the three-level one is deferred)
  task-active --repo R                         the active task folder
  task-set    --repo R key=value ...           set fields of the active task's task.json
  task-close  --repo R                         mark the active task closed and clear `active`
  chunk <state.md> --chunk K<n> [--force]     the Manager starts a chunk on a lane: chunk key,
                                               the chunk's folders and the worker's lane-state.md;
                                               refuses a lane whose chunk is not finished
                                               (chunk-status other than none/DONE/DROPPED)
  item  <lane-state.md> --chunk K<n> --slug S (--item "<plan line>" | --item-file F)
        [--attempts N] [--force]
                                               start an item on a lane: attempt=1, key, report;
                                               refuses a slug used before (its report exists) and,
                                               without --force, a lane whose item is not finished
                                               (status other than none/MERGED/CLOSED/DROPPED);
                                               --attempts N: the chunk plan runs the item in N
                                               planned executor attempts (batches) - the stall
                                               watch counts a loop only past them (default 1)
  bump  <lane-state.md>                        next attempt of the lane's item; prints KEY <key>
  get   <state.md> <key>                       one field
  set   <state.md> key=value ... [--expect key=value ...]
                                               set fields of an EXISTING lane state; refuse unknown
                                               keys; with --expect refuse unless they still hold
  show  <state.md>                             all fields
  line  <lanes/N/state.md> <TYPE> [<key|ck>]  the Manager, on every line from the worker: stamps
                                               last-line (and progress-line for PLAN, READY,
                                               MERGED, CHUNK_DONE), clears death-turn, does the
                                               late check (LATE ... exit 4, logged to events.log)
                                               and opens the decision wait on DECISION/BLOCKED;
                                               TYPE ANSWERED (the Manager's own mark when it
                                               sends the user's answer) closes that wait
  book  <lanes/N/state.md> <pr> --repo R      the Manager, on a merge: confirms it on GitHub,
                                               sets booked=<pr> pr=none pr-status=none and adds
                                               the merge wait: BOOKED <pr> <sha> <date> |
                                               ALREADY BOOKED <pr> | NOT MERGED <pr> <state> (4)
  verify-pr <pr> --repo R --report F [--area "glob,glob"] [--lane <lanes/N/state.md>]
                                               check a PR the worker calls ready against GitHub
                                               and the report: VERIFY OK <pr> <sha> (exit 0) or
                                               VERIFY FAIL <pr> <reasons> (exit 4); the profile's
                                               required_checks must all be registered; with --lane
                                               OK sets pr, pr-status=READY and opens the merge
                                               wait, FAIL sets pr-status=REDIRECTED
  required-checks --repo R                     the profile's required_checks, one per line
  stall-check <state.md> [--repo R] [--window-h H] [--max-attempts M]
              [--watch [--every S] [--hours H]]
                                               is the lane moving: STALL OK | STALL LOOP <key>
                                               attempt=<n> | STALL QUIET <h>h since <t> | STALL IDLE;
                                               progress is `progress-line` (PLAN, READY, MERGED,
                                               CHUNK_DONE), not any line; a loop counts attempts
                                               above `loop-ack` (<item key>#<attempt> acknowledged);
                                               idle while paused, waiting on the user or the merge;
                                               --watch waits for the first non-OK line (a timer)
  lane-env --repo R --lane N                   write <task>/lanes/N/env from project.json lane_env
  cut-check <cut.md> [--repo R] [--files F] [--max-lanes N]
                                               can the cut's chunks run in parallel: chunks that
                                               do not come AFTER one another must not share a file
                                               (the main checkout's git ls-files, or --files) nor
                                               overlapping AREA globs; AFTER must name chunks and
                                               hold no cycle; an item sits in one chunk only;
                                               prints CHUNK / WAVES lines, a LANES line (how many
                                               rounds each number of lanes takes), then CUT OK
                                               lanes=<n> or CUT FAIL <reasons> (exit 4)
  usage <task folder> [--manager <dir|file|cwd>]... [--worker <dir>]... [--since T] [--until T]
                                               who spent the tokens, from the transcripts on disk
                                               (no model call): manager, worker (own turns),
                                               executors (workers' subagents), each with a share
                                               of relative cost, and COORDINATION <n>%; the window
                                               is task.json created..closed (or now); workers are
                                               every lane's worker-dir and earlier workers of the
                                               lane; the Manager counts only with --manager
  lock acquire <resource> --holder H --repo R  take a machine-wide lock (exit 4 if another holds it;
                                               the same holder, any attempt, gets it again)
  lock release <resource> --holder H --repo R  release it (exit 4 if another holder has it)
  lock show [<resource>]                       who holds what, since when
  lock break <resource> --by H                 remove a dead holder's lock (the Manager only)

A holder is <repo>:<key>, compared without its `#<attempt>`: o/r:t1/L1/K1/x#1 and o/r:t1/L1/K1/x#2
are the same holder; o/r:t1/L1/K1/x and o/q:t1/L1/K1/x are not.
item/bump/set/task-set/task-close serialise on a lock file beside the file they change.

Exit codes: 0 done, 1 a file could not be read or written, 2 usage, 3 not found, 4 refused.
"""
import json
import os
import pathlib
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from fnmatch import fnmatchcase

HOME = pathlib.Path(os.environ.get("LIPOK_HOME", pathlib.Path.home() / ".lipok"))

# The Manager's lane state (v6, chunk level).
LANE_KEYS = [
    "task", "lane", "repo", "worker", "worker-dir", "branch-name", "chunk", "chunk-key",
    "chunk-status", "lane-state", "pr", "pr-status", "booked", "worker-watch", "stall-watch",
    "pending", "last-line", "progress-line", "loop-ack", "death-turn", "paused",
    "wait-since", "wait-kind", "merge-wait-min", "decision-wait-min",
]
# v5 lane-state fields, still accepted in an old state.md so a v5 task can be read and moved on.
LEGACY_LANE_KEYS = ["item", "slug", "attempt", "key", "status", "report", "watch", "rerun",
                    "last-turn"]
# The worker's lane state (v6, item level).
ITEM_KEYS = [
    "task", "lane", "repo", "chunk", "item", "slug", "attempt", "key", "status", "report", "pr",
    "watch", "gate-run", "rerun", "last-turn", "turn", "booked", "paused", "planned-attempts",
]
CHUNK_DONE = {"none", "DONE", "DROPPED"}
TASK_KEYS = {
    "id", "title", "repo", "plan", "scheme", "lanes", "item_profile", "created", "status",
    "manager", "plan_version", "closed", "arch",
}
TASK_INT_KEYS = {"lanes", "plan_version"}
PROFILE_REQUIRED = ["repo", "main_checkout", "base_branch", "gate", "quiet_window_min", "author"]
PROFILE_INTS = ["quiet_window_min", "gate_minutes", "max_lanes", "max_ready_prs",
                "progress_window_h", "max_attempts"]
ITEM_DONE = {"none", "MERGED", "CLOSED", "DROPPED"}


class Usage(Exception):
    pass


class NotFound(Exception):
    pass


class Refused(Exception):
    pass


class Broken(Exception):
    pass


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def show_path(p):
    return pathlib.Path(p).as_posix()


def read_text(path):
    # Windows refuses a read for an instant while another process replaces the file
    # (write_atomic's os.replace): about 1% of reads under 8 concurrent writers (2026-11-15).
    for i in range(100):
        try:
            return pathlib.Path(path).read_text(encoding="utf-8-sig")
        except UnicodeDecodeError as e:
            raise Broken(f"ERROR {show_path(path)} is not UTF-8: {e}")
        except PermissionError:
            if i == 99:
                raise
            time.sleep(0.05)


def read_json(path):
    try:
        return json.loads(read_text(path))
    except json.JSONDecodeError as e:
        raise Broken(f"ERROR {show_path(path)} is not valid JSON: {e}")


def write_atomic(path, text):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        # Windows refuses the replace while another process has the target open: retry briefly.
        for i in range(100):
            try:
                os.replace(tmp, path)
                return
            except PermissionError:
                if i == 99:
                    raise
                time.sleep(0.05)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


@contextmanager
def file_lock(path, timeout=30):
    """Serialise read-modify-write of one file across processes."""
    lock = pathlib.Path(str(path) + ".lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    end = time.time() + timeout
    while True:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, f"{os.getpid()} {now()}\n".encode())
            os.close(fd)
            break
        except (FileExistsError, PermissionError):
            # PermissionError: Windows, while another process is deleting the lock file.
            try:
                if time.time() - lock.stat().st_mtime > 120:   # left by a killed process
                    lock.unlink()
                    continue
            except (FileNotFoundError, PermissionError):
                continue
            if time.time() > end:
                raise Refused(f"REFUSED {show_path(path)} is locked by another writer ({show_path(lock)})")
            time.sleep(0.05)
    try:
        yield
    finally:
        for i in range(100):
            try:
                lock.unlink()
                break
            except FileNotFoundError:
                break
            except PermissionError:
                time.sleep(0.05)


def project_dir(repo):
    if not repo or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise Usage(f"--repo must be owner/name, got {repo!r}")
    return HOME / "projects" / repo.replace("/", "-")


def read_fields(path, must_exist=True):
    p = pathlib.Path(path)
    if not p.is_file():
        if must_exist:
            raise NotFound(f"NO STATE FILE {show_path(p)}")
        return {}
    fields = {}
    for line in read_text(p).splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        k, sep, v = line.partition(":")
        if sep:
            fields[k.strip()] = v.strip()
    return fields


def is_item_state(path):
    return pathlib.Path(path).name == "lane-state.md"


def keys_for(path):
    return ITEM_KEYS if is_item_state(path) else LANE_KEYS + LEGACY_LANE_KEYS


def write_fields(path, fields):
    known = keys_for(path)
    order = [k for k in known if k in fields] + [k for k in fields if k not in known]
    write_atomic(path, "".join(f"{k}: {fields[k]}\n" for k in order))


def check_value(k, v):
    if "\n" in v or "\r" in v:
        raise Usage(f"value of {k} must be one line")


def parse_pairs(items):
    out = {}
    for item in items:
        k, sep, v = item.partition("=")
        if not sep or not k:
            raise Usage(f"expected key=value, got {item!r}")
        check_value(k, v)
        out[k] = v
    return out


def opt(args, name, default=None):
    if name in args:
        i = args.index(name)
        if i + 1 >= len(args):
            raise Usage(f"{name} needs a value")
        val = args[i + 1]
        del args[i:i + 2]
        return val
    return default


def flag(args, name):
    if name in args:
        args.remove(name)
        return True
    return False


def no_rest(args):
    if args:
        raise Usage(f"unexpected arguments: {' '.join(args)}")


def active_task(repo):
    pdir = project_dir(repo)
    a = pdir / "active"
    if not a.exists():
        return None
    tid = read_text(a).strip()
    if not tid:
        return None
    t = pdir / "tasks" / tid
    if not (t / "task.json").is_file():
        raise NotFound(f"ACTIVE TASK MISSING {show_path(t)} (fix or empty {show_path(a)})")
    return t


def need_active(repo):
    t = active_task(repo)
    if t is None:
        raise NotFound("NO ACTIVE TASK")
    return t


def load_profile(repo):
    p = project_dir(repo) / "project.json"
    if not p.exists():
        raise NotFound(f"NO PROFILE {show_path(p)}")
    return p, read_json(p)


def lane_key(f):
    for k in ("task", "lane", "chunk", "slug", "attempt"):
        if f.get(k, "none") in ("", "none"):
            raise Refused(f"REFUSED cannot build the key: field {k} is {f.get(k)!r}")
    return f"{f['task']}/L{f['lane']}/{f['chunk']}/{f['slug']}#{f['attempt']}"


def holder_base(h):
    return re.sub(r"#\d+$", "", h.strip())


def task_dir_of(state_path):
    # <task>/lanes/<N>/state.md  or  <task>/chunks/<K>/lane-state.md: both three levels down
    return pathlib.Path(state_path).resolve().parent.parent.parent


def cmd_root(args):
    repo = opt(args, "--repo")
    no_rest(args)
    print(show_path(project_dir(repo)))


def cmd_profile(args):
    repo = opt(args, "--repo")
    no_rest(args)
    p, data = load_profile(repo)
    if data.get("repo") and data["repo"] != repo:
        raise Refused(f"PROFILE MISMATCH repo={data['repo']} asked={repo}")
    print(json.dumps(data, ensure_ascii=False, indent=2))
    missing = [k for k in PROFILE_REQUIRED if k not in data]
    if missing:
        raise Refused(f"PROFILE INCOMPLETE missing={','.join(missing)}")
    bad = profile_problems(data)
    if bad:
        raise Refused(f"PROFILE INVALID {', '.join(bad)} (numbers must be positive integers)")
    print(f"PROFILE OK {show_path(p)}")


def profile_problems(data):
    bad = [k for k in PROFILE_INTS if k in data
           and not (isinstance(data[k], int) and not isinstance(data[k], bool) and data[k] > 0)]
    rc = data.get("required_checks")
    if rc is not None and not (isinstance(rc, list) and all(isinstance(x, str) and x.strip() for x in rc)):
        bad.append("required_checks (a list of check names)")
    a = data.get("author")
    if not (isinstance(a, dict) and a.get("name") and a.get("email")):
        bad.append("author (needs name and email)")
    return bad


def cmd_profile_set(args):
    """Change fields of an existing profile. A value that parses as JSON is JSON (3, true,
    ["a","b"], {"name":"n","email":"e"}); anything else is a string. Nothing is written unless the
    whole profile is still valid."""
    repo = opt(args, "--repo")
    pairs = parse_pairs(args)
    if not pairs:
        raise Usage("profile-set --repo R key=value ...")
    if "repo" in pairs:
        raise Refused("REFUSED repo cannot change; a profile belongs to one repository")
    p, _ = load_profile(repo)
    with file_lock(p):
        data = read_json(p)
        old = {k: data.get(k) for k in pairs}
        for k, v in pairs.items():
            try:
                data[k] = json.loads(v)
            except ValueError:
                data[k] = v
        bad = profile_problems(data) + [k for k in PROFILE_REQUIRED if k not in data]
        if bad:
            raise Refused(f"REFUSED the profile would be invalid: {', '.join(bad)}")
        write_atomic(p, json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    for k in pairs:
        print(f"SET {k}: {json.dumps(old[k], ensure_ascii=False)} -> {json.dumps(data[k], ensure_ascii=False)}")
    print(f"PROFILE OK {show_path(p)}")


def cmd_task_new(args):
    repo, title = opt(args, "--repo"), opt(args, "--title")
    plan, scheme = opt(args, "--plan", ""), opt(args, "--scheme", "flat")
    item_profile, lanes_s = opt(args, "--item-profile", ""), opt(args, "--lanes", "1")
    no_rest(args)
    if not title:
        raise Usage("task-new needs --title")
    if scheme != "flat":
        raise Refused("REFUSED only the flat scheme is supported (v6: the three-level one is deferred)")
    if not lanes_s.isdigit() or int(lanes_s) < 1:
        raise Usage(f"--lanes must be a positive number, got {lanes_s!r}")
    for k, v in (("title", title), ("plan", plan), ("item-profile", item_profile)):
        check_value(k, v)
    pdir = project_dir(repo)
    cur = active_task(repo)
    if cur is not None:
        raise Refused(f"REFUSED active task exists: {show_path(cur)}")
    lanes = int(lanes_s)
    tasks = pdir / "tasks"
    tasks.mkdir(parents=True, exist_ok=True)
    nums = [int(m.group(1)) for d in tasks.iterdir() if (m := re.fullmatch(r"t(\d+)", d.name))]
    tid = f"t{max(nums, default=0) + 1}"
    tdir = tasks / tid
    task = {
        "id": tid, "title": title, "repo": repo, "plan": plan, "scheme": scheme,
        "lanes": lanes, "item_profile": item_profile,
        "created": now(), "status": "active", "plan_version": 1, "arch": "v6",
    }
    for sub in ["decomposition", "decisions", "reviews", "chunks"]:
        (tdir / sub).mkdir(parents=True, exist_ok=True)
    for n in range(1, lanes + 1):
        write_fields(tdir / "lanes" / str(n) / "state.md", fresh_lane(tid, n, repo))
    write_atomic(tdir / "task.json", json.dumps(task, ensure_ascii=False, indent=2) + "\n")
    write_atomic(pdir / "active", tid + "\n")
    print(f"TASK {tid} {show_path(tdir)}")


def cmd_task_active(args):
    repo = opt(args, "--repo")
    no_rest(args)
    print(show_path(need_active(repo)))


def cmd_task_set(args):
    t = need_active(opt(args, "--repo"))
    pairs = parse_pairs(args)
    if not pairs:
        raise Usage("task-set --repo R key=value ...")
    bad = [k for k in pairs if k not in TASK_KEYS]
    if bad:
        raise Refused(f"REFUSED unknown task keys: {','.join(bad)}")
    notint = [k for k in pairs if k in TASK_INT_KEYS and not pairs[k].isdigit()]
    if notint:
        raise Usage(f"{','.join(notint)} must be a number")
    tj = t / "task.json"
    with file_lock(tj):
        data = read_json(tj)
        for k, v in pairs.items():
            data[k] = int(v) if k in TASK_INT_KEYS else v
        write_atomic(tj, json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    print(f"SET {','.join(pairs)} in {show_path(tj)}")


def cmd_task_close(args):
    repo = opt(args, "--repo")
    no_rest(args)
    t = need_active(repo)
    tj = t / "task.json"
    with file_lock(tj):
        data = read_json(tj)
        data["status"], data["closed"] = "closed", now()
        write_atomic(tj, json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    write_atomic(project_dir(repo) / "active", "")
    print(f"CLOSED {data['id']}")


def cmd_item(args):
    chunk, slug = opt(args, "--chunk"), opt(args, "--slug")
    item, item_file = opt(args, "--item"), opt(args, "--item-file")
    planned = opt(args, "--attempts", "1")
    force = flag(args, "--force")
    if len(args) != 1 or not (chunk and slug) or (item is None) == (item_file is None):
        raise Usage("item <state.md> --chunk K<n> --slug S (--item \"<plan line>\" | --item-file F) "
                    "[--attempts N] [--force]")
    if not planned.isdigit() or int(planned) < 1:
        raise Usage(f"--attempts must be a positive whole number, got {planned!r}")
    if item_file is not None:
        lines = [l.strip() for l in read_text(item_file).splitlines() if l.strip()]
        if len(lines) != 1:
            raise Usage(f"--item-file must hold one non-empty line, it holds {len(lines)}")
        item = lines[0]
    check_value("item", item)
    if not item.strip():
        raise Usage("the item line is empty")
    if not re.fullmatch(r"K[0-9]+", chunk):
        raise Usage(f"chunk must be K<number>, got {chunk!r}")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", slug):
        raise Usage(f"slug must be lower-case letters, digits and dashes, got {slug!r}")
    path = args[0]
    if not is_item_state(path):
        raise Usage("item works on the worker's chunks/<K>/lane-state.md (v6), not on lanes/<N>/state.md")
    with file_lock(path):
        f = read_fields(path)
        if f.get("chunk") not in (None, "none", chunk):
            raise Refused(f"REFUSED this lane-state is chunk {f.get('chunk')}, not {chunk}")
        if not force and f.get("status", "none") not in ITEM_DONE:
            raise Refused(f"REFUSED lane item {f.get('key')} is {f.get('status')}; finish it, "
                          f"set status=DROPPED, or pass --force")
        report = task_dir_of(path) / "chunks" / chunk / "reports" / f"{slug}.md"
        if report.exists():
            raise Refused(f"REFUSED slug {slug} was used before ({show_path(report)}); pick a new slug")
        f.update({"chunk": chunk, "slug": slug, "item": item, "attempt": "1", "status": "WORKING",
                  "last-turn": "none", "pr": "none", "watch": "none", "rerun": "none", "gate-run": "none",
                  "planned-attempts": str(int(planned))})
        f["key"] = lane_key(f)
        f["report"] = show_path(report)
        for sub in ("briefs", "reports", "notes"):
            (task_dir_of(path) / "chunks" / chunk / sub).mkdir(parents=True, exist_ok=True)
        write_fields(path, f)
    print(f"REPORT {f['report']}")
    print(f"KEY {f['key']}")


def cmd_bump(args):
    if len(args) != 1:
        raise Usage("bump <state.md>")
    with file_lock(args[0]):
        f = read_fields(args[0])
        if not f.get("attempt", "").isdigit() or f["attempt"] == "0":
            raise Refused(f"REFUSED no item on this lane (attempt {f.get('attempt')!r})")
        f["attempt"] = str(int(f["attempt"]) + 1)
        f["key"] = lane_key(f)
        write_fields(args[0], f)
    print(f"KEY {f['key']}")


def cmd_get(args):
    if len(args) != 2:
        raise Usage("get <state.md> <key>")
    f = read_fields(args[0])
    if args[1] not in f:
        raise NotFound(f"NO FIELD {args[1]}")
    print(f[args[1]])


def cmd_set(args):
    # Every pair after --expect is a condition (2026-11-15: `--expect a=1 b=2` used to SET b=2).
    expect = []
    if "--expect" in args:
        i = args.index("--expect")
        expect = [a for a in args[i + 1:] if a != "--expect"]
        args = args[:i]
        if not expect:
            raise Usage("--expect needs key=value")
    if len(args) < 2:
        raise Usage("set <state.md> key=value ... [--expect key=value ...]")
    path, pairs = args[0], parse_pairs(args[1:])
    known = keys_for(path)
    bad = [k for k in pairs if k not in known]
    if bad:
        raise Refused(f"REFUSED unknown keys: {','.join(bad)} (known: {','.join(known)})")
    with file_lock(path):
        f = read_fields(path)
        for k, v in parse_pairs(expect).items():
            if f.get(k) != v:
                raise Refused(f"REFUSED expected {k}={v}, found {k}={f.get(k)}")
        f.update(pairs)
        write_fields(path, f)
    print(f"SET {' '.join(f'{k}={v}' for k, v in pairs.items())}")


def cmd_show(args):
    if len(args) != 1:
        raise Usage("show <state.md>")
    for k, v in read_fields(args[0]).items():
        print(f"{k}: {v}")


def cmd_lane_env(args):
    repo, lane = opt(args, "--repo"), opt(args, "--lane")
    no_rest(args)
    if not lane or not lane.isdigit() or int(lane) < 1:
        raise Usage("lane-env --repo R --lane N")
    lane = str(int(lane))
    t = need_active(repo)
    _, prof = load_profile(repo)
    env = {}
    for k, tmpl in (prof.get("lane_env") or {}).items():
        s = str(tmpl)
        m = (re.fullmatch(r"\s*(\d+)\s*\+\s*\{N\}\s*", s)
             or re.fullmatch(r"\s*\{N\}\s*\+\s*(\d+)\s*", s))
        env[k] = str(int(m.group(1)) + int(lane)) if m else s.replace("{N}", lane)
        check_value(k, env[k])
    out = t / "lanes" / lane / "env"
    write_atomic(out, "".join(f"{k}={v}\n" for k, v in env.items()))
    print(f"LANE-ENV {len(env)} vars {show_path(out)}")


def fresh_lane(tid, n, repo):
    return {
        "task": tid, "lane": str(n), "repo": repo, "worker": "none", "worker-dir": "none",
        "branch-name": "none", "chunk": "none", "chunk-key": "none", "chunk-status": "none",
        "lane-state": "none", "pr": "none", "pr-status": "none", "booked": "none",
        "worker-watch": "none", "stall-watch": "none", "pending": "none",
        "last-line": "none", "progress-line": "none", "loop-ack": "none",
        "death-turn": "none", "paused": "no",
        "wait-since": "none", "wait-kind": "none", "merge-wait-min": "0", "decision-wait-min": "0",
    }


def cmd_chunk(args):
    chunk = opt(args, "--chunk")
    force = flag(args, "--force")
    if len(args) != 1 or not chunk:
        raise Usage("chunk <lanes/N/state.md> --chunk K<n> [--force]")
    if not re.fullmatch(r"K[0-9]+", chunk):
        raise Usage(f"chunk must be K<number>, got {chunk!r}")
    path = args[0]
    if is_item_state(path):
        raise Usage("chunk works on the Manager's lanes/<N>/state.md")
    tdir = task_dir_of(path)
    with file_lock(path):
        f = read_fields(path)
        if not force and f.get("chunk-status", "none") not in CHUNK_DONE:
            raise Refused(f"REFUSED lane chunk {f.get('chunk-key')} is {f.get('chunk-status')}; "
                          f"finish it, set chunk-status=DROPPED, or pass --force")
        cdir = tdir / "chunks" / chunk
        ls = cdir / "lane-state.md"
        if ls.exists() and not force:
            raise Refused(f"REFUSED chunk {chunk} was started before ({show_path(ls)}); pick a new one")
        for sub in ("briefs", "reports", "notes"):
            (cdir / sub).mkdir(parents=True, exist_ok=True)
        for k in ("task", "lane"):
            if f.get(k, "none") in ("", "none"):
                raise Refused(f"REFUSED lane state has no {k}")
        ckey = f"{f['task']}/L{f['lane']}/{chunk}"
        write_fields(ls, {
            "task": f["task"], "lane": f["lane"], "repo": f.get("repo", "none"), "chunk": chunk,
            "item": "none", "slug": "none", "attempt": "0", "key": "none", "status": "none",
            "report": "none", "pr": "none", "watch": "none", "gate-run": "none", "rerun": "none",
            "last-turn": "none", "turn": "none", "booked": "none", "paused": "no",
            "planned-attempts": "none",
        })
        f.update({"chunk": chunk, "chunk-key": ckey, "chunk-status": "BRIEFED",
                  "lane-state": show_path(ls), "pr": "none", "pr-status": "none",
                  "last-line": now(), "progress-line": now(), "loop-ack": "none",
                  "death-turn": "none"})
        write_fields(path, f)
    print(f"BRIEF {show_path(cdir / 'brief.md')}")
    print(f"PLAN {show_path(cdir / 'plan.md')}")
    print(f"LANE-STATE {show_path(ls)}")
    print(f"CHUNK-KEY {ckey}")


WORKER_LINES = {"LANE", "PLAN", "READY", "MERGED", "DECISION", "BLOCKED", "CHUNK_DONE", "ALIVE",
                "PAUSED"}
PROGRESS_LINES = {"PLAN", "READY", "MERGED", "CHUNK_DONE"}
ITEM_LINES = {"READY", "DECISION", "BLOCKED", "ALIVE", "PAUSED"}


def minutes_since(stamp, until=None):
    try:
        start = parse_time(stamp)
    except ValueError:
        return 0
    end = until or datetime.now(timezone.utc)
    return max(0, int((end - start).total_seconds() // 60))


def add_minutes(f, field, n):
    cur = f.get(field, "0")
    f[field] = str((int(cur) if cur.isdigit() else 0) + n)


def cmd_line(args):
    """The Manager's bookkeeping for one line from the worker. Every field it writes used to be a
    hand-typed `set`; one was forgotten on 2026-11-12 (progress-line on a MERGED) and the stall
    watch raised a false STALL QUIET three hours later."""
    if len(args) not in (2, 3):
        raise Usage("line <lanes/N/state.md> <TYPE> [<key|ck>]")
    path, kind = args[0], args[1]
    key = args[2] if len(args) == 3 else ""
    if is_item_state(path):
        raise Usage("line works on the Manager's lanes/<N>/state.md")
    if kind not in WORKER_LINES | {"ANSWERED"}:
        raise Usage(f"TYPE must be one of {', '.join(sorted(WORKER_LINES))} or ANSWERED, got {kind!r}")
    t = now()
    with file_lock(path):
        f = read_fields(path)
        if kind == "ANSWERED":
            if f.get("wait-kind") == "decision" and f.get("wait-since", "none") not in ("", "none"):
                n = minutes_since(f["wait-since"])
                add_minutes(f, "decision-wait-min", n)
                f["wait-since"], f["wait-kind"] = "none", "none"
                write_fields(path, f)
                print(f"ANSWERED after {n}m")
            else:
                print("ANSWERED (no decision wait open)")
            return
        f["last-line"], f["death-turn"] = t, "none"
        late = ""
        if key and kind not in ("LANE",):
            ck = "/".join(key.split("/")[:3])
            if f.get("chunk-key", "none") not in ("", "none") and ck != f["chunk-key"]:
                late = f"chunk {ck} is not the lane's {f['chunk-key']}"
            elif kind in ITEM_LINES and key.count("/") >= 3:
                ls = f.get("lane-state", "none")
                cur = read_fields(ls, must_exist=False).get("key", "none") if ls not in ("", "none") else "none"
                if cur not in ("", "none") and key != cur:
                    late = f"item {key} is not the lane-state's {cur}"
        if late:
            write_fields(path, f)
            log = pathlib.Path(path).parent / "events.log"
            with open(log, "a", encoding="utf-8", newline="\n") as fh:
                fh.write(f"{t}  LATE  {kind} {key} ({late})\n")
            raise Refused(f"LATE {kind} {key}: {late}; logged to {show_path(log)}")
        if kind in PROGRESS_LINES:
            f["progress-line"] = t
        if kind in ("DECISION", "BLOCKED") and f.get("wait-kind", "none") in ("", "none"):
            f["wait-since"], f["wait-kind"] = t, "decision"
        write_fields(path, f)
    print(f"LINE {kind} {t}")


def cmd_book(args):
    repo = opt(args, "--repo")
    if len(args) != 2 or not args[1].isdigit():
        raise Usage("book <lanes/N/state.md> <pr> --repo R")
    path, pr = args
    if is_item_state(path):
        raise Usage("book works on the Manager's lanes/<N>/state.md")
    project_dir(repo)
    # `booked` lists every PR booked on the lane, so an old line cannot book one twice; a lane
    # holding another PR refuses (2026-11-15 audit: `book 7` wiped PR #9's READY).
    def booked(f):
        return [b for b in f.get("booked", "none").split(",") if b not in ("", "none")]
    f0 = read_fields(path)
    if pr in booked(f0):
        print(f"ALREADY BOOKED {pr}")
        return
    if f0.get("pr", "none") not in ("", "none", pr):
        raise Refused(f"REFUSED the lane holds PR #{f0['pr']} ({f0.get('pr-status')}), not #{pr}")
    v = gh_json(["pr", "view", pr, "--repo", repo, "--json", "state,mergedAt,mergeCommit"])
    if v.get("state") != "MERGED" or not v.get("mergedAt"):
        raise Refused(f"NOT MERGED {pr} {v.get('state')}")
    sha = ((v.get("mergeCommit") or {}).get("oid") or "")[:7]
    merged = parse_time(v["mergedAt"])
    with file_lock(path):
        f = read_fields(path)
        if pr in booked(f):
            print(f"ALREADY BOOKED {pr}")
            return
        wait = ""
        if f.get("wait-kind") == "merge" and f.get("wait-since", "none") not in ("", "none"):
            n = minutes_since(f["wait-since"], merged)
            add_minutes(f, "merge-wait-min", n)
            f["wait-since"], f["wait-kind"] = "none", "none"
            wait = f" waited {n}m"
        f["booked"] = ",".join(booked(f) + [pr])
        f["pr"], f["pr-status"] = "none", "none"
        write_fields(path, f)
    print(f"BOOKED {pr} {sha} {merged:%Y-%m-%d}{wait}")


def gh_json(args):
    """Run gh (or $LIPOK_GH, for tests) and parse its JSON. `gh pr checks` exits 8 or 1 with
    pending or failing checks and still prints JSON, so the output decides, not the exit code."""
    cmd = shlex.split(os.environ.get("LIPOK_GH", "gh")) + args
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    except OSError as e:
        raise Broken(f"ERROR cannot run {cmd[0]}: {e}")
    try:
        return json.loads(p.stdout)
    except ValueError:
        # A PR with no check at all: `gh pr checks` prints this and no JSON (exit 1).
        if args[:2] == ["pr", "checks"] and "no checks reported" in (p.stderr + p.stdout):
            return []
        msg = (p.stderr or p.stdout).strip().replace("\n", " ")[:300]
        raise Broken(f"ERROR gh {' '.join(args[:2])} failed (exit {p.returncode}): {msg}")


def parse_time(s):
    """An ISO time; one without a zone is UTC (a hand-typed stamp used to crash the comparison
    with an aware one). Anything else raises ValueError."""
    t = datetime.fromisoformat(str(s).strip().replace("Z", "+00:00"))
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


THREADS_QUERY = ("query($owner:String!,$name:String!,$number:Int!){repository(owner:$owner,name:$name)"
                 "{pullRequest(number:$number){reviewThreads(first:100){nodes{isResolved}}}}}")


def report_checks(header, files, prof):
    """What the item report claims, checked for shape and consistency. Returns failure strings."""
    fails = []
    m = re.search(r"^STATUS:\s*(\S+)", header, re.M)
    if not m or m.group(1) != "REVIEWED":
        fails.append(f"report STATUS is {m.group(1) if m else 'missing'}, not REVIEWED")
    m = re.search(r"^TESTS:\s*run\s+(\d+),\s*failed\s+(\d+)", header, re.M)
    if not m:
        fails.append("report has no 'TESTS: run <n>, failed <n>'")
    elif int(m.group(1)) == 0 or int(m.group(2)) != 0:
        fails.append(f"tests run {m.group(1)}, failed {m.group(2)}")
    m = re.search(r"^REVIEW:\s*rounds\s+(\d+),\s*open majors\s+(\d+)", header, re.M)
    if not m:
        fails.append("report has no 'REVIEW: rounds <n>, open majors <n>'")
    elif int(m.group(1)) == 0 or int(m.group(2)) != 0:
        fails.append(f"review rounds {m.group(1)}, open Blocker/Critical/Major {m.group(2)}")
    m = re.search(r"^BOTS:\s*answered\s+(\d+)\s+of\s+(\d+)", header, re.M)
    if not m:
        fails.append("report has no 'BOTS: answered <n> of <m>'")
    elif m.group(1) != m.group(2):
        fails.append(f"bot/CodeQL comments answered {m.group(1)} of {m.group(2)}")
    code = [p for p in files if not (p.lower().endswith((".md", ".txt", ".rst")) or p.startswith("docs/"))]
    if prof.get("sabotages", True) and code:
        m = re.search(r"^SABOTAGES:\s*caught\s+(\d+)\s+of\s+(\d+)", header, re.M)
        if not m:
            fails.append("code changed, report has no 'SABOTAGES: caught <n> of <m>'")
        elif int(m.group(2)) == 0 or m.group(1) != m.group(2):
            fails.append(f"sabotages caught {m.group(1)} of {m.group(2)}")
    return fails


def gate_check(header, last_commit):
    m = re.search(r"^GATE:\s*(\S.*?)\s*$", header, re.M)
    if not m or m.group(1) == "none":
        return ["report names no gate output file ('GATE: <path>')"]
    g = pathlib.Path(m.group(1))
    if not g.is_file():
        return [f"gate file {m.group(1)} does not exist"]
    lines = [l.strip() for l in read_text(g).splitlines() if l.strip()]
    if not lines or lines[-1] != "GATE PASS":
        return [f"gate file ends {lines[-1][:60] if lines else '(empty)'!r}, not GATE PASS"]
    if last_commit:
        mt = datetime.fromtimestamp(g.stat().st_mtime, timezone.utc)
        if mt < last_commit:
            return [f"gate ran {mt:%Y-%m-%dT%H:%MZ}, before the head commit {last_commit:%Y-%m-%dT%H:%MZ}"]
    return []


def cmd_verify_pr(args):
    repo, report = opt(args, "--repo"), opt(args, "--report")
    area, lane = opt(args, "--area", ""), opt(args, "--lane")
    if len(args) != 1 or not args[0].isdigit() or not report:
        raise Usage('verify-pr <pr> --repo R --report F [--area "glob,glob"] [--lane <lanes/N/state.md>]')
    pr = args[0]
    if lane is not None:
        if is_item_state(lane):
            raise Usage("--lane is the Manager's lanes/<N>/state.md")
        read_fields(lane)   # it must exist before GitHub is asked anything
    try:
        verify_pr(pr, repo, report, area)
    except Refused:
        if lane is not None:
            with file_lock(lane):
                f = read_fields(lane)
                f["pr"], f["pr-status"] = pr, "REDIRECTED"
                write_fields(lane, f)
        raise
    if lane is not None:
        with file_lock(lane):
            f = read_fields(lane)
            f["pr"], f["pr-status"] = pr, "READY"
            if f.get("wait-kind", "none") != "merge":
                f["wait-since"], f["wait-kind"] = now(), "merge"
            write_fields(lane, f)


def required_checks(prof):
    return [x.strip() for x in prof.get("required_checks") or [] if isinstance(x, str) and x.strip()]


def cmd_required_checks(args):
    repo = opt(args, "--repo")
    no_rest(args)
    for name in required_checks(load_profile(repo)[1]):
        print(name)


def verify_pr(pr, repo, report, area):
    _, prof = load_profile(repo)
    base = prof.get("base_branch")
    v = gh_json(["pr", "view", pr, "--repo", repo, "--json",
                 "state,isDraft,headRefOid,baseRefName,files,autoMergeRequest,commits,"
                 "mergeable,reviewDecision"])
    fails = []
    if v.get("state") != "OPEN":
        fails.append(f"PR is {v.get('state')}")
    if v.get("isDraft"):
        fails.append("PR is a draft")
    if v.get("baseRefName") != base:
        fails.append(f"base is {v.get('baseRefName')}, not {base}")
    if v.get("autoMergeRequest"):
        fails.append("auto-merge is on")
    # A PR the human cannot merge, or one a reviewer sent back, is not ready (2026-11-15 audit).
    if v.get("mergeable") == "CONFLICTING":
        fails.append("conflicts with the base branch")
    elif v.get("mergeable") == "UNKNOWN":
        fails.append("mergeability unknown (GitHub is still computing it): run verify-pr again in a minute")
    if v.get("reviewDecision") == "CHANGES_REQUESTED":
        fails.append("a reviewer requested changes")
    head = v.get("headRefOid", "")
    files = [f.get("path", "") for f in v.get("files") or []]
    if len(files) >= 100:   # gh lists at most 100 files: the area check would miss the rest
        fails.append(f"{len(files)}+ files: too many to check against the area; split the PR")
    commits = v.get("commits") or []
    last_commit = parse_time(commits[-1]["committedDate"]) if commits and commits[-1].get("committedDate") else None

    full = read_text(report)
    header = full.split("\n---", 1)[0]
    note = prof.get("note_field") or "PLAN-NOTE"
    if not re.search(rf"^{re.escape(note)}:[ \t]*\S", full, re.M):
        fails.append(f"report has no '{note}: <one line>' (the profile's note_field)")
    m = re.search(r"HEAD:\s*([0-9a-f]{7,40})", header)
    if not m or not head.startswith(m.group(1)):
        fails.append(f"report HEAD {m.group(1) if m else 'missing'} is not the PR head {head[:7]}")
    fails += report_checks(header, files, prof)
    fails += gate_check(header, last_commit)

    checks = gh_json(["pr", "checks", pr, "--repo", repo, "--json", "name,bucket"])
    if not checks:
        fails.append("no CI checks registered")
    else:
        failing = [c["name"] for c in checks if c.get("bucket") in ("fail", "cancel")]
        pending = [c["name"] for c in checks if c.get("bucket") == "pending"]
        if failing:
            fails.append("CI failing: " + ", ".join(failing))
        if pending:
            fails.append("CI pending: " + ", ".join(pending))
    # A required check that never registered looks like green CI (2026-11-12: a deploy check
    # had not started while the test check was already green).
    names = {c.get("name", "") for c in checks or []}
    missing = [n for n in required_checks(prof) if n not in names]
    if missing:
        fails.append("required check not registered: " + ", ".join(missing))

    owner, name = repo.split("/")
    t = gh_json(["api", "graphql", "-f", f"query={THREADS_QUERY}", "-F", f"owner={owner}",
                 "-F", f"name={name}", "-F", f"number={pr}"])
    try:
        nodes = t["data"]["repository"]["pullRequest"]["reviewThreads"]["nodes"]
    except (KeyError, TypeError):
        raise Broken(f"ERROR unexpected review-threads answer: {str(t)[:200]}")
    open_threads = sum(1 for n in nodes if not n.get("isResolved"))
    if open_threads:
        fails.append(f"{open_threads} unresolved review thread(s)")

    globs = [g.strip() for g in area.split(",") if g.strip()]
    if globs:
        outside = [p for p in files if not any(fnmatchcase(p, g) for g in globs)]
        if outside:
            more = f" (+{len(outside) - 3})" if len(outside) > 3 else ""
            fails.append("outside the chunk's area: " + ", ".join(outside[:3]) + more)

    if fails:
        raise Refused(f"VERIFY FAIL {pr}: " + "; ".join(fails))
    print(f"VERIFY OK {pr} {head[:7]}")


def stall_line(path, window_h, max_attempts):
    f = read_fields(path)
    status = f.get("chunk-status", "none")
    if f.get("paused") == "yes" or status in CHUNK_DONE | {"PLAN", "DECISION", "BLOCKED", "PAUSED"}:
        return f"STALL IDLE chunk-status={status} paused={f.get('paused')}"
    if f.get("pr-status") == "READY":
        return f"STALL IDLE PR #{f.get('pr')} READY, waiting on the merge"
    ls = f.get("lane-state", "none")
    ls_path = pathlib.Path(ls) if ls not in ("", "none") else None
    if ls_path and ls_path.is_file():
        g = read_fields(ls_path)
        a, key = g.get("attempt", "0"), g.get("key", "none")
        ack = 0
        la = f.get("loop-ack", "none")
        if la not in ("", "none") and key not in ("", "none") and la.rsplit("#", 1)[0] == key.rsplit("#", 1)[0]:
            tail = la.rsplit("#", 1)[-1]
            ack = int(tail) if tail.isdigit() else 0
        # Attempts the chunk plan planned (an item run in batches) are work, not a loop
        # (2026-11-12: an item run in 4 planned batches tripped STALL LOOP).
        pa = g.get("planned-attempts", "none")
        planned = int(pa) if pa.isdigit() and int(pa) > 0 else 1
        limit = ack + max_attempts if ack else max_attempts + planned - 1
        if a.isdigit() and int(a) > limit:
            return f"STALL LOOP {key} attempt={a}" + (f" planned={planned}" if planned > 1 else "")
    last = f.get("progress-line", "none")
    if last in ("", "none"):
        last = f.get("last-line", "none")
    if last in ("", "none"):
        if not (ls_path and ls_path.is_file()):
            return "STALL OK no line yet, no lane-state"
        ref = datetime.fromtimestamp(ls_path.stat().st_mtime, timezone.utc)
        last = ref.strftime("%Y-%m-%dT%H:%M:%SZ")
    else:
        try:
            ref = parse_time(last)
        except ValueError:
            return f"STALL QUIET unreadable stamp {last!r} in {show_path(path)}: fix progress-line"
    age_h = (datetime.now(timezone.utc) - ref).total_seconds() / 3600
    if age_h > window_h:
        return f"STALL QUIET {age_h:.1f}h since {last}"
    return f"STALL OK last line {int(age_h * 60)}m ago"


def cmd_stall_check(args):
    repo = opt(args, "--repo")
    window, maxa = opt(args, "--window-h"), opt(args, "--max-attempts")
    every, hours = opt(args, "--every", "300"), opt(args, "--hours", "12")
    watch = flag(args, "--watch")
    if len(args) != 1:
        raise Usage("stall-check <lanes/N/state.md> [--repo R] [--window-h H] [--max-attempts M] "
                    "[--watch [--every S] [--hours H]]")
    prof = load_profile(repo)[1] if repo else {}
    try:
        window_h = float(window if window is not None else prof.get("progress_window_h", 3))
        max_attempts = int(maxa if maxa is not None else prof.get("max_attempts", 3))
        every_s, hours_f = int(every), float(hours)
    except ValueError:
        raise Usage("--window-h, --hours are numbers; --max-attempts, --every are whole numbers")
    path = args[0]
    if not watch:
        print(stall_line(path, window_h, max_attempts))
        return
    end = time.time() + hours_f * 3600
    while time.time() < end:
        line = stall_line(path, window_h, max_attempts)
        if not line.startswith("STALL OK"):
            print(line)
            return
        time.sleep(max(1, min(every_s, end - time.time())))
    print(f"STALL OK after {hours}h")


def read_holder(d):
    h = d / "holder"
    return read_text(h).strip() if h.exists() else "? (no holder file)"


def cmd_lock(args):
    if not args:
        raise Usage("lock acquire|release|show|break ...")
    sub = args.pop(0)
    locks = HOME / "locks"
    locks.mkdir(parents=True, exist_ok=True)
    if sub == "show":
        names = [args.pop(0)] if args else sorted(p.name for p in locks.iterdir() if p.is_dir())
        no_rest(args)
        if not names:
            print("NO LOCKS")
        for n in names:
            d = locks / n
            print(f"{n}: {read_holder(d)}" if d.is_dir() else f"{n}: free")
        return
    if not args:
        raise Usage(f"lock {sub} <resource> ...")
    res = args.pop(0)
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", res):
        raise Usage(f"resource must be lower-case letters, digits and dashes, got {res!r}")
    d = locks / res
    def full_holder(verb):
        # A key like t1/L1/K1/x#2 repeats in every project: the holder carries its repository,
        # or one project could take or release another's lock (2026-11-15 audit).
        h, r = opt(args, "--holder"), opt(args, "--repo")
        no_rest(args)
        if not h or not r:
            raise Usage(f"lock {verb} <resource> --holder H --repo R")
        project_dir(r)
        check_value("holder", h)
        return f"{r}:{h}"
    if sub == "acquire":
        holder = full_holder("acquire")
        try:
            d.mkdir()
        except FileExistsError:
            cur = read_holder(d)
            if holder_base(cur.split(" since ")[0]) == holder_base(holder):
                write_atomic(d / "holder", f"{holder} since {now()}\n")
                print(f"ACQUIRED {res} {holder} (already held by this holder)")
                return
            raise Refused(f"HELD {res} by {cur}")
        write_atomic(d / "holder", f"{holder} since {now()}\n")
        print(f"ACQUIRED {res} {holder}")
    elif sub == "release":
        holder = full_holder("release")
        if not d.exists():
            raise NotFound(f"NOT HELD {res}")
        cur = read_holder(d).split(" since ")[0].strip()
        if holder_base(cur) != holder_base(holder):
            raise Refused(f"REFUSED {res} is held by {cur!r}, not {holder!r}")
        shutil.rmtree(d)
        print(f"RELEASED {res}")
    elif sub == "break":
        by = opt(args, "--by")
        no_rest(args)
        if not by:
            raise Usage("lock break <resource> --by H")
        if not d.exists():
            raise NotFound(f"NOT HELD {res}")
        was = read_holder(d)
        with open(locks / "broken.log", "a", encoding="utf-8") as fh:
            fh.write(f"{now()} {res} held by [{was}] broken by {by}\n")
        shutil.rmtree(d)
        print(f"BROKEN {res} (was {was})")
    else:
        raise Usage(f"unknown lock command {sub!r}")


CHUNK_KINDS = ("contract", "foundation", "impl", "assembly")


def parse_cut(path):
    """The cut file (references/decomposition.md, "The cut file"): one `## K<n> <kind> — <title>`
    block per chunk with `AREA:`, `AFTER:`, `ITEMS:` and `RESOURCES:` lines (a field may repeat,
    and an indented line after a field continues it), plus the free-text `DONE WHEN:` and
    `SEAMS:`. Anything else inside a chunk, and any `##`/`###` heading that is not a chunk, is
    refused: a line the parser skips is an area nobody checks (2026-11-15 audit: a heading without
    the dash vanished and its AREA was added to the chunk above)."""
    chunks, cur, bad = {}, None, []
    last = None                                     # the list field an indented line continues
    for no, line in enumerate(read_text(path).splitlines(), 1):
        if re.match(r"^#{2,}\s", line):
            m = re.match(r"^##\s+(K\d+)\s+(\S+)\s+[—–-]+\s*(.*)$", line)
            if not m or m.group(2) not in CHUNK_KINDS:
                bad.append(f"line {no}: a chunk heading is '## K<n> <{'|'.join(CHUNK_KINDS)}> — "
                           f"<title>', got {line.strip()!r}")
                cur, last = None, None
                continue
            cid = m.group(1)
            if cid in chunks:
                bad.append(f"line {no}: {cid} twice")
            cur = chunks[cid] = {"kind": m.group(2), "title": m.group(3).strip(), "area": [],
                                 "after": [], "items": [], "resources": []}
            last = None
            continue
        if cur is None or not line.strip():
            if not line.strip():
                last = None
            continue
        m = re.match(r"^(AREA|AFTER|ITEMS|RESOURCES):\s*(.*)$", line.strip())
        if m:
            last = m.group(1).lower()
            text = m.group(2)
        elif re.match(r"^(DONE WHEN|SEAMS):", line.strip()):
            last = None
            continue
        elif line[:1] in (" ", "\t") and last:
            text = line.strip()
        else:
            bad.append(f"line {no}: not a field of chunk {list(chunks)[-1]}: {line.strip()[:60]!r} "
                       f"(fields: AREA, AFTER, ITEMS, RESOURCES, DONE WHEN, SEAMS)")
            continue
        vals = [v.strip() for v in re.split(r"[,;]", text) if v.strip()]
        if [v.lower() for v in vals] == ["none"]:
            vals = []
        cur[last] += vals
    return chunks, bad


def area_glob_problem(g):
    """A glob verify-pr would read differently from what its author meant, or not at all."""
    if "{" in g or "}" in g:
        return "braces are not globs here; list each path"
    if "\\" in g:
        return "use / not \\"
    if g.startswith("./") or g.startswith("/"):
        return "paths are relative to the repository root, without ./ or /"
    if g.endswith("/"):
        return "a folder is <folder>/**"
    return None


def glob_prefix(g):
    m = re.search(r"[*?\[]", g)
    return g if not m else g[:m.start()]


def globs_may_overlap(a, b):
    """Could one path match both globs (fnmatch, as verify-pr reads AREA: `*` crosses `/`)?
    Conservative: a glob whose literal prefix is a prefix of the other's covers it."""
    a, b = a.lower(), b.lower()       # conservative: on a case-insensitive disk these are one file
    if a == b:
        return True       # conservative: on a case-insensitive disk these are one file
    sample = lambda g: re.sub(r"\[[^\]]*\]", "x", g).replace("**", "x").replace("*", "x").replace("?", "x")
    if fnmatchcase(sample(a), b) or fnmatchcase(sample(b), a):
        return True
    pa, pb = glob_prefix(a), glob_prefix(b)
    if pa != a and pb.startswith(pa):
        return True
    if pb != b and pa.startswith(pb):
        return True
    return False


def cmd_cut_check(args):
    """Can the chunks of a cut run in parallel without two lanes changing one file? Two chunks
    may share files only when one comes AFTER the other (its last PR merged first)."""
    repo = opt(args, "--repo")
    files_from = opt(args, "--files")
    max_lanes_s = opt(args, "--max-lanes")
    if len(args) != 1:
        raise Usage("cut-check <cut.md> [--repo R] [--files <list>] [--max-lanes N]")
    chunks, fails = parse_cut(args[0])
    notes = []
    if not chunks:
        fails.append("no chunks ('## K<n> <kind> — <title>')")
    prof = load_profile(repo)[1] if repo else {}
    max_lanes = int(max_lanes_s) if max_lanes_s and max_lanes_s.isdigit() else prof.get("max_lanes", 1)
    files = None
    if files_from:
        files = [l.strip() for l in read_text(files_from).splitlines() if l.strip()]
    elif prof.get("main_checkout"):
        r = subprocess.run(["git", "-C", prof["main_checkout"], "ls-files"], capture_output=True,
                           text=True, encoding="utf-8", errors="replace")
        if r.returncode == 0:
            files = r.stdout.split()
        else:
            notes.append(f"git ls-files failed in {prof['main_checkout']}: only globs compared")
    if files is None and not notes:
        notes.append("no file list (--files or a profile's main_checkout): only globs compared")

    if not repo or "max_lanes" not in prof:
        if not max_lanes_s:
            notes.append("no max_lanes in the profile: capped at 1 lane (set it in project.json)")
    for cid, c in chunks.items():
        if not c["area"]:
            fails.append(f"{cid} has no AREA")
        for g in c["area"]:
            why = area_glob_problem(g)
            if why:
                fails.append(f"{cid} AREA {g!r}: {why}")
        for a in c["after"]:
            if a not in chunks:
                fails.append(f"{cid} AFTER {a}: no such chunk")
        if files is not None:
            c["files"] = {p for p in files if any(fnmatchcase(p, g) for g in c["area"])}
            if not c["files"] and c["kind"] != "contract":
                notes.append(f"{cid}: AREA matches no existing file (new files only?)")
    # Transitive AFTER; a cycle is a cut no lane can start.
    before = {}
    def deps(cid, path=()):
        if cid in before:
            return before[cid]
        if cid in path:
            fails.append("AFTER cycle: " + " -> ".join(path + (cid,)))
            return set()
        out = set()
        for a in chunks.get(cid, {}).get("after", []):
            if a in chunks:
                out |= {a} | deps(a, path + (cid,))
        before[cid] = out
        return out
    for cid in chunks:
        deps(cid)

    ids = sorted(chunks, key=lambda k: int(k[1:]))
    seen_items = {}
    for cid in ids:
        for it in chunks[cid]["items"]:
            if it in seen_items:
                fails.append(f"item {it} in {seen_items[it]} and {cid}")
            seen_items[it] = cid
    for i, x in enumerate(ids):
        for y in ids[i + 1:]:
            if x in before[y] or y in before[x]:
                continue                      # one runs after the other: they may share files
            cx, cy = chunks[x], chunks[y]
            pairs = [f"{a} ~ {b}" for a in cx["area"] for b in cy["area"] if globs_may_overlap(a, b)]
            lx = {p.lower(): p for p in cx.get("files", set())}
            shared = sorted(lx[k] for k in lx.keys() & {p.lower() for p in cy.get("files", set())})
            if shared:
                more = f" (+{len(shared) - 3})" if len(shared) > 3 else ""
                fails.append(f"{x} and {y} run in parallel and both may change "
                             + ", ".join(shared[:3]) + more)
            elif pairs:
                fails.append(f"{x} and {y} run in parallel and their areas may overlap: "
                             + ", ".join(pairs[:3]))
            res = sorted(set(cx["resources"]) & set(cy["resources"]))
            if res:
                notes.append(f"{x} and {y} share {', '.join(res)}: they queue on its lock")
    # Waves: a chunk's wave is one more than the deepest chunk it comes after.
    wave = {}
    def depth(cid):
        if cid not in wave:
            wave[cid] = 0  # cycle guard
            wave[cid] = 1 + max((depth(a) for a in chunks[cid]["after"] if a in chunks), default=0)
        return wave[cid]
    waves = {}
    for cid in ids:
        waves.setdefault(depth(cid), []).append(cid)
    width = max((len(v) for v in waves.values()), default=0)
    # A "round" is one chunk's run on one lane; a wave of n chunks on L lanes takes ceil(n/L)
    # rounds, and the waves run one after another. Lanes past the widest wave buy nothing.
    rounds = lambda n_lanes: sum(-(-len(v) // n_lanes) for v in waves.values())
    options = []
    for n in range(1, width + 1):
        if not options or rounds(n) < options[-1][1]:
            options.append((n, rounds(n)))
    for cid in ids:
        c = chunks[cid]
        nf = f" files={len(c['files'])}" if "files" in c else ""
        print(f"CHUNK {cid} {c['kind']} wave={wave[cid]} after={','.join(c['after']) or 'none'}"
              f" area={','.join(c['area']) or 'none'}{nf}")
    print("WAVES " + " | ".join(f"{w}: {','.join(v)}" for w, v in sorted(waves.items()))
          + f" — parallel width {width}")
    for n in notes:
        print(f"NOTE {n}")
    if fails:
        raise Refused("CUT FAIL " + "; ".join(fails))
    if options:
        print("LANES " + " | ".join(f"{n} lane{'s' if n > 1 else ''}: {r} round{'s' if r > 1 else ''}"
                                    for n, r in options) + f" (fastest: {width})")
    print(f"CUT OK lanes={max(1, min(width, max_lanes))} (width {width}, max_lanes {max_lanes})")


PROJECTS = pathlib.Path(os.environ.get("LIPOK_PROJECTS_DIR",
                                       pathlib.Path.home() / ".claude" / "projects"))
# Relative cost of one token of each kind at Anthropic's list ratios (input = 1): enough to compare
# who in a task spent what, never a bill.
USAGE_WEIGHTS = {"in": 1.0, "cw": 1.25, "cr": 0.1, "out": 5.0}


def transcript_folder(value):
    """A transcript folder from a folder name under PROJECTS, a path to it, or a session's working
    directory (Claude Code names the folder after it, every non-alphanumeric character a '-')."""
    value = value.rstrip("/\\") or value                # a trailing slash used to drop the folder
    m = re.match(r"^/([A-Za-z])/(.*)$", value)          # Git Bash /c/Dev/x
    if m and os.name == "nt":
        value = f"{m.group(1).upper()}:/{m.group(2)}"
    p = pathlib.Path(value)
    # Only a folder right under PROJECTS is a transcript folder; a working directory that happens
    # to hold a *.jsonl is a working directory (2026-11-15 audit).
    if p.is_dir() and p.resolve().parent == PROJECTS.resolve():
        return p
    if not re.search(r"[/\\:]", value) and (PROJECTS / value).is_dir():   # a bare folder name
        return PROJECTS / value
    return PROJECTS / re.sub(r"[^A-Za-z0-9]", "-", value)


def usage_of(files, since, until, seen):
    """Token usage of the assistant messages in these transcripts inside [since, until]. A message
    is split over several records that repeat its usage: each message id counts once."""
    tot = {"turns": 0, "in": 0, "cw": 0, "cr": 0, "out": 0}
    lo, hi = parse_time(since), parse_time(until)        # times, not strings: ".500Z" > "Z"
    for f in files:
        try:
            fh = open(f, encoding="utf-8", errors="replace")
        except OSError:
            continue
        with fh:
            for line in fh:
                if '"usage"' not in line:
                    continue
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                try:
                    ts = parse_time(r.get("timestamp") or "")
                except ValueError:
                    continue
                if not (lo <= ts <= hi):
                    continue
                m = r.get("message")
                u = m.get("usage") if isinstance(m, dict) else None
                if not isinstance(u, dict):
                    continue
                mid = m.get("id") or f"{f}:{ts}"
                if mid in seen:
                    continue
                seen.add(mid)
                tot["turns"] += 1
                tot["in"] += u.get("input_tokens") or 0
                tot["cw"] += u.get("cache_creation_input_tokens") or 0
                tot["cr"] += u.get("cache_read_input_tokens") or 0
                tot["out"] += u.get("output_tokens") or 0
    tot["weight"] = sum(tot[k] * w for k, w in USAGE_WEIGHTS.items())
    return tot


def subagent_files(main_files):
    out = []
    for f in main_files:
        out += sorted((f.parent / f.stem / "subagents").glob("*.jsonl"))
    return out


def human(n):
    for unit, d in (("M", 1e6), ("k", 1e3)):
        if n >= d:
            return f"{n / d:.1f}{unit}"
    return str(int(n))


def cmd_usage(args):
    """Who in a task spent the tokens: the Manager (its turns and its own subagents, such as the
    chunk reviewer), the workers' own turns (leading the chunk), and the executors (the workers'
    subagents: item work and reviews). Read from the transcripts on disk; no model is called.
    Added 2026-11-14: the pilot's split was counted by hand (Manager 8%, worker 7%, executors 85%)."""
    managers = []
    while "--manager" in args:
        managers.append(opt(args, "--manager"))
    workers = []
    while "--worker" in args:
        workers.append(opt(args, "--worker"))
    since = opt(args, "--since")
    until = opt(args, "--until")
    if len(args) != 1:
        raise Usage("usage <task folder> [--manager <dir|file|cwd>]... [--worker <dir>]... "
                    "[--since T] [--until T]")
    t = pathlib.Path(args[0])
    tj = read_json(t / "task.json") if (t / "task.json").is_file() else None
    if tj is None:
        raise NotFound(f"NO TASK {show_path(t)}")
    tid = tj.get("id") or t.name
    since = since or tj.get("created") or "1970-01-01T00:00:00Z"
    until = until or tj.get("closed") or now()
    for name, v in (("--since", since), ("--until", until)):
        try:
            parse_time(v)
        except ValueError:
            raise Usage(f"{name} must be an ISO time like 2026-11-12T13:00:00Z, got {v!r}")
    # Transcripts that name this task's folder (any slash, JSON-escaped or not).
    marker = re.compile(re.escape(t.parent.parent.name) + r"[/\\]+tasks[/\\]+" + re.escape(tid)
                        + r"(?![A-Za-z0-9])")

    def names_task(f):
        try:
            with open(f, encoding="utf-8", errors="replace") as fh:
                return any(marker.search(line) for line in fh)
        except OSError:
            return False

    man_main = []
    for v in managers:
        if v.endswith(".jsonl"):
            if not pathlib.Path(v).is_file():
                raise NotFound(f"NO TRANSCRIPT {v}")
            man_main.append(pathlib.Path(v))
        else:
            d = transcript_folder(v)
            if not d.is_dir():
                raise NotFound(f"NO TRANSCRIPT FOLDER {show_path(d)}")
            man_main += [f for f in sorted(d.glob("*.jsonl")) if names_task(f)]

    # Worker folders: every lane's worker-dir, every earlier worker of a lane (the worktree folder
    # is lipok-<tid>-l<N>[-r<k>]-<hex> beside the current one), and any given with --worker.
    wdirs = []
    for s in sorted(t.glob("lanes/*/state.md")):
        wd = read_fields(s).get("worker-dir", "none")
        if wd in ("", "none"):
            continue
        d = transcript_folder(wd)
        wdirs.append(d)
        prefix = d.name.split("--claude-worktrees-")[0]
        for name in ("lipok", "archon"):         # archon-: worktrees from before the rename (2026-11-15)
            wdirs += sorted(PROJECTS.glob(f"{prefix}--claude-worktrees-{name}-{tid}-l*"))
    for v in workers:
        d = transcript_folder(v)
        if not d.is_dir():
            raise NotFound(f"NO TRANSCRIPT FOLDER {show_path(d)}")
        wdirs.append(d)
    wdirs = list(dict.fromkeys(d.resolve() for d in wdirs if d.is_dir()))
    wk_main = [f for d in wdirs for f in sorted(d.glob("*.jsonl"))]

    seen = set()
    rows = []
    if man_main:
        rows.append(("manager", usage_of(man_main + subagent_files(man_main), since, until, seen)))
    rows.append(("worker", usage_of(wk_main, since, until, seen)))
    rows.append(("executors", usage_of(subagent_files(wk_main), since, until, seen)))
    total = sum(r["weight"] for _, r in rows) or 1
    print(f"USAGE {tid} {since}..{until} lanes' worker folders={len(wdirs)}"
          f" manager transcripts={len(man_main)}")
    for name, r in rows:
        print(f"{name:<10} turns={r['turns']} out={human(r['out'])} cache-read={human(r['cr'])}"
              f" cache-write={human(r['cw'])} in={human(r['in'])} weight={human(r['weight'])}"
              f" share={100 * r['weight'] / total:.0f}%")
    if not man_main:
        print("manager    not counted: give --manager <the Manager's working directory>")
    coord = sum(r["weight"] for n, r in rows if n != "executors")
    print(f"COORDINATION {100 * coord / total:.0f}% (manager + workers' own turns; "
          f"weights in=1 cache-write=1.25 cache-read=0.1 out=5)")


COMMANDS = {
    "usage": cmd_usage, "cut-check": cmd_cut_check, "profile-set": cmd_profile_set,
    "root": cmd_root, "profile": cmd_profile, "task-new": cmd_task_new,
    "task-active": cmd_task_active, "task-set": cmd_task_set, "task-close": cmd_task_close,
    "item": cmd_item, "bump": cmd_bump, "get": cmd_get, "set": cmd_set, "show": cmd_show,
    "lane-env": cmd_lane_env, "lock": cmd_lock, "chunk": cmd_chunk,
    "verify-pr": cmd_verify_pr, "stall-check": cmd_stall_check, "line": cmd_line,
    "book": cmd_book, "required-checks": cmd_required_checks,
}


def main(argv):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass
    if len(argv) < 2 or argv[1] not in COMMANDS:
        print(__doc__)
        return 2
    try:
        COMMANDS[argv[1]](list(argv[2:]))
        return 0
    except Usage as e:
        print(f"USAGE {e}")
        return 2
    except NotFound as e:
        print(str(e))
        return 3
    except Refused as e:
        print(str(e))
        return 4
    except Broken as e:
        print(str(e))
        return 1
    except OSError as e:
        print(f"ERROR {type(e).__name__}: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
