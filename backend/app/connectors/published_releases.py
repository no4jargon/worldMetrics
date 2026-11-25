"""Bounded, deterministic readers for published national CPI/cement/housing releases.

Discovery uses MoSPI's public release API, ICRA's sector listing and the JLL /
EquityBulls sitemaps. A discovery or format change raises instead of fabricating
an observation; the cloud refresh retains the last verified data on failure.
"""
from __future__ import annotations

import io
import json
import re
import xml.etree.ElementTree as ET
from calendar import monthrange
from datetime import date, datetime
from html import unescape
from typing import Callable
from urllib.parse import quote, urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from app.connectors.icra_cement import ICRACementMonthlyUpdatesConnector
from app.core.models import CanonicalObservation

Reader = Callable[[str], bytes]
UA = 'Mozilla/5.0 (compatible; WorldMetrics/1.0; published-economic-data)'
MOSPI_ORIGIN = 'https://www.mospi.gov.in/'
MOSPI_RELEASE_API = MOSPI_ORIGIN + 'api/latest-release/get-web-latest-release-list'
JLL_SITEMAP = 'https://www.jll.com/en-in/sitemap.xml'
EQUITY_SITEMAP = 'https://www.equitybulls.com/sitemap.xml'
MONTH_NAMES = ('January February March April May June July August September October November December').split()
MONTH_PATTERN = '(?:' + '|'.join(MONTH_NAMES) + ')'
NUMBER = r'(-?\d[\d,]*(?:\.\d+)?)'


def _request(url: str, *, payload: dict | None = None) -> bytes:
    parts = urlsplit(url)
    safe_url = urlunsplit((parts.scheme, parts.netloc, quote(parts.path, safe='/%:._-()'), parts.query, ''))
    body = json.dumps(payload).encode() if payload is not None else None
    headers = {'User-Agent': UA, 'Accept': '*/*'}
    if body is not None:
        headers['Content-Type'] = 'application/json'
    with urlopen(Request(safe_url, data=body, headers=headers), timeout=20) as response:
        contents = response.read(8 * 1024 * 1024 + 1)
    if not contents or len(contents) > 8 * 1024 * 1024:
        raise ValueError('Published release is empty or exceeds the 8 MiB limit')
    return contents


def _read(url: str) -> bytes:
    return _request(url)


def _text(contents: bytes | str) -> str:
    if isinstance(contents, bytes) and contents.startswith(b'%PDF'):
        from pypdf import PdfReader
        contents = '\n'.join(page.extract_text() or '' for page in PdfReader(io.BytesIO(contents)).pages)
    elif isinstance(contents, bytes):
        contents = contents.decode('utf-8', 'ignore')
    contents = re.sub(r'<(script|style)\b[^>]*>[\s\S]*?</\1>', ' ', contents, flags=re.I)
    return re.sub(r'\s+', ' ', unescape(re.sub(r'<[^>]+>', ' ', contents))).strip()


def _month(name: str, year: str | int) -> str:
    return f'{int(year):04d}-{[n.lower() for n in MONTH_NAMES].index(name.lower()) + 1:02d}'


def _release_date(raw: str, text: str = '') -> date:
    patterns = [
        r'(?:article:published_time["\'][^>]*content=["\']|datePublished["\']\s*:\s*["\']|datetime=["\'])(\d{4}-\d{2}-\d{2})',
        r'(?:Posted On\s*:|Dated|Monthly Update|Published(?: on)?)[\s:]*?(\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+,?\s+\d{4})',
    ]
    for pattern in patterns:
        match = re.search(pattern, raw, re.I) or re.search(pattern, text, re.I)
        if match:
            value = match.group(1)
            if re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
                return date.fromisoformat(value)
            value = re.sub(r'(\d)(st|nd|rd|th)\b', r'\1', value, flags=re.I).replace(',', '')
            for fmt in ['%d %B %Y', '%d %b %Y']:
                try:
                    return datetime.strptime(value, fmt).date()
                except ValueError:
                    pass
    raise ValueError('Published release date could not be determined')


def _monthly(code: str, period: str, value: float, unit: str, released: date,
             url: str, notes: str, *, preliminary: bool = False) -> CanonicalObservation:
    year, month = map(int, period.split('-'))
    return CanonicalObservation(code, period, date(year, month, 1),
                                date(year, month, monthrange(year, month)[1]), value, unit,
                                source_release_date=released, source_url=url,
                                notes=notes, is_preliminary=preliminary)


def _dedupe(observations: list[CanonicalObservation]) -> list[CanonicalObservation]:
    result = {}
    for obs in observations:
        key = obs.metric_code, obs.period_label
        prior = result.get(key)
        if prior is None or (obs.source_release_date or date.min) > (prior.source_release_date or date.min):
            result[key] = obs
        elif obs.source_release_date == prior.source_release_date and obs.value != prior.value:
            raise ValueError(f'Conflicting published values for {obs.metric_code} {obs.period_label}')
    return sorted(result.values(), key=lambda obs: (obs.period_start, obs.metric_code))


