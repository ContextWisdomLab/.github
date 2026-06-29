## 2024-06-20 - Prevent HTML Comment Breakout in JSON Serialization
**Vulnerability:** Markdown Injection / HTML Comment Breakout
**Learning:** JSON serialized into HTML comments (like `<!-- json -->`) can contain `-->` in string values, causing GitHub's Markdown parser to close the comment prematurely and render the remaining JSON as attacker-controlled text or Markdown.
**Prevention:** Always escape `<` and `>` as `\u003c` and `\u003e` (and `&` as `\u0026`) when embedding JSON in HTML contexts (even Markdown comments) to prevent breakout.
## 2024-06-25 - Force Python JSON Normalizer to Prevent CI Gate Bypass
**Vulnerability:** Workflow CI Security Bypass / Markdown Injection
**Learning:** The GitHub Actions workflow `opencode-review.yml` attempted to optimize performance by doing a fast-path bash string extraction. If this succeeded, it skipped the Python JSON normalizer (`opencode_review_normalize_output.py`). This is a security flaw because the bash script does not escape `<, >, &` characters, allowing attackers to inject `-->` directly in JSON strings to break out of HTML comment sections.
**Prevention:** Removed the fast-path check entirely. We must always enforce JSON normalization via `opencode_review_normalize_output.py` because it correctly parses the JSON payload and safely escapes all characters as `\u003c`, `\u003e` and `\u0026`.
## 2026-06-29 - Prevent API Key Leak via Subprocess Environment
**Vulnerability:** API keys passed through environment variables without adequate masking
**Learning:** In bash, passing secrets as environment variables to a child process (like `strix`) can inadvertently expose them in logs, process lists, or crash dumps. The Strix scanner specifically flagged `STRIX_CHILD_LLM_API_KEY` and `LLM_API_KEY` being passed as environment variables.
**Prevention:** Whenever possible, write secrets to a temporary file with strict permissions (e.g., `umask 077`) and pass the file path to child processes instead of passing the secret string directly in the environment.
