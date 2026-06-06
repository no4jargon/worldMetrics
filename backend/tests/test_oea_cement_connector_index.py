import unittest
from datetime import date

from app.connectors.oea_cement import OEACoreIndustriesConnector
from app.core.models import FetchResult


class OEACoreIndustriesConnectorIndexTests(unittest.TestCase):
    def test_parse_converts_oea_payload_to_cement_output_index_observation(self):
        connector = OEACoreIndustriesConnector()
        raw = FetchResult(
            dataset_code='oea_core_industries',
            status='success',
            parser_version='test',
            source_url='https://example.test/oea/core-industries',
            payload_type='json',
            payload={
                'records': [
                    {
                        'month': '2026-02',
                        'cement_output_index': 235.2,
                        'release_date': '2026-03-20',
                        'is_provisional': True,
                    }
                ]
            },
        )

        observations = connector.parse(raw)

        self.assertEqual(1, len(observations))
        observation = observations[0]
        self.assertEqual('cement_output_index', observation.metric_code)
        self.assertEqual(235.2, observation.value)
        self.assertEqual('index', observation.unit)
        self.assertTrue(observation.is_preliminary)
        self.assertEqual(date(2026, 3, 20), observation.source_release_date)


if __name__ == '__main__':
    unittest.main()
