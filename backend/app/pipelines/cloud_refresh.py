"""Incremental, unattended refresh of the public dashboard data.

Each source is validated independently before it can revise the cached history.
The website consumes snapshot.json, which is replaced last and atomically. A
failed source never erases prior figures or advances its last-success timestamp.
"""
from __future__ import annotations

import argparse
from calendar import monthrange
from contextlib import contextmanager
from dataclasses import replace
from datetime import date, datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import signal
import tempfile
import threading
import time
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from zoneinfo import ZoneInfo

from app.core.metric_registry import CANONICAL_METRIC_UNITS, canonicalize_observations
from app.core.models import CanonicalObservation
from app.core.validation import validate_observations
from app.pipelines.build_snapshots import (
    DATASET_META, METRIC_META, build_snapshots_from_observations,
)
from app.pipelines.fii_refresh import _records as validate_fii_records, refresh_fii_flows


Collector = Callable[[], list[CanonicalObservation]]
FiiRefresher = Callable[..., dict[str, Any]]
INDIA = ZoneInfo('Asia/Kolkata')
FII_DATASET = 'nse_fii_flows'


class SourceDeadline(BaseException):
    """Not swallowed by source connectors' broad per-request Exception handlers."""


@contextmanager
def _deadline(seconds: int):
    # GitHub's Linux CLI runs on the main thread. Leave embedded/threaded callers
    # untouched instead of changing a different thread's signal handlers.
    supported = hasattr(signal, 'SIGALRM') and threading.current_thread() is threading.main_thread()
    if not supported or seconds <= 0:
        yield
        return
    previous_handler = signal.getsignal(signal.SIGALRM)
    previous_timer = signal.getitimer(signal.ITIMER_REAL)
    if previous_timer[0]:
        yield
        return

    def expired(_signum, _frame):
        raise SourceDeadline(f'Source exceeded its {seconds}-second deadline.')

    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)


def _json(path: Path, fallback: Any) -> Any:
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else fallback


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         prefix=f'.{path.name}-', suffix='.tmp', delete=False) as handle:
            name = handle.name
            json.dump(payload, handle, indent=2, ensure_ascii=False, allow_nan=False)
            handle.write('\n')
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
    finally:
        if name and Path(name).exists():
            Path(name).unlink()


def _bounds(period: str) -> tuple[date, date]:
    monthly = re.fullmatch(r'(\d{4})-(0[1-9]|1[0-2])', period)
    quarterly = re.fullmatch(r'(\d{4})-Q([1-4])', period)
    if monthly:
        year, month = map(int, monthly.groups())
        return date(year, month, 1), date(year, month, monthrange(year, month)[1])
    if quarterly:
        year, quarter = map(int, quarterly.groups())
        first_month, last_month = (quarter - 1) * 3 + 1, quarter * 3
        return date(year, first_month, 1), date(year, last_month, monthrange(year, last_month)[1])
    raise ValueError(f'Invalid reporting period: {period}')


def _observation(payload: dict[str, Any]) -> CanonicalObservation:
    values = dict(payload)
    for key in ('period_start', 'period_end', 'source_release_date'):
        if isinstance(values.get(key), str):
            values[key] = date.fromisoformat(values[key])
    return CanonicalObservation(**values)


def load_history(data_dir: Path) -> list[CanonicalObservation]:
    """Prefer lossless canonical history; bootstrap from the prior public series."""
    canonical = data_dir / 'canonical-observations.json'
    if canonical.exists():
        payload = _json(canonical, [])
        if isinstance(payload, dict):
            payload = payload.get('observations')
        if not isinstance(payload, list):
            raise ValueError('Canonical history must be a list of observations.')
        return [_observation(item) for item in payload]

    overview = _json(data_dir / 'overview.json', {'cards': []})
    cards = {card['metric_code']: card for card in overview.get('cards', [])}
    series = _json(data_dir / 'series.json', {})
    if not isinstance(series, dict):
        raise ValueError('Cached series must be an object.')
    observations = []
    for metric, transforms in series.items():
        if metric not in CANONICAL_METRIC_UNITS:
            continue
        level = transforms.get('level', {})
        card = cards.get(metric, {})
        for point in level.get('points', []):
            start, end = _bounds(point['period'])
            release_date = card.get('release_date') if point['period'] == card.get('latest_period') else None
            observations.append(CanonicalObservation(
                metric_code=metric, period_label=point['period'], period_start=start, period_end=end,
                value=point['value'], unit=CANONICAL_METRIC_UNITS[metric],
                segment=card.get('segment'),
                source_release_date=date.fromisoformat(release_date) if release_date else None,
                source_url=level.get('source_url') or card.get('source_url'),
                notes='Imported cached level series; individual historical release provenance was not retained in the snapshot.',
            ))
    return observations


