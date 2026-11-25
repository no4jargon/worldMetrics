from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import replace
from pathlib import Path
from typing import Any

from app.connectors.factory import build_real_connectors
from app.core.metric_registry import CANONICAL_METRIC_UNITS, canonicalize_observations
from app.core.models import CanonicalObservation
from app.core.transforms import compute_transforms
from app.core.validation import validate_observations

ROOT = Path(__file__).resolve().parents[3]
WEB_DATA = ROOT / 'web' / 'data'

METRIC_META = {
    'power_output_total': {'title': 'Power output', 'source': 'NPP', 'panel': 'power', 'unit': CANONICAL_METRIC_UNITS['power_output_total'], 'dataset_code': 'npp_monthly_generation', 'source_url': 'https://npp.gov.in/monthlyGenerationReportsAct'},
    'power_consumed_total': {'title': 'Power consumed', 'source': 'Target website', 'panel': 'power', 'unit': CANONICAL_METRIC_UNITS['power_consumed_total'], 'dataset_code': 'playwright_power_consumption'},
    'power_utilization_plf': {'title': 'Power utilization', 'source': 'NPP', 'panel': 'power', 'unit': CANONICAL_METRIC_UNITS['power_utilization_plf'], 'dataset_code': 'npp_monthly_generation', 'source_url': 'https://npp.gov.in/monthlyGenerationReportsAct'},
    'cement_output': {'title': 'Cement output', 'source': 'ICRA', 'panel': 'construction', 'unit': CANONICAL_METRIC_UNITS['cement_output'], 'dataset_code': 'oea_core_industries'},
    'cement_utilization_est': {'title': 'Cement utilization', 'source': 'Estimated', 'panel': 'construction', 'unit': CANONICAL_METRIC_UNITS['cement_utilization_est'], 'dataset_code': 'oea_core_industries'},
    'home_sales_jll': {'title': 'Home sales', 'source': 'JLL India', 'panel': 'construction', 'unit': CANONICAL_METRIC_UNITS['home_sales_jll'], 'dataset_code': 'jll_residential_sales'},
    'auto_sales_total': {'title': 'Auto sales', 'source': 'VAHAN registration proxy', 'panel': 'demand', 'unit': CANONICAL_METRIC_UNITS['auto_sales_total'], 'dataset_code': 'vahan_vehicle_registrations', 'retrieval_skill': 'vahan-dashboard', 'source_url': 'https://vahan.parivahan.gov.in/vahan4dashboard/'},
    'two_wheeler_sales': {'title': 'Two-wheeler sales', 'source': 'VAHAN registration proxy', 'panel': 'demand', 'unit': CANONICAL_METRIC_UNITS['two_wheeler_sales'], 'dataset_code': 'vahan_vehicle_registrations', 'retrieval_skill': 'vahan-dashboard', 'source_url': 'https://vahan.parivahan.gov.in/vahan4dashboard/'},
    'four_wheeler_sales': {'title': 'Four-wheeler sales', 'source': 'VAHAN registration proxy', 'panel': 'demand', 'unit': CANONICAL_METRIC_UNITS['four_wheeler_sales'], 'dataset_code': 'vahan_vehicle_registrations', 'retrieval_skill': 'vahan-dashboard', 'source_url': 'https://vahan.parivahan.gov.in/vahan4dashboard/'},
    'cpi_headline': {'title': 'CPI inflation', 'source': 'MoSPI', 'panel': 'inflation', 'unit': CANONICAL_METRIC_UNITS['cpi_headline'], 'dataset_code': 'mospi_cpi'},
    'cpi_index': {'title': 'CPI index', 'source': 'MoSPI', 'panel': 'inflation', 'unit': CANONICAL_METRIC_UNITS['cpi_index'], 'dataset_code': 'mospi_cpi'},
}

DATASET_META = {
    'npp_monthly_generation': {'cadence': 'monthly', 'metric_codes': ['power_output_total', 'power_utilization_plf']},
    'playwright_power_consumption': {'cadence': 'monthly', 'metric_codes': ['power_consumed_total']},
    'oea_core_industries': {'cadence': 'monthly', 'metric_codes': ['cement_output', 'cement_utilization_est']},
    'jll_residential_sales': {'cadence': 'quarterly', 'metric_codes': ['home_sales_jll']},
    'vahan_vehicle_registrations': {'cadence': 'monthly', 'metric_codes': ['auto_sales_total', 'two_wheeler_sales', 'four_wheeler_sales']},
    'mospi_cpi': {'cadence': 'monthly', 'metric_codes': ['cpi_headline', 'cpi_index']},
}

