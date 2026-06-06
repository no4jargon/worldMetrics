import unittest
from datetime import date

from app.core.models import CanonicalObservation
from app.core.validation import ValidationError, collect_validation_warnings, validate_observations


class ValidateObservationsTests(unittest.TestCase):
    def test_quarterly_observation_must_end_on_quarter_end(self):
        observations = [
            CanonicalObservation(
                metric_code='home_sales_jll',
                period_label='2025-Q1',
                period_start=date(2025, 1, 1),
                period_end=date(2025, 3, 30),
                value=70300,
                unit='units',
                segment='top_7_cities',
            )
        ]

        with self.assertRaises(ValidationError):
            validate_observations(observations)

    def test_missing_month_in_monthly_series_returns_warning(self):
        observations = [
            CanonicalObservation(
                metric_code='power_output_total',
                period_label='2026-01',
                period_start=date(2026, 1, 1),
                period_end=date(2026, 1, 31),
                value=100.0,
                unit='BU',
            ),
            CanonicalObservation(
                metric_code='power_output_total',
                period_label='2026-03',
                period_start=date(2026, 3, 1),
                period_end=date(2026, 3, 31),
                value=110.0,
                unit='BU',
            ),
        ]

        warnings = collect_validation_warnings(observations)

        self.assertEqual(1, len(warnings))
        self.assertIn('missing period', warnings[0])
        self.assertIn('2026-02', warnings[0])


if __name__ == '__main__':
    unittest.main()
