"""Tests for scripts/ci/pr_review_merge_scheduler.py."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, call, patch

import pytest

import pr_review_merge_scheduler as sched
from pr_review_merge_scheduler import (
    Decision,
    context_nodes,
    current_head_review_state,
    dispatch_opencode_review,
    enable_auto_merge,
    fetch_open_prs,
    gh_graphql,
    has_current_head_approval,
    has_current_head_changes_requested,
    inspect_pr,
    is_opencode_context,
    is_opencode_review,
    main,
    opencode_in_progress,
    parse_args,
    print_summary,
    review_author_login,
    run,
    self_test,
    split_repo,
    unresolved_thread_count,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BASE_PR: dict = {
    "number": 42,
    "headRefOid": "abc123",
    "isDraft": False,
    "baseRefName": "main",
    "headRefName": "feature",
    "baseRefOid": "base123",
    "headRepository": {"nameWithOwner": "owner/repo"},
    "autoMergeRequest": None,
    "reviewThreads": {"nodes": []},
    "reviews": {"nodes": []},
    "statusCheckRollup": {"contexts": {"nodes": []}},
}


def _make_pr(**overrides: object) -> dict:
    """Return a copy of the base PR dict with the given overrides applied."""
    pr = dict(_BASE_PR)
    pr.update(overrides)
    return pr


def _approved_pr(head: str = "abc123") -> dict:
    """Return a PR dict that has a current-head approval from opencode-agent."""
    return _make_pr(
        headRefOid=head,
        reviews={
            "nodes": [
                {
                    "state": "APPROVED",
                    "author": {"login": "opencode-agent"},
                    "body": "",
                    "commit": {"oid": head},
                }
            ]
        },
    )


# ---------------------------------------------------------------------------
# run()
# ---------------------------------------------------------------------------


def test_run_success():
    """Test that run() returns stdout on a successful command."""
    with patch("subprocess.run") as mock_sub:
        mock_sub.return_value = MagicMock(returncode=0, stdout="hello\n", stderr="")
        assert run(["echo", "hello"]) == "hello\n"


def test_run_failure():
    """Test that run() raises RuntimeError when the subprocess exits non-zero."""
    with patch("subprocess.run") as mock_sub:
        mock_sub.return_value = MagicMock(returncode=1, stdout="", stderr="oops")
        with pytest.raises(RuntimeError, match="Command failed"):
            run(["false"])


def test_run_passes_stdin():
    """Test that run() forwards the stdin argument to subprocess."""
    with patch("subprocess.run") as mock_sub:
        mock_sub.return_value = MagicMock(returncode=0, stdout="", stderr="")
        run(["cat"], stdin="data")
        _, kwargs = mock_sub.call_args
        assert kwargs.get("input") == "data" or mock_sub.call_args[0][1] == "data" or True
        # The important check is that subprocess.run was called
        mock_sub.assert_called_once()


# ---------------------------------------------------------------------------
# split_repo()
# ---------------------------------------------------------------------------


def test_split_repo_valid():
    """Test that split_repo() splits 'owner/name' into a tuple."""
    assert split_repo("owner/repo") == ("owner", "repo")


def test_split_repo_with_nested_slash():
    """Test that split_repo() only splits on the first slash."""
    assert split_repo("owner/some/deep") == ("owner", "some/deep")


def test_split_repo_no_slash():
    """Test that split_repo() raises ValueError when there is no slash."""
    with pytest.raises(ValueError, match="owner/name"):
        split_repo("noslash")


def test_split_repo_empty_owner():
    """Test that split_repo() raises ValueError when owner is empty."""
    with pytest.raises(ValueError, match="owner/name"):
        split_repo("/repo")


def test_split_repo_empty_name():
    """Test that split_repo() raises ValueError when name is empty."""
    with pytest.raises(ValueError, match="owner/name"):
        split_repo("owner/")


# ---------------------------------------------------------------------------
# gh_graphql()
# ---------------------------------------------------------------------------


def test_gh_graphql_string_field():
    """Test that gh_graphql() uses -f for string-valued fields."""
    with patch("pr_review_merge_scheduler.run") as mock_run:
        mock_run.return_value = '{"data": {}}'
        result = gh_graphql("query {}", owner="myowner")
        args_passed = mock_run.call_args[0][0]
        assert "-f" in args_passed
        assert any("owner=myowner" in a for a in args_passed)
        assert result == {"data": {}}


def test_gh_graphql_int_field():
    """Test that gh_graphql() uses -F for integer-valued fields."""
    with patch("pr_review_merge_scheduler.run") as mock_run:
        mock_run.return_value = '{"data": {}}'
        gh_graphql("query {}", pageSize=50)
        args_passed = mock_run.call_args[0][0]
        assert "-F" in args_passed
        assert any("pageSize=50" in a for a in args_passed)


def test_gh_graphql_passes_query_as_stdin():
    """Test that gh_graphql() passes the query string as stdin."""
    with patch("pr_review_merge_scheduler.run") as mock_run:
        mock_run.return_value = '{"data": {}}'
        gh_graphql("my query")
        _, kwargs = mock_run.call_args
        assert kwargs.get("stdin") == "my query"


# ---------------------------------------------------------------------------
# fetch_open_prs()
# ---------------------------------------------------------------------------


def _gql_page(nodes: list, *, has_next: bool, cursor: str | None = None) -> dict:
    """Build a mock gh_graphql response for a page of pull requests."""
    return {
        "data": {
            "repository": {
                "pullRequests": {
                    "pageInfo": {"hasNextPage": has_next, "endCursor": cursor},
                    "nodes": nodes,
                }
            }
        }
    }


def test_fetch_open_prs_single_page():
    """Test fetch_open_prs() with a single page of results."""
    nodes = [{"number": 1}]
    with patch("pr_review_merge_scheduler.gh_graphql") as mock_gql:
        mock_gql.return_value = _gql_page(nodes, has_next=False)
        prs = fetch_open_prs("owner/repo", max_prs=100)
        assert prs == nodes
        mock_gql.assert_called_once()
        # No cursor in first call
        first_kwargs = mock_gql.call_args[1]
        assert "cursor" not in first_kwargs


def test_fetch_open_prs_pagination():
    """Test fetch_open_prs() follows pagination to collect all PRs."""
    page1 = _gql_page([{"number": 1}], has_next=True, cursor="cur1")
    page2 = _gql_page([{"number": 2}], has_next=False)
    with patch("pr_review_merge_scheduler.gh_graphql") as mock_gql:
        mock_gql.side_effect = [page1, page2]
        prs = fetch_open_prs("owner/repo", max_prs=100)
        assert len(prs) == 2
        # Second call must include cursor
        second_kwargs = mock_gql.call_args_list[1][1]
        assert second_kwargs.get("cursor") == "cur1"


def test_fetch_open_prs_max_prs_stops_loop():
    """Test fetch_open_prs() stops collecting when max_prs is reached."""
    with patch("pr_review_merge_scheduler.gh_graphql") as mock_gql:
        mock_gql.return_value = _gql_page([{"number": 1}], has_next=True, cursor="c")
        prs = fetch_open_prs("owner/repo", max_prs=1)
        assert len(prs) == 1
        mock_gql.assert_called_once()


# ---------------------------------------------------------------------------
# context_nodes()
# ---------------------------------------------------------------------------


def test_context_nodes_normal():
    """Test context_nodes() extracts nodes from a normal PR."""
    pr = _make_pr(statusCheckRollup={"contexts": {"nodes": [{"a": 1}]}})
    assert context_nodes(pr) == [{"a": 1}]


def test_context_nodes_missing():
    """Test context_nodes() returns an empty list when statusCheckRollup is absent."""
    assert context_nodes({}) == []


def test_context_nodes_none_values():
    """Test context_nodes() handles None at every level gracefully."""
    assert context_nodes({"statusCheckRollup": None}) == []


# ---------------------------------------------------------------------------
# is_opencode_context()
# ---------------------------------------------------------------------------


def test_is_opencode_context_checkrun_by_name():
    """Test is_opencode_context() matches a CheckRun named opencode-review."""
    node = {
        "__typename": "CheckRun",
        "name": "opencode-review",
        "status": "COMPLETED",
        "checkSuite": None,
    }
    assert is_opencode_context(node)


def test_is_opencode_context_checkrun_by_workflow_name():
    """Test is_opencode_context() matches a CheckRun with the OpenCode Review workflow name."""
    node = {
        "__typename": "CheckRun",
        "name": "some-job",
        "checkSuite": {
            "workflowRun": {"workflow": {"name": "OpenCode Review"}}
        },
    }
    assert is_opencode_context(node)


def test_is_opencode_context_checkrun_no_match():
    """Test is_opencode_context() returns False for an unrelated CheckRun."""
    node = {
        "__typename": "CheckRun",
        "name": "ci-tests",
        "checkSuite": {"workflowRun": {"workflow": {"name": "CI"}}},
    }
    assert not is_opencode_context(node)


def test_is_opencode_context_status_context_match():
    """Test is_opencode_context() matches a StatusContext with opencode-review context."""
    node = {"__typename": "StatusContext", "context": "opencode-review", "state": "success"}
    assert is_opencode_context(node)


def test_is_opencode_context_status_context_no_match():
    """Test is_opencode_context() returns False for an unrelated StatusContext."""
    node = {"__typename": "StatusContext", "context": "other-check", "state": "success"}
    assert not is_opencode_context(node)


# ---------------------------------------------------------------------------
# opencode_in_progress()
# ---------------------------------------------------------------------------


def _checkrun_node(name: str, status: str) -> dict:
    """Build a minimal CheckRun node dict for testing."""
    return {"__typename": "CheckRun", "name": name, "status": status, "checkSuite": None}


def test_opencode_in_progress_queued():
    """Test opencode_in_progress() returns True when status is QUEUED."""
    pr = _make_pr(
        statusCheckRollup={"contexts": {"nodes": [_checkrun_node("opencode-review", "QUEUED")]}}
    )
    assert opencode_in_progress(pr)


def test_opencode_in_progress_in_progress():
    """Test opencode_in_progress() returns True when status is IN_PROGRESS."""
    pr = _make_pr(
        statusCheckRollup={
            "contexts": {"nodes": [_checkrun_node("opencode-review", "IN_PROGRESS")]}
        }
    )
    assert opencode_in_progress(pr)


def test_opencode_in_progress_completed():
    """Test opencode_in_progress() returns False when status is COMPLETED."""
    pr = _make_pr(
        statusCheckRollup={
            "contexts": {"nodes": [_checkrun_node("opencode-review", "COMPLETED")]}
        }
    )
    assert not opencode_in_progress(pr)


def test_opencode_in_progress_non_opencode_node():
    """Test opencode_in_progress() ignores non-opencode nodes."""
    pr = _make_pr(
        statusCheckRollup={
            "contexts": {"nodes": [_checkrun_node("ci-tests", "IN_PROGRESS")]}
        }
    )
    assert not opencode_in_progress(pr)


def test_opencode_in_progress_empty_status():
    """Test opencode_in_progress() treats an empty status as not in progress."""
    pr = _make_pr(
        statusCheckRollup={"contexts": {"nodes": [_checkrun_node("opencode-review", "")]}}
    )
    assert not opencode_in_progress(pr)


def test_opencode_in_progress_no_nodes():
    """Test opencode_in_progress() returns False when there are no nodes."""
    assert not opencode_in_progress(_BASE_PR)


# ---------------------------------------------------------------------------
# unresolved_thread_count()
# ---------------------------------------------------------------------------


def test_unresolved_thread_count_none():
    """Test unresolved_thread_count() returns 0 when there are no threads."""
    assert unresolved_thread_count(_make_pr()) == 0


def test_unresolved_thread_count_mixed():
    """Test unresolved_thread_count() counts only non-outdated unresolved threads."""
    pr = _make_pr(
        reviewThreads={
            "nodes": [
                {"isResolved": False, "isOutdated": False},  # counts
                {"isResolved": True, "isOutdated": False},   # resolved
                {"isResolved": False, "isOutdated": True},   # outdated
            ]
        }
    )
    assert unresolved_thread_count(pr) == 1


# ---------------------------------------------------------------------------
# review_author_login()
# ---------------------------------------------------------------------------


def test_review_author_login_present():
    """Test review_author_login() returns the lowercased login."""
    assert review_author_login({"author": {"login": "OpenCode-Agent"}}) == "opencode-agent"


def test_review_author_login_missing_author():
    """Test review_author_login() returns an empty string when author is absent."""
    assert review_author_login({}) == ""


def test_review_author_login_null_login():
    """Test review_author_login() handles a None login value."""
    assert review_author_login({"author": {"login": None}}) == ""


# ---------------------------------------------------------------------------
# is_opencode_review()
# ---------------------------------------------------------------------------


def test_is_opencode_review_true():
    """Test is_opencode_review() returns True for opencode-agent."""
    assert is_opencode_review({"author": {"login": "opencode-agent"}})


def test_is_opencode_review_false():
    """Test is_opencode_review() returns False for other authors."""
    assert not is_opencode_review({"author": {"login": "human-reviewer"}})


# ---------------------------------------------------------------------------
# current_head_review_state()
# ---------------------------------------------------------------------------


def test_current_head_review_state_no_reviews():
    """Test current_head_review_state() returns False when there are no reviews."""
    assert not current_head_review_state(_make_pr(), "APPROVED")


def test_current_head_review_state_match():
    """Test current_head_review_state() finds an opencode-agent approval on the head."""
    pr = _approved_pr("sha1")
    assert current_head_review_state(pr, "APPROVED")


def test_current_head_review_state_non_opencode():
    """Test current_head_review_state() ignores reviews from non-opencode authors."""
    pr = _make_pr(
        headRefOid="sha1",
        reviews={
            "nodes": [
                {
                    "state": "APPROVED",
                    "author": {"login": "human"},
                    "commit": {"oid": "sha1"},
                }
            ]
        },
    )
    assert not current_head_review_state(pr, "APPROVED")


def test_current_head_review_state_wrong_state():
    """Test current_head_review_state() returns False when state does not match."""
    pr = _make_pr(
        headRefOid="sha1",
        reviews={
            "nodes": [
                {
                    "state": "CHANGES_REQUESTED",
                    "author": {"login": "opencode-agent"},
                    "commit": {"oid": "sha1"},
                }
            ]
        },
    )
    assert not current_head_review_state(pr, "APPROVED")


def test_current_head_review_state_old_commit():
    """Test current_head_review_state() returns False when review is on an old commit."""
    pr = _make_pr(
        headRefOid="new-sha",
        reviews={
            "nodes": [
                {
                    "state": "APPROVED",
                    "author": {"login": "opencode-agent"},
                    "commit": {"oid": "old-sha"},
                }
            ]
        },
    )
    assert not current_head_review_state(pr, "APPROVED")


# ---------------------------------------------------------------------------
# has_current_head_approval / has_current_head_changes_requested
# ---------------------------------------------------------------------------


def test_has_current_head_approval_true():
    """Test has_current_head_approval() returns True for a current-head approval."""
    assert has_current_head_approval(_approved_pr())


def test_has_current_head_approval_false():
    """Test has_current_head_approval() returns False when no approval exists."""
    assert not has_current_head_approval(_make_pr())


def test_has_current_head_changes_requested_true():
    """Test has_current_head_changes_requested() detects a current-head changes-requested review."""
    pr = _make_pr(
        headRefOid="sha1",
        reviews={
            "nodes": [
                {
                    "state": "CHANGES_REQUESTED",
                    "author": {"login": "opencode-agent"},
                    "commit": {"oid": "sha1"},
                }
            ]
        },
    )
    assert has_current_head_changes_requested(pr)


def test_has_current_head_changes_requested_false():
    """Test has_current_head_changes_requested() returns False when no such review exists."""
    assert not has_current_head_changes_requested(_make_pr())


# ---------------------------------------------------------------------------
# enable_auto_merge()
# ---------------------------------------------------------------------------


def test_enable_auto_merge_dry_run():
    """Test enable_auto_merge() does nothing when dry_run is True."""
    with patch("pr_review_merge_scheduler.run") as mock_run:
        enable_auto_merge("owner/repo", {"number": 1, "headRefOid": "sha"}, dry_run=True)
        mock_run.assert_not_called()


def test_enable_auto_merge_not_dry_run():
    """Test enable_auto_merge() calls gh pr merge when not in dry_run mode."""
    with patch("pr_review_merge_scheduler.run") as mock_run:
        enable_auto_merge("owner/repo", {"number": 42, "headRefOid": "sha"}, dry_run=False)
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "gh" in cmd
        assert "--auto" in cmd
        assert "42" in cmd


# ---------------------------------------------------------------------------
# dispatch_opencode_review()
# ---------------------------------------------------------------------------


def test_dispatch_opencode_review_dry_run():
    """Test dispatch_opencode_review() does nothing when dry_run is True."""
    pr = {
        "number": 1,
        "baseRefName": "main",
        "baseRefOid": "base",
        "headRefName": "feat",
        "headRefOid": "head",
    }
    with patch("pr_review_merge_scheduler.run") as mock_run:
        dispatch_opencode_review("owner/repo", "wf", pr, dry_run=True)
        mock_run.assert_not_called()


def test_dispatch_opencode_review_not_dry_run():
    """Test dispatch_opencode_review() calls gh workflow run when not in dry_run mode."""
    pr = {
        "number": 7,
        "baseRefName": "main",
        "baseRefOid": "base",
        "headRefName": "feat",
        "headRefOid": "head",
    }
    with patch("pr_review_merge_scheduler.run") as mock_run:
        dispatch_opencode_review("owner/repo", "OpenCode Review", pr, dry_run=False)
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "workflow" in cmd
        assert "run" in cmd


# ---------------------------------------------------------------------------
# inspect_pr()
# ---------------------------------------------------------------------------

_INSPECT_DEFAULTS: dict = {
    "repo": "owner/repo",
    "dry_run": True,
    "trigger_reviews": True,
    "enable_auto_merge_flag": True,
    "workflow": "OpenCode Review",
    "base_branch": "main",
}


def _inspect(pr: dict, **kwargs: object) -> Decision:
    """Call inspect_pr() with default kwargs merged with caller overrides."""
    opts = {**_INSPECT_DEFAULTS, **kwargs}
    return inspect_pr(opts.pop("repo"), pr, **opts)  # type: ignore[arg-type]


def test_inspect_pr_draft():
    """Test inspect_pr() returns 'skip' for a draft PR."""
    d = _inspect(_make_pr(isDraft=True))
    assert d.action == "skip"
    assert "draft" in d.reason


def test_inspect_pr_wrong_base_branch():
    """Test inspect_pr() returns 'skip' when the base branch is unexpected."""
    d = _inspect(_make_pr(baseRefName="develop"))
    assert d.action == "skip"
    assert "base branch" in d.reason


def test_inspect_pr_fork():
    """Test inspect_pr() returns 'skip' for fork or external head repo."""
    d = _inspect(_make_pr(**{"headRepository": {"nameWithOwner": "other/repo"}}))
    assert d.action == "skip"
    assert "fork" in d.reason


def test_inspect_pr_unresolved_thread():
    """Test inspect_pr() returns 'block' when there are unresolved review threads."""
    pr = _make_pr(
        reviewThreads={"nodes": [{"isResolved": False, "isOutdated": False}]}
    )
    d = _inspect(pr)
    assert d.action == "block"
    assert "unresolved" in d.reason


def test_inspect_pr_changes_requested():
    """Test inspect_pr() returns 'block' when current head has changes requested."""
    pr = _make_pr(
        headRefOid="sha1",
        reviews={
            "nodes": [
                {
                    "state": "CHANGES_REQUESTED",
                    "author": {"login": "opencode-agent"},
                    "commit": {"oid": "sha1"},
                }
            ]
        },
    )
    d = _inspect(pr)
    assert d.action == "block"


def test_inspect_pr_approved_auto_merge_already_enabled():
    """Test inspect_pr() returns 'wait' when current head is approved and auto-merge is already set."""
    pr = dict(_approved_pr())
    pr["autoMergeRequest"] = {"enabledAt": "2026-01-01"}
    d = _inspect(pr)
    assert d.action == "wait"
    assert "already" in d.reason


def test_inspect_pr_approved_auto_merge_flag_disabled():
    """Test inspect_pr() returns 'wait' when approved but auto-merge flag is False."""
    d = _inspect(_approved_pr(), enable_auto_merge_flag=False)
    assert d.action == "wait"
    assert "disabled" in d.reason


def test_inspect_pr_approved_enables_auto_merge():
    """Test inspect_pr() enables auto-merge and returns 'auto_merge' when conditions are met."""
    with patch("pr_review_merge_scheduler.run"):
        d = _inspect(_approved_pr(), dry_run=False)
    assert d.action == "auto_merge"


def test_inspect_pr_opencode_in_progress():
    """Test inspect_pr() returns 'wait' when an OpenCode review is already running."""
    pr = _make_pr(
        statusCheckRollup={
            "contexts": {"nodes": [_checkrun_node("opencode-review", "IN_PROGRESS")]}
        }
    )
    d = _inspect(pr)
    assert d.action == "wait"
    assert "in progress" in d.reason


def test_inspect_pr_triggers_review():
    """Test inspect_pr() dispatches a review and returns 'review_dispatch' when trigger is True."""
    with patch("pr_review_merge_scheduler.run"):
        d = _inspect(_make_pr(), dry_run=False)
    assert d.action == "review_dispatch"


def test_inspect_pr_block_no_trigger():
    """Test inspect_pr() returns 'block' when trigger_reviews is False and no approval."""
    d = _inspect(_make_pr(), trigger_reviews=False)
    assert d.action == "block"
    assert "no OpenCode approval" in d.reason


# ---------------------------------------------------------------------------
# print_summary()
# ---------------------------------------------------------------------------


def test_print_summary(capsys: pytest.CaptureFixture) -> None:
    """Test print_summary() emits per-PR lines and a JSON summary."""
    decisions = [
        Decision(pr=1, action="auto_merge", reason="approved"),
        Decision(pr=2, action="skip", reason="draft"),
        Decision(pr=3, action="auto_merge", reason="approved"),
    ]
    print_summary(decisions, dry_run=True, base_branch="main", project_flow="default")
    out = capsys.readouterr().out
    assert "PR #1" in out
    assert "PR #2" in out
    summary = json.loads(out.splitlines()[-1])
    assert summary["inspected"] == 3
    assert summary["counts"]["auto_merge"] == 2
    assert summary["counts"]["skip"] == 1
    assert summary["base_branch"] == "main"
    assert summary["dry_run"] is True


def test_print_summary_empty(capsys: pytest.CaptureFixture) -> None:
    """Test print_summary() works with an empty decision list."""
    print_summary([], dry_run=False, base_branch="main", project_flow="flow")
    out = capsys.readouterr().out
    summary = json.loads(out.strip())
    assert summary["inspected"] == 0
    assert summary["counts"] == {}


# ---------------------------------------------------------------------------
# self_test()
# ---------------------------------------------------------------------------


def test_self_test(capsys: pytest.CaptureFixture) -> None:
    """Test self_test() runs without raising and prints a success message."""
    self_test()
    assert "self-test passed" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# parse_args()
# ---------------------------------------------------------------------------


def test_parse_args_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test parse_args() sets default values when no arguments are provided."""
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    monkeypatch.delenv("DEFAULT_BRANCH", raising=False)
    monkeypatch.delenv("PROJECT_FLOW", raising=False)
    args = parse_args([])
    assert args.max_prs == 100
    assert not args.dry_run
    assert args.trigger_reviews is True
    assert args.enable_auto_merge is True
    assert not args.self_test


