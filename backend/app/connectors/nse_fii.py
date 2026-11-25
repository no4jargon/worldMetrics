"""Daily combined-exchange FII/FPI equity cash flows, in rupees crore.

NSE publishes the latest session only. Historical observations are backfilled
from Groww's public cash-market report in calendar-month windows; longer
custom windows can return weekly aggregates and must not be used here.
"""
from __future__ import annotations

from calendar import monthrange
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
import json
import math
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


NSE_FII_SOURCE_NAME = 'NSE'
NSE_FII_SOURCE_URL = 'https://www.nseindia.com/reports/fii-dii'
NSE_FII_DATA_URL = 'https://www.nseindia.com/api/fiidiiTradeReact'
NSE_FII_HOLIDAYS_URL = 'https://www.nseindia.com/api/holiday-master?type=trading'
GROWW_FII_SOURCE_URL = 'https://groww.in/fii-dii-data'
GROWW_FII_DATA_URL = 'https://groww.in/v1/api/search/v3/query/fii_dii/st_fii_dii'
NSE_FII_SCOPE = 'Combined NSE, BSE and MSEI equity cash market'
MAX_RESPONSE_BYTES = 4 * 1024 * 1024


def _india_today() -> date:
    return datetime.now(ZoneInfo('Asia/Kolkata')).date()


def _number(value: Any, field: str) -> float:
    if isinstance(value, bool) or value is None:
        raise ValueError(f'Invalid FII {field}: {value!r}')
    if isinstance(value, str):
        value = value.strip().replace(',', '')
        if value.startswith('(') and value.endswith(')'):
            value = '-' + value[1:-1]
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f'Invalid FII {field}: {value!r}') from error
    if not math.isfinite(result):
        raise ValueError(f'Non-finite FII {field}')
    return result


def _record(day: Any, buy: Any, sell: Any, net: Any, *, today: date) -> dict[str, Any]:
    parsed: date | None = None
    for fmt in ('%Y-%m-%d', '%d-%b-%Y'):
        try:
            parsed = datetime.strptime(str(day), fmt).date()
            break
        except ValueError:
            pass
    if parsed is None or parsed > today:
        raise ValueError(f'Invalid or future FII trading date: {day!r}')
    buy_value = _number(buy, 'buy')
    sell_value = _number(sell, 'sell')
    net_value = _number(net, 'net')
    if buy_value < 0 or sell_value < 0:
        raise ValueError('FII gross purchases and sales must be nonnegative')
    if abs((buy_value - sell_value) - net_value) > 0.05:
        raise ValueError(f'FII buy minus sell does not match net on {parsed}')
    return {
        'date': parsed.isoformat(),
        'buy': round(buy_value, 2),
        'sell': round(sell_value, 2),
        'net': round(net_value, 2),
    }


def _unique(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_date: dict[str, dict[str, Any]] = {}
    for record in records:
        day = record['date']
        if day in by_date and record != by_date[day]:
            raise ValueError(f'Conflicting FII observations for {day}')
        by_date[day] = record
    return [by_date[day] for day in sorted(by_date)]


def parse_nse_fii_payload(payload: Any, *, today: date | None = None) -> list[dict[str, Any]]:
    """Select FII/FPI only from NSE's combined cash-market JSON response."""
    if not isinstance(payload, list):
        raise ValueError('NSE FII response must be a list')
    current_day = today or _india_today()
    records = []
    for item in payload:
        if not isinstance(item, dict):
            raise ValueError('NSE FII response contains a malformed row')
        category = str(item.get('category', '')).replace(' ', '').upper()
        if category not in {'FII/FPI', 'FII', 'FPI'}:
            continue
        records.append(_record(item.get('date'), item.get('buyValue'), item.get('sellValue'), item.get('netValue'), today=current_day))
    if not records:
        raise ValueError('NSE response contains no FII/FPI cash-market observation')
    return _unique(records)


def parse_groww_fii_payload(
    payload: Any,
    *,
    start: date,
    end: date,
    today: date | None = None,
) -> list[dict[str, Any]]:
    """Parse one calendar month's daily cash-market history, never aggregates."""
    if start.year != end.year or start.month != end.month or start > end:
        raise ValueError('FII historical requests must stay within one calendar month')
    if not isinstance(payload, dict) or payload.get('errors'):
        raise ValueError('Groww FII historical response is invalid')
    wrapper = payload.get('data')
    items = wrapper.get('data') if isinstance(wrapper, dict) else None
    if not isinstance(items, list):
        raise ValueError('Groww FII historical response has no daily data list')
    records = []
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get('fii'), dict):
            raise ValueError('Groww FII historical response contains a malformed row')
        values = item['fii']
        record = _record(item.get('date'), values.get('grossBuy'), values.get('grossSell'), values.get('netBuySell'), today=today or _india_today())
        if not start.isoformat() <= record['date'] <= end.isoformat():
            raise ValueError(f'Historical FII date outside requested month: {record["date"]}')
        records.append(record)
    return _unique(records)


