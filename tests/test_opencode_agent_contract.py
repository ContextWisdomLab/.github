import json
import re
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
        assert agents[primary_agent]["reasoningEffort"] == "high"
        permission = agents[primary_agent]["permission"]
        assert permission["bash"] == "allow"
        assert permission["task"] == "allow"
        assert permission["webfetch"] == "allow"
        assert permission["websearch"] == "allow"
        assert permission["lsp"] == "allow"

    models = config["provider"]["github-models"]["models"]
    high_reasoning_models = {
        "openai/gpt-5",
        "openai/gpt-5-chat",
        "openai/gpt-5-mini",
        "deepseek/deepseek-r1-0528",
        "openai/o3",
        "openai/o3-mini",
        "openai/o4-mini",
    }
    for model_name in high_reasoning_models:
        assert models[model_name]["reasoning"] is True
        assert models[model_name]["options"]["reasoningEffort"] == "high"
        assert models[model_name]["variants"]["high"]["reasoningEffort"] == "high"
    for model_name, model_config in models.items():
        if model_config.get("reasoning") is True:
            assert model_config["options"]["reasoningEffort"] == "high", model_name
            assert model_config["variants"]["high"]["reasoningEffort"] == "high", model_name


def test_opencode_model_pool_sets_high_effort_for_capable_candidates():
    """Guard every review-pool candidate against silent reasoning-effort drift."""
    config = json.loads(Path("opencode.jsonc").read_text(encoding="utf-8"))
    workflow = Path(".github/workflows/opencode-review.yml").read_text(encoding="utf-8")
    models = config["provider"]["github-models"]["models"]
    candidates_match = re.search(r'OPENCODE_MODEL_CANDIDATES: "([^"]+)"', workflow)

    assert candidates_match is not None
    candidates = candidates_match.group(1).split()
    candidate_models = [candidate.removeprefix("github-models/") for candidate in candidates]

    assert set(candidate_models) == set(models)

    def is_reasoning_capable(model_name: str) -> bool:
        return (
            model_name.startswith("openai/gpt-5")
            or model_name.startswith("openai/o3")
            or model_name.startswith("openai/o4")
            or model_name.startswith("deepseek/deepseek-r1")
        )

    for model_name in candidate_models:
        model_config = models[model_name]
        if is_reasoning_capable(model_name):
            assert model_config["reasoning"] is True, model_name
            assert model_config["options"]["reasoningEffort"] == "high", model_name
            assert model_config["variants"]["high"]["reasoningEffort"] == "high", model_name
        else:
            assert model_config.get("reasoning") is not True, model_name
            assert "reasoningEffort" not in model_config.get("options", {}), model_name
            assert "variants" not in model_config, model_name


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
    assert "Docker, Docker Compose, devcontainer, Nix" in prompt
    assert "single happy-path test is not sufficient" in prompt
    assert "object naming and reserved-word safety" in prompt
    assert "connected code" in prompt
    assert "cannot be sandboxed safely" not in prompt
    assert "scripts/ci/sandboxed_verify.py" in prompt
    assert "--allow-env NAME" in prompt
    assert "--network required" in prompt
    assert "Review execution contracts" in ci_prompt
    assert "unpackaged" in ci_prompt
    assert "No material issues found in the reviewed diff." in prompt
    assert "code-reviewer" in ci_prompt
    assert "Execution evidence must be sandboxed" in ci_prompt
    assert "SANDBOXED_VERIFY_RESULT" in ci_prompt
    assert "Docker, Docker Compose, devcontainer, Nix" in ci_prompt
    assert "single happy-path test is not sufficient" in ci_prompt
    assert "object naming and reserved-word safety" in ci_prompt
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
    assert "Docker Compose, devcontainer, Nix, or temporary package-install sandbox" in workflow
    assert "scientific, statistical, simulation" in workflow
    assert "skewed true" in workflow
    assert "object naming" in workflow
    assert "connected code paths, rendering paths" in workflow
    assert "CHECK_LOOKUP_GH_TOKEN" in workflow
    assert "retrying with workflow github token" in workflow
    assert "Review execution contracts" in workflow
    assert "Accessibility/i18n:" in workflow
    assert "Supply-chain/license:" in workflow
    assert "Packaging:" in workflow
    assert '"code-reviewer"' in workflow
    assert workflow.count('"reasoningEffort": "high"') >= 10
    assert '"task": "allow"' in workflow
    assert 'cat >"$prompt_file" <<EOF' not in workflow
    assert 'cat >"$prompt_file" <<\'EOF\'' not in workflow
    assert "Run OpenCode PR Review model pool" in workflow
    assert "opencode_review_model_pool" in workflow
    assert "run_opencode_review_model_pool.sh" in workflow
    assert "OPENCODE_MODEL_CANDIDATES" in workflow
    model_pool_runner = Path("scripts/ci/run_opencode_review_model_pool.sh").read_text(encoding="utf-8")
    assert "assert_reasoning_effort_for_candidate" in model_pool_runner
    assert 'reasoningEffort == "high"' in model_pool_runner
    assert "OpenCode reasoning-capable candidate %s must set reasoningEffort=high" in model_pool_runner
    assert 'timeout-minutes: 45' in workflow
    assert 'OPENCODE_RUN_TIMEOUT_SECONDS: "180"' in workflow
    assert 'OPENCODE_TOTAL_RETRY_BUDGET_SECONDS: "2400"' in workflow
    assert "${{ runner.temp }}/opencode-review-model-pool.md" in workflow

    strix_workflow = Path(".github/workflows/strix.yml").read_text(encoding="utf-8")
    assert "STRIX_REASONING_EFFORT: high" in strix_workflow

    prompt_template = Path("scripts/ci/opencode_review_prompt_template.md").read_text(encoding="utf-8")
    assert "${OPENCODE_REVIEW_INTRO}" in prompt_template
    assert "CodeGraph MCP is mandatory" in prompt_template
    assert "Context7" in prompt_template
    assert "web_search" in prompt_template
    assert "Playwright visual" in prompt_template
    assert "balanced and skewed parameters" in prompt_template
    assert "Docker, Docker Compose, devcontainer, Nix" in prompt_template
    assert "naming and reserved-word" in prompt_template
    assert "connected code paths" in prompt_template
    assert "Korean PRs must receive Korean" in prompt_template
    assert "Never approve material workflow, script, source, config, package, or test changes" in prompt_template


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