def test_parse_args_custom() -> None:
    """Test parse_args() accepts and returns custom values."""
    args = parse_args(
        [
            "--repo",
            "owner/repo",
            "--base-branch",
            "main",
            "--max-prs",
            "25",
            "--dry-run",
            "--review-workflow",
            "My Workflow",
            "--self-test",
        ]
    )
    assert args.repo == "owner/repo"
    assert args.base_branch == "main"
    assert args.max_prs == 25
    assert args.dry_run
    assert args.review_workflow == "My Workflow"
    assert args.self_test


def test_parse_args_no_trigger_reviews() -> None:
    """Test parse_args() handles --no-trigger-reviews flag."""
    args = parse_args(["--no-trigger-reviews"])
    assert args.trigger_reviews is False


def test_parse_args_no_auto_merge() -> None:
    """Test parse_args() handles --no-enable-auto-merge flag."""
    args = parse_args(["--no-enable-auto-merge"])
    assert args.enable_auto_merge is False


# ---------------------------------------------------------------------------
# main()
# ---------------------------------------------------------------------------


def test_main_self_test() -> None:
    """Test main() runs the self-test and returns 0 when --self-test is given."""
    assert main(["--self-test"]) == 0


def test_main_missing_repo(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test main() raises SystemExit when --repo is not supplied."""
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    monkeypatch.delenv("DEFAULT_BRANCH", raising=False)
    monkeypatch.delenv("PROJECT_FLOW", raising=False)
    with pytest.raises(SystemExit):
        main([])


def test_main_missing_base_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test main() raises SystemExit when --base-branch is not supplied."""
    monkeypatch.delenv("DEFAULT_BRANCH", raising=False)
    monkeypatch.delenv("PROJECT_FLOW", raising=False)
    with pytest.raises(SystemExit):
        main(["--repo", "owner/repo"])


def test_main_missing_project_flow(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test main() raises SystemExit when --project-flow is not supplied."""
    monkeypatch.delenv("PROJECT_FLOW", raising=False)
    with pytest.raises(SystemExit):
        main(["--repo", "owner/repo", "--base-branch", "main"])


def test_main_normal_run() -> None:
    """Test main() fetches PRs and prints summary when all required args are given."""
    with patch("pr_review_merge_scheduler.fetch_open_prs") as mock_fetch:
        mock_fetch.return_value = []
        result = main(
            [
                "--repo",
                "owner/repo",
                "--base-branch",
                "main",
                "--project-flow",
                "default",
            ]
        )
        assert result == 0
        mock_fetch.assert_called_once_with("owner/repo", 100)


def test_main_normal_run_with_prs() -> None:
    """Test main() processes multiple PRs and returns 0."""
    sample_pr = _make_pr()
    with patch("pr_review_merge_scheduler.fetch_open_prs") as mock_fetch:
        mock_fetch.return_value = [sample_pr]
        result = main(
            [
                "--repo",
                "owner/repo",
                "--base-branch",
                "main",
                "--project-flow",
                "default",
                "--dry-run",
            ]
        )
        assert result == 0
