#!/usr/bin/env python3
"""Schedule OpenCode reviews and auto-merges for open pull requests."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from typing import Any


OPEN_PRS_QUERY = """\
query($owner: String!, $name: String!, $pageSize: Int!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    pullRequests(first: $pageSize, after: $cursor, states: OPEN, orderBy: {field: CREATED_AT, direction: ASC}) {
      pageInfo { hasNextPage endCursor }
      nodes {
        number
        title
        isDraft
        mergeable
        reviewDecision
        baseRefName
        baseRefOid
        headRefName
        headRefOid
        headRepository { nameWithOwner }
        autoMergeRequest { enabledAt }
        reviewThreads(first: 100) {
          nodes { isResolved isOutdated }
        }
        reviews(last: 50) {
          nodes {
            state
            body
            submittedAt
            author { login }
            commit { oid }
          }
        }
        statusCheckRollup {
          contexts(first: 100) {
            nodes {
              __typename
              ... on CheckRun {
                name
                status
                conclusion
                checkSuite {
                  workflowRun {
                    workflow { name }
                  }
                }
              }
              ... on StatusContext {
                context
                state
              }
            }
          }
        }
      }
    }
  }
}
"""


@dataclass
class Decision:
    """Holds the scheduling decision for a single pull request."""

    pr: int
    action: str
    reason: str


def run(args: list[str], *, stdin: str | None = None) -> str:
    """Run a subprocess and return its stdout, raising RuntimeError on failure."""
    process = subprocess.run(args, input=stdin, capture_output=True, text=True)
    if process.returncode != 0:
        raise RuntimeError(
            f"Command failed ({process.returncode}): {' '.join(args)}\n{process.stderr}"
        )
    return process.stdout


def split_repo(repo: str) -> tuple[str, str]:
    """Split an 'owner/name' repository string into a (owner, name) tuple."""
    try:
        owner, name = repo.split("/", 1)
    except ValueError as exc:
        raise ValueError(f"repo must be owner/name, got {repo!r}") from exc
    if not owner or not name:
        raise ValueError(f"repo must be owner/name, got {repo!r}")
    return owner, name


def gh_graphql(query: str, **fields: str | int) -> dict[str, Any]:
    """Execute a GitHub GraphQL query via the gh CLI and return the parsed JSON response."""
    cmd = ["gh", "api", "graphql", "-F", "query=@-"]
    for key, value in fields.items():
        flag = "-F" if isinstance(value, int) else "-f"
        cmd.extend([flag, f"{key}={value}"])
    return json.loads(run(cmd, stdin=query))


def fetch_open_prs(repo: str, max_prs: int) -> list[dict[str, Any]]:
    """Fetch up to max_prs open pull requests from the repository using pagination."""
    owner, name = split_repo(repo)
    prs: list[dict[str, Any]] = []
    cursor: str | None = None

    while len(prs) < max_prs:
        page_size = min(100, max_prs - len(prs))
        fields: dict[str, str | int] = {
            "owner": owner,
            "name": name,
            "pageSize": page_size,
        }
        if cursor:
            fields["cursor"] = cursor
        payload = gh_graphql(OPEN_PRS_QUERY, **fields)
        pr_page = payload["data"]["repository"]["pullRequests"]
        prs.extend(pr_page.get("nodes") or [])
        if not pr_page["pageInfo"]["hasNextPage"]:
            break
        cursor = pr_page["pageInfo"]["endCursor"]

    return prs


def context_nodes(pr: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the list of status-check context nodes from a PR's statusCheckRollup."""
    rollup = pr.get("statusCheckRollup") or {}
    contexts = rollup.get("contexts") or {}
    return contexts.get("nodes") or []


def is_opencode_context(node: dict[str, Any]) -> bool:
    """Return True if the status-check node belongs to the OpenCode review workflow."""
    if node.get("__typename") == "CheckRun":
        workflow = (
            ((node.get("checkSuite") or {}).get("workflowRun") or {}).get("workflow")
            or {}
        )
        return node.get("name") == "opencode-review" or workflow.get("name") == "OpenCode Review"
    return node.get("context") == "opencode-review"


