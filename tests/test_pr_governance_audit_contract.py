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
    assert "PR #3 is the lowest open PR" in audit
    assert "has no check runs and no reviews" in audit
    assert "do not bypass the review gate" in audit
