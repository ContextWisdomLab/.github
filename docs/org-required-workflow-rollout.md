# ContextualWisdomLab central required workflow rollout

Updated: 2026-06-29 02:34 KST

## Decision

Use an organization repository ruleset instead of copying workflow files into each repository.

- Ruleset: `CWL Central required workflows`
- Ruleset ID: `18156473`
- Enforcement: `active`
- Target: branch rules on each target repository's default branch (`~DEFAULT_BRANCH`)
- Required workflow source repository: `ContextualWisdomLab/.github`
- Required workflow source repository ID: `1274066402`
- Active required workflow paths:
  - `.github/workflows/strix.yml`
  - `.github/workflows/opencode-review.yml`
  - `.github/workflows/pr-review-merge-scheduler.yml`
- Required workflow ref: `refs/heads/codex/rerun-required-opencode-job`
- Required workflow head: `3c62c37a4deabdb0c6ed4ddf0951c1987f09866b`
- Required workflow trigger support: `pull_request_target`

The current ref is a temporary proof pin for `.github` PR `#100`. Restore this ruleset to `.github@main` immediately after PR `#100` merges.

This keeps Strix security evidence, OpenCode review evidence, and merge/update automation sourced from the central `.github` repository. Target repositories do not need local copies of these workflows for the organization required workflow rule.

## OpenCode required workflow posture

The central `.github/workflows/opencode-review.yml` is now part of the active organization required workflow ruleset.

- Required workflow trigger support: `pull_request_target`
- Stable required check job name: `opencode-review`
- Trusted source: `ContextualWisdomLab/.github`
- PR-head handling: checkout or fetch PR head as review data only; trusted scripts come from the central `.github` ref
- Model token posture: use the organization `STRIX_GITHUB_MODELS_TOKEN` secret for GitHub Models calls, with `github.token` as the fallback; live workflow evidence showed `github.token` alone can return 403 from `models.github.ai/inference`
- Write posture: OpenCode may create review/comment side effects through the OpenCode app token when available; `github.token` remains the last fallback and publication failures are soft-failed
- Coverage execution posture: privileged `pull_request_target` coverage runs only for same-repository PR heads; fork PR heads must be covered by an unprivileged PR-side check or manually trusted dispatch before approval
- Fork posture: PR heads are fetched through `refs/pull/<number>/head` when direct head-SHA fetch is not available, so review can inspect fork PR source as data without executing it in the trusted workflow context
- Runtime posture: pre-model failed-check evidence waits are capped at about five minutes; the later approval gate still rechecks current-head peer checks before approving

Keep the OpenCode required workflow active only while the central workflow keeps proving current-head coverage, CodeGraph initialization, bounded evidence, model review output, and approval-gate publication on the current head.

## Scheduler required workflow posture

The central `.github/workflows/pr-review-merge-scheduler.yml` is now part of the active organization required workflow ruleset.

- Required workflow trigger support: `pull_request_target`
- Stable required check job name: `scan-pr-queue`
- Trusted source: `ContextualWisdomLab/.github`
- PR-event scope: when GitHub invokes the workflow for a PR, the scheduler passes `--pr-number` and inspects only that PR instead of scanning or mutating the whole repository queue
- Token posture: the workflow passes `GH_TOKEN: ${{ github.token }}` so stale-thread resolution, branch update, auto-merge, and direct merge mutations are attributed to the target repository's `github-actions[bot]`
- Flow posture: default branches named `main` or `master` are treated as GitHub Flow; default branches named `develop` are treated as Git Flow unless a repository explicitly sets `PROJECT_FLOW`
- Automation boundary: `update-branch` handles `BEHIND` PRs only after current-head OpenCode approval; `DIRTY` or `CONFLICTING` PRs still require author or maintainer conflict resolution guidance
- Retry posture: before retrying OpenCode, the scheduler force-cancels older active OpenCode runs for the same PR number and a previous head SHA. It does not automatically cancel Strix runs because security evidence should not be silently discarded by force-push churn.

Do not centralize the scheduler by running a `.github` scheduled job against other repositories with the `.github` repository token. That would either fail permission checks or use the wrong mutation actor. The central path is a required workflow executed in each target repository context.