def _validate(observations: list[CanonicalObservation], today: date) -> list[CanonicalObservation]:
    if not isinstance(observations, list):
        raise ValueError('Source observations must be a list.')
    for obs in observations:
        if not isinstance(obs, CanonicalObservation):
            raise ValueError('Source returned an invalid observation.')
        if isinstance(obs.value, bool) or not isinstance(obs.value, (int, float)) or not math.isfinite(obs.value):
            raise ValueError(f'Nonfinite or nonnumeric value for {obs.metric_code}.')
        start, end = _bounds(obs.period_label)
        if obs.period_start != start or obs.period_end != end:
            raise ValueError(f'Calendar bounds do not match {obs.metric_code} {obs.period_label}.')
        if end > today:
            raise ValueError(f'Incomplete or future reporting period: {obs.metric_code} {obs.period_label}.')
        if obs.source_release_date and obs.source_release_date > today:
            raise ValueError(f'Future release date for {obs.metric_code} {obs.period_label}.')
        if obs.source_url and not re.match(r'^https?://', obs.source_url):
            raise ValueError(f'Invalid public source URL for {obs.metric_code}.')
    canonical = canonicalize_observations(observations)
    validate_observations(canonical)
    if any(obs.unit != 'percent' and obs.value < 0 for obs in canonical):
        raise ValueError('A physical level or count cannot be negative.')
    return canonical


def _key(obs: CanonicalObservation) -> tuple[str, str, str]:
    return obs.metric_code, obs.period_label, obs.segment or 'ALL'


def _match_segment(obs: CanonicalObservation, existing: list[CanonicalObservation]) -> CanonicalObservation:
    # Earlier manually verified snapshots used None for the same national/top-7
    # series. Avoid splitting their history when a connector adds its label.
    alias = {'home_sales_jll': 'top_7_cities', 'two_wheeler_sales': 'domestic', 'four_wheeler_sales': 'domestic'}.get(obs.metric_code)
    if alias is None:
        return obs
    segments = {item.segment for item in existing if item.metric_code == obs.metric_code and item.geography == obs.geography}
    if len(segments) == 1:
        segment = next(iter(segments))
        if segment in {None, alias} and obs.segment in {None, alias}:
            return replace(obs, segment=segment)
    return obs


def _recent_months(today: date) -> list[str]:
    index = today.year * 12 + today.month - 1
    return [f'{(index - offset) // 12:04d}-{(index - offset) % 12 + 1:02d}' for offset in (2, 1, 0)]


def _connector_runner(connector, *, omit_blank_values: bool = False, network_attempts: int = 1) -> Collector:
    def collect():
        attempts = max(1, min(3, network_attempts))
        for attempt in range(attempts):
            try:
                raw = connector.fetch()
                break
            except (URLError, ConnectionError, TimeoutError) as exc:
                # HTTPError subclasses URLError: authentication/client errors
                # need a real fix, while a source's 5xx response may be transient.
                if isinstance(exc, HTTPError) and not 500 <= exc.code < 600:
                    raise
                if attempt == attempts - 1:
                    raise
                time.sleep(attempt + 1)
        if raw.status != 'success':
            raise ValueError(f'Source returned {raw.status}; no validated release was retrieved.')
        # Parsing and validation are deliberately outside the retry loop.
        parsed = connector.parse(raw)
        # VAHAN's year table includes blank/unpublished month cells as zero.
        # These national aggregates are not evidence of actual zero sales.
        if omit_blank_values:
            parsed = [obs for obs in parsed if obs.value != 0]
        return [obs if obs.source_url else replace(obs, source_url=raw.source_url) for obs in parsed]
    return collect


