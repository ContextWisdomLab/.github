## 2024-06-20 - Prevent HTML Comment Breakout in JSON Serialization
**Vulnerability:** Markdown Injection / HTML Comment Breakout
**Learning:** JSON serialized into HTML comments (like `<!-- json -->`) can contain `-->` in string values, causing GitHub's Markdown parser to close the comment prematurely and render the remaining JSON as attacker-controlled text or Markdown.
**Prevention:** Always escape `<` and `>` as `\u003c` and `\u003e` (and `&` as `\u0026`) when embedding JSON in HTML contexts (even Markdown comments) to prevent breakout.
## 2024-06-25 - Force Python JSON Normalizer to Prevent CI Gate Bypass
**Vulnerability:** Workflow CI Security Bypass / Markdown Injection
**Learning:** The GitHub Actions workflow `opencode-review.yml` attempted to optimize performance by doing a fast-path bash string extraction. If this succeeded, it skipped the Python JSON normalizer (`opencode_review_normalize_output.py`). This is a security flaw because the bash script does not escape `<, >, &` characters, allowing attackers to inject `-->` directly in JSON strings to break out of HTML comment sections.
**Prevention:** Removed the fast-path check entirely. We must always enforce JSON normalization via `opencode_review_normalize_output.py` because it correctly parses the JSON payload and safely escapes all characters as `\u003c`, `\u003e` and `\u0026`.
## 2026-06-29 - Prevent Silent Failure by Capturing stderr in CI Scripts
**Vulnerability:** Silent Failure / Secret Leakage Risk
**Learning:** In `scripts/ci/opencode_review_approve_gate.sh`, `subprocess.run` dropped `stderr` entirely (`stderr=subprocess.DEVNULL`). This hides potential Git errors and causes maintainability regressions. Blindly logging `stderr` instead, however, risks leaking sensitive credentials injected by GitHub Actions.
**Prevention:** Capture `stderr` and filter out known credential patterns (e.g., Bearer tokens, GitHub PATs) before writing errors to `sys.stderr`. Never drop `stderr` completely on subprocess failures.
## 2026-07-01 - Prevent Information Disclosure in Timeout Exceptions
**Vulnerability:** Information Disclosure / Secret Leakage
**Learning:** In `scripts/ci/strix_quick_gate.sh`, `subprocess.Popen.communicate()` returned an `output` string that was printed directly to stdout and a log file when a `TimeoutExpired` exception or other failure occurred. If a timeout happens, the raw output may contain sensitive data such as `Bearer` tokens, API keys, or `GitHub PATs` from the invoked program.
**Prevention:** Apply the `scrub_sensitive_data` utility function directly to the `output` before logging or writing to disk to sanitize any exposed credentials.
