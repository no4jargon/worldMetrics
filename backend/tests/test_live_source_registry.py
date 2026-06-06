import unittest

from app.live.source_registry import DEFAULT_SOURCE_CONFIGS, source_config_by_dataset


class LiveSourceRegistryTests(unittest.TestCase):
    def test_default_source_configs_include_personal_tracker_sources(self):
        self.assertEqual('https://www.jll.com/en-in/newsroom', source_config_by_dataset('jll_residential_sales').listing_url)
        self.assertEqual('https://vahan.parivahan.gov.in/vahan4dashboard/', source_config_by_dataset('vahan_vehicle_registrations').listing_url)
        self.assertEqual(2, len(DEFAULT_SOURCE_CONFIGS))

    def test_vahan_config_points_to_manual_dashboard_skill(self):
        vahan = source_config_by_dataset('vahan_vehicle_registrations')

        self.assertEqual('vahan-dashboard', vahan.filters['retrieval_skill'])
        self.assertEqual('true', vahan.filters['auto_call'])
        self.assertEqual('Tabular Summary', vahan.filters['view'])
        self.assertEqual('Month Wise', vahan.filters['x_axis'])
        self.assertEqual('agent_skill:vahan-dashboard', vahan.extraction_mode)


if __name__ == '__main__':
    unittest.main()
