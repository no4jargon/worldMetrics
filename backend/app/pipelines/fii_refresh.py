"""Refresh the independent, daily FII cash-equity snapshot.

This job deliberately does not run the slower monthly macro connectors. Source
dates are retained verbatim: a missing publication is never represented as zero.
"""
from __future__ import annotations

import fcntl
import json
import math
import os
import re
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo


WEB_DATA = Path(__file__).resolve().parents[3] / 'web' / 'data'
FII_FILENAME = 'fii-flows.json'
SOURCE_URL = 'https://www.nseindia.com/reports/fii-dii'
INDIA = ZoneInfo('Asia/Kolkata')
SourceFetcher = Callable[[], dict[str, Any]]


def _empty_payload() -> dict[str, Any]:
    return {
        'records': [],
        'source_name': 'NSE',
        'source_url': SOURCE_URL,
        'scope': 'NSE, BSE and MSEI cash market',
        'unit': '₹ crore',
        'is_provisional': True,
        'last_checked_at': None,
        'last_success_at': None,
        'error': None,
        'status': 'unavailable',
    }


def _records(records: Any, today: date) -> list[dict[str, Any]]:
    if not isinstance(records, list):
        raise ValueError('FII source records must be a list')
    normalized: dict[str, dict[str, Any]] = {}
    for row in records:
        if not isinstance(row, dict):
            raise ValueError('FII source contains an invalid record')
        label = row.get('date')
        if not isinstance(label, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', label):
            raise ValueError('FII record must have an ISO trading date')
        trading_date = date.fromisoformat(label)
        if trading_date > today:
            raise ValueError(f'FII source contains a future trading date: {label}')
        values: dict[str, float] = {}
        for field in ('buy', 'sell', 'net'):
            raw = row.get(field)
            if isinstance(raw, bool) or not isinstance(raw, (int, float)) or not math.isfinite(raw):
                raise ValueError(f'FII {field} is not a finite number on {label}')
            values[field] = round(float(raw), 2)
        if values['buy'] < 0 or values['sell'] < 0:
            raise ValueError(f'FII gross purchases and sales must be nonnegative on {label}')
        if abs(values['buy'] - values['sell'] - values['net']) > 0.05:
            raise ValueError(f'FII purchases less sales do not match net flow on {label}')
        record = {'date': label, **values}
        if label in normalized and normalized[label] != record:
            raise ValueError(f'FII source contains conflicting records for {label}')
        normalized[label] = record
    return [normalized[label] for label in sorted(normalized)]


def _read_snapshot(path: Path, today: date) -> dict[str, Any]:
    if not path.exists():
        return _empty_payload()
    payload = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(payload, dict):
        raise ValueError('Existing FII snapshot is invalid; refusing to replace it')
    payload['records'] = _records(payload.get('records'), today)
    return {**_empty_payload(), **payload}


def _write_snapshot(path: Path, payload: dict[str, Any]) -> None:
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         prefix='.fii-flows-', suffix='.json', delete=False) as handle:
            temporary_path = Path(handle.name)
            json.dump(payload, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write('\n')
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _history_metadata(existing: dict[str, Any], fetched: dict[str, Any],
                      records: list[dict[str, Any]]) -> dict[str, Any]:
    """Keep coverage and attribution for history retained outside this fetch."""
    result = {key: value for key, value in existing.items() if key.startswith('history_')}
    result.update({key: value for key, value in fetched.items() if key.startswith('history_')})
    dates = {row['date'] for row in records}

    def months(payload: dict[str, Any], key: str) -> set[str]:
        return {item for item in (payload.get(key) or [])
                if isinstance(item, str) and re.fullmatch(r'\d{4}-\d{2}', item)}

    complete = months(existing, 'history_complete_months') | months(fetched, 'history_complete_months')
    incomplete = (months(existing, 'history_incomplete_months') | months(existing, 'history_missing_months')
                  | months(fetched, 'history_incomplete_months') | months(fetched, 'history_missing_months'))
    identified_missing = {item for payload in (existing, fetched)
                          for item in (payload.get('history_missing_dates') or [])
                          if isinstance(item, str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}', item)}
    missing = identified_missing - dates
    missing_months = {label[:7] for label in missing}
    # Existing verified coverage survives a narrower/failed history request,
    # unless its newly identified missing sessions are also absent from cache.
    complete -= missing_months
    incomplete |= missing_months
    incomplete -= complete
    for month in list(incomplete):
        known_gaps = {label for label in identified_missing if label.startswith(month)}
        if known_gaps and known_gaps <= dates and month < records[-1]['date'][:7]:
            incomplete.remove(month)
            complete.add(month)
    result['history_complete_months'] = sorted(complete)
    result['history_incomplete_months'] = sorted(incomplete)
    result['history_missing_months'] = sorted(incomplete)
    result['history_missing_dates'] = sorted(missing)
    starts = [item for item in (existing.get('history_start_month'), fetched.get('history_start_month'),
                               min(complete) if complete else None) if item]
    result['history_start_month'] = min(starts) if starts else None
    requested = [item for item in (existing.get('history_requested_start'), fetched.get('history_requested_start')) if item]
    result['history_requested_start'] = min(requested) if requested else None
    if fetched.get('history_requested_start'):
        result['history_last_requested_start'] = fetched['history_requested_start']

    retained_mirror = bool(existing.get('history_source_url')) and not fetched.get('history_source_url')
    for key in ('history_source_url', 'history_source_name', 'history_calendar_url'):
        if not fetched.get(key) and existing.get(key):
            result[key] = existing[key]
    result['history_verified'] = bool(existing.get('history_verified') or fetched.get('history_verified'))
    if retained_mirror:
        note = existing.get('history_note') or 'Previously checked historical daily observations are retained from the historical mirror.'
        warning = 'Latest historical backfill was unavailable or unverified; previously cached history is retained.'
        if warning not in note:
            note += ' ' + warning
    else:
        note = fetched.get('history_note') or existing.get('history_note')
    if incomplete:
        warning = 'Some historical months have missing or unverified sessions and are marked partial.'
        if not note:
            note = warning
        elif warning not in note:
            note += ' ' + warning
    if note:
        result['history_note'] = note
    # Retain old dated warnings for months that this request did not repair.
    old_errors = [message for message in (existing.get('history_errors') or [])
                  if isinstance(message, str) and message[:7] in incomplete]
    result['history_errors'] = sorted(set(old_errors + list(fetched.get('history_errors') or [])))
    return result


def _backup_corrupt_snapshot(output: Path, contents: bytes) -> str:
    with tempfile.NamedTemporaryFile(mode='wb', dir=output, prefix='fii-flows.corrupt-',
                                     suffix='.json', delete=False) as handle:
        handle.write(contents)
        handle.flush()
        os.fsync(handle.fileno())
        return Path(handle.name).name


def refresh_fii_flows(
    output_dir: Path | str | None = None,
    *,
    fetcher: SourceFetcher | None = None,
    fixture_path: Path | str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Upsert dated observations, preserving the prior snapshot on fetch failure.

    ``refresh_status`` is success, failed, or skipped. ``status`` describes
    whether records remain available, even when the latest refresh failed.
    """
    output = Path(output_dir) if output_dir is not None else WEB_DATA
    output.mkdir(parents=True, exist_ok=True)
    path = output / FII_FILENAME
    clock = now or datetime.now(timezone.utc)
    if clock.tzinfo is None:
        clock = clock.replace(tzinfo=timezone.utc)
    today = clock.astimezone(INDIA).date()
    checked_at = clock.astimezone(timezone.utc).isoformat()

    with (output / '.fii-refresh.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {**_empty_payload(), 'refresh_status': 'skipped', 'skip_reason': 'Another FII refresh is running'}
        try:
            corrupt_bytes: bytes | None = None
            read_error: str | None = None
            try:
                existing = _read_snapshot(path, today)
            except (ValueError, UnicodeError) as error:
                # Recover only after a successful source fetch, and preserve the
                # exact original bytes in a uniquely named evidence file first.
                corrupt_bytes = path.read_bytes()
                read_error = str(error) or type(error).__name__
                existing = _empty_payload()
            try:
                if fixture_path is not None:
                    fetched = json.loads(Path(fixture_path).read_text(encoding='utf-8'))
                    if isinstance(fetched, list):
                        fetched = {'records': fetched}
                else:
                    if fetcher is None:
                        from app.connectors.nse_fii import fetch_fii_records
                        history_months = 12
                        if existing['records']:
                            last_date = date.fromisoformat(existing['records'][-1]['date'])
                            month_gap = (today.year - last_date.year) * 12 + today.month - last_date.month
                            # Recheck the current and prior months for revisions;
                            # fetch a wider window after the dashboard was idle.
                            history_months = min(12, max(2, month_gap + 2))
                        fetcher = lambda: fetch_fii_records(history_months=history_months)
                    fetched = fetcher()
                if not isinstance(fetched, dict):
                    raise ValueError('FII source response must be an object')
                incoming = _records(fetched.get('records'), today)
                if not incoming:
                    raise ValueError('FII source returned no dated equity-flow records')
                by_date = {row['date']: row for row in existing['records']}
                by_date.update({row['date']: row for row in incoming})
                merged = [by_date[label] for label in sorted(by_date)]
                payload = {
                    **existing,
                    'records': merged,
                    'source_name': fetched.get('source_name', fetched.get('source', existing['source_name'])),
                    'source_url': fetched.get('source_url', existing['source_url']),
                    'scope': fetched.get('scope', existing['scope']),
                    'is_provisional': fetched.get('is_provisional', existing['is_provisional']),
                    'coverage_start': merged[0]['date'],
                    'coverage_end': merged[-1]['date'],
                    'last_checked_at': checked_at,
                    'last_success_at': checked_at,
                    'error': None,
                    'status': 'available',
                    'refresh_status': 'success',
                }
                if 'data_url' in fetched:
                    payload['data_url'] = fetched['data_url']
                payload.update(_history_metadata(existing, fetched, merged))
            except Exception as error:
                payload = {
                    **existing,
                    'last_checked_at': checked_at,
                    'error': ((f'Existing snapshot could not be read: {read_error}. ' if read_error else '')
                              + (str(error) or type(error).__name__)),
                    'status': 'available' if existing['records'] else 'unavailable',
                    'refresh_status': 'failed',
                }
            if corrupt_bytes is not None:
                if payload['refresh_status'] != 'success':
                    # Report the error to the CLI without destroying recoverable
                    # bytes when both the cache and current source are unusable.
                    return payload
                payload['recovered_from_corrupt_snapshot'] = _backup_corrupt_snapshot(output, corrupt_bytes)
                payload['recovery_warning'] = f'Unreadable snapshot was backed up before source recovery: {read_error}'
            _write_snapshot(path, payload)
            return payload
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)
