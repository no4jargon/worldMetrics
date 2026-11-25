"""Completed-month VAHAN category totals from the official public chart API.

The endpoint and January–December array order are used by the portal's own
``resources/js/analytics/public/vahan/registrationLineChartComparisonView.js``.
This is an unauthenticated chart request, separate from CAPTCHA-protected
public tabular reports. No login, challenge solving, or session emulation.
"""
from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime
import json
import math
import re
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from app.core.models import CanonicalObservation

PORTAL_URL = 'https://analytics.parivahan.gov.in/analytics/publicdashboard/vahan?lang=en'
API_URL = 'https://analytics.parivahan.gov.in/analytics/publicdashboard/vahandashboard/vahanYearWiseRegistrationComparisonChart'
DATASET_CODE = 'vahan_vehicle_registrations'
CATEGORY_GROUPS = {
    'two_wheeler_sales': ('TWO WHEELER(NT)', 'TWO WHEELER(T)', 'TWO WHEELER (Invalid Carriage)'),
    'four_wheeler_sales': ('LIGHT MOTOR VEHICLE', 'MEDIUM MOTOR VEHICLE', 'HEAVY MOTOR VEHICLE', 'FOUR WHEELER (Invalid Carriage)'),
}


def _india_today() -> date:
    return datetime.now(ZoneInfo('Asia/Kolkata')).date()


def _years(years: list[int], today: date) -> list[int]:
    if not years or any(isinstance(year, bool) or not isinstance(year, int) or not 1900 <= year <= today.year for year in years):
        raise ValueError('VAHAN requested years must be nonfuture calendar years')
    return sorted(set(years))


def public_request_url(metric_code: str, years: list[int]) -> str:
    """Reproduce the published public chart's filters, including legacy groups."""
    if metric_code not in CATEGORY_GROUPS:
        raise ValueError(f'Unsupported VAHAN metric: {metric_code}')
    if not years:
        raise ValueError('VAHAN request requires at least one year')
    return API_URL + '?' + urlencode({
        'fromYear': min(years), 'toYear': max(years), 'stateCode': '', 'rtoCode': 0,
        'vehicleClasses': '', 'vehicleSubCategories': ','.join(CATEGORY_GROUPS[metric_code]),
        'timePeriod': 0, 'vehicleCategoryGroup': '', 'vehicleType': '',
    })


def parse_vahan_public(
    payload: object,
    metric_code: str,
    requested_years: list[int],
    today: date,
    source_url: str | None = None,
) -> list[CanonicalObservation]:
    """Parse actual month slots; missing slots never become zero observations.

    The API returns up to three year arrays even for one selected year. Keep
    only requested years. A missing requested year is a source failure, so the
    pipeline retains its cache. Null/omitted months are absent, not zero. The
    current month and every future month are excluded even if already present.
    """
    years = _years(requested_years, today)
    if metric_code not in CATEGORY_GROUPS:
        raise ValueError(f'Unsupported VAHAN metric: {metric_code}')
    if not isinstance(payload, dict) or not payload:
        raise ValueError('VAHAN public response must be a nonempty year-to-month-array object')
    for year, counts in payload.items():
        if not isinstance(year, str) or not re.fullmatch(r'(19|20)\d{2}', year):
            raise ValueError('VAHAN response contains an invalid year key')
        if not isinstance(counts, list) or len(counts) > 12:
            raise ValueError(f'VAHAN {year} must contain at most twelve January–December slots')
        for value in counts:
            if value is None:
                continue
            if (isinstance(value, bool) or not isinstance(value, (int, float))
                    or not math.isfinite(value) or value < 0 or value != int(value)):
                raise ValueError(f'VAHAN {year} contains a nonfinite, negative, or noninteger count')
    missing = [year for year in years if str(year) not in payload]
    if missing:
        raise ValueError(f'VAHAN public response omitted requested years: {missing}')
    observations = []
    source_url = source_url or public_request_url(metric_code, years)
    note = ('VAHAN public national registration chart; calendar months; category union: '
            + ', '.join(CATEGORY_GROUPS[metric_code])
            + '. Current month excluded. Historical counts may be revised by the source.')
    for year in years:
        for month, value in enumerate(payload[str(year)], start=1):
            start = date(year, month, 1)
            if value is None or (year, month) >= (today.year, today.month):
                continue
            observations.append(CanonicalObservation(
                metric_code=metric_code, period_label=start.strftime('%Y-%m'),
                period_start=start, period_end=date(year, month, monthrange(year, month)[1]),
                value=float(value), unit='units', segment='domestic', source_url=source_url,
                notes=note, is_preliminary=True,
            ))
    return observations


def fetch_vahan_public(years: list[int] | None = None) -> list[CanonicalObservation]:
    """Fetch two national category unions without discarding cached history.

    Raises if either category fetch/validation fails. The pipeline should merge
    the complete returned batch into its retained cache only after success.
    """
    today = _india_today()
    years = _years(years if years is not None else [today.year - 1, today.year], today)
    observations = []
    for metric_code in CATEGORY_GROUPS:
        url = public_request_url(metric_code, years)
        request = Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Referer': PORTAL_URL, 'Accept': 'application/json'})
        with urlopen(request, timeout=45) as response:
            if response.status != 200:
                raise ValueError(f'VAHAN public API returned HTTP {response.status}')
            body = response.read(2_000_001)
        if len(body) > 2_000_000:
            raise ValueError('VAHAN public response exceeds expected size')
        payload = json.loads(body)
        parsed = parse_vahan_public(payload, metric_code, years, today, url)
        if not parsed:
            raise ValueError(f'VAHAN public response contains no completed months for {metric_code}')
        observations.extend(parsed)
    if not observations:
        raise ValueError('VAHAN public response contains no completed-month observations')
    return observations
