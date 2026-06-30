# ContextualWisdomLab central required workflow rollout

Updated: 2026-07-01 05:10 KST

## Decision

Use an organization repository ruleset instead of copying workflow files into each repository.

- Ruleset: `CWL Central required workflows`
- Ruleset ID: `18156473`
- Enforcement: `active`
- Target: branch rules on every repository's default branch (`repository_name.include=["~ALL"]`, `ref_name.include=["~DEFAULT_BRANCH"]`)
- Required workflow source repository: `ContextualWisdomLab/.github`
- Required workflow source repository ID: `1274066402`
- Active required workflow paths:
  - `.github/workflows/strix.yml`
  - `.github/workflows/opencode-review.yml`
  - `.github/workflows/pr-review-merge-scheduler.yml`
- Required workflow ref: `refs/heads/main`
- Last verified workflow implementation base commit: `482b05c6c11d9da9895246406aca1c3bd8f6a691` (`#235`)
- Required workflow trigger support: `pull_request_target`, `push`, `workflow_run`

`.github` PRs through `#235` are now in `main`. The required-workflow
ruleset points at `.github@main`; if live organization ruleset inspection
reports another ref, treat that as operations drift and restore ruleset
`18156473` to the current `main` head.

This keeps Strix security evidence, OpenCode review evidence, and merge/update automation sourced from the central `.github` repository. Target repositories do not need local copies of these workflows for the organization required workflow rule, and new repositories inherit the rule without a repository-name list update.

## OpenCode required workflow posture

The central `.github/workflows/opencode-review.yml` is now part of the active organization required workflow ruleset.

- Required workflow trigger support: `pull_request_target`
- Stable required check job name: `opencode-review`
- Trusted source: `ContextualWisdomLab/.github`
- PR-head handling: checkout or fetch PR head as review data only; trusted scripts come from the central `.github` ref
- Manual target support: OpenCode and Strix `workflow_dispatch` runs can still pass `target_repository` for targeted diagnostics, but required-workflow coverage comes from the organization ruleset rather than repo-local workflow copies
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
- Token posture: the workflow passes the first available mutation credential in this order: `PR_REVIEW_MERGE_TOKEN`, `OPENCODE_APPROVE_TOKEN`, exchanged OpenCode GitHub App token, then the target repository workflow token. The scheduler reports the non-secret token source and expected actor class in every mutation decision.
- Flow posture: default branches named `main` or `master` are treated as GitHub Flow; default branches named `develop` are treated as Git Flow unless a repository explicitly sets `PROJECT_FLOW`
- Merge posture: the default merge mode is `direct_or_auto`. When a current-head approved PR is same-repository and the scheduler has no failed-check, action-required, unresolved-thread, or conflict blocker, it requests an immediate guarded squash merge with `--match-head-commit`. This includes PRs where native GitHub auto-merge is already enabled; native auto-merge is a fallback queue, not the scheduler's first stop when direct merge is possible.
- Fork posture: fork or external-head PRs remain reviewable, but the scheduler does not direct-merge them and does not enable auto-merge for them. A maintainer must make the final merge decision after same-head OpenCode approval, same-head Strix evidence, required checks, and unresolved-thread checks are clean.
- Branch freshness posture: the scheduler also runs after protected base-branch pushes to `main`, `develop`, or `master`, because those pushes can create the GitHub UI state where reviews are satisfied, auto-merge is enabled, checks are stale or failed, and the PR shows `Update branch` without a PR `synchronize` event.
- Auto-merge posture: `auto_merge_enabled` PR events trigger the scheduler so an already stale branch is refreshed immediately after native auto-merge is turned on instead of waiting for the periodic schedule. If the same PR is already mergeable, the scheduler attempts the guarded direct merge immediately.
- Automation boundary: current-head failed checks and `ACTION_REQUIRED` checks are reported before branch updates, so an update attempt does not hide the concrete reason a PR cannot merge. `update-branch` handles approved `BEHIND` PRs and already queued auto-merge PRs only when there is no current-head failed or action-required check to diagnose first. `DIRTY` or `CONFLICTING` PRs still require author or maintainer conflict resolution guidance; current-head approved conflicts may keep or queue native GitHub auto-merge as a wait state while the conflict is repaired, but the scheduler must not treat queued auto-merge as a conflict resolver.
- Retry posture: before retrying OpenCode, the scheduler force-cancels older active OpenCode runs for the same PR number and a previous head SHA. It does not automatically cancel Strix runs because security evidence should not be silently discarded by force-push churn.

