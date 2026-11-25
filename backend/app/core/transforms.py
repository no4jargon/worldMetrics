from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from .models import CanonicalObservation, DerivedObservation


def _group_key(obs: CanonicalObservation) -> tuple[str, str]:
    return obs.metric_code, obs.segment or 'ALL'


def compute_transforms(observations: Iterable[CanonicalObservation]) -> list[DerivedObservation]:
    grouped: dict[tuple[str, str], list[CanonicalObservation]] = defaultdict(list)
    for obs in observations:
        grouped[_group_key(obs)].append(obs)

    derived: list[DerivedObservation] = []

    for (_, segment_key), series in grouped.items():
        series = sorted(series, key=lambda x: x.period_start)
        by_period = {item.period_label: item for item in series}
        for i, obs in enumerate(series):
            if i >= 1 and series[i - 1].value != 0:
                prev = series[i - 1].value
                derived.append(
                    DerivedObservation(
                        metric_code=obs.metric_code,
                        period_label=obs.period_label,
                        transform='change_prev_pct',
                        value=((obs.value / prev) - 1.0) * 100.0,
                        unit='percent',
                        segment=None if segment_key == 'ALL' else segment_key,
                    )
                )

            if i >= 2:
                window = series[i - 2 : i + 1]
                derived.append(
                    DerivedObservation(
                        metric_code=obs.metric_code,
                        period_label=obs.period_label,
                        transform='rolling_3p_avg',
                        value=sum(item.value for item in window) / len(window),
                        unit=obs.unit,
                        segment=None if segment_key == 'ALL' else segment_key,
                    )
                )

            year_ago_label = f"{int(obs.period_label[:4]) - 1}{obs.period_label[4:]}"
            year_ago = by_period.get(year_ago_label)
            if year_ago is not None and year_ago.value != 0:
                base = year_ago.value
                derived.append(
                    DerivedObservation(
                        metric_code=obs.metric_code,
                        period_label=obs.period_label,
                        transform='yoy',
                        value=((obs.value / base) - 1.0) * 100.0,
                        unit='percent',
                        segment=None if segment_key == 'ALL' else segment_key,
                    )
                )

        if series:
            base = series[0].value or 1.0
            for obs in series:
                derived.append(
                    DerivedObservation(
                        metric_code=obs.metric_code,
                        period_label=obs.period_label,
                        transform='indexed_100',
                        value=(obs.value / base) * 100.0,
                        unit='index',
                        segment=None if segment_key == 'ALL' else segment_key,
                    )
                )

    return derived
