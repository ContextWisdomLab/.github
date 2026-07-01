"""Test for PR review merge scheduler."""
import pytest
import argparse
import json
import subprocess
from unittest.mock import patch, MagicMock

import pr_review_merge_scheduler as scheduler

def test_run_success():
    """Docstring."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="output")
        assert scheduler.run(["echo", "hello"]) == "output"

def test_run_failure():
    """Docstring."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stderr="error")
        with pytest.raises(RuntimeError, match="Command failed"):
            scheduler.run(["fail"])

def test_split_repo():
    """Docstring."""
    assert scheduler.split_repo("owner/name") == ("owner", "name")
    with pytest.raises(ValueError):
        scheduler.split_repo("owner")
    with pytest.raises(ValueError):
        scheduler.split_repo("/name")
    with pytest.raises(ValueError):
        scheduler.split_repo("owner/")

def test_gh_graphql():
    """Docstring."""
    with patch("pr_review_merge_scheduler.run") as mock_run:
        mock_run.return_value = '{"data": {}}'
        assert scheduler.gh_graphql("query", owner="owner", pageSize=100) == {"data": {}}
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert "gh" in args

def test_fetch_open_prs():
    """Docstring."""
    with patch("pr_review_merge_scheduler.gh_graphql") as mock_graphql:
        mock_graphql.side_effect = [
            {
                "data": {
                    "repository": {
                        "pullRequests": {
                            "nodes": [{"number": 1}],
                            "pageInfo": {"hasNextPage": True, "endCursor": "c1"}
                        }
                    }
                }
            },
            {
                "data": {
                    "repository": {
                        "pullRequests": {
                            "nodes": [{"number": 2}],
                            "pageInfo": {"hasNextPage": False, "endCursor": "c2"}
                        }
                    }
                }
            }
        ]
        prs = scheduler.fetch_open_prs("owner/name", 100)
        assert len(prs) == 2
        assert prs[0]["number"] == 1
        assert prs[1]["number"] == 2

def test_fetch_open_prs_limit():
    """Docstring."""
    with patch("pr_review_merge_scheduler.gh_graphql") as mock_graphql:
        mock_graphql.return_value = {
            "data": {
                "repository": {
                    "pullRequests": {
                        "nodes": [{"number": 1}],
                        "pageInfo": {"hasNextPage": True, "endCursor": "c1"}
                    }
                }
            }
        }
        prs = scheduler.fetch_open_prs("owner/name", 1)
        assert len(prs) == 1

def test_is_opencode_context():
    """Docstring."""
    assert scheduler.is_opencode_context({"__typename": "CheckRun", "name": "opencode-review"})
    assert scheduler.is_opencode_context({"__typename": "CheckRun", "checkSuite": {"workflowRun": {"workflow": {"name": "OpenCode Review"}}}})
    assert scheduler.is_opencode_context({"context": "opencode-review"})
    assert not scheduler.is_opencode_context({"context": "other"})

def test_unresolved_thread_count():
    """Docstring."""
    assert scheduler.unresolved_thread_count({"reviewThreads": {"nodes": [{"isResolved": False, "isOutdated": False}]}}) == 1
    assert scheduler.unresolved_thread_count({"reviewThreads": {"nodes": [{"isResolved": True, "isOutdated": False}]}}) == 0
    assert scheduler.unresolved_thread_count({}) == 0

def test_review_author_login():
    """Docstring."""
    assert scheduler.review_author_login({"author": {"login": "Agent"}}) == "agent"
    assert scheduler.review_author_login({}) == ""

def test_enable_auto_merge():
    """Docstring."""
    with patch("pr_review_merge_scheduler.run") as mock_run:
        scheduler.enable_auto_merge("owner/name", {"number": 1, "headRefOid": "abc"}, dry_run=False)
        mock_run.assert_called_once()

    with patch("pr_review_merge_scheduler.run") as mock_run:
        scheduler.enable_auto_merge("owner/name", {"number": 1, "headRefOid": "abc"}, dry_run=True)
        mock_run.assert_not_called()

