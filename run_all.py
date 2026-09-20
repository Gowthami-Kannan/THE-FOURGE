"""
Run every test with the standard library only:

    python tests/run_all.py

Tests that need FastAPI report as skipped if the web stack is not installed.
"""

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite = loader.discover(start_dir=os.path.join(ROOT, "tests"),
                            pattern="test_*.py", top_level_dir=ROOT)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