## Scope

The active ruleset targets the public, non-fork repositories found by live GitHub inventory on 2026-06-29 02:34 KST.

| Repository | Default branch | Flow | Open PRs | Default-branch workflow footprint | Local central-workflow copies | Rollout status |
| --- | --- | --- | ---: | --- | --- | --- |
| `ContextualWisdomLab/.github` | `main` | GitHub Flow | 1 | OpenCode, scheduler, Strix | central source; keep | PR `#100` proving required-workflow retry fix |
| `ContextualWisdomLab/ContextualWisdomLab.github.io` | `main` | GitHub Flow | 1 | none | none | migrated; re-verify before final closure |
| `ContextualWisdomLab/appguardrail` | `develop` | Git Flow | 1 | none | none | migrated; re-verify before final closure |
| `ContextualWisdomLab/bandscope` | `develop` | Git Flow | 1 | none | none | no local central copies observed; verify inherited checks on next PR |
| `ContextualWisdomLab/clearfolio` | `main` | GitHub Flow | 1 | none | none | migrated; re-verify before final closure |
| `ContextualWisdomLab/codec-carver` | `main` | GitHub Flow | 1 | OpenCode, scheduler, Strix | OpenCode, scheduler, Strix | quality uplift first: 100% test/docstring coverage is not yet proven |
| `ContextualWisdomLab/contextual-orchestrator` | `main` | GitHub Flow | 0 | none | none | no local central copies observed; verify inherited checks on next PR |
| `ContextualWisdomLab/hyosung-itx-slogan-brief` | `main` | GitHub Flow | 0 | none | none | migrated; re-verify before final closure |
| `ContextualWisdomLab/naruon` | `develop` | Git Flow | 1 | OpenCode, scheduler, Strix, PR governance, Strix self-test | OpenCode, scheduler, Strix | complex local review/process contract; inspect #745-era behavior before removal |
| `ContextualWisdomLab/newsdom-api` | `develop` | Git Flow | 1 | OpenCode, scheduler, Strix | OpenCode, scheduler, Strix | rewrite local workflow/runtime-env tests before removal |
| `ContextualWisdomLab/pg-erd-cloud` | `main` | GitHub Flow | 1 | OpenCode, scheduler, Strix, autofix/fix scheduler | OpenCode, scheduler, Strix | preserve/autonomize autofix contract before removing local governance copies |
| `ContextualWisdomLab/scopeweave` | `develop` | Git Flow | 1 | OpenCode, scheduler, Strix, Strix self-test | OpenCode, scheduler, Strix | rewrite docs/tests that treat local Strix/OpenCode files as the contract |

## Current policy

1. Security evidence, review evidence, and mechanical merge/update automation are centralized through the organization `workflows` ruleset rule.
2. The central required workflows come from `.github`; repositories should not receive copied Strix, OpenCode, or scheduler workflow files only to satisfy this rollout.
3. GitHub Flow repositories are those whose default branch is `main`.
4. Git Flow repositories are those whose default branch is `develop`.
5. OpenCode remains responsible for review judgment and structured decisions.
6. GitHub Actions remains responsible for mechanical branch updates and merges.
7. A merge is acceptable only when the current head has required checks passing, current-head OpenCode approval, no unresolved review threads, and a clean or mergeable merge state.
8. Previous-head approvals or checks are not merge evidence.

## Evidence from this rollout

