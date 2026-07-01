1. **Analyze:** We need ONE small performance improvement.
In `scripts/ci/pr_review_merge_scheduler.py`, the `active_workflow_runs` function fetches "queued" and "in_progress" workflow runs sequentially via `gh api`.
These two API calls are entirely independent and block execution. By using `concurrent.futures.ThreadPoolExecutor`, we can execute them concurrently, reducing the wall-clock network delay by ~50% per invocation.

2. **Implement:**
Update `scripts/ci/pr_review_merge_scheduler.py`:
```python
<<<<<<< SEARCH
def active_workflow_runs(repo: str) -> list[dict[str, Any]]:
    """Return queued and in-progress workflow runs for a repository."""
    runs: list[dict[str, Any]] = []
    for status in ("queued", "in_progress"):
        payload = json.loads(
            run_github_actions(
                [
                    "gh",
                    "api",
                    "--method",
                    "GET",
                    f"repos/{repo}/actions/runs",
                    "-f",
                    f"status={status}",
                    "-F",
                    "per_page=100",
                ]
            )
        )
        runs.extend(payload.get("workflow_runs") or [])
    return runs
=======
def active_workflow_runs(repo: str) -> list[dict[str, Any]]:
    """Return queued and in-progress workflow runs for a repository."""
    runs: list[dict[str, Any]] = []

    def fetch_runs_by_status(status: str) -> list[dict[str, Any]]:
        payload = json.loads(
            run_github_actions(
                [
                    "gh",
                    "api",
                    "--method",
                    "GET",
                    f"repos/{repo}/actions/runs",
                    "-f",
                    f"status={status}",
                    "-F",
                    "per_page=100",
                ]
            )
        )
        return payload.get("workflow_runs") or []

    # ⚡ Bolt: Fetch queued and in_progress runs concurrently to avoid sequential API blocking
    # Impact: Halves network wait time by performing two independent REST API requests simultaneously
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        for run_list in executor.map(fetch_runs_by_status, ("queued", "in_progress")):
            runs.extend(run_list)

    return runs
>>>>>>> REPLACE
```

3. **Verify:**
   - Run tests: `python3 scripts/ci/pr_review_merge_scheduler.py --self-test`
   - Run other CI checks: `bash scripts/ci/test_opencode_fact_gate_contract.sh`

4. **Complete Pre Commit Steps:** Complete pre commit steps to ensure proper testing, verification, review, and reflection are done.

5. **Commit and create PR:**
Create a PR with a description explaining the optimization and expected impact.
