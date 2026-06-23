## 2024-06-20 - Prevent HTML Comment Breakout in JSON Serialization
**Vulnerability:** Markdown Injection / HTML Comment Breakout
**Learning:** JSON serialized into HTML comments (like `<!-- json -->`) can contain `-->` in string values, causing GitHub's Markdown parser to close the comment prematurely and render the remaining JSON as attacker-controlled text or Markdown.
**Prevention:** Always escape `<` and `>` as `\u003c` and `\u003e` (and `&` as `\u0026`) when embedding JSON in HTML contexts (even Markdown comments) to prevent breakout.

## 2024-06-25 - Force Python JSON Normalizer to Prevent CI Gate Bypass
**Vulnerability:** Workflow CI Security Bypass / Markdown Injection
**Learning:** The GitHub Actions workflow `opencode-review.yml` attempted to optimize performance by doing a fast-path bash string extraction. If this succeeded, it skipped the Python JSON normalizer (`opencode_review_normalize_output.py`). This is a security flaw because the bash script does not escape `<, >, &` characters, allowing attackers to inject `-->` directly in JSON strings to break out of HTML comment sections.
**Prevention:** Removed the fast-path check entirely. We must always enforce JSON normalization via `opencode_review_normalize_output.py` because it correctly parses the JSON payload and safely escapes all characters as `\u003c`, `\u003e` and `\u0026`.

## 2025-02-23 - [Information Leakage in CI Subprocess Errors]
**Vulnerability:** The script `scripts/ci/pr_review_merge_scheduler.py` included `process.stderr` in the `RuntimeError` exception when a subprocess failed. This could potentially leak sensitive information (e.g., API keys, auth tokens) into GitHub Actions logs.
**Learning:** CI/CD error messages must fail securely without exposing the stderr of external commands that may contain sensitive data, especially when interfacing with authenticated CLI tools like `gh`.
**Prevention:** Avoid printing or including raw `stderr` in exceptions or logs unless sanitized.
