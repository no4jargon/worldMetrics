from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path
from typing import Iterable

from app.core.models import CanonicalObservation

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DB_PATH = ROOT / 'backend' / 'data' / 'worldmetrics.sqlite3'

SCHEMA = '''
create table if not exists observations (
  metric_code text not null,
  period_label text not null,
  period_start text not null,
  period_end text not null,
  value real not null,
  unit text not null,
  geography text not null default 'India',
  segment text,
  segment_key text not null default 'ALL',
  source_release_date text,
  is_preliminary integer not null default 0,
  notes text,
  source_url text,
  updated_at text not null default current_timestamp,
  primary key (metric_code, period_label, segment_key)
);

create table if not exists connector_runs (
  dataset_code text primary key,
  status text not null,
  observations_emitted integer not null default 0,
  error_message text,
  run_at text not null default current_timestamp
);
'''


def reset_database(db_path: Path = DEFAULT_DB_PATH) -> None:
    if db_path.exists():
        db_path.unlink()
    init_database(db_path)


def init_database(db_path: Path = DEFAULT_DB_PATH) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.executescript(SCHEMA)
        columns = {row[1] for row in conn.execute('pragma table_info(observations)').fetchall()}
        if 'source_url' not in columns:
            conn.execute('alter table observations add column source_url text')


def delete_observations_for_metrics(metric_codes: Iterable[str], db_path: Path = DEFAULT_DB_PATH) -> None:
    init_database(db_path)
    codes = list(metric_codes)
    if not codes:
        return
    placeholders = ','.join('?' for _ in codes)
    with sqlite3.connect(db_path) as conn:
        conn.execute(f'delete from observations where metric_code in ({placeholders})', codes)


def upsert_observations(observations: Iterable[CanonicalObservation], db_path: Path = DEFAULT_DB_PATH) -> None:
    init_database(db_path)
    rows = []
    for obs in observations:
        rows.append(
            (
                obs.metric_code,
                obs.period_label,
                obs.period_start.isoformat(),
                obs.period_end.isoformat(),
                obs.value,
                obs.unit,
                obs.geography,
                obs.segment,
                obs.segment or 'ALL',
                obs.source_release_date.isoformat() if obs.source_release_date else None,
                1 if obs.is_preliminary else 0,
                obs.notes,
                obs.source_url,
            )
        )
    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            '''
            insert into observations (
              metric_code, period_label, period_start, period_end, value, unit,
              geography, segment, segment_key, source_release_date, is_preliminary, notes, source_url
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(metric_code, period_label, segment_key) do update set
              period_start=excluded.period_start,
              period_end=excluded.period_end,
              value=excluded.value,
              unit=excluded.unit,
              geography=excluded.geography,
              source_release_date=excluded.source_release_date,
              is_preliminary=excluded.is_preliminary,
              notes=excluded.notes,
              source_url=excluded.source_url,
              updated_at=current_timestamp
            ''',
            rows,
        )


def replace_connector_statuses(statuses: dict[str, dict], db_path: Path = DEFAULT_DB_PATH) -> None:
    init_database(db_path)
    rows = [
        (
            dataset_code,
            str(status.get('status')),
            int(status.get('observations_emitted') or 0),
            status.get('error_message'),
        )
        for dataset_code, status in statuses.items()
    ]
    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            '''
            insert into connector_runs (dataset_code, status, observations_emitted, error_message)
            values (?, ?, ?, ?)
            on conflict(dataset_code) do update set
              status=excluded.status,
              observations_emitted=excluded.observations_emitted,
              error_message=excluded.error_message,
              run_at=current_timestamp
            ''',
            rows,
        )


def load_observations(db_path: Path = DEFAULT_DB_PATH) -> list[CanonicalObservation]:
    init_database(db_path)
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            '''
            select metric_code, period_label, period_start, period_end, value, unit,
                   geography, segment, source_release_date, is_preliminary, notes, source_url
            from observations
            order by period_start, metric_code, segment_key
            '''
        ).fetchall()
    observations: list[CanonicalObservation] = []
    for row in rows:
        observations.append(
            CanonicalObservation(
                metric_code=row[0],
                period_label=row[1],
                period_start=date.fromisoformat(row[2]),
                period_end=date.fromisoformat(row[3]),
                value=float(row[4]),
                unit=row[5],
                geography=row[6],
                segment=row[7],
                source_release_date=date.fromisoformat(row[8]) if row[8] else None,
                is_preliminary=bool(row[9]),
                notes=row[10],
                source_url=row[11],
            )
        )
    return observations


def load_connector_statuses(db_path: Path = DEFAULT_DB_PATH) -> dict[str, dict]:
    init_database(db_path)
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            '''
            select dataset_code, status, observations_emitted, error_message
            from connector_runs
            '''
        ).fetchall()
    return {
        row[0]: {
            'dataset_code': row[0],
            'status': row[1],
            'observations_emitted': row[2],
            'error_message': row[3],
        }
        for row in rows
    }