DASHBOARD_EXCLUDED_METRICS = {'cement_output_index', 'auto_sales_total'}

OVERVIEW_METRICS = [
    'power_output_total',
    'power_utilization_plf',
    'cement_output',
    'cement_utilization_est',
    'home_sales_jll',
    'two_wheeler_sales',
    'four_wheeler_sales',
    'cpi_headline',
]

ConnectorStatus = dict[str, str | int | None]


def _group(observations: list[CanonicalObservation]) -> dict[tuple[str, str], list[CanonicalObservation]]:
    grouped: dict[tuple[str, str], list[CanonicalObservation]] = defaultdict(list)
    for obs in observations:
        grouped[(obs.metric_code, obs.segment or 'ALL')].append(obs)
    for key in grouped:
        grouped[key] = sorted(grouped[key], key=lambda x: x.period_start)
    return grouped


def _series_for_metric(grouped: dict[tuple[str, str], list[CanonicalObservation]], metric_code: str) -> list[CanonicalObservation] | None:
    return grouped.get((metric_code, 'ALL')) or grouped.get((metric_code, 'domestic')) or grouped.get((metric_code, 'top_7_cities'))


def _skill_note(metric_code: str) -> str:
    skill = METRIC_META.get(metric_code, {}).get('retrieval_skill')
    return f' Use /skill:{skill} for the manual VAHAN retrieval workflow.' if skill else ''


def _metric_source_url(metric_code: str, obs: CanonicalObservation | None = None) -> str | None:
    if obs and obs.source_url:
        return obs.source_url
    value = METRIC_META.get(metric_code, {}).get('source_url')
    return str(value) if value else None


def _missing_metric_note(metric_code: str, connector_statuses: dict[str, ConnectorStatus]) -> str:
    dataset_code = str(METRIC_META[metric_code]['dataset_code'])
    connector_status = connector_statuses.get(dataset_code)
    if connector_status is None:
        return 'No connector is registered for this metric.' + _skill_note(metric_code)
    status = connector_status.get('status')
    error_message = connector_status.get('error_message')
    if status == 'not_configured':
        return 'Connector exists, but no live source URL or fixture was configured.' + _skill_note(metric_code)
    if status == 'failed':
        return (f'Connector failed: {error_message}' if error_message else 'Connector failed.') + _skill_note(metric_code)
    if status == 'success':
        return 'Connector ran, but emitted no observation for this metric.' + _skill_note(metric_code)
    if status == 'skill_requested':
        return 'VAHAN retrieval skill was automatically requested by the dashboard refresh.' + _skill_note(metric_code)
    return 'No current observation is available for this metric.' + _skill_note(metric_code)


def _summary(grouped: dict[tuple[str, str], list[CanonicalObservation]]) -> str:
    clauses = []
    comparisons = [
        ('power_output_total', 'power is accelerating', 'power softened'),
        ('cement_output', 'cement is accelerating', 'cement softened'),
        ('home_sales_jll', 'housing remains firm', 'housing eased'),
        ('two_wheeler_sales', 'two-wheelers improved', 'two-wheelers softened'),
        ('four_wheeler_sales', 'four-wheelers improved', 'four-wheelers softened'),
        ('cpi_headline', 'inflation ticked up', 'inflation eased'),
    ]
    for code, up_text, down_text in comparisons:
        series = _series_for_metric(grouped, code)
        if not series or len(series) < 2:
            continue
        clauses.append(up_text if series[-1].value >= series[-2].value else down_text)
    return ', '.join(clauses).capitalize() + '.' if clauses else 'No live connector data available. Check connector configuration in the release monitor.'


def _missing_overview_card(metric_code: str, connector_statuses: dict[str, ConnectorStatus]) -> dict[str, Any]:
    meta = METRIC_META[metric_code]
    return {
        'metric_code': metric_code,
        'title': meta['title'],
        'latest_period': None,
        'latest_value': None,
        'unit': meta['unit'],
        'change_prev': None,
        'change_prev_unit': 'percent',
        'change_yoy': None,
        'change_yoy_unit': 'percent',
        'sparkline': [],
        'source': meta['source'],
        'release_date': None,
        'latest_retrieved_for': None,
        'segment': None,
        'status': 'missing',
        'status_note': _missing_metric_note(metric_code, connector_statuses),
        'retrieval_skill': meta.get('retrieval_skill'),
        'source_url': _metric_source_url(metric_code),
    }


def _overview_chart_points(series: list[CanonicalObservation]) -> list[dict[str, float | str]]:
    window = 40 if series[-1].period_label and '-Q' in series[-1].period_label else 120
    return [
        {'period': item.period_label, 'value': round(item.value, 2)}
        for item in series[-window:]
    ]


