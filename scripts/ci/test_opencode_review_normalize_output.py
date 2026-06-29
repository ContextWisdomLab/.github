#!/usr/bin/env python3
import json
import subprocess
import sys
from pathlib import Path

def test_json_escaping():
    repo_root = Path(__file__).resolve().parent.parent.parent
    normalizer = repo_root / "scripts" / "ci" / "opencode_review_normalize_output.py"

    # Create dummy input with malicious content
    dummy_control = {
        "head_sha": "abc123def456",
        "run_id": "12345",
        "run_attempt": "1",
        "result": "APPROVE",
        "reason": "Looking good at paths/file.js. <script>alert(1)</script> -->",
        "summary": "Looks good! & so on."
    }
    input_text = json.dumps(dummy_control)

    input_file = Path("test_input.json")
    input_file.write_text(input_text, encoding="utf-8")

    output_file = Path("test_input.json")

    try:
        subprocess.run(
            [sys.executable, str(normalizer), "abc123def456", "12345", "1", str(output_file)],
            check=True
        )

        output_text = output_file.read_text(encoding="utf-8")

        # Check if the output contains the properly escaped characters
        assert r"\u003c" in output_text, "Failed to escape <"
        assert r"\u003e" in output_text, "Failed to escape >"
        assert r"\u0026" in output_text, "Failed to escape &"
        assert "<" not in output_text.split("<!-- opencode-review-control-v1")[1].split("-->")[0], "Found unescaped < in JSON block"

        # Check that it's still valid JSON
        json_content = output_text.split("<!-- opencode-review-control-v1\n")[1].split("\n-->")[0]
        parsed = json.loads(json_content)
        assert parsed["reason"] == dummy_control["reason"], "JSON value changed after parsing"

        print("opencode_review_normalize_output escaping tests passed")
    finally:
        if input_file.exists():
            input_file.unlink()

if __name__ == "__main__":
    test_json_escaping()