def default_collectors(today: date, artifacts: Path) -> dict[str, Collector]:
    from app.connectors.npp_power import NPPMonthlyGenerationConnector
    from app.connectors.vahan_skill import VAHANDashboardSkillConnector
    from app.connectors.published_releases import fetch_cement, fetch_cpi, fetch_jll

    return {
        'npp_monthly_generation': _connector_runner(NPPMonthlyGenerationConnector(
            months=_recent_months(today), artifact_dir=artifacts / 'npp')),
        'vahan_vehicle_registrations': _connector_runner(VAHANDashboardSkillConnector(
            live=True, years=[today.year - 1, today.year], include_current_month=False),
            omit_blank_values=True, network_attempts=3),
        'oea_core_industries': fetch_cement,
        'mospi_cpi': fetch_cpi,
        'jll_residential_sales': fetch_jll,
    }


def _latest_period(dataset: str, observations: list[CanonicalObservation]) -> str | None:
    metrics = DATASET_META.get(dataset, {}).get('metric_codes', [])
    records = [obs for obs in observations if obs.metric_code in metrics]
    return max(records, key=lambda obs: obs.period_end).period_label if records else None


def _error(error: BaseException) -> str:
    # Do not publish full browser tracebacks or absolute home-directory paths.
    message = (str(error).splitlines() or [type(error).__name__])[0]
    return f'{type(error).__name__}: {message}'.replace(str(Path.home()), '~')[:600]


def _latest_success(*values: Any, clock: datetime) -> str | None:
    """Migrate older bundles whose aggregate timestamp predates a source check."""
    valid: list[tuple[datetime, str]] = []
    for value in values:
        if not isinstance(value, str):
            continue
        try:
            parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            if parsed <= clock:
                valid.append((parsed, value))
        except ValueError:
            continue
    return max(valid, key=lambda item: item[0])[1] if valid else None