Do not centralize the scheduler by running a `.github` scheduled job against other repositories with the `.github` repository token. That would either fail permission checks or use the wrong mutation actor. The central path is a required workflow executed in each target repository context.

## Scope

The active ruleset no longer maintains a repository-name allowlist. Live ruleset inspection on 2026-07-01 02:52 KST reports `repository_name.include=["~ALL"]`, so all current and future organization repositories inherit the three central required workflows on their default branch unless a later ruleset exclusion is added. The table below is an inventory snapshot and rollout ledger, not the ruleset target list.

| Repository | Visibility | Default branch | Flow | Open PRs | Local central-workflow copies on default branch | Rollout status |
| --- | --- | --- | --- | ---: | --- | --- |
| `ContextualWisdomLab/.github` | public | `main` | GitHub Flow | 23 | central source; keep | single source of truth; PRs through `#235` merged |
| `ContextualWisdomLab/appguardrail` | public | `develop` | Git Flow | 7 | none | migrated; re-verify inherited checks before final closure |
| `ContextualWisdomLab/bandscope` | public | `develop` | Git Flow | 78 | none | no local central copies observed; verify inherited checks on active PRs |
| `ContextualWisdomLab/clearfolio` | public | `main` | GitHub Flow | 45 | none | migrated; re-verify inherited checks before final closure |
| `ContextualWisdomLab/codec-carver` | public | `main` | GitHub Flow | 35 | none | local workflows already gone; quality uplift still needs 100% test/docstring evidence before closure |
| `ContextualWisdomLab/contextual-orchestrator` | public | `main` | GitHub Flow | 0 | none | default branch has no local central copies; no open PR evidence to verify |
| `ContextualWisdomLab/ContextualWisdomLab.github.io` | public | `main` | GitHub Flow | 19 | none | migrated; re-verify inherited checks on current open PRs |
| `ContextualWisdomLab/fast-mlsirm` | public | `main` | GitHub Flow | 9 | none | migrated; re-verify inherited checks on current open PRs |
| `ContextualWisdomLab/hyosung-itx-slogan-brief` | public | `main` | GitHub Flow | 1 | none | migrated; re-verify inherited checks on current open PR |
| `ContextualWisdomLab/naruon` | public | `develop` | Git Flow | 47 | none | default branch has no repo-local OpenCode, Strix, or scheduler copies; application/security workflows remain repository-owned |
| `ContextualWisdomLab/newsdom-api` | public | `develop` | Git Flow | 0 | none | local workflows already gone; no open PR evidence to verify |
| `ContextualWisdomLab/pg-erd-cloud` | public | `main` | GitHub Flow | 85 | none | central required-workflow copies are gone; repo-local autofix worker remains separate from merge authority |
| `ContextualWisdomLab/scopeweave` | public | `develop` | Git Flow | 0 | none | local workflows already gone; no open PR evidence to verify |
| `ContextualWisdomLab/semantic-data-portal` | public | `main` | GitHub Flow | 2 | none | PR `#3` merged; default branch has no local central copies |
| `ContextualWisdomLab/aFIPC` | private | `master` | Git Flow (master) | 16 | none | ruleset target includes this repo; verify inherited checks on active PRs |
| `ContextualWisdomLab/linux-cluster-ops` | private | `develop` | Git Flow | 68 | none | ruleset target includes this repo; verify inherited checks on active PRs |
| `ContextualWisdomLab/noema` | private | `main` | GitHub Flow | 1 | none | ruleset target includes this repo; verify inherited checks on active PR |
| `ContextualWisdomLab/xtrmLLMBatchPython` | private | `develop` | Git Flow | 35 | none | ruleset target includes this repo; verify inherited checks on active PRs |

## Current policy

1. Security evidence, review evidence, and mechanical merge/update automation are centralized through the organization `workflows` ruleset rule.
2. The central required workflows come from `.github`; repositories should not receive copied Strix, OpenCode, or scheduler workflow files only to satisfy this rollout.
3. GitHub Flow repositories are those whose default branch is `main`.
4. Git Flow repositories are those whose default branch is `develop`.
5. OpenCode remains responsible for review judgment and structured decisions.
6. GitHub Actions remains responsible for mechanical branch updates and merges.
7. A merge is acceptable only when the current head has required checks passing, current-head OpenCode approval, no unresolved review threads, and a clean or mergeable merge state.
8. Previous-head approvals or checks are not merge evidence.
9. Same-repository approved PRs should merge immediately when GitHub reports `CLEAN`; fork or external-head PRs are excluded from scheduler merge and auto-merge.

