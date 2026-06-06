from __future__ import annotations

from dataclasses import replace
from typing import Callable

from app.core.models import CanonicalObservation


class UnitConversionError(ValueError):
    pass


CANONICAL_METRIC_UNITS: dict[str, str] = {
    # Energy totals: store as gigawatt-hours. Indian power releases often report
    # "BU" / "billion units"; 1 BU = 1,000 GWh.
    'power_output_total': 'GWh',
    'power_consumed_total': 'GWh',
    # Utilization / rates
    'power_utilization_plf': 'percent',
    'cement_utilization_est': 'percent',
    'cpi_headline': 'percent',
    # Physical/index/count metrics
    'cement_output': 'MT',
    'cement_output_index': 'index',
    'home_sales_jll': 'units',
    'auto_sales_total': 'units',
    'two_wheeler_sales': 'units',
    'four_wheeler_sales': 'units',
    'cpi_index': 'index',
}


def _identity(value: float) -> float:
    return value


def _bu_to_gwh(value: float) -> float:
    return value * 1000.0


def _gwh_to_bu(value: float) -> float:
    return value / 1000.0


_UNIT_ALIASES: dict[str, str] = {
    '%': 'percent',
    'percentage': 'percent',
    'percentage_points': 'percentage_points',
    'pp': 'percentage_points',
    'gwh': 'GWh',
    'gwhr': 'GWh',
    'gigawatt-hour': 'GWh',
    'gigawatt-hours': 'GWh',
    'gigawatt hours': 'GWh',
    'bu': 'BU',
    'billion unit': 'BU',
    'billion units': 'BU',
    'billion kwh': 'BU',
    'bkwh': 'BU',
    'mt': 'MT',
    'million tonne': 'MT',
    'million tonnes': 'MT',
    'million tons': 'MT',
    'index': 'index',
    'units': 'units',
    'unit': 'units',
}

_CONVERSIONS: dict[tuple[str, str], Callable[[float], float]] = {
    ('GWh', 'GWh'): _identity,
    ('BU', 'BU'): _identity,
    ('BU', 'GWh'): _bu_to_gwh,
    ('GWh', 'BU'): _gwh_to_bu,
    ('percent', 'percent'): _identity,
    ('index', 'index'): _identity,
    ('units', 'units'): _identity,
    ('MT', 'MT'): _identity,
}


def normalize_unit(unit: str) -> str:
    normalized = unit.strip()
    return _UNIT_ALIASES.get(normalized.lower(), normalized)


def canonical_unit_for_metric(metric_code: str) -> str | None:
    return CANONICAL_METRIC_UNITS.get(metric_code)


def convert_value(value: float, from_unit: str, to_unit: str) -> float:
    source = normalize_unit(from_unit)
    target = normalize_unit(to_unit)
    converter = _CONVERSIONS.get((source, target))
    if converter is None:
        raise UnitConversionError(f'No conversion available from {source} to {target}')
    return converter(float(value))


def canonicalize_observation(obs: CanonicalObservation) -> CanonicalObservation:
    canonical_unit = canonical_unit_for_metric(obs.metric_code)
    if canonical_unit is None:
        return replace(obs, unit=normalize_unit(obs.unit))

    source_unit = normalize_unit(obs.unit)
    value = convert_value(obs.value, source_unit, canonical_unit)
    return replace(obs, value=value, unit=canonical_unit)


def canonicalize_observations(observations: list[CanonicalObservation]) -> list[CanonicalObservation]:
    return [canonicalize_observation(obs) for obs in observations]
