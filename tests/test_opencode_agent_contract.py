import json
from pathlib import Path


def test_code_reviewer_subagent_contract_is_configured():
    """Guard the read-only code-reviewer subagent contract."""
    config = json.loads(Path("opencode.jsonc").read_text(encoding="utf-8"))
    agents = config["agent"]
    reviewer = agents["code-reviewer"]

    assert reviewer["mode"] == "subagent"
    assert reviewer["prompt"] == "{file:./code-reviewer-prompt.md}"
    assert reviewer["steps"] == 16
    assert reviewer["color"] == "#7c3aed"
    assert reviewer["reasoningEffort"] == "high"
    assert "model" not in reviewer
    assert "Reviews only; never edits code" in reviewer["description"]

    permission = reviewer["permission"]
    assert permission["edit"] == "deny"
    assert permission["read"] == "allow"
    assert permission["grep"] == "allow"
    assert permission["glob"] == "allow"
    assert permission["bash"] == "allow"
    assert permission["list"] == "allow"
    assert permission["task"] == "deny"
    assert permission["webfetch"] == "deny"
    assert permission["websearch"] == "deny"
    assert permission["lsp"] == "deny"

    for primary_agent in ("ci-review", "ci-review-fallback"):
        permission = agents[primary_agent]["permission"]
        assert permission["bash"] == "allow"
        assert permission["task"] == "allow"
        assert permission["webfetch"] == "allow"
        assert permission["websearch"] == "allow"
        assert permission["lsp"] == "allow"


def test_code_reviewer_prompt_preserves_review_only_policy():
    """Guard the reviewer-only behavior and output rubric in the prompt."""
    prompt = Path("code-reviewer-prompt.md").read_text(encoding="utf-8")
    ci_prompt = Path("ci-review-prompt.md").read_text(encoding="utf-8")

    assert "senior staff-level code reviewer" in prompt
    assert "Do not edit files" in prompt
    assert "git diff --stat" in prompt
    assert "git add" in prompt
    assert "P0" in prompt
    assert "P1" in prompt
    assert "Execution evidence must be sandboxed" in prompt
    assert "mktemp -d" in prompt
    assert "scripts/ci/sandboxed_verify.py" in prompt
    assert "--allow-env NAME" in prompt
    assert "--network required" in prompt
    assert "Review execution contracts" in ci_prompt
    assert "unpackaged" in ci_prompt
    assert "No material issues found in the reviewed diff." in prompt
    assert "code-reviewer" in ci_prompt
    assert "Execution evidence must be sandboxed" in ci_prompt
    assert "SANDBOXED_VERIFY_RESULT" in ci_prompt
    assert "opencode-review-control-v1" in ci_prompt


def test_workflow_provisions_sandbox_tool_and_reviewer_agent():
    """Guard the runtime OpenCode workspace, not only repo-local config."""
    workflow = Path(".github/workflows/opencode-review.yml").read_text(
        encoding="utf-8"
    )

    assert "code-reviewer-prompt.md" in workflow
    assert "sandboxed_verify.py" in workflow
    assert "sandboxed_web_e2e.py" in workflow
    assert "review_execution_contracts.py" in workflow
    assert "SANDBOXED_VERIFY_RESULT" in workflow
    assert "SANDBOXED_WEB_E2E_RESULT" in workflow
    assert "CHECK_LOOKUP_GH_TOKEN" in workflow
    assert "retrying with workflow github token" in workflow
    assert "Review execution contracts" in workflow
    assert "Accessibility/i18n:" in workflow
    assert "Supply-chain/license:" in workflow
    assert "Packaging:" in workflow
    assert '"code-reviewer"' in workflow
    assert '"task": "allow"' in workflow
    assert 'cat >"$prompt_file" <<EOF' not in workflow
    assert workflow.count('cat >"$prompt_file" <<\'EOF\'') == 4
    assert workflow.count("render_opencode_prompt_template.py") == 4
    assert (
        'PROMPT_MODEL_CANDIDATE="$model_candidate" '
        'python3 "$GITHUB_WORKSPACE/scripts/ci/render_opencode_prompt_template.py" '
        '"$prompt_file"'
    ) in workflow


def test_merge_scheduler_uses_escalating_mutation_credentials():
    """Guard immediate merge/update execution credentials for central scheduling."""
    workflow = Path(".github/workflows/pr-review-merge-scheduler.yml").read_text(
        encoding="utf-8"
    )

    assert "id-token: write" in workflow
    assert "Exchange OpenCode app token for scheduler mutations" in workflow
    assert "secrets.PR_REVIEW_MERGE_TOKEN" in workflow
    assert "secrets.OPENCODE_APPROVE_TOKEN" in workflow
    assert "steps.scheduler_app_token.outputs.token" in workflow
    assert "SCHEDULER_READ_TOKEN: ${{ github.token }}" in workflow
    assert "SCHEDULER_MUTATION_TOKEN_SOURCE" in workflow
    assert 'default: "-1"' in workflow
    assert 'review_dispatch_limit="-1"' in workflow


def test_opencode_runs_merge_scheduler_after_review_without_repo_local_dispatch():
    """Guard immediate post-review merge/update follow-up from OpenCode."""
    workflow = Path(".github/workflows/opencode-review.yml").read_text(
        encoding="utf-8"
    )

    assert "Run merge scheduler after approval" in workflow
    assert "python3 scripts/ci/pr_review_merge_scheduler.py" in workflow
    assert "gh workflow run pr-review-merge-scheduler.yml" not in workflow
    assert "secrets.PR_REVIEW_MERGE_TOKEN || secrets.OPENCODE_APPROVE_TOKEN || steps.opencode_app_token.outputs.token" in workflow
    assert "--no-trigger-reviews" in workflow
    assert "--enable-auto-merge" in workflow
    assert "--no-update-branches" in workflow
    assert "Merge scheduler follow-up skipped after approval because no mutation credential was available" in workflow