## Evidence from this rollout

- On 2026-06-30 08:33 KST, organization ruleset `18156473` was changed from an explicit repository-name list to `repository_name.include=["~ALL"]` while keeping `ref_name.include=["~DEFAULT_BRANCH"]` and the same three central required workflow paths from `.github@refs/heads/main`.
- On 2026-07-01 02:52 KST, ruleset `18156473` still reported `enforcement=active`, `repository_name.include=["~ALL"]`, `ref_name.include=["~DEFAULT_BRANCH"]`, and the three required workflow paths from `ContextualWisdomLab/.github@refs/heads/main`.
- `.github` PR `#225` raised high reasoning effort for all reasoning-capable OpenCode review model definitions and merged at `50c6ef82f52af3eeb0e58c174902fc9855c36682`.
- `.github` PR `#226` stopped the merge scheduler from treating old deterministic fallback approval bodies as current-head approval evidence and merged at `57a1fa580731a0f76b31dcf29a597c5715dba2fd`.
- `.github` PR `#230` added changed-file candidates to merge-conflict guidance so `DIRTY` or `CONFLICTING` PRs name the first files to inspect instead of giving only generic conflict instructions. It merged at `0cab5c8d46e88c1a3f68ef3f71b5d44d971cd2ef`.
- `.github` PR `#232` removed the workflow-only deterministic approval fallback introduced by PR `#231`; model-pool exhaustion now stays on the fail-closed `REQUEST_CHANGES` path, and reasoning-capable OpenCode model candidates must have `reasoningEffort: high` before execution. It merged at `f545a9917933f8f81a76ea0044cbce0aae1ac5bd`.
- `.github` PR `#233` blocks false trivial approval reasons such as `Typo fix in documentation string` when current-head changed files include workflow, script/source, or test surfaces. It merged at `4ff660c8396b78a1b82aef8c316b26527864d450`.
- `.github` PR `#234` made approval-summary repair parse bullet-form changed-file evidence from bounded review logs, so changed-file evidence is not lost when the evidence section is rendered as a Markdown list. It merged at `da3a4a5788e7019229d66247c360b258b1a5b1f7`.
- `.github` PR `#235` changed the post-approval OpenCode merge-scheduler follow-up to prefer the workflow `github.token` for same-repository mechanical merge/update mutations, keeping secret/app fallbacks for cross-repository manual dispatch. It merged at `482b05c6c11d9da9895246406aca1c3bd8f6a691`.
- `.github` scheduler default merge mode is now `direct_or_auto`: approved same-repository `CLEAN` PRs request immediate guarded merge, approved non-clean same-repository PRs can queue native auto-merge, and fork or external-head PRs are left for maintainer merge.
- OpenCode approval runs the trusted central merge scheduler script directly with `pr_number` and `max_prs=1`, so the just-reviewed PR is inspected immediately even when organization required workflows are not repo-local `workflow_dispatch` targets.
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
- `.github` PR `#100` added required-workflow job rerun support and cancels older same-PR OpenCode runs before retrying the current head. Local verification on head `3c62c37a4deabdb0c6ed4ddf0951c1987f09866b`: `pytest -q` passed 38 tests, `coverage report --fail-under=100` reported 100%, `interrogate --fail-under=100 .` reported 100%.
- `.github` PR `#100` merged at 2026-06-29 05:45 KST with merge commit `81408f3dbe0a3c43dc4b76133f72a5e314df8a10`. A follow-up admin check should verify organization ruleset `18156473` is no longer pinned to `refs/heads/codex/rerun-required-opencode-job`.
- On 2026-06-29 16:33 KST, `ContextualWisdomLab/aFIPC` PR `#78` proved a target coverage gap: PR `#78` lacks inherited OpenCode, Strix, and scheduler required-workflow checks. The PR had local `check`, `quality`, and `secret-and-workflow-audit` check runs, and repository ruleset `PR` (`12815994`) required only those three local checks with zero required approvals.
- `.github` PR `#136` changed approved stale PR handling so `BEHIND` branches are updated before failed-check or `ACTION_REQUIRED` decisions disable auto-merge.
- `.github` PR `#137` made the central `PR Review Fix Scheduler` target-repository aware through `workflow_call`, `workflow_dispatch`, schedule, and `.github` repository variables. `.github` variables currently target `ContextualWisdomLab/pg-erd-cloud` on `main`.
- `.github` PR `#138` added compare-API branch freshness evidence so approved PRs with auto-merge enabled can still receive `update-branch` when GitHub reports `BLOCKED` but the base branch is ahead. Local verification passed `pytest -q`, scheduler self-test, `py_compile`, 100% coverage, 100% docstring coverage, `actionlint`, `bash -n`, and `git diff --check`.
- `.github` PR `#140` extended `update-branch` handling to PRs where auto-merge is already enabled even if the scheduler cannot find a current-head OpenCode approval node, so queued auto-merge PRs with failed checks can still be refreshed when compare evidence shows the base branch is ahead. Local verification passed `pytest -q`, `coverage report` at 100%, `interrogate` at 100%, `py_compile`, `bash -n`, and `git diff --check`.
- `.github` PR `#145` treats compare API `status: behind` as branch-staleness evidence even when `behind_by` is missing or zero, so an auto-merge-enabled PR with failed checks and a visible GitHub "Update branch" action requests `update_branch` before disabling auto-merge. It merged at 2026-06-29 23:14 KST with merge commit `1ec0f3dcc7250fdf4a5a3ec6c26feaa98cce4f48`.
- Live dry runs on 2026-06-30 00:40 KST found update-branch candidates in `.github` PR `#147` and `naruon` PR `#803`. The follow-up scheduler trigger change runs the central queue scan after base-branch pushes and `auto_merge_enabled` events, so those UI-visible stale-branch states are not left waiting only for the periodic schedule.
- `.github` PR `#151` added protected base-branch `push` triggers and the `auto_merge_enabled` PR event to the central scheduler, then merged at 2026-06-30 00:56 KST with merge commit `00018f7783522447a71acd08a946e3504e18ff74`. The merge created push-triggered scheduler run `28385177585`, proving the new trigger path is registered; the job remained queued because runner assignment was still pending.
- The earlier compare API `behind` handling is superseded by the current immediate-action order: `CLEAN` and current-head approved PRs merge before update-branch, failed or `ACTION_REQUIRED` checks are surfaced before any update attempt, and only approved `BEHIND` PRs without current-head check blockers request `update-branch` through the configured scheduler mutation credential.
- `.github` PR `#146` taught central OpenCode `coverage-evidence` to discover nested requirements-only Python test projects such as `backend/requirements.txt` plus `backend/tests`, install those requirements, and run tests from that project directory. It merged at 2026-06-29 23:24 KST with merge commit `0393bc1c48b80597d6d35c336aca43aee18e22b9`.
- `.github` PR `#149` tightened the central OpenCode model-failure path and merged at 2026-06-30 00:26 KST with merge commit `919b83faf29237803cfdd0cfd6febbe5ae1a8a3c`. The follow-up commit `6fdffe43b50a2246b3db2790a0ab532618a89c2b` fixed the fallback approval path so pending-check and human-thread evidence are written to real temporary files instead of empty paths. Local verification passed `pytest -q`, `coverage report --fail-under=100`, `interrogate --fail-under=100`, `actionlint -shellcheck=`, targeted OpenCode quick-gate assertions, `bash -n`, and `git diff --check`; the full quick-gate script exceeded the local 300s timeout in this environment.
- Organization ruleset `18156473` previously targeted all live non-fork repositories, including private `aFIPC`, `linux-cluster-ops`, and `xtrmLLMBatchPython`; this has been superseded by the all-repository `~ALL` condition above.
- `ContextualWisdomLab/semantic-data-portal` PR `#3` removed repo-local OpenCode, Strix, and scheduler workflows; the default branch now has no `.github/workflows` directory.
- `ContextualWisdomLab/pg-erd-cloud` PR `#361` removed the repo-local `pr-review-fix-scheduler.yml` wrapper after central `.github` gained target repository support. It merged at 2026-06-29 22:40 KST with merge commit `21cbc14b21d59ac28ac789de58502816cc8df6ad`; live default-branch content lookup returned 404 for that wrapper path after merge.
- `ContextualWisdomLab/naruon` classic branch protection no longer requires direct `strix` or `opencode-review` status checks on `develop`; after deletion, `branches/develop/protection/required_status_checks` returns `404 Required status checks not enabled`, while org ruleset `18156473` remains `active` and still targets `naruon`.
- `ContextualWisdomLab/naruon` PR `#852` rewrites `backend/tests/test_release_governance.py` and `docs/development/merge-gate-policy.md` to make the central scheduler the contract, then deletes the repo-local `pr-review-merge-scheduler.yml`. The first current-head central `coverage-evidence` failed because nested `backend/requirements.txt` was not installed; `.github` PR `#146` fixed that central path. PR `#852` was pushed to head `2c8257ce0d02838b80650997d65e85569f4ab27f` to generate fresh required workflows from the updated central main. The stale OpenCode `CHANGES_REQUESTED` review `4592643416` on previous head `0f103836f15d9055c4ed85152f925a6e9514adb2` was dismissed on 2026-06-30 00:25 KST; the PR now requires fresh current-head OpenCode/coverage evidence and still has queued `coverage-evidence`.

