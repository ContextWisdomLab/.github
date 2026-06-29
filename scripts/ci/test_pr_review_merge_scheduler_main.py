import pytest
import sys
import subprocess
import pr_review_merge_scheduler as scheduler
from unittest.mock import patch

def test_main_block_success():
    result = subprocess.run([sys.executable, "scripts/ci/pr_review_merge_scheduler.py", "--self-test"], capture_output=True, text=True)
    assert result.returncode == 0
    assert "self-test passed" in result.stdout

def test_main_block_runtime_error():
    with open("scripts/ci/pr_review_merge_scheduler.py", "r") as f:
        code = f.read()

    with open("scripts/ci/dummy_test_main.py", "w") as f:
        f.write(code.replace("def main(argv: list[str]) -> int:", "def main(argv: list[str]) -> int:\n    raise RuntimeError('test error')"))

    result = subprocess.run([sys.executable, "scripts/ci/dummy_test_main.py", "--self-test"], capture_output=True, text=True)
    assert result.returncode == 1
    assert "test error" in result.stderr

def test_opencode_in_progress_no_match():
    pr = {
        "statusCheckRollup": {
            "contexts": {
                "nodes": [
                    {"__typename": "CheckRun", "name": "other"}
                ]
            }
        }
    }
    assert not scheduler.opencode_in_progress(pr)

def test_opencode_in_progress_not_match_other():
    pr = {
        "statusCheckRollup": {
            "contexts": {
                "nodes": [
                    {"context": "other"}
                ]
            }
        }
    }
    assert not scheduler.opencode_in_progress(pr)
