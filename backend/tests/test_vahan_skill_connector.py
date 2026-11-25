import unittest

from app.connectors.vahan_skill import VAHANDashboardSkillConnector, _extract_vahan_year_records
from app.core.models import FetchResult


class VAHANDashboardSkillConnectorTests(unittest.TestCase):
    def test_extract_vahan_year_records_sums_tracked_vehicle_categories(self):
        table_html = """
        <div id="combTablePnl">
          <table>
            <thead>
              <tr>
                <th>S No</th><th>Vehicle Category</th><th colspan="2">Month Wise</th><th>TOTAL</th>
              </tr>
              <tr><th>JAN</th><th>FEB</th></tr>
            </thead>
            <tbody id="groupingTable_data">
              <tr><td>1</td><td>FOUR WHEELER (Invalid Carriage)</td><td>10</td><td>20</td><td>30</td></tr>
              <tr><td>2</td><td>HEAVY MOTOR VEHICLE</td><td>1</td><td>2</td><td>3</td></tr>
              <tr><td>3</td><td>LIGHT GOODS VEHICLE</td><td>999</td><td>999</td><td>1,998</td></tr>
              <tr><td>4</td><td>LIGHT MOTOR VEHICLE</td><td>6,29,000</td><td>4,72,240</td><td>11,01,240</td></tr>
              <tr><td>5</td><td>MEDIUM MOTOR VEHICLE</td><td>808</td><td>873</td><td>1,681</td></tr>
              <tr><td>6</td><td>TWO WHEELER (Invalid Carriage)</td><td>2,618</td><td>5,337</td><td>7,955</td></tr>
              <tr><td>7</td><td>TWO WHEELER(NT)</td><td>19,19,913</td><td>17,66,036</td><td>36,85,949</td></tr>
              <tr><td>8</td><td>TWO WHEELER(T)</td><td>2,745</td><td>2,856</td><td>5,601</td></tr>
            </tbody>
          </table>
        </div>
        """

        records = _extract_vahan_year_records(table_html, 2026)

        self.assertEqual('2026-01', records[0]['month'])
        self.assertEqual(1925276.0, records[0]['two_wheeler_sales'])
        self.assertEqual(629819.0, records[0]['four_wheeler_sales'])
        self.assertEqual('2026-02', records[1]['month'])
        self.assertEqual(1774229.0, records[1]['two_wheeler_sales'])
        self.assertEqual(473135.0, records[1]['four_wheeler_sales'])

    def test_parse_converts_vahan_json_payload_to_registration_observations(self):
        connector = VAHANDashboardSkillConnector()
        raw = FetchResult(
            dataset_code='vahan_vehicle_registrations',
            status='success',
            parser_version='test',
            source_url='https://example.test/vahan',
            payload_type='json',
            payload={'records': [{'month': '2026-06', 'two_wheeler_sales': 1826985, 'four_wheeler_sales': 468179}]},
        )

        observations = connector.parse(raw)

        self.assertEqual(['two_wheeler_sales', 'four_wheeler_sales'], [obs.metric_code for obs in observations])
        self.assertEqual(1826985.0, observations[0].value)
        self.assertEqual(468179.0, observations[1].value)
        self.assertEqual('units', observations[0].unit)


if __name__ == '__main__':
    unittest.main()
