## 2024-06-20 - Prevent HTML Comment Breakout in JSON Serialization
**Vulnerability:** Markdown Injection / HTML Comment Breakout
**Learning:** JSON serialized into HTML comments (like `<!-- json -->`) can contain `-->` in string values, causing GitHub's Markdown parser to close the comment prematurely and render the remaining JSON as attacker-controlled text or Markdown.
**Prevention:** Always escape `<` and `>` as `\u003c` and `\u003e` (and `&` as `\u0026`) when embedding JSON in HTML contexts (even Markdown comments) to prevent breakout.
## 2024-06-25 - Force Python JSON Normalizer to Prevent CI Gate Bypass
**Vulnerability:** Workflow CI Security Bypass / Markdown Injection
**Learning:** The GitHub Actions workflow `opencode-review.yml` attempted to optimize performance by doing a fast-path bash string extraction. If this succeeded, it skipped the Python JSON normalizer (`opencode_review_normalize_output.py`). This is a security flaw because the bash script does not escape `<, >, &` characters, allowing attackers to inject `-->` directly in JSON strings to break out of HTML comment sections.
**Prevention:** Removed the fast-path check entirely. We must always enforce JSON normalization via `opencode_review_normalize_output.py` because it correctly parses the JSON payload and safely escapes all characters as `\u003c`, `\u003e` and `\u0026`.
## 2024-06-22 - [CRITICAL] Prevent Sensitive Token Leakage in Subprocess Calls

**Vulnerability:**
The CI script (`pr_review_merge_scheduler.py`) included the command arguments (`{' '.join(args)}`) in its `RuntimeError` message when a subprocess failed. This can potentially leak sensitive information like GitHub tokens or internal environment variables that are passed directly as command-line arguments into CI/CD logs.

**Learning:**
In an automated environment with complex bash and Python CI integration scripts, failing securely is paramount. Directly dumping command arguments into standard error strings can unknowingly expose credentials when commands fail in unexpected ways. Suppressing `stderr` is an anti-pattern as it hinders debugging, so it must be preserved.

**Prevention:**
Never include the exact command string/arguments (`args`) in standard exception messages from automated scripts if there is any chance they contain secrets. Provide the command name or a generic description along with the `stderr` to aid debugging without exposing secrets.