def _build_overview(
    observations: list[CanonicalObservation],
    derived_map: dict[tuple[str, str, str], float],
    connector_statuses: dict[str, ConnectorStatus],
) -> list[dict[str, Any]]:
    grouped = _group(observations)
    cards = []
    for metric_code in OVERVIEW_METRICS:
        series = _series_for_metric(grouped, metric_code)
        if not series:
            cards.append(_missing_overview_card(metric_code, connector_statuses))
            continue
        latest = series[-1]
        prev = series[-2] if len(series) > 1 else None
        prev_change = None
        if prev and prev.value != 0:
            prev_change = round(((latest.value / prev.value) - 1.0) * 100.0, 2)
        yoy = derived_map.get((metric_code, latest.period_label, 'yoy'))
        cards.append(
            {
                'metric_code': metric_code,
                'title': METRIC_META[metric_code]['title'],
                'latest_period': latest.period_label,
                'latest_value': latest.value,
                'unit': latest.unit,
                'change_prev': prev_change,
                'change_prev_unit': 'percent',
                'change_yoy': round(yoy, 2) if yoy is not None else None,
                'change_yoy_unit': 'percent',
                'sparkline': _overview_chart_points(series),
                'source': METRIC_META[metric_code]['source'],
                'release_date': latest.source_release_date.isoformat() if latest.source_release_date else None,
                'latest_retrieved_for': latest.period_end.isoformat(),
                'segment': latest.segment,
                'status': 'available',
                'status_note': None,
                'retrieval_skill': METRIC_META[metric_code].get('retrieval_skill'),
                'source_url': _metric_source_url(metric_code, latest),
            }
        )
    return cards


def _empty_series_payload(metric_code: str, connector_statuses: dict[str, ConnectorStatus]) -> dict[str, Any]:
    return {
        'metric_code': metric_code,
        'transform': 'level',
        'points': [],
        'source': METRIC_META.get(metric_code, {}).get('source', 'Unknown'),
        'status': 'missing',
        'status_note': _missing_metric_note(metric_code, connector_statuses),
        'retrieval_skill': METRIC_META.get(metric_code, {}).get('retrieval_skill'),
        'source_url': _metric_source_url(metric_code),
    }


def _build_series(
    observations: list[CanonicalObservation],
    derived_map: dict[tuple[str, str, str], float],
    connector_statuses: dict[str, ConnectorStatus],
) -> dict[str, dict[str, dict[str, Any]]]:
    grouped = _group(observations)
    payload: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for metric_code in METRIC_META:
        payload[metric_code]['level'] = _empty_series_payload(metric_code, connector_statuses)

    for (metric_code, _), series in grouped.items():
        payload[metric_code]['level'] = {
            'metric_code': metric_code,
            'transform': 'level',
            'points': [{'period': obs.period_label, 'value': obs.value} for obs in series],
            'source': METRIC_META.get(metric_code, {}).get('source', 'Unknown'),
            'status': 'available',
            'status_note': None,
            'retrieval_skill': METRIC_META.get(metric_code, {}).get('retrieval_skill'),
            'source_url': _metric_source_url(metric_code, series[-1]),
        }
        for transform in ('yoy', 'indexed_100', 'change_prev_pct', 'rolling_3p_avg'):
            points = []
            for obs in series:
                key = (metric_code, obs.period_label, transform)
                if key in derived_map:
                    points.append({'period': obs.period_label, 'value': round(derived_map[key], 2)})
            if points:
                payload[metric_code][transform] = {
                    'metric_code': metric_code,
                    'transform': transform,
                    'points': points,
                    'source': METRIC_META.get(metric_code, {}).get('source', 'Unknown'),
                    'status': 'available',
                    'status_note': None,
                    'retrieval_skill': METRIC_META.get(metric_code, {}).get('retrieval_skill'),
                    'source_url': _metric_source_url(metric_code, series[-1]),
                }
    return payload


def _latest_for_dataset(
    grouped: dict[tuple[str, str], list[CanonicalObservation]],
    metric_codes: list[str],
) -> CanonicalObservation | None:
    latest: CanonicalObservation | None = None
    for metric_code in metric_codes:
        series = _series_for_metric(grouped, metric_code)
        if not series:
            continue
        candidate = series[-1]
        if latest is None or candidate.period_end > latest.period_end:
            latest = candidate
    return latest


