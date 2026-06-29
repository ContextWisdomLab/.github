#!/bin/bash
coverage erase

export PYTHONPATH="scripts/ci:$PYTHONPATH"

# 1. Run the test file normally
coverage run -p -m pytest scripts/ci/test_pr_review_merge_scheduler.py

# 2. Run the main block using a dummy script that imports it
cat << 'PY_EOF' > run_main.py
import sys
import pr_review_merge_scheduler as prms
# This will execute the main function inside test_pr_review_merge_scheduler.py
# However, to hit the __main__ condition, we can use a small hack
import runpy
runpy.run_path("scripts/ci/pr_review_merge_scheduler.py", run_name="__main__")
PY_EOF

# Ensure we pass the --self-test to it
coverage run -p run_main.py --self-test > /dev/null

# 3. Simulate an error in the __main__ block
cat << 'PY_EOF' > run_main_error.py
import sys
# patch main to throw RuntimeError
import runpy

def patch_and_run():
    # we inject a mocked `main` into the script's global scope using a pre-exec trick or simple file rewrite
    with open("scripts/ci/pr_review_merge_scheduler.py", "r") as f:
        code = f.read()

    code = code.replace("def main(argv: list[str]) -> int:", "def main(argv: list[str]) -> int:\n    raise RuntimeError('custom_error')\n")
    with open("scripts/ci/dummy_prms.py", "w") as f:
        f.write(code)

    runpy.run_path("scripts/ci/dummy_prms.py", run_name="__main__")

patch_and_run()
PY_EOF

coverage run -p run_main_error.py --self-test > /dev/null 2>&1

# Combine and report
coverage combine
coverage report -m scripts/ci/pr_review_merge_scheduler.py
