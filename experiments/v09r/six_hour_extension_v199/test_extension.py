"""New glue-only checks. No environment, training, old fixture or old native run."""
import unittest
from pathlib import Path
import launch as L
import continue_run as E


class ExtensionChecks(unittest.TestCase):
    def test_learning_configuration_unchanged(self):
        original = E.V.config('long')
        revised = E.extension_config(53)
        changed = {k for k in original if original[k] != revised[k]}
        self.assertEqual(changed, {'wall_seconds', 'report_blocks'})
        self.assertEqual(revised['wall_seconds'], 21600)
        self.assertEqual(revised['report_blocks'][:3], [61,69,77])

    def test_executes_existing_learner_not_reimplementation(self):
        self.assertEqual(Path(E.V.run_task.__code__.co_filename).resolve(), E.PARENT/'run.py')
        self.assertEqual(Path(E.V.Agent.learn.__code__.co_filename).resolve(), E.PARENT/'learning.py')
        self.assertEqual(len(E.SEEDS)*len(E.GROUPS),20)

    def test_dependency_not_assumed_successful(self):
        good = dict(exit_code=0, interruption=None)
        self.assertEqual(L.parent_status(None,None),'WAITING')
        self.assertEqual(L.parent_status(good,None),'WAITING')
        self.assertEqual(L.parent_status(good,dict(exit_code=0)),'READY')
        self.assertEqual(L.parent_status(dict(exit_code=1,interruption=None),None),'FAILED')
        self.assertEqual(L.parent_status(dict(exit_code=0,interruption='WALL_BUDGET'),None),'FAILED')
        self.assertEqual(L.parent_status(good,dict(exit_code=1)),'FAILED')


if __name__ == '__main__':
    unittest.main(verbosity=2)