def refresh_cloud_data(
    data_dir: Path | str,
    *,
    collectors: Mapping[str, Collector] | None = None,
    fii_refresher: FiiRefresher | None = None,
    now: datetime | None = None,
    source_timeout_seconds: int = 180,
) -> dict[str, Any]:
    output = Path(data_dir)
    output.mkdir(parents=True, exist_ok=True)
    clock = now or datetime.now(timezone.utc)
    if clock.tzinfo is None:
        clock = clock.replace(tzinfo=timezone.utc)
    today = clock.astimezone(INDIA).date()
    checked_at = clock.astimezone(timezone.utc).isoformat()
    previous = _json(output / 'snapshot.json', {})
    previous_sources = previous.get('sources', {})
    stored = _validate(load_history(output), today)
    by_key = {_key(obs): obs for obs in stored}
    cached_fii = _json(output / 'fii-flows.json', {'records': []})
    validate_fii_records(cached_fii.get('records'), today)
    sources = dict(previous_sources)
    statuses: dict[str, dict[str, Any]] = {}
    successes = 0
    attempted = 0

    with tempfile.TemporaryDirectory(prefix='worldmetrics-refresh-') as temporary:
        root = Path(temporary)
        active = default_collectors(today, root) if collectors is None else collectors
        for dataset, collect in active.items():
            attempted += 1
            old = previous_sources.get(dataset, {})
            incoming: list[CanonicalObservation] = []
            error = None
            try:
                with _deadline(source_timeout_seconds):
                    incoming = _validate(collect(), today)
                if not incoming:
                    raise ValueError('Source returned no observations; cached figures were retained.')
                allowed = DATASET_META.get(dataset, {}).get('metric_codes')
                if allowed and any(obs.metric_code not in allowed for obs in incoming):
                    raise ValueError('Source returned an observation for an unrelated metric.')
                incoming = [_match_segment(obs, stored) for obs in incoming]
                # Validate the entire source's proposed merge before accepting it.
                proposed = {**by_key, **{_key(obs): obs for obs in incoming}}
                _validate(list(proposed.values()), today)
                by_key = proposed
                successes += 1
            except (Exception, SourceDeadline) as exc:
                incoming = []
                error = _error(exc)
            status = 'success' if incoming else 'failed'
            sources[dataset] = {
                'status': status, 'last_checked_at': checked_at,
                'last_success_at': checked_at if incoming else old.get('last_success_at'),
                'last_successful_period': _latest_period(dataset, list(by_key.values())),
                'error': error,
            }
            statuses[dataset] = {'dataset_code': dataset, 'status': status,
                                 'observations_emitted': len(incoming), 'error_message': error}

        attempted += 1
        old_fii_source = previous_sources.get(FII_DATASET, {})
        fii = cached_fii
        fii_error = None
        try:
            # The FII helper persists its own cache and lock. Stage those writes
            # too, so a later snapshot-build failure leaves public data intact.
            fii_stage = root / 'fii'
            _write_json(fii_stage / 'fii-flows.json', cached_fii)
            with _deadline(source_timeout_seconds):
                fresh_fii = (fii_refresher or refresh_fii_flows)(output_dir=fii_stage, now=clock)
            records = validate_fii_records(fresh_fii.get('records'), today)
            if fresh_fii.get('refresh_status') != 'success' or not records:
                raise ValueError(fresh_fii.get('error') or fresh_fii.get('skip_reason') or 'No fresh FII source records were retrieved.')
            # Retain old sessions even when an injected collector returns a narrow window.
            merged_fii = {item['date']: item for item in cached_fii['records']}
            merged_fii.update({item['date']: item for item in records})
            fii = {**cached_fii, **fresh_fii, 'records': [merged_fii[day] for day in sorted(merged_fii)]}
            fii['coverage_start'] = fii['records'][0]['date']
            fii['coverage_end'] = fii['records'][-1]['date']
            fii.update(last_checked_at=checked_at, last_success_at=checked_at,
                       refresh_status='success', status='available', error=None)
            successes += 1
        except (Exception, SourceDeadline) as exc:
            fii_error = _error(exc)
            fii = {**cached_fii, 'last_checked_at': checked_at, 'refresh_status': 'failed', 'error': fii_error}
        sources[FII_DATASET] = {
            'status': 'success' if fii_error is None else 'failed', 'last_checked_at': checked_at,
            'last_success_at': checked_at if fii_error is None else _latest_success(
                old_fii_source.get('last_success_at'), cached_fii.get('last_success_at'), clock=clock),
            'last_successful_period': fii['records'][-1]['date'] if fii.get('records') else None,
            'error': fii_error,
        }

        observations = sorted(by_key.values(), key=lambda obs: (obs.metric_code, obs.period_start, obs.segment or ''))
        stage = root / 'snapshots'
        build_snapshots_from_observations(observations, statuses, output_dir=stage)
        overview = _json(stage / 'overview.json', {})
        for card in overview.get('cards', []):
            source = sources.get(METRIC_META.get(card['metric_code'], {}).get('dataset_code'), {})
            if card.get('latest_period') and source.get('status') == 'failed':
                card['status_note'] = 'Latest source check failed; retained the last known figures.'
        last_success_at = checked_at if successes else _latest_success(
            previous.get('last_success_at'), cached_fii.get('last_success_at'),
            *(source.get('last_success_at') for source in previous_sources.values()), clock=clock)
        snapshot = {
            'schema_version': 1, 'generated_at': checked_at, 'last_attempt_at': checked_at,
            'last_success_at': last_success_at, 'overview': overview,
            'series': _json(stage / 'series.json', {}),
            'release_monitor': _json(stage / 'release-monitor.json', []),
            'fii_flows': fii, 'sources': sources,
            'update_status': 'success' if successes == attempted else 'partial' if successes else 'failed',
        }
        # Build output is staged before any public snapshot is replaced.
        _write_json(output / 'canonical-observations.json', [obs.to_dict() for obs in observations])
        for name, payload in [('overview', overview), ('series', snapshot['series']),
                              ('release-monitor', snapshot['release_monitor']), ('fii-flows', fii)]:
            _write_json(output / f'{name}.json', payload)
        _write_json(output / 'snapshot.json', snapshot)
        return snapshot


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=Path('published-data'))
    args = parser.parse_args(argv)
    try:
        result = refresh_cloud_data(args.data_dir)
    except Exception as exc:
        print(json.dumps({'update_status': 'failed', 'error': _error(exc)}))
        return 1
    print(json.dumps({'update_status': result['update_status'], 'last_attempt_at': result['last_attempt_at'],
                      'last_success_at': result['last_success_at'], 'sources': result['sources']}))
    return 0 if result['update_status'] == 'success' else 1


if __name__ == '__main__':
    raise SystemExit(main())
