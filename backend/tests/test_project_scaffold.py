import json
import unittest
from pathlib import Path


class ProjectScaffoldTests(unittest.TestCase):
    def test_frontend_scaffold_files_exist(self):
        root = Path(__file__).resolve().parents[2]

        required_paths = [
            root / 'web' / 'package.json',
            root / 'web' / 'app' / 'page.tsx',
            root / 'web' / 'app' / 'power' / 'page.tsx',
            root / 'web' / 'app' / 'construction' / 'page.tsx',
            root / 'web' / 'app' / 'demand' / 'page.tsx',
            root / 'web' / 'app' / 'inflation' / 'page.tsx',
            root / 'web' / 'app' / 'release-monitor' / 'page.tsx',
            root / 'web' / 'app' / 'api' / 'overview' / 'route.ts',
            root / 'web' / 'app' / 'api' / 'series' / 'route.ts',
        ]

        for path in required_paths:
            self.assertTrue(path.exists(), f'missing scaffold file: {path}')

    def test_frontend_package_declares_nextjs_dependencies(self):
        root = Path(__file__).resolve().parents[2]
        package_json = root / 'web' / 'package.json'

        data = json.loads(package_json.read_text())

        self.assertEqual('world-metrics-web', data['name'])
        self.assertIn('next', data['dependencies'])
        self.assertIn('react', data['dependencies'])
        self.assertIn('react-dom', data['dependencies'])

    def test_frontend_typescript_config_is_valid_json(self):
        root = Path(__file__).resolve().parents[2]
        tsconfig_json = root / 'web' / 'tsconfig.json'

        data = json.loads(tsconfig_json.read_text())

        self.assertIn('compilerOptions', data)
        self.assertEqual('bundler', data['compilerOptions']['moduleResolution'])


if __name__ == '__main__':
    unittest.main()