def parse_cpi(contents: bytes | str, source_url: str, released: date | None = None) -> list[CanonicalObservation]:
    text = _text(contents)
    title = re.search(r'CONSUMER PRICE INDEX.{0,100}?FOR\s+(' + MONTH_PATTERN + r'),?\s+(\d{4})', text, re.I)
    if title is None or 'All India Consumer Price Index' not in text:
        raise ValueError('Not an identifiable all-India CPI release')
    period = _month(*title.groups())
    y, m = map(int, period.split('-'))
    prior_y, prior_m = (y - 1, 12) if m == 1 else (y, m - 1)
    prior_period = f'{prior_y:04d}-{prior_m:02d}'
    header = re.search(r'(' + MONTH_PATTERN + r'),?\s+(\d{4})\s*\(Final\)\s*(' + MONTH_PATTERN + r'),?\s+(\d{4})\s*\(Provisional\)', text, re.I)
    if not header or _month(header[1], header[2]) != prior_period or _month(header[3], header[4]) != period:
        raise ValueError('CPI final/provisional reporting columns could not be verified')
    rows = re.findall(r'CPI\s*\(General\)\s+' + r'\s+'.join([NUMBER] * 6), text, re.I)
    if len(rows) < 2:
        raise ValueError('CPI general inflation/index six-column tables could not be parsed')
    inflation, indices = [[float(n.replace(',', '')) for n in row] for row in rows[:2]]
    released = released or _release_date(str(contents), text)
    output = []
    for label, offset, preliminary in [(prior_period, 2, False), (period, 5, True)]:
        note = 'MoSPI all-India combined CPI, base 2024=100; ' + ('provisional.' if preliminary else 'final.')
        output.extend([
            _monthly('cpi_headline', label, inflation[offset], 'percent', released, source_url, note, preliminary=preliminary),
            _monthly('cpi_index', label, indices[offset], 'index', released, source_url, note, preliminary=preliminary),
        ])
    return output


def fetch_cpi(*, reader: Reader = _read, listing_loader: Callable[[], dict] | None = None) -> list[CanonicalObservation]:
    listing = listing_loader() if listing_loader else json.loads(_request(MOSPI_RELEASE_API, payload={
        'page_no': 1, 'page_size': 25, 'search_term': 'CPI', 'sort_field': 'published_year',
        'sort_order': 'DESC', 'from_date': '', 'to_date': '', 'lang': 'en', 'data_source': 'web',
    }))
    candidates = []
    for row in listing.get('data', []):
        if not re.search(r'(?:\bCPI\b|consumer price index)', row.get('title', ''), re.I):
            continue
        item = row.get('file_one') or {}
        path = item.get('path', '')
        if path.lower().endswith('.pdf'):
            candidates.append((row.get('published_year', ''), urljoin(MOSPI_ORIGIN, path)))
    if not candidates:
        raise ValueError('MoSPI returned no CPI PDF release candidates')
    errors = []
    # Start with the newest dated release; its table includes the previous final month.
    for release, url in sorted(candidates, reverse=True)[:3]:
        try:
            return parse_cpi(reader(url), url, date.fromisoformat(release[:10]))
        except Exception as error:
            errors.append(str(error))
    raise ValueError('No MoSPI CPI candidate parsed: ' + '; '.join(errors))


def parse_cement(contents: bytes | str, source_url: str, released: date | None = None) -> list[CanonicalObservation]:
    text = _text(contents)
    released = released or _release_date(str(contents), text)
    patterns = [
        r'Cement\s+production\s+volumes?.{0,120}?in\s+(' + MONTH_PATTERN + r')\s+(\d{4})\s+to\s+(\d+(?:\.\d+)?)\s+million\s+(?:metric\s+)?tonnes?',
        r'Cement\s+production\s+volumes?.{0,120}?to\s+(\d+(?:\.\d+)?)\s+million\s+(?:metric\s+)?tonnes?\s*(?:\(MT\))?\s+in\s+(' + MONTH_PATTERN + r')\s+(\d{4})',
    ]
    output = []
    for index, pattern in enumerate(patterns):
        for match in re.finditer(pattern, text, re.I):
            month, year, value = match.groups() if index == 0 else (match[2], match[3], match[1])
            output.append(_monthly('cement_output', _month(month, year), float(value), 'MT', released,
                                   source_url, match[0]))
    if not output:
        raise ValueError('No explicit named-calendar-month cement production level found')
    return _dedupe(output)


