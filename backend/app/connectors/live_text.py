from __future__ import annotations

import re
import urllib.request
from datetime import date
from urllib.parse import urljoin

from app.core.models import FetchResult

MONTHS = {
    'jan': 1,
    'january': 1,
    'feb': 2,
    'february': 2,
    'mar': 3,
    'march': 3,
    'apr': 4,
    'april': 4,
    'may': 5,
    'jun': 6,
    'june': 6,
    'jul': 7,
    'july': 7,
    'aug': 8,
    'august': 8,
    'sep': 9,
    'sept': 9,
    'september': 9,
    'oct': 10,
    'october': 10,
    'nov': 11,
    'november': 11,
    'dec': 12,
    'december': 12,
}


DEFAULT_USER_AGENT = 'world-metrics/0.1'


def read_text_url(url: str) -> str:
    request = urllib.request.Request(url, headers={'User-Agent': DEFAULT_USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode('utf-8')


def extract_links(html: str) -> list[tuple[str, str]]:
    pattern = re.compile(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL)
    return [(href, re.sub(r'<[^>]+>', ' ', text).strip()) for href, text in pattern.findall(html)]


def normalize_space(value: str) -> str:
    return re.sub(r'\s+', ' ', value).strip()


def parse_month_year(label: str) -> tuple[int, int] | None:
    match = re.search(r'(?i)(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)[-\s,]*([0-9]{2,4})', label)
    if not match:
        return None
    month = MONTHS[match.group(1).lower()]
    year = int(match.group(2))
    if year < 100:
        year += 2000
    return year, month


def month_label(label: str) -> str:
    year, month = parse_month_year(label) or (0, 0)
    return f'{year:04d}-{month:02d}'


def quarter_label(label: str) -> str | None:
    match = re.search(r'(?i)q([1-4])\s*-?\s*([0-9]{4})|([0-9]{4})[\s\S]*?q([1-4])', label)
    if not match:
        return None
    if match.group(1) and match.group(2):
        quarter = int(match.group(1))
        year = int(match.group(2))
    else:
        year = int(match.group(3))
        quarter = int(match.group(4))
    return f'{year}-Q{quarter}'


def parse_date_text(label: str) -> date | None:
    match = re.search(r'(?i)(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+),?\s+(\d{4})', label)
    if match:
        day = int(match.group(1))
        month = MONTHS[match.group(2).lower()]
        year = int(match.group(3))
        return date(year, month, day)

    match = re.search(r'(?i)([A-Za-z]+)\s+(\d{1,2}),\s*(\d{4})', label)
    if match:
        month = MONTHS[match.group(1).lower()]
        day = int(match.group(2))
        year = int(match.group(3))
        return date(year, month, day)

    match = re.search(r'(\d{4})-(\d{2})-(\d{2})', label)
    if match:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))

    match = re.search(r'(\d{2})/(\d{2})/(\d{4})', label)
    if match:
        return date(int(match.group(3)), int(match.group(2)), int(match.group(1)))

    match = re.search(r'(\d{2})-(\d{2})-(\d{4})', label)
    if match:
        return date(int(match.group(3)), int(match.group(2)), int(match.group(1)))

    return None


def resolve_link(base_url: str, href: str) -> str:
    return urljoin(base_url, href)


def latest_link(html: str, base_url: str, predicate) -> str:
    candidates: list[tuple[tuple[int, int], str]] = []
    fallback_matches: list[str] = []
    for href, text in extract_links(html):
        candidate_text = normalize_space(f'{href} {text}')
        if not predicate(candidate_text):
            continue
        fallback_matches.append(resolve_link(base_url, href))
        parsed = parse_month_year(candidate_text)
        if parsed is None:
            continue
        candidates.append((parsed, resolve_link(base_url, href)))
    if candidates:
        return max(candidates, key=lambda item: item[0])[1]
    if len(fallback_matches) == 1:
        return fallback_matches[0]
    raise ValueError('No matching release links found')


def build_fetch_result(dataset_code: str, parser_version: str, source_url: str, payload: dict) -> FetchResult:
    return FetchResult(
        dataset_code=dataset_code,
        status='success',
        parser_version=parser_version,
        source_url=source_url,
        payload_type='json',
        payload=payload,
    )