def _fetch_json(url: str, timeout: float) -> Any:
    request = Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (compatible; WorldMetrics/0.1)',
        'Accept': 'application/json',
        'Referer': NSE_FII_SOURCE_URL if 'nseindia.com/' in url else GROWW_FII_SOURCE_URL,
    })
    with urlopen(request, timeout=timeout) as response:
        body = response.read(MAX_RESPONSE_BYTES + 1)
    if len(body) > MAX_RESPONSE_BYTES:
        raise ValueError('FII response exceeds maximum size')
    return json.loads(body.decode('utf-8-sig'))


def _month_windows(today: date, months: int) -> list[tuple[date, date]]:
    windows = []
    for offset in range(months):
        index = today.year * 12 + today.month - 1 - offset
        year, month0 = divmod(index, 12)
        start = date(year, month0 + 1, 1)
        end = min(date(year, month0 + 1, monthrange(year, month0 + 1)[1]), today)
        windows.append((start, end))
    return windows


def _fetch_history_window(start: date, end: date, today: date, timeout: float) -> list[dict[str, Any]]:
    url = GROWW_FII_DATA_URL + '?' + urlencode({
        'segment': 'Cash Market', 'period': 'custom',
        'startDate': start.isoformat(), 'endDate': end.isoformat(),
    })
    return parse_groww_fii_payload(_fetch_json(url, timeout), start=start, end=end, today=today)


def _parse_holidays(payload: Any) -> tuple[set[date], set[int]]:
    rows = payload.get('CM') if isinstance(payload, dict) else None
    if not isinstance(rows, list) or not rows:
        raise ValueError('NSE cash-market trading holiday calendar is unavailable')
    holidays = {datetime.strptime(item['tradingDate'], '%d-%b-%Y').date() for item in rows}
    return holidays, {day.year for day in holidays}


def _missing_sessions(records: list[dict[str, Any]], start: date, end: date, holidays: set[date]) -> list[str]:
    available = {item['date'] for item in records}
    missing = []
    current = start
    while current <= end:
        if current.weekday() < 5 and current not in holidays and current.isoformat() not in available:
            missing.append(current.isoformat())
        current += timedelta(days=1)
    return missing


