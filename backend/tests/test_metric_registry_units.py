from __future__ import annotations

from datetime import date

from app.core.metric_registry import canonicalize_observation
from app.core.models import CanonicalObservation
from app.core.validation import ValidationError, validate_observations


def test_power_bu_is_canonicalized_to_gwh() -> None:
    obs = CanonicalObservation(
        metric_code='power_output_total',
        period_label='2026-02',
        period_start=date(2026, 2, 1),
        period_end=date(2026, 2, 28),
        value=142.5,
        unit='BU',
    )

    canonical = canonicalize_observation(obs)

    assert canonical.value == 142500.0
    assert canonical.unit == 'GWh'


def test_percent_metrics_must_be_percent_units() -> None:
    obs = CanonicalObservation(
        metric_code='power_utilization_plf',
        period_label='2026-02',
        period_start=date(2026, 2, 1),
        period_end=date(2026, 2, 28),
        value=69.1,
        unit='GWh',
    )

    try:
        validate_observations([obs])
    except ValidationError as error:
        assert 'wrong unit' in str(error)
    else:
        raise AssertionError('ValidationError was not raised')
