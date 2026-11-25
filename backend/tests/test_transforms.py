import unittest
from datetime import date

from app.core.models import CanonicalObservation
from app.core.transforms import compute_transforms


class ComputeTransformsTests(unittest.TestCase):
    def test_yoy_uses_same_calendar_period_with_gaps_and_quarters(self):
        for labels in [('2025-08', '2026-07', '2026-08'),
                       ('2025-Q2', '2026-Q1', '2026-Q2')]:
            observations = [
                CanonicalObservation('example', label, date(int(label[:4]), month, 1),
                                     date(int(label[:4]), month, 28), value, 'units')
                for label, month, value in zip(labels, [6, 3, 6] if 'Q' in labels[0] else [8, 7, 8], [100, 200, 120])
            ]
            yoy = [item for item in compute_transforms(observations) if item.transform == 'yoy']
            self.assertEqual(1, len(yoy))
            self.assertEqual(labels[-1], yoy[0].period_label)
            self.assertAlmostEqual(20, yoy[0].value)

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
