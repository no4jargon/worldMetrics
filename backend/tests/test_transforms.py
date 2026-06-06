import unittest
from datetime import date

from app.core.models import CanonicalObservation
from app.core.transforms import compute_transforms


class ComputeTransformsTests(unittest.TestCase):
    def test_rolling_3_period_average_is_emitted_for_third_observation(self):
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
                period_label='2026-02',
                period_start=date(2026, 2, 1),
                period_end=date(2026, 2, 28),
                value=110.0,
                unit='BU',
            ),
            CanonicalObservation(
                metric_code='power_output_total',
                period_label='2026-03',
                period_start=date(2026, 3, 1),
                period_end=date(2026, 3, 31),
                value=120.0,
                unit='BU',
            ),
        ]

        derived = compute_transforms(observations)

        rolling = [
            item for item in derived
            if item.metric_code == 'power_output_total'
            and item.period_label == '2026-03'
            and item.transform == 'rolling_3p_avg'
        ]

        self.assertEqual(1, len(rolling))
        self.assertAlmostEqual(110.0, rolling[0].value)


if __name__ == '__main__':
    unittest.main()