def _build_release_monitor(
    observations: list[CanonicalObservation],
    connector_statuses: dict[str, ConnectorStatus],
) -> list[dict[str, str | int | None]]:
    grouped = _group(observations)
    monitor = []
    dataset_codes = list(DATASET_META.keys())
    for dataset_code in connector_statuses:
        if dataset_code not in dataset_codes:
            dataset_codes.append(dataset_code)

    for dataset_code in dataset_codes:
        meta = DATASET_META.get(dataset_code, {'cadence': 'unknown', 'metric_codes': []})
        metric_codes = list(meta['metric_codes'])
        latest = _latest_for_dataset(grouped, metric_codes)
        connector_status = connector_statuses.get(dataset_code)
        status = connector_status.get('status') if connector_status else 'missing_connector'
        if status == 'success' and latest is None:
            status = 'no_observations'
        monitor.append(
            {
                'dataset_code': dataset_code,
                'status': status,
                'last_successful_period': latest.period_label if latest else None,
                'last_release_date': latest.source_release_date.isoformat() if latest and latest.source_release_date else None,
                'cadence': str(meta['cadence']),
                'next_expected_window': 'based on release_lag_days metadata' if latest else None,
                'observations_emitted': connector_status.get('observations_emitted') if connector_status else 0,
                'error_message': connector_status.get('error_message') if connector_status else 'No connector registered in default connector set.',
            }
        )
    return monitor


def _connector_status_for_error(dataset_code: str, error: Exception) -> ConnectorStatus:
    status = 'not_configured' if isinstance(error, NotImplementedError) else 'failed'
    return {
        'dataset_code': dataset_code,
        'status': status,
        'observations_emitted': 0,
        'error_message': str(error),
    }


def _attach_source_url(observations: list[CanonicalObservation], source_url: str | None) -> list[CanonicalObservation]:
    return [obs if obs.source_url else replace(obs, source_url=source_url) for obs in observations]


def collect_from_connectors(connectors: list) -> tuple[list[CanonicalObservation], dict[str, ConnectorStatus]]:
    observations: list[CanonicalObservation] = []
    connector_statuses: dict[str, ConnectorStatus] = {}

    for connector in connectors:
        dataset_code = getattr(connector, 'dataset_code', connector.__class__.__name__)
        try:
            raw = connector.fetch()
            parsed = _attach_source_url(canonicalize_observations(connector.parse(raw)), raw.source_url)
        except Exception as error:  # keep dashboard build alive and show connector state explicitly
            connector_statuses[dataset_code] = _connector_status_for_error(dataset_code, error)
            continue

        observations.extend(parsed)
        raw_status = getattr(raw, 'status', 'success')
        error_message = None
        if raw_status != 'success':
            payload = getattr(raw, 'payload', None)
            if isinstance(payload, dict) and payload.get('skipped'):
                error_message = f"No observations emitted. Skipped months: {payload.get('skipped')}"
            elif isinstance(payload, dict) and payload.get('message'):
                error_message = str(payload.get('message'))
        connector_statuses[dataset_code] = {
            'dataset_code': dataset_code,
            'status': raw_status,
            'observations_emitted': len(parsed),
            'error_message': error_message,
            'source_url': raw.source_url,
        }

    return observations, connector_statuses


def build_snapshots_from_observations(
    observations: list[CanonicalObservation],
    connector_statuses: dict[str, ConnectorStatus] | None = None,
    output_dir: Path | None = None,
) -> None:
    connector_statuses = connector_statuses or {}
    observations = [
        obs for obs in canonicalize_observations(observations)
        if obs.metric_code not in DASHBOARD_EXCLUDED_METRICS
    ]
    validate_observations(observations)
    derived = compute_transforms(observations)
    derived_map = {(item.metric_code, item.period_label, item.transform): item.value for item in derived}

    overview = _build_overview(observations, derived_map, connector_statuses)
    grouped = _group(observations)
    summary = _summary(grouped)
    series = _build_series(observations, derived_map, connector_statuses)
    release_monitor = _build_release_monitor(observations, connector_statuses)

    target_dir = output_dir or WEB_DATA
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / 'overview.json').write_text(json.dumps({'cards': overview, 'summary': summary}, indent=2))
    (target_dir / 'series.json').write_text(json.dumps(series, indent=2))
    (target_dir / 'release-monitor.json').write_text(json.dumps(release_monitor, indent=2))


def build_snapshots(output_dir: Path | None = None, connectors: list | None = None) -> None:
    connectors = connectors if connectors is not None else build_real_connectors()
    observations, connector_statuses = collect_from_connectors(connectors)
    build_snapshots_from_observations(observations, connector_statuses, output_dir=output_dir)


if __name__ == '__main__':
    build_snapshots()
