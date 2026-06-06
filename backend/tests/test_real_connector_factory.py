import unittest
from pathlib import Path

from app.connectors.factory import build_real_connectors


class RealConnectorFactoryTests(unittest.TestCase):
    def test_build_real_connectors_returns_one_connector_per_default_dataset(self):
        fixture_paths = {
            'npp_monthly_generation': Path('/tmp/npp.json'),
            'oea_core_industries': Path('/tmp/oea-cement.json'),
            'jll_residential_sales': Path('/tmp/jll-residential.json'),
            'mospi_cpi': Path('/tmp/mospi-cpi.json'),
        }

        connectors = build_real_connectors(fixture_paths=fixture_paths)
        dataset_codes = [connector.dataset_code for connector in connectors]

        self.assertEqual(
            [
                'npp_monthly_generation',
                'oea_core_industries',
                'jll_residential_sales',
                'vahan_vehicle_registrations',
                'mospi_cpi',
            ],
            dataset_codes,
        )

        vahan = connectors[3]
        raw = vahan.fetch()
        self.assertEqual('skill_requested', raw.status)
        self.assertEqual('/skill:vahan-dashboard', raw.payload['skill_command'])
        self.assertTrue(raw.payload['auto_requested'])


if __name__ == '__main__':
    unittest.main()