def fetch_cement(*, reader: Reader = _read, reports_loader=None) -> list[CanonicalObservation]:
    connector = ICRACementMonthlyUpdatesConnector(max_pages=1, request_delay_seconds=0)
    reports = reports_loader() if reports_loader else connector._fetch_report_listing()[0]
    if not reports:
        raise ValueError('ICRA monthly cement listing returned no reports')
    output, errors = [], []
    for report in sorted(reports, key=lambda item: connector._parse_release_date(item.release_date) or date.min, reverse=True)[:3]:
        try:
            output.extend(parse_cement(reader(report.report_url), report.report_url,
                                       connector._parse_release_date(report.release_date)))
        except Exception as error:
            errors.append(str(error))
    if not output:
        raise ValueError('No ICRA monthly cement report parsed: ' + '; '.join(errors))
    return _dedupe(output)


def _sitemap_rows(contents: bytes) -> list[tuple[str, str]]:
    root = ET.fromstring(contents)
    rows = []
    for row in root:
        fields = {child.tag.rsplit('}', 1)[-1]: child.text or '' for child in row}
        if fields.get('loc'):
            rows.append((fields.get('lastmod', ''), fields['loc']))
    return rows


def parse_jll(contents: bytes | str, source_url: str, released: date | None = None) -> list[CanonicalObservation]:
    text = _text(contents)
    if not re.search(r'\bJLL\b', text):
        raise ValueError('Housing article does not attribute data to JLL')
    released = released or _release_date(contents.decode('utf-8', 'ignore') if isinstance(contents, bytes) else contents, text)
    # National total is read from the explicitly labelled sales table, not YTD or launches.
    table = re.search(r'Residential\s+Sales\s*\(in units\)\s+Q([1-4])\s+(\d{4})\s+Sales.{0,100}?Q([1-4])\s+(\d{4})\s+sales.{0,1500}?\bIndia\s+([\d,]+)\s+([\d,]+)', text, re.I)
    output = []
    if table:
        for quarter, year, value in [(table[1], table[2], table[5]), (table[3], table[4], table[6])]:
            year, quarter = int(year), int(quarter)
            start_month, end_month = (quarter - 1) * 3 + 1, quarter * 3
            output.append(CanonicalObservation('home_sales_jll', f'{year}-Q{quarter}',
                date(year, start_month, 1), date(year, end_month, monthrange(year, end_month)[1]),
                float(value.replace(',', '')), 'units', source_release_date=released, source_url=source_url,
                notes='JLL REIS top-seven-city apartment sales table; ' + ('reproduced by EquityBulls.' if 'equitybulls.com' in source_url else 'JLL published release.')))
    else:
        # A direct national JLL report can state a quarter and explicit sales count in prose.
        if not re.search(r'(?:top\s+(?:seven|7)|seven\s+(?:major|urban))\s+(?:cities|markets)', text, re.I):
            raise ValueError('No national top-seven-city JLL sales scope found')
        match = re.search(r'Residential\s+sales.{0,110}?to\s+([\d,]+)\s+units\s+in\s+Q([1-4])\s+(\d{4})', text, re.I)
        if not match:
            raise ValueError('No explicit quarter-level national JLL sales total found')
        value, quarter, year = float(match[1].replace(',', '')), int(match[2]), int(match[3])
        end_month = quarter * 3
        output.append(CanonicalObservation('home_sales_jll', f'{year}-Q{quarter}', date(year, end_month-2, 1),
            date(year, end_month, monthrange(year, end_month)[1]), value, 'units',
            source_release_date=released, source_url=source_url, notes='JLL top-seven-city residential sales; explicit quarter total.'))
    return _dedupe(output)


def fetch_jll(*, reader: Reader = _read) -> list[CanonicalObservation]:
    candidates, discovery_errors = [], []
    try:
        for modified, url in _sitemap_rows(reader(JLL_SITEMAP)):
            if '/en-in/' in url and ('/newsroom/' in url or '/insights/' in url) and any(
                term in url for term in ['housing-market', 'housing-demand', 'residential-sales', 'india-residential', 'premium-housing']):
                candidates.append((modified, url))
    except Exception as error:
        discovery_errors.append(str(error))
    try:
        maps = [url for _, url in _sitemap_rows(reader(EQUITY_SITEMAP)) if re.search(r'/sitemap-news-\d+\.xml$', url)]
        maps.sort(key=lambda url: int(re.search(r'news-(\d+)', url)[1]), reverse=True)
        for sitemap in maps[:2]:
            for modified, url in _sitemap_rows(reader(sitemap)):
                if any(term in url for term in ['housing-market', 'residential-market', 'housing-sales', 'premium-homes', 'jll-']):
                    candidates.append((modified, url))
    except Exception as error:
        discovery_errors.append(str(error))
    output, errors = [], discovery_errors
    for _, url in sorted(set(candidates), reverse=True)[:8]:
        try:
            output.extend(parse_jll(reader(url), url))
        except Exception as error:
            errors.append(str(error))
    if not output:
        raise ValueError('No national JLL quarterly release parsed: ' + '; '.join(errors[-6:]))
    # Include comparison/revision observations, preferring the latest published release.
    return _dedupe(output)
