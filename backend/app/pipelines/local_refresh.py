from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

from app.connectors.factory import build_real_connectors
from app.connectors.npp_power import NPPMonthlyGenerationConnector
from app.pipelines.build_snapshots import build_snapshots_from_observations, collect_from_connectors
from app.storage.sqlite_store import (
    DEFAULT_DB_PATH,
    delete_observations_for_metrics,
    load_connector_statuses,
    load_observations,
    replace_connector_statuses,
    reset_database,
    upsert_observations,
)


def last_n_months(months: int, end_period: str | None = None) -> list[str]:
    if months <= 0:
        raise ValueError('months must be positive')
    if end_period:
        year, month = [int(part) for part in end_period.split('-')]
    else:
        today = date.today()
        year, month = today.year, today.month

    periods: list[str] = []
    for _ in range(months):
        periods.append(f'{year:04d}-{month:02d}')
        month -= 1
        if month == 0:
            year -= 1
            month = 12
    return list(reversed(periods))


def _write_refresh_status(
    target_dir: Path,
    status: str,
    months: int,
    end_period: str | None,
    message: str | None = None,
    progress: dict | None = None,
) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        'status': status,
        'updated_at': datetime.now(timezone.utc).isoformat(),
        'months_requested': months,
        'end_period': end_period,
        'message': message,
    }
    if progress:
        payload.update(progress)
        total = int(progress.get('total_months') or progress.get('total_years') or 0)
        completed = int(progress.get('completed_months') or progress.get('completed_years') or 0)
        if total > 0:
            payload['progress_percent'] = round((completed / total) * 100, 1)
    (target_dir / 'refresh-status.json').write_text(json.dumps(payload, indent=2))


def refresh_local_database(
    months: int = 60,
    db_path: Path = DEFAULT_DB_PATH,
    output_dir: Path | None = None,
    reset: bool = False,
    end_period: str | None = None,
) -> None:
    """Refresh local SQLite and dashboard snapshots from real connectors.

    This is intentionally dev-local. It gives us a persistent cache for expensive
    scraping, while `reset=True` gives a clean rebuild command whenever desired.
    """

    target_dir = output_dir or Path(__file__).resolve().parents[3] / 'web' / 'data'
    _write_refresh_status(target_dir, 'running', months, end_period, 'Refreshing local metric database in the background.')

    try:
        if reset:
            reset_database(db_path)

        requested_months = last_n_months(months, end_period=end_period)
        vahan_years = sorted({int(month_label[:4]) for month_label in requested_months})

        def progress_callback(progress: dict) -> None:
            current_month = progress.get('current_month')
            completed = progress.get('completed_months', 0)
            total = progress.get('total_months', months)
            records_found = progress.get('records_found', 0)
            skipped_months = progress.get('skipped_months', 0)
            if current_month:
                message = f"NPP power: {current_month} ({completed}/{total} months checked, {records_found} found, {skipped_months} skipped)."
            else:
                message = f"NPP power: {completed}/{total} months checked."
            _write_refresh_status(target_dir, 'running', months, end_period, message, progress=progress)

        def vahan_progress_callback(progress: dict) -> None:
            message = str(progress.get('message') or 'VAHAN: fetching registration data.')
            _write_refresh_status(target_dir, 'running', months, end_period, message, progress=progress)

        connectors = build_real_connectors(
            live_vahan=True,
            vahan_years=vahan_years,
            vahan_progress_callback=vahan_progress_callback,
        )

        for index, connector in enumerate(connectors):
            if isinstance(connector, NPPMonthlyGenerationConnector):
                connectors[index] = NPPMonthlyGenerationConnector(months=requested_months, progress_callback=progress_callback)

        observations, connector_statuses = collect_from_connectors(connectors)
        if any(obs.metric_code in {'two_wheeler_sales', 'four_wheeler_sales'} for obs in observations):
            delete_observations_for_metrics(['two_wheeler_sales', 'four_wheeler_sales'], db_path=db_path)
        upsert_observations(observations, db_path=db_path)
        replace_connector_statuses(connector_statuses, db_path=db_path)

        stored_observations = load_observations(db_path=db_path)
        stored_statuses = load_connector_statuses(db_path=db_path)
        build_snapshots_from_observations(stored_observations, stored_statuses, output_dir=output_dir)

        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / 'refresh-metadata.json').write_text(
            json.dumps(
                {
                    'refreshed_at': datetime.now(timezone.utc).isoformat(),
                    'months_requested': months,
                    'end_period': end_period,
                    'db_path': str(db_path),
                },
                indent=2,
            )
        )
        _write_refresh_status(target_dir, 'success', months, end_period, 'Local metric database refresh complete.')
    except Exception as error:
        _write_refresh_status(target_dir, 'failed', months, end_period, str(error))
        raise
