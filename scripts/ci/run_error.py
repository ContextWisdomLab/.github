import sys
import unittest.mock

with unittest.mock.patch("sys.argv", ["prog", "--missing-flag-to-cause-error-or-mock-main"]):
    pass
