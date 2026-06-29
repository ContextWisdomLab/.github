import sys
import runpy

def patch_and_run():
    sys.argv = ['pr_review_merge_scheduler.py', '--self-test']

    with open("scripts/ci/pr_review_merge_scheduler.py", "r") as f:
        code = f.read()

    # We want to keep original filename in coverage if possible, or we can just
    # mock sys.argv inside the original script execution without patching the code
    # to throw runtime error directly from main using mock
    pass

import pr_review_merge_scheduler
from unittest.mock import patch
with patch("pr_review_merge_scheduler.main", side_effect=RuntimeError("err")):
    # Run the exact code block
    try:
        # We need to execute the __main__ block code literally
        with open("scripts/ci/pr_review_merge_scheduler.py") as f:
            code = f.read()

        main_block = code.split("if __name__ == \"__main__\":")[1]

        # We define a dummy main to throw the error
        exec(
            "def main(argv):\n"
            "    raise RuntimeError('custom')\n"
            + main_block
        )
    except SystemExit:
        pass