def opencode_in_progress(pr: dict[str, Any]) -> bool:
    """Return True if an OpenCode review is currently queued or running for the PR."""
    for node in context_nodes(pr):
        if not is_opencode_context(node):
            continue
        status = (node.get("status") or node.get("state") or "").upper()
        if status and status not in {"COMPLETED", "SUCCESS", "FAILURE", "ERROR"}:
            return True
    return False


def unresolved_thread_count(pr: dict[str, Any]) -> int:
    """Return the number of non-outdated, unresolved review threads on the PR."""
    threads = ((pr.get("reviewThreads") or {}).get("nodes") or [])
    return sum(1 for thread in threads if not thread.get("isResolved") and not thread.get("isOutdated"))


def review_author_login(review: dict[str, Any]) -> str:
    """Return the lowercased login of the review author, or empty string if absent."""
    return ((review.get("author") or {}).get("login") or "").lower()


def is_opencode_review(review: dict[str, Any]) -> bool:
    """Return True if the review was submitted by the opencode-agent bot."""
    return review_author_login(review) == "opencode-agent"


def current_head_review_state(pr: dict[str, Any], state: str) -> bool:
    """Return True if the latest opencode-agent review on the current head has the given state."""
    head = pr.get("headRefOid")
    for review in reversed((pr.get("reviews") or {}).get("nodes") or []):
        if not is_opencode_review(review):
            continue
        if (review.get("state") or "").upper() != state:
            continue
        commit = (review.get("commit") or {}).get("oid")
        if commit == head:
            return True
    return False


def has_current_head_approval(pr: dict[str, Any]) -> bool:
    """Return True if the opencode-agent approved the current head commit."""
    return current_head_review_state(pr, "APPROVED")


def has_current_head_changes_requested(pr: dict[str, Any]) -> bool:
    """Return True if the opencode-agent requested changes on the current head commit."""
    return current_head_review_state(pr, "CHANGES_REQUESTED")


def enable_auto_merge(repo: str, pr: dict[str, Any], *, dry_run: bool) -> None:
    """Enable auto-merge for the PR via gh CLI, unless dry_run is True."""
    number = str(pr["number"])
    head = pr["headRefOid"]
    if dry_run:
        return
    run(["gh", "pr", "merge", number, "--repo", repo, "--auto", "--merge", "--match-head-commit", head])


def dispatch_opencode_review(repo: str, workflow: str, pr: dict[str, Any], *, dry_run: bool) -> None:
    """Trigger the OpenCode review workflow for the PR, unless dry_run is True."""
    if dry_run:
        return
    run(
        [
            "gh",
            "workflow",
            "run",
            workflow,
            "--repo",
            repo,
            "--ref",
            pr["baseRefName"],
            "-f",
            f"pr_number={pr['number']}",
            "-f",
            f"pr_base_ref={pr['baseRefName']}",
            "-f",
            f"pr_base_sha={pr['baseRefOid']}",
            "-f",
            f"pr_head_ref={pr['headRefName']}",
            "-f",
            f"pr_head_sha={pr['headRefOid']}",
        ]
    )


def inspect_pr(
    repo: str,
    pr: dict[str, Any],
    *,
    dry_run: bool,
    trigger_reviews: bool,
    enable_auto_merge_flag: bool,
    workflow: str,
    base_branch: str,
) -> Decision:
    """Determine what action to take for a single open pull request."""
    number = pr["number"]
    head_repo = (pr.get("headRepository") or {}).get("nameWithOwner")
    base_ref = pr.get("baseRefName")

    if pr.get("isDraft"):
        return Decision(number, "skip", "draft PR")
    if base_ref != base_branch:
        return Decision(number, "skip", f"base branch is {base_ref}; expected {base_branch}")
    if head_repo != repo:
        return Decision(number, "skip", f"fork or external head repo: {head_repo}")

    unresolved = unresolved_thread_count(pr)
    if unresolved:
        return Decision(number, "block", f"{unresolved} unresolved review thread(s)")

    if has_current_head_changes_requested(pr):
        return Decision(number, "block", "current-head OpenCode review requested changes")

    if has_current_head_approval(pr):
        if pr.get("autoMergeRequest"):
            return Decision(number, "wait", "current head is approved; auto-merge already enabled")
        if not enable_auto_merge_flag:
            return Decision(number, "wait", "current head is approved; auto-merge disabled by scheduler inputs")
        enable_auto_merge(repo, pr, dry_run=dry_run)
        return Decision(number, "auto_merge", "current head is approved; auto-merge enabled")

    if opencode_in_progress(pr):
        return Decision(number, "wait", "OpenCode review is already in progress")

    if trigger_reviews:
        dispatch_opencode_review(repo, workflow, pr, dry_run=dry_run)
        return Decision(number, "review_dispatch", "current head has no OpenCode approval")

    return Decision(number, "block", "current head has no OpenCode approval")


