import sys

def main():
    import pr_review_merge_scheduler
    pr_review_merge_scheduler.main = lambda x: (_ for _ in ()).throw(RuntimeError("error"))
    # We will run this with coverage
    # We need to simulate the if __name__ == "__main__": block
    try:
        raise SystemExit(pr_review_merge_scheduler.main(sys.argv[1:]))
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc

if __name__ == "__main__":
    main()
