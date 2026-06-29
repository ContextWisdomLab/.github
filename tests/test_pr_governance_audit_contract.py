from pathlib import Path


def test_html4tree_public_fork_queue_requires_central_review_gate():
    """Guard the html4tree onboarding gap documented by the live audit."""
    audit = Path("PR_GOVERNANCE_AUDIT.md").read_text(encoding="utf-8")

    assert "html4tree" in audit
    assert "Do not leave an active public fork PR queue in the inventory-only state." in audit
    assert "organization required-workflow ruleset" in audit
    assert "temporary thin caller" in audit
    assert "same-head central review evidence" in audit
    assert "2026-06-29 KST `html4tree` onboarding gap" in audit
    assert "PR #20 is the lowest open PR" in audit
    assert "real generated-HTML accessibility changes" in audit
    assert "has no check runs" in audit
    assert "no reviews from the central `.github` process" in audit
    assert "do not bypass the review gate" in audit


def test_central_review_workflows_are_reusable_for_thin_callers():
    """Temporary repo callers must delegate implementation to .github."""
    strix = Path(".github/workflows/strix.yml").read_text(encoding="utf-8")
    opencode = Path(".github/workflows/opencode-review.yml").read_text(encoding="utf-8")
    scheduler = Path(".github/workflows/pr-review-merge-scheduler.yml").read_text(encoding="utf-8")

    for workflow in (strix, opencode, scheduler):
        assert "workflow_call:" in workflow

    assert "inputs.pr_number || github.event.inputs.pr_number" in strix
    assert "inputs.pr_head_sha || github.event.inputs.pr_head_sha" in strix
    assert "github.event_name == 'workflow_call'" in opencode
    assert "inputs.pr_number || github.event.inputs.pr_number" in opencode


def test_afipc_queue_requires_central_required_workflow_evidence():
    """Guard the aFIPC central required-workflow coverage gap."""
    audit = Path("PR_GOVERNANCE_AUDIT.md").read_text(encoding="utf-8")
    rollout = Path("docs/org-required-workflow-rollout.md").read_text(
        encoding="utf-8"
    )

    assert "aFIPC" in audit
    assert "aFIPC" in rollout
    assert "PR #78" in audit
    assert "PR `#78` lacks inherited OpenCode, Strix, and scheduler" in rollout
    assert "zero approving reviews" in audit
    assert "must not be merged until organization required-workflow evidence exists" in audit
