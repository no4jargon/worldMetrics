from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import date
from typing import Optional


@dataclass
class CanonicalObservation:
    metric_code: str
    period_label: str
    period_start: date
    period_end: date
    value: float
    unit: str
    geography: str = 'India'
    segment: Optional[str] = None
    source_release_date: Optional[date] = None
    is_preliminary: bool = False
    notes: Optional[str] = None
    source_url: Optional[str] = None

    def to_dict(self) -> dict:
        data = asdict(self)
        for key in ('period_start', 'period_end', 'source_release_date'):
            if data[key] is not None:
                data[key] = data[key].isoformat()
        return data


@dataclass
class DerivedObservation:
    metric_code: str
    period_label: str
    transform: str
    value: float
    unit: str
    segment: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class FetchResult:
    dataset_code: str
    status: str
    parser_version: str
    source_url: str
    payload_type: str
    payload: dict | str
