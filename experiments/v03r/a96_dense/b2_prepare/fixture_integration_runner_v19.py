"""Fixed targeted construction integration; no collection or key allocation."""
from pathlib import Path
import sys
import unittest

if __name__ == "__main__":
    if len(sys.argv) != 1:
        raise SystemExit("closed four-module engineering suite; no overrides")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    names = ("test_fixture_source_candidate", "test_seed_plan_candidate",
             "test_history_seed_audit_candidate", "test_history_schedule_candidate")
    suite = unittest.defaultTestLoader.loadTestsFromNames(names)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() and not result.skipped else 1)

