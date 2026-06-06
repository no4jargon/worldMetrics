from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Iterable

from .metric_registry import UnitConversionError, canonical_unit_for_metric, convert_value, normalize_unit
from .models import CanonicalObservation


class ValidationError(Exception):
    pass


MONTHLY_PREFIX = 7
QUARTERLY_PREFIX = 6
QUARTER_ENDS = {(3, 31), (6, 30), (9, 30), (12, 31)}


def _is_quarterly(obs: CanonicalObservation) -> bool:
    return '-Q' in obs.period_label


def _validate_period_label(obs: CanonicalObservation) -> None:
    if _is_quarterly(obs):
        if len(obs.period_label) < QUARTERLY_PREFIX:
            raise ValidationError(f'invalid quarterly label: {obs.period_label}')
        if (obs.period_end.month, obs.period_end.day) not in QUARTER_ENDS:
            raise ValidationError(f'quarterly observation must end on quarter end: {obs.metric_code} {obs.period_label}')
    else:
        if len(obs.period_label) < MONTHLY_PREFIX:
            raise ValidationError(f'invalid monthly label: {obs.period_label}')


def _expected_next_period_start(obs: CanonicalObservation) -> date:
    if _is_quarterly(obs):
        month = obs.period_start.month + 3
    else:
        month = obs.period_start.month + 1
    year = obs.period_start.year + ((month - 1) // 12)
    month = ((month - 1) % 12) + 1
    return date(year, month, 1)


def collect_validation_warnings(observations: Iterable[CanonicalObservation]) -> list[str]:
    grouped: dict[tuple[str, str], list[CanonicalObservation]] = defaultdict(list)
    for obs in observations:
        grouped[(obs.metric_code, obs.segment or 'ALL')].append(obs)

    warnings: list[str] = []
    for (metric_code, segment), items in grouped.items():
        items.sort(key=lambda x: x.period_start)
        for prev, curr in zip(items, items[1:]):
            expected = _expected_next_period_start(prev)
            if curr.period_start != expected:
                warnings.append(
                    f'missing period for {metric_code} segment={segment}: expected {expected.isoformat()[:7]} before {curr.period_label}'
                )
    return warnings


def validate_observations(observations: Iterable[CanonicalObservation]) -> None:
    seen = set()
    grouped: dict[tuple[str, str], list[CanonicalObservation]] = defaultdict(list)

    for obs in observations:
        key = (obs.metric_code, obs.period_label, obs.segment or 'ALL')
        if key in seen:
            raise ValidationError(f'duplicate observation: {key}')
        seen.add(key)
        grouped[(obs.metric_code, obs.segment or 'ALL')].append(obs)

        canonical_unit = canonical_unit_for_metric(obs.metric_code)
        normalized_unit = normalize_unit(obs.unit)
        validation_value = obs.value
        if canonical_unit is not None:
            try:
                validation_value = convert_value(obs.value, normalized_unit, canonical_unit)
            except UnitConversionError as error:
                raise ValidationError(f'wrong unit for {obs.metric_code}: expected {canonical_unit}, got {obs.unit}') from error
        elif normalized_unit != obs.unit:
            validation_value = obs.value

        if (canonical_unit or normalized_unit) == 'percent' and not (0 <= validation_value <= 100):
            raise ValidationError(f'percent metric out of range for {obs.metric_code} {obs.period_label}: {obs.value}')

        _validate_period_label(obs)

    for _, items in grouped.items():
        items.sort(key=lambda x: x.period_start)
        for prev, curr in zip(items, items[1:]):
            if curr.period_start <= prev.period_start:
                raise ValidationError(f'non-increasing periods for {curr.metric_code}')
