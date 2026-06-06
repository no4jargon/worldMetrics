import json
import tempfile
import unittest
from pathlib import Path

from app.main import run


class MainTests(unittest.TestCase):
    def test_run_builds_snapshot_files_in_output_directory(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir)

            run(output_dir=output_dir)

            overview = json.loads((output_dir / 'overview.json').read_text())
            self.assertIn('cards', overview)
            self.assertIn('summary', overview)


if __name__ == '__main__':
    unittest.main()
