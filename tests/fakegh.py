"""Fake gh for lipok.py tests. Scenario from $FAKE_GH_CASE; JSON on stdout."""
import json, os, sys
case = os.environ.get("FAKE_GH_CASE", "good")
a = sys.argv[1:]
head = "abc1234def5678"
if a[:2] == ["pr", "view"] and "state,mergedAt,mergeCommit" in a:
    if case == "merged":
        print(json.dumps({"state": "MERGED", "mergedAt": "2026-01-01T02:30:00Z",
                          "mergeCommit": {"oid": "fedcba9876543210"}}))
    else:
        print(json.dumps({"state": "OPEN", "mergedAt": None, "mergeCommit": None}))
elif a[:2] == ["pr", "view"]:
    print(json.dumps({
        "state": "OPEN", "isDraft": case == "draft", "headRefOid": head,
        "baseRefName": "main", "autoMergeRequest": None,
        "files": [{"path": "src/app.js"}, {"path": "docs/x.md"}] + ([{"path": "other/y.js"}] if case == "outside" else []),
        "commits": [{"committedDate": "2026-01-01T00:00:00Z"}],
    }))
elif a[:2] == ["pr", "checks"]:
    if case == "nochecks":
        print("[]")
    else:
        print(json.dumps([{"name": "build", "bucket": "fail" if case == "cifail" else "pass"},
                          {"name": "lint", "bucket": "pending" if case == "pending" else "pass"}]))
        sys.exit(8 if case == "pending" else 0)
elif a[:2] == ["api", "graphql"]:
    nodes = [{"isResolved": True}] + ([{"isResolved": False}] if case == "threads" else [])
    print(json.dumps({"data": {"repository": {"pullRequest": {"reviewThreads": {"nodes": nodes}}}}}))
else:
    print("unknown", file=sys.stderr); sys.exit(1)
