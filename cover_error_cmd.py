import sys
import runpy

def patch_and_run():
    with open("scripts/ci/pr_review_merge_scheduler.py", "r") as f:
        code = f.read()

    # Simple replace
    new_code = code.replace("def main(argv: list[str]) -> int:", "def main(argv: list[str]) -> int:\n    raise RuntimeError('custom error')")

    with open("scripts/ci/pr_review_merge_scheduler.py", "w") as f:
        f.write(new_code)

    try:
        runpy.run_path("scripts/ci/pr_review_merge_scheduler.py", run_name="__main__")
    except SystemExit:
        pass

    # Restore
    with open("scripts/ci/pr_review_merge_scheduler.py", "w") as f:
        f.write(code)

patch_and_run()
