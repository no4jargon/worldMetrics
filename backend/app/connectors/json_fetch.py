from __future__ import annotations

import json
import urllib.request
from pathlib import Path

from app.core.models import FetchResult


DEFAULT_USER_AGENT = 'world-metrics/0.1'


class JsonFetchMixin:
    dataset_code: str
    parser_version: str
    fixture_path: Path | None
    source_url: str | None

    def _fetch_json(self) -> FetchResult:
        if self.fixture_path is not None:
            payload = json.loads(self.fixture_path.read_text())
            source_url = str(self.fixture_path)
        elif self.source_url is not None:
            request = urllib.request.Request(self.source_url, headers={'User-Agent': DEFAULT_USER_AGENT})
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.loads(response.read().decode('utf-8'))
            source_url = self.source_url
        else:
            raise NotImplementedError('Provide fixture_path or source_url')

        return FetchResult(
            dataset_code=self.dataset_code,
            status='success',
            parser_version=self.parser_version,
            source_url=source_url,
            payload_type='json',
            payload=payload,
        )
