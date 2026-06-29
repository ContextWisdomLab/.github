import sys
import coverage

cov = coverage.Coverage()
cov.start()

import pr_review_merge_scheduler as scheduler
scheduler.main = lambda x: (_ for _ in ()).throw(RuntimeError("error test"))

# Simulate __main__ directly
try:
    raise SystemExit(scheduler.main(sys.argv[1:]))
except RuntimeError as exc:
    print(str(exc), file=sys.stderr)
    try:
        raise SystemExit(1) from exc
    except SystemExit:
        pass

cov.stop()
cov.save()
