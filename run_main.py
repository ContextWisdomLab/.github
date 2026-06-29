import sys
import runpy

try:
    sys.argv = ['pr_review_merge_scheduler.py', '--self-test']
    runpy.run_path("scripts/ci/pr_review_merge_scheduler.py", run_name="__main__")
except SystemExit:
    pass

with open("scripts/ci/pr_review_merge_scheduler.py", "r") as f:
    code = f.read()

new_code = code.replace("def main(argv: list[str]) -> int:", "def main(argv: list[str]) -> int:\n    raise RuntimeError('custom')")
with open("scripts/ci/pr_review_merge_scheduler.py", "w") as f:
    f.write(new_code)

try:
    sys.argv = ['pr_review_merge_scheduler.py']
    runpy.run_path("scripts/ci/pr_review_merge_scheduler.py", run_name="__main__")
except SystemExit:
    pass

with open("scripts/ci/pr_review_merge_scheduler.py", "w") as f:
    f.write(code)