- `.github` PR `#74` changed OpenCode review model order to DeepSeek R1 first and added a catalog fallback pool.
- `.github` PR `#75` removed the Strix finding against the scheduler command wrapper by using `subprocess.run(..., check=True)` and preserving the existing scrubbed failure contract.
- `.github` main Strix run `28218982899` passed after PR `#75` merged.
- `.github` PR `#77` merged the central OpenCode required-workflow path.
- `.github` PR `#77` same-head OpenCode proof run `28224085121` passed coverage evidence, CodeGraph initialization, bounded evidence preparation, model review, review comment publication, and approval-gate publication on head `59a8da0b2f56b862f6c5a0c69885f4045d6dc732`.
- `.github` PR `#77` central Strix required workflow run `28223698075` passed on the same head before merge.
- Organization ruleset `18156473` was renamed to `CWL Central required workflows` and required `.github/workflows/strix.yml` and `.github/workflows/opencode-review.yml` from `.github@main` SHA `6440d493816f8a4d66e32f2e5e8e6a9156d7f488`.
- `.github` PR `#79` merged the central scheduler `pull_request_target` path and PR-scoped `--pr-number` lookup.
- `.github` PR `#79` second current-head proof passed coverage evidence in 10s, Strix in 8m33s, and OpenCode review in 8m57s on head `17c62f3809c57ca4b1a9a63e14f325c9f2a1acdb`.
- Organization ruleset `18156473` now requires `.github/workflows/strix.yml`, `.github/workflows/opencode-review.yml`, and `.github/workflows/pr-review-merge-scheduler.yml` from `.github@main` SHA `807254a04efafd5f806e0f70cb067ecf050cfd11`.
- `.github` PR `#85` installed target repository `requirements.txt` before Python coverage evidence, so central coverage measurement can run repo tests that require project dependencies.
- `.github` PR `#88` hardened the OpenCode output normalizer so the Python normalizer is part of the trusted approval gate path.
- `.github` PR `#94` hardened the central OpenCode prompt and generated review DAG contract so Mermaid labels are quoted and render safely.
- `.github` PR `#95` blocks OpenCode approvals that claim no source, test, or executable changes when exact changed-file evidence lists workflow, script, source, or test files.
- On 2026-06-28 20:09 KST, ruleset `18156473` was re-pinned to `.github@main` SHA `531482764986bf7da98c1317d59e6e51e7c61d02` for all three required workflow paths.
- `ContextualWisdomLab/naruon` reports inherited active ruleset `18156473` with all three required workflow paths, proving target-repository inheritance after the scheduler ruleset update.
- `ContextualWisdomLab/ContextualWisdomLab.github.io` PR `#25` merged the thin central scheduler caller and repository-local bootstrap fixes. Its main Strix run `28217860369` passed.
- The organization ruleset API reports the central required workflows ruleset as `active` and inherited by each public non-fork target repository.
- `.github` PR `#100` adds required-workflow job rerun support and cancels older same-PR OpenCode runs before retrying the current head. Local verification on head `3c62c37a4deabdb0c6ed4ddf0951c1987f09866b`: `pytest -q` passed 38 tests, `coverage report --fail-under=100` reported 100%, `interrogate --fail-under=100 .` reported 100%.
- On 2026-06-29 02:34 KST, `.github` PR `#100` current-head required workflow runs were still queued after old-head PR `#100` runs `28329720827`, `28329593435`, and `28329593433` were force-cancelled.

## Good patterns to keep

- `naruon`: separates PR Governance, OpenCode review, Strix evidence, and application CI into explicit checks.
- `.github`: centralizes reusable workflow logic and review/merge scheduler code.
- `pg-erd-cloud`: has separate autofix/fix scheduler workflows, useful as a reference for repair automation but not as a merge authority.
- `ContextualWisdomLab.github.io`: thin caller pattern is acceptable for repository-local workflows only when GitHub does not offer an organization-level control. It should not be the default rollout mechanism.

## Risks and follow-up

- Existing open PRs may need a new push or base update before the latest required workflow SHA appears on their current head.
- The central OpenCode workflow now retries DeepSeek R1, DeepSeek V3, GPT-5, and a catalog fallback pool. Keep model/tooling failures out of PR comments unless there is a source-backed failed-check diagnosis.
- Generated OpenCode review DAGs must use quoted Mermaid labels such as `A["text"]`; unquoted labels with spaces, punctuation, parentheses, or file counts can fail to render.
- OpenCode approval summaries must not contradict exact changed-file evidence by saying no source, test, or executable files changed when workflow, script, source, or test files are present.
- Some repositories still have local Strix/OpenCode/scheduler workflows. Do not copy more workflows into repositories; retire local copies only after repository tests and docs are rewritten to the central required-workflow contract.
- Repositories with local autofix/update workflows, especially `pg-erd-cloud`, need an explicit central autofix contract before local workflows are removed.
- Some repositories use classic branch protection while others use rulesets. Normalize branch protection into rulesets without removing repository-specific required application checks.
