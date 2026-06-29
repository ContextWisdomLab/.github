import json
import time

import pytest

from scripts.ci import pr_review_autofix_context as context
from scripts.ci import pr_review_fix_scheduler as fix


def make_pr(**overrides):
    value = {
        "number": 7,
        "isDraft": False,
        "baseRefName": "main",
        "baseRefOid": "b" * 40,
        "headRefName": "feature",
        "headRefOid": "a" * 40,
        "headRepository": {"nameWithOwner": "owner/repo"},
        "reviews": {"nodes": []},
        "reviewThreads": {"nodes": []},
    }
    value.update(overrides)
    return value


def test_recent_fix_marker_is_head_scoped():
    head = "a" * 40
    comments = [{"body": f"{fix.FIX_MARKER} head_sha={head} epoch={int(time.time())} -->"}]

    assert fix.recent_fix_marker_exists(comments, head, 24 * 3600)
    assert not fix.recent_fix_marker_exists(comments, "b" * 40, 24 * 3600)


def test_needs_autofix_uses_current_head_evidence():
    head = "a" * 40
    pr = make_pr(
        headRefOid=head,
        reviews={
            "nodes": [
                {"state": "APPROVED", "author": {"login": "opencode-agent"}, "commit": {"oid": head}},
                {"state": "CHANGES_REQUESTED", "author": {"login": "opencode-agent"}, "commit": {"oid": head}},
            ]
        },
        reviewThreads={"nodes": [{"id": "thread", "isResolved": False, "isOutdated": False}]},
    )

    assert fix.needs_autofix(pr) == (
        True,
        ("current-head OpenCode requested changes", "1 active unresolved review thread(s)"),
    )


def test_process_queue_dispatches_same_repo_current_head(monkeypatch, capsys):
    pr = make_pr()
    calls = []

    monkeypatch.setattr(fix, "fetch_open_prs", lambda repo, max_prs: [pr])
    monkeypatch.setattr(fix, "needs_autofix", lambda pr: (True, ("current-head OpenCode requested changes",)))
    monkeypatch.setattr(fix, "issue_comments", lambda repo, number: [])
    monkeypatch.setattr(fix, "dispatch_autofix", lambda repo, pr, workflow, dry_run: calls.append(("dispatch", repo, pr["number"], workflow, dry_run)))
    monkeypatch.setattr(fix, "create_fix_marker", lambda repo, pr, dry_run: calls.append(("marker", repo, pr["number"], dry_run)))

    assert fix.main(["--repo", "owner/repo", "--base-branch", "main", "--dry-run"]) == 0

    assert calls == [
        ("dispatch", "owner/repo", 7, "pr-review-autofix.yml", True),
        ("marker", "owner/repo", 7, True),
    ]
    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert payload["autofix_dispatches"] == 1


def test_autofix_context_filters_outdated_threads_and_renders_checks():
    assert context.repo_parts("owner/repo") == ("owner", "repo")
    assert context.check_summary(
        [
            {"__typename": "CheckRun", "workflowName": "OpenCode Review", "name": "opencode-review", "status": "COMPLETED", "conclusion": "FAILURE"},
            {"__typename": "StatusContext", "context": "lint", "state": "SUCCESS"},
        ]
    ) == ["- OpenCode Review/opencode-review: COMPLETED FAILURE", "- lint: SUCCESS"]
    with pytest.raises(SystemExit):
        context.parse_args(["--repo", "bad repo", "--pr-number", "1", "--head-sha", "a" * 40, "--output", "out.md"])