def test_dispatch_opencode_review():
    """Docstring."""
    with patch("pr_review_merge_scheduler.run") as mock_run:
        scheduler.dispatch_opencode_review("owner/name", "workflow", {"number": 1, "baseRefName": "base", "baseRefOid": "b1", "headRefName": "head", "headRefOid": "h1"}, dry_run=False)
        mock_run.assert_called_once()

    with patch("pr_review_merge_scheduler.run") as mock_run:
        scheduler.dispatch_opencode_review("owner/name", "workflow", {"number": 1, "baseRefName": "base", "baseRefOid": "b1", "headRefName": "head", "headRefOid": "h1"}, dry_run=True)
        mock_run.assert_not_called()

def test_inspect_pr_draft():
    """Docstring."""
    assert scheduler.inspect_pr("repo", {"number": 1, "isDraft": True}, dry_run=True, trigger_reviews=True, enable_auto_merge_flag=True, workflow="w", base_branch="base").action == "skip"

def test_inspect_pr_base_ref():
    """Docstring."""
    assert scheduler.inspect_pr("repo", {"number": 1, "baseRefName": "other"}, dry_run=True, trigger_reviews=True, enable_auto_merge_flag=True, workflow="w", base_branch="base").action == "skip"

def test_inspect_pr_head_repo():
    """Docstring."""
    assert scheduler.inspect_pr("repo", {"number": 1, "baseRefName": "base", "headRepository": {"nameWithOwner": "other"}}, dry_run=True, trigger_reviews=True, enable_auto_merge_flag=True, workflow="w", base_branch="base").action == "skip"

def test_inspect_pr_unresolved():
    """Docstring."""
    pr = {"number": 1, "baseRefName": "base", "headRepository": {"nameWithOwner": "repo"}, "reviewThreads": {"nodes": [{"isResolved": False, "isOutdated": False}]}}
    assert scheduler.inspect_pr("repo", pr, dry_run=True, trigger_reviews=True, enable_auto_merge_flag=True, workflow="w", base_branch="base").action == "block"

def test_inspect_pr_changes_requested():
    """Docstring."""
    pr = {
        "number": 1, "baseRefName": "base", "headRepository": {"nameWithOwner": "repo"},
        "headRefOid": "abc",
        "reviews": {"nodes": [{"state": "CHANGES_REQUESTED", "author": {"login": "opencode-agent"}, "commit": {"oid": "abc"}}]}
    }
    assert scheduler.inspect_pr("repo", pr, dry_run=True, trigger_reviews=True, enable_auto_merge_flag=True, workflow="w", base_branch="base").action == "block"

def test_inspect_pr_approval():
    """Docstring."""
    pr = {
        "number": 1, "baseRefName": "base", "headRepository": {"nameWithOwner": "repo"},
        "headRefOid": "abc",
        "reviews": {"nodes": [{"state": "APPROVED", "author": {"login": "opencode-agent"}, "commit": {"oid": "abc"}}]}
    }
    assert scheduler.inspect_pr("repo", pr, dry_run=True, trigger_reviews=True, enable_auto_merge_flag=True, workflow="w", base_branch="base").action == "auto_merge"

    pr["autoMergeRequest"] = True
    assert scheduler.inspect_pr("repo", pr, dry_run=True, trigger_reviews=True, enable_auto_merge_flag=True, workflow="w", base_branch="base").action == "wait"

    del pr["autoMergeRequest"]
    assert scheduler.inspect_pr("repo", pr, dry_run=True, trigger_reviews=True, enable_auto_merge_flag=False, workflow="w", base_branch="base").action == "wait"

def test_inspect_pr_in_progress():
    """Docstring."""
    pr = {
        "number": 1, "baseRefName": "base", "headRepository": {"nameWithOwner": "repo"},
        "headRefOid": "abc",
        "statusCheckRollup": {"contexts": {"nodes": [{"__typename": "CheckRun", "name": "opencode-review", "status": "IN_PROGRESS"}]}}
    }
    assert scheduler.inspect_pr("repo", pr, dry_run=True, trigger_reviews=True, enable_auto_merge_flag=True, workflow="w", base_branch="base").action == "wait"