def print_summary(
    decisions: list[Decision],
    *,
    dry_run: bool,
    base_branch: str,
    project_flow: str,
) -> None:
    """Print a per-PR decision log and a JSON summary to stdout."""
    counts: dict[str, int] = {}
    for decision in decisions:
        counts[decision.action] = counts.get(decision.action, 0) + 1
        print(f"PR #{decision.pr}: {decision.action}: {decision.reason}")
    print(
        json.dumps(
            {
                "base_branch": base_branch,
                "dry_run": dry_run,
                "inspected": len(decisions),
                "counts": counts,
                "project_flow": project_flow,
            },
            sort_keys=True,
        )
    )


def self_test() -> None:
    """Run built-in assertions to verify core logic is correct."""
    sample = {
        "number": 1,
        "headRefOid": "abc",
        "isDraft": False,
        "headRepository": {"nameWithOwner": "owner/repo"},
        "reviewDecision": "REVIEW_REQUIRED",
        "reviewThreads": {"nodes": []},
        "reviews": {
            "nodes": [
                {
                    "state": "APPROVED",
                    "author": {"login": "opencode-agent"},
                    "body": "OpenCode Agent approved this head.",
                    "commit": {"oid": "abc"},
                }
            ]
        },
        "statusCheckRollup": {"contexts": {"nodes": []}},
    }
    assert has_current_head_approval(sample)
    assert not has_current_head_changes_requested(sample)
    sample["reviews"]["nodes"].append(
        {
            "state": "APPROVED",
            "author": {"login": "not-opencode-agent"},
            "body": "OpenCode Agent approved this head.",
            "commit": {"oid": "abc"},
        }
    )
    assert has_current_head_approval(sample)
    sample["reviews"]["nodes"] = [sample["reviews"]["nodes"][-1]]
    assert not has_current_head_approval(sample)
    sample["reviews"]["nodes"].append(
        {
            "state": "CHANGES_REQUESTED",
            "author": {"login": "opencode-agent"},
            "commit": {"oid": "old"},
        }
    )
    assert not has_current_head_changes_requested(sample)
    sample["statusCheckRollup"]["contexts"]["nodes"].append(
        {"__typename": "CheckRun", "name": "opencode-review", "status": "IN_PROGRESS"}
    )
    assert opencode_in_progress(sample)
    print("self-test passed")


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse command-line arguments and return the resulting Namespace."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--base-branch", default=os.environ.get("DEFAULT_BRANCH", ""))
    parser.add_argument("--project-flow", default=os.environ.get("PROJECT_FLOW", ""))
    parser.add_argument("--max-prs", type=int, default=100)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--trigger-reviews", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--enable-auto-merge", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--review-workflow", default="OpenCode Review")
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    """Entry point: parse args, fetch PRs, inspect each, print summary."""
    args = parse_args(argv)
    if args.self_test:
        self_test()
        return 0
    if not args.repo:
        raise SystemExit("--repo is required")
    if not args.base_branch:
        raise SystemExit("--base-branch is required")
    if not args.project_flow:
        raise SystemExit("--project-flow is required")
    prs = fetch_open_prs(args.repo, args.max_prs)
    decisions = [
        inspect_pr(
            args.repo,
            pr,
            dry_run=args.dry_run,
            trigger_reviews=args.trigger_reviews,
            enable_auto_merge_flag=args.enable_auto_merge,
            workflow=args.review_workflow,
            base_branch=args.base_branch,
        )
        for pr in prs
    ]
    print_summary(
        decisions,
        dry_run=args.dry_run,
        base_branch=args.base_branch,
        project_flow=args.project_flow,
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    try:
        raise SystemExit(main(sys.argv[1:]))
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
