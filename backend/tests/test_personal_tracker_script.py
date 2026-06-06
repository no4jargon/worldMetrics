import unittest
from pathlib import Path


class PersonalTrackerScriptTests(unittest.TestCase):
    def test_run_personal_tracker_script_exists(self):
        script_path = Path('scripts/run-personal-tracker.sh')

        self.assertTrue(script_path.exists())


if __name__ == '__main__':
    unittest.main()