def test_inspect_pr_review_dispatch():
    """Docstring."""
    pr = {
        "number": 1, "baseRefName": "base", "headRepository": {"nameWithOwner": "repo"},
        "baseRefOid": "b1", "headRefName": "head", "headRefOid": "h1"
    }
    with patch("pr_review_merge_scheduler.dispatch_opencode_review"):
        assert scheduler.inspect_pr("repo", pr, dry_run=True, trigger_reviews=True, enable_auto_merge_flag=True, workflow="w", base_branch="base").action == "review_dispatch"
        assert scheduler.inspect_pr("repo", pr, dry_run=True, trigger_reviews=False, enable_auto_merge_flag=True, workflow="w", base_branch="base").action == "block"

def test_print_summary(capsys):
    """Docstring."""
    scheduler.print_summary([scheduler.Decision(1, "action", "reason")], dry_run=True, base_branch="base", project_flow="flow")
    captured = capsys.readouterr()
    assert "PR #1: action: reason" in captured.out
    assert '"counts": {"action": 1}' in captured.out

def test_parse_args():
    """Docstring."""
    args = scheduler.parse_args(["--repo", "r", "--base-branch", "b", "--project-flow", "f"])
    assert args.repo == "r"
    assert args.base_branch == "b"

def test_main():
    """Docstring."""
    with patch("pr_review_merge_scheduler.fetch_open_prs") as mock_fetch, \
         patch("pr_review_merge_scheduler.inspect_pr") as mock_inspect, \
         patch("pr_review_merge_scheduler.print_summary") as mock_print:
        mock_fetch.return_value = [{"number": 1}]
        mock_inspect.return_value = scheduler.Decision(1, "act", "reason")

        assert scheduler.main(["--repo", "r", "--base-branch", "b", "--project-flow", "f"]) == 0

        with pytest.raises(SystemExit) as se:
            scheduler.main(["--base-branch", "b", "--project-flow", "f"])
        with pytest.raises(SystemExit) as se:
            scheduler.main(["--repo", "r", "--project-flow", "f"])
        with pytest.raises(SystemExit) as se:
            scheduler.main(["--repo", "r", "--base-branch", "b"])


        assert scheduler.main(['--self-test']) == 0



def test_get_current_head_opencode_review_state():
    """Docstring."""
    pr = {"headRefOid": "abc"}
    assert scheduler.get_current_head_opencode_review_state(pr) is None
    pr["reviews"] = {"nodes": [{"state": "APPROVED", "author": {"login": "opencode-agent"}, "commit": {"oid": "abc"}}]}
    assert scheduler.get_current_head_opencode_review_state(pr) == "APPROVED"
    pr["reviews"]["nodes"].append({"state": "CHANGES_REQUESTED", "author": {"login": "opencode-agent"}, "commit": {"oid": "abc"}})
    assert scheduler.get_current_head_opencode_review_state(pr) == "CHANGES_REQUESTED"

def test_get_current_head_opencode_review_state_not_actionable():
    """Docstring."""
    pr = {"headRefOid": "abc"}
    pr["reviews"] = {"nodes": [{"state": "COMMENTED", "author": {"login": "opencode-agent"}, "commit": {"oid": "abc"}}]}
    assert scheduler.get_current_head_opencode_review_state(pr) is None

    pr["reviews"]["nodes"].append({"state": "DISMISSED", "author": {"login": "opencode-agent"}, "commit": {"oid": "abc"}})
    assert scheduler.get_current_head_opencode_review_state(pr) is None


def test_opencode_in_progress_continue():
    """Docstring."""
    pr = {
        "statusCheckRollup": {
            "contexts": {
                "nodes": [
                    {"__typename": "CheckRun", "name": "other-review"},
                    {"__typename": "CheckRun", "name": "opencode-review", "status": "IN_PROGRESS"}
                ]
            }
        }
    }
    assert scheduler.opencode_in_progress(pr)

def test_opencode_in_progress_completed():
    """Docstring."""
    pr = {
        "statusCheckRollup": {
            "contexts": {
                "nodes": [
                    {"__typename": "CheckRun", "name": "opencode-review", "status": "COMPLETED"}
                ]
            }
        }
    }
    assert not scheduler.opencode_in_progress(pr)