def fetch_fii_records(
    *, timeout: float = 20, history_months: int = 12, today: date | None = None,
) -> dict[str, Any]:
    """Fetch authoritative latest flow and optional matching daily history.

    A failed latest NSE fetch raises so the caller can preserve its last good
    snapshot. Historical failures never replace that official latest record.
    Groww history is accepted only after an overlapping day agrees with NSE.
    """
    if isinstance(history_months, bool) or not isinstance(history_months, int) or not 0 <= history_months <= 120:
        raise ValueError('history_months must be an integer between 0 and 120')
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError('timeout must be positive and finite')
    current_day = today or _india_today()
    official = parse_nse_fii_payload(_fetch_json(NSE_FII_DATA_URL, timeout), today=current_day)
    latest_day = official[-1]['date']
    windows = _month_windows(current_day, history_months)
    historical: list[dict[str, Any]] = []
    errors: list[str] = []
    completed_months: list[str] = []
    successful_months: list[str] = []
    missing_months: list[str] = []
    if windows:
        with ThreadPoolExecutor(max_workers=min(4, len(windows))) as pool:
            pending = {pool.submit(_fetch_history_window, start, end, current_day, timeout): (start, end) for start, end in windows}
            for future in as_completed(pending):
                start, end = pending[future]
                try:
                    rows = future.result()
                    historical.extend(rows)
                    if rows:
                        successful_months.append(start.isoformat()[:7])
                    else:
                        missing_months.append(start.isoformat()[:7])
                        errors.append(f'{start:%Y-%m}: historical source returned no daily observations')
                except Exception as error:
                    missing_months.append(start.isoformat()[:7])
                    errors.append(f'{start:%Y-%m}: {type(error).__name__}: {error}')
    historical = _unique(historical)
    history_by_date = {item['date']: item for item in historical}
    overlaps = [(item, history_by_date[item['date']]) for item in official if item['date'] in history_by_date]
    history_verified = bool(overlaps) and all(
        abs(authoritative[field] - mirrored[field]) <= 0.02
        for authoritative, mirrored in overlaps for field in ('buy', 'sell', 'net')
    )
    if historical and not history_verified:
        errors.append('Historical mirror did not match an overlapping official NSE observation; history was not imported.')
        historical = []
        completed_months = []
        successful_months = []
        missing_months = [start.isoformat()[:7] for start, _ in windows]
    missing_dates: list[str] = []
    if historical:
        try:
            holidays, calendar_years = _parse_holidays(_fetch_json(NSE_FII_HOLIDAYS_URL, timeout))
            for start, end in windows:
                month = start.isoformat()[:7]
                if month not in successful_months:
                    continue
                if start.year not in calendar_years:
                    missing_months.append(month)
                    continue
                missing = _missing_sessions(historical, start, min(end, date.fromisoformat(latest_day)), holidays)
                missing_dates.extend(missing)
                if missing:
                    missing_months.append(month)
                elif end.isoformat() < latest_day:
                    completed_months.append(month)
        except Exception as error:
            missing_months.extend(successful_months)
            errors.append(f'Calendar coverage verification: {type(error).__name__}: {error}')
    # Latest official observations always win when provisional values change.
    merged = {item['date']: item for item in historical if item['date'] <= latest_day}
    merged.update({item['date']: item for item in official})
    records = [merged[day] for day in sorted(merged)]
    result: dict[str, Any] = {
        'records': records,
        'source': NSE_FII_SOURCE_NAME,
        'source_name': NSE_FII_SOURCE_NAME,
        'source_url': NSE_FII_SOURCE_URL,
        'data_url': NSE_FII_DATA_URL,
        'scope': NSE_FII_SCOPE,
        'is_provisional': True,
        'coverage_start': records[0]['date'],
        'history_source_url': GROWW_FII_SOURCE_URL if historical else None,
        'history_source_name': 'Groww' if historical else None,
        'history_note': 'Historical daily exchange cash-market figures are mirrored by Groww; overlapping observations were checked against NSE. Latest values come directly from NSE.' if historical else 'History accumulates from daily NSE observations.',
        'history_verified': history_verified,
        'history_complete_months': sorted(completed_months),
        'history_start_month': min(completed_months) if completed_months else None,
        'history_incomplete_months': sorted(set(missing_months)),
        'history_missing_months': sorted(set(missing_months)),
        'history_missing_dates': sorted(set(missing_dates)),
        'history_calendar_url': NSE_FII_HOLIDAYS_URL if historical else None,
        'history_requested_start': windows[-1][0].isoformat() if windows else None,
    }
    if errors:
        result['history_errors'] = sorted(errors)
    if missing_months:
        result['history_note'] += ' Some historical months have missing or unverified sessions and are marked partial.'
    elif errors:
        result['history_note'] += ' Historical backfill was unavailable; daily NSE observations are retained.'
    return result