## Good patterns to keep

- `naruon`: separates PR Governance, OpenCode review, Strix evidence, and application CI into explicit checks.
- `.github`: centralizes reusable workflow logic and review/merge scheduler code.
- `pg-erd-cloud`: has separate autofix/fix scheduler workflows, useful as a reference for repair automation but not as a merge authority.
- `ContextualWisdomLab.github.io`: thin caller pattern is acceptable for repository-local workflows only when GitHub does not offer an organization-level control. It should not be the default rollout mechanism.

## Risks and follow-up

- Existing open PRs may need a new push or base update before the latest required workflow SHA appears on their current head.
- The central OpenCode workflow now retries DeepSeek R1, DeepSeek V3, GPT-5, and a catalog fallback pool. Keep model/tooling failures out of PR comments unless there is a source-backed failed-check diagnosis.
- The central OpenCode config includes a read-only `code-reviewer` subagent for focused review passes. The subagent may read, grep, glob, and run safe local verification commands, but it must not edit files, stage changes, commit, push, install dependencies, mutate branches, or touch production state.
- OpenCode execution evidence must be sandboxed in the CI workspace or an isolated temporary directory, with a credential-scrubbed environment by default and no persistent mutation outside test caches or scratch files. Prefer `python3 scripts/ci/sandboxed_verify.py --repo-root <reviewed worktree> -- <verification command>` when the central helper is available, and cite its `SANDBOXED_VERIFY_RESULT` line. When repo-native verification legitimately needs network access or GitHub Secrets, pass only the needed names with `--allow-env`, record `--network required`, and explain it with `--evidence-note` without printing secret values. The helper does not replace existing bash, task, webfetch, websearch, lsp, CodeGraph, DeepWiki, Context7, or web_search review policy. If a verification cannot be sandboxed without changing the result, the review must say so instead of presenting an unsafe run as evidence.
- Web application reviews should run backend, frontend, and repository-native E2E checks together through `python3 scripts/ci/sandboxed_web_e2e.py --repo-root <reviewed worktree> --backend-cmd <backend command> --frontend-cmd <frontend command> --e2e-cmd <e2e command>` when those contracts exist, then cite `SANDBOXED_WEB_E2E_RESULT`. If backend/frontend/E2E/readiness contracts are missing, the review must name the gap instead of treating unit or lint evidence as full E2E proof.
- Bounded OpenCode evidence includes `Review execution contracts`, which inventories runtime matrices, package manifests, test, coverage, docstring, E2E, lint, security, Docker, and unpackaged-source gaps before the model chooses verification commands.
- Generated OpenCode review DAGs must use quoted Mermaid labels such as `A["text"]`; unquoted labels with spaces, punctuation, parentheses, or file counts can fail to render.
- OpenCode approval summaries must not contradict exact changed-file evidence by saying no source, test, or executable files changed when workflow, script, source, or test files are present.
- OpenCode approval reasons must not trivialize material workflow, script/source, or test changes as docs-only, typo-only, or string-only changes. The normalizer now rejects those approvals before publication.
- Same-repository post-approval merge/update follow-up should use the workflow `github.token` first so the mechanical actor is `github-actions[bot]`; cross-repository manual dispatch may still fall back to configured secrets or the OpenCode app token when the workflow token cannot mutate the target repository.
- Do not copy central Strix, OpenCode, or merge scheduler workflows into repositories. Repository-local application CI, security CI, or targeted autofix workers may remain when they are not substitutes for the required central workflows.
- `pg-erd-cloud` still has a repository-local `pr-review-autofix.yml` worker; keep it out of the central required-workflow contract unless the autofix path is also moved to organization-level execution.
- Some repositories use classic branch protection while others use rulesets. Normalize branch protection into rulesets without removing repository-specific required application checks.
- Existing PRs may not show newly inherited required workflows until a new PR event or branch update occurs, even though the org ruleset now uses the all-repository condition.
