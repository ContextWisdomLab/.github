#!/usr/bin/env python3
"""Submit a Noema, non-OpenCode PR approval after primary gates pass."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Sequence
from typing import Any


PRIMARY_REVIEW_AUTHORS = {
    "opencode-agent[bot]",
    "opencode-agent",
    "github-actions[bot]",
}
PRIMARY_REVIEW_MARKERS = (
    "OpenCode reviewed the current-head bounded evidence and found no blocking issues.",
    "Result: APPROVE",
    "opencode-review-control-v1",
)
IGNORED_RUNNING_CHECKS = {
    "approve-after-primary-review",
    "Required Noema Review",
}
FAILED_CONCLUSIONS = {"FAILURE", "ERROR", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED", "STARTUP_FAILURE"}
RUNNING_STATES = {"QUEUED", "IN_PROGRESS", "PENDING", "REQUESTED", "WAITING", "EXPECTED"}


def run(args: Sequence[str], *, stdin: str | None = None) -> str:
    if isinstance(args, str):
        raise TypeError("run() requires argv, not a shell command string")
    completed = subprocess.run(
        list(args),
        input=stdin,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"Command failed ({completed.returncode}): {' '.join(args)}\n{completed.stderr.strip()}"
        )
    return completed.stdout


def gh_json(args: Sequence[str]) -> Any:
    return json.loads(run(["gh", "api", *args]))


def split_repo(repo: str) -> tuple[str, str]:
    owner, name = repo.split("/", 1)
    if not owner or not name:
        raise ValueError(f"repo must be owner/name, got {repo!r}")
    return owner, name


def graphql(query: str, **fields: str | int) -> dict[str, Any]:
    args = ["gh", "api", "graphql", "-F", "query=@-"]
    for key, value in fields.items():
        args.extend(["-F" if isinstance(value, int) else "-f", f"{key}={value}"])
    return json.loads(run(args, stdin=query))


PR_QUERY = """\
query($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      number
      title
      isDraft
      headRefOid
      reviewDecision
      reviewThreads(first: 100) {
        nodes { isResolved isOutdated }
      }
      reviews(last: 100) {
        nodes {
          state
          body
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
"""


def fetch_pr(repo: str, number: int) -> dict[str, Any]:
    owner, name = split_repo(repo)
    data = graphql(PR_QUERY, owner=owner, name=name, number=number)
    pr = data.get("data", {}).get("repository", {}).get("pullRequest")
    if not pr:
        raise RuntimeError(f"PR #{number} was not found in {repo}")
    return pr


def review_author(review: dict[str, Any]) -> str:
    return ((review.get("author") or {}).get("login") or "").strip()


def review_commit(review: dict[str, Any]) -> str:
    return ((review.get("commit") or {}).get("oid") or "").strip()


def current_primary_approval(pr: dict[str, Any]) -> dict[str, Any] | None:
    head_sha = str(pr.get("headRefOid") or "")
    reviews = (((pr.get("reviews") or {}).get("nodes")) or [])
    for review in reversed(reviews):
        if review_commit(review) != head_sha:
            continue
        if str(review.get("state") or "").upper() != "APPROVED":
            continue
        body = str(review.get("body") or "")
        author = review_author(review)
        if author in PRIMARY_REVIEW_AUTHORS and any(marker in body for marker in PRIMARY_REVIEW_MARKERS):
            return review
    return None


def has_current_changes_requested(pr: dict[str, Any]) -> bool:
    head_sha = str(pr.get("headRefOid") or "")
    reviews = (((pr.get("reviews") or {}).get("nodes")) or [])
    for review in reversed(reviews):
        if review_commit(review) == head_sha and str(review.get("state") or "").upper() == "CHANGES_REQUESTED":
            return True
    return False


def has_unresolved_threads(pr: dict[str, Any]) -> bool:
    threads = (((pr.get("reviewThreads") or {}).get("nodes")) or [])
    return any(not thread.get("isResolved") and not thread.get("isOutdated") for thread in threads)


def check_label(node: dict[str, Any]) -> str:
    if node.get("__typename") == "StatusContext":
        return str(node.get("context") or "")
    workflow = ((((node.get("checkSuite") or {}).get("workflowRun") or {}).get("workflow") or {}).get("name") or "")
    name = str(node.get("name") or "")
    return f"{workflow} / {name}" if workflow else name


def blocking_checks(pr: dict[str, Any]) -> list[str]:
    contexts = ((((pr.get("statusCheckRollup") or {}).get("contexts") or {}).get("nodes")) or [])
    blockers: list[str] = []
    for node in contexts:
        label = check_label(node)
        if label in IGNORED_RUNNING_CHECKS or str(node.get("name") or "") in IGNORED_RUNNING_CHECKS:
            continue
        if node.get("__typename") == "StatusContext":
            state = str(node.get("state") or "").upper()
            if state not in {"SUCCESS", "NEUTRAL"}:
                blockers.append(f"{label}: {state}")
            continue
        status = str(node.get("status") or "").upper()
        conclusion = str(node.get("conclusion") or "").upper()
        if conclusion in FAILED_CONCLUSIONS:
            blockers.append(f"{label}: {conclusion}")
        elif status in RUNNING_STATES and conclusion not in {"SUCCESS", "NEUTRAL", "SKIPPED"}:
            blockers.append(f"{label}: {status}")
    return blockers


def existing_secondary_review(pr: dict[str, Any], actor: str) -> bool:
    head_sha = str(pr.get("headRefOid") or "")
    marker = "<!-- noema-review-gate"
    for review in (((pr.get("reviews") or {}).get("nodes")) or []):
        if review_commit(review) != head_sha:
            continue
        if str(review.get("state") or "").upper() != "APPROVED":
            continue
        if review_author(review) == actor or marker in str(review.get("body") or ""):
            return True
    return False


def current_actor() -> str:
    try:
        return run(["gh", "api", "user", "--jq", ".login"]).strip()
    except Exception:
        return ""


def approve(repo: str, number: int, pr: dict[str, Any], actor: str) -> None:
    head_sha = str(pr.get("headRefOid") or "")
    source = os.environ.get("NOEMA_REVIEW_TOKEN_SOURCE") or "NOEMA_REVIEW_TOKEN"
    body = "\n".join(
        [
            "## Noema review gate",
            "",
            "Noema found a current-head primary OpenCode approval, no current-head change requests, no unresolved review threads, and no blocking GitHub checks.",
            "",
            "This approval is generated by Noema, a dedicated review app identity separate from OpenCode Agent.",
            "",
            "- Result: APPROVE",
            f"- Head SHA: `{head_sha}`",
            f"- Reviewer credential: `{source}`",
            f"- Actor: `{actor or 'unknown'}`",
            "",
            f"<!-- noema-review-gate head_sha={head_sha} -->",
        ]
    )
    payload = {
        "commit_id": head_sha,
        "event": "APPROVE",
        "body": body,
    }
    run(
        ["gh", "api", "-X", "POST", f"repos/{repo}/pulls/{number}/reviews", "--input", "-"],
        stdin=json.dumps(payload),
    )
    print(f"Noema approval submitted for {repo}#{number} at {head_sha}.")


def inspect_and_approve(repo: str, number: int) -> int:
    pr = fetch_pr(repo, number)
    actor = current_actor()
    if actor in PRIMARY_REVIEW_AUTHORS:
        print(
            f"Current token actor {actor!r} is already a primary review actor; "
            "Noema approval skipped so GitHub receives an independent reviewer."
        )
        return 0
    if pr.get("isDraft"):
        print("PR is draft; Noema approval skipped.")
        return 0
    if existing_secondary_review(pr, actor):
        print("Current head already has a Noema approval; nothing to do.")
        return 0
    if not current_primary_approval(pr):
        print("Current head does not have a primary OpenCode approval; Noema approval skipped.")
        return 0
    if has_current_changes_requested(pr):
        print("Current head has requested changes; Noema approval skipped.")
        return 0
    if has_unresolved_threads(pr):
        print("PR has unresolved review threads; Noema approval skipped.")
        return 0
    blockers = blocking_checks(pr)
    if blockers:
        print("Blocking checks remain; Noema approval skipped:")
        for blocker in blockers:
            print(f"- {blocker}")
        return 0
    approve(repo, number, pr, actor)
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--pr-number", required=True, type=int)
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    if args.pr_number <= 0:
        raise SystemExit("--pr-number must be positive")
    return inspect_and_approve(args.repo, args.pr_number)


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
