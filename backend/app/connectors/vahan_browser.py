"""Normal Chromium transport for the existing public VAHAN JSF workflow.

The urllib collector remains the first choice. This fallback uses a real browser
navigation and same-origin form POSTs, sharing browser cookies and TLS. It does
not use proxies, change network identity, solve challenges, or bypass sign-in.
The existing VAHAN connector continues to own filters, categories, and parsing.
"""
from __future__ import annotations

from typing import Any

from app.connectors.vahan_skill import VAHANDashboardSkillConnector


MAX_RESPONSE_BYTES = 8 * 1024 * 1024


class VAHANBrowserConnector(VAHANDashboardSkillConnector):
    parser_version = 'vahan-tabular-monthwise-browser-v1'

    def __init__(self, *, timeout_ms: int = 20_000, **kwargs):
        super().__init__(**kwargs)
        self.timeout_ms = timeout_ms
        self._page = None

    def _fetch_live(self):
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                # Keep Chromium's ordinary default settings and TLS validation.
                page = browser.new_page()
                page.set_default_timeout(self.timeout_ms)
                self._page = page
                return super()._fetch_live()
            finally:
                self._page = None
                browser.close()

    def _require_page(self):
        if self._page is None:
            raise RuntimeError('VAHAN browser transport is not open.')
        return self._page

    @staticmethod
    def _bounded(text: str) -> str:
        if len(text.encode('utf-8')) > MAX_RESPONSE_BYTES:
            raise ValueError('VAHAN browser response exceeds the maximum size.')
        return text

    def _read_text(self, _opener, url: str) -> str:
        page = self._require_page()
        response = page.goto(url, wait_until='domcontentloaded', timeout=self.timeout_ms)
        if response is None or not response.ok:
            status = response.status if response is not None else 'no response'
            raise RuntimeError(f'VAHAN browser navigation failed: HTTP {status}.')
        page.wait_for_selector('form#masterLayout_formlogin', state='attached', timeout=self.timeout_ms)
        return self._bounded(page.content())

    def _post_ajax(
        self, _opener, url: str, form_fields: dict[str, str], source: str,
        execute: str, render: str, event: str | None = None, command_field: bool = False,
    ) -> str:
        payload = dict(form_fields)
        payload.update({
            'javax.faces.partial.ajax': 'true',
            'javax.faces.source': source,
            'javax.faces.partial.execute': execute,
            'javax.faces.partial.render': render,
        })
        if event is not None:
            payload['javax.faces.behavior.event'] = event
            payload['javax.faces.partial.event'] = event
        if command_field:
            payload[source] = source
        page = self._require_page()
        result: dict[str, Any] = page.evaluate(
            """async ({url, payload, timeoutMs}) => {
                const controller = new AbortController();
                const timer = setTimeout(() => controller.abort(), timeoutMs);
                try {
                    const response = await fetch(url, {
                        method: 'POST', credentials: 'same-origin',
                        headers: {
                            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                            'Faces-Request': 'partial/ajax',
                            'X-Requested-With': 'XMLHttpRequest'
                        },
                        body: new URLSearchParams(payload).toString(),
                        signal: controller.signal
                    });
                    return {ok: response.ok, status: response.status, text: await response.text()};
                } finally { clearTimeout(timer); }
            }""",
            {'url': url, 'payload': payload, 'timeoutMs': self.timeout_ms},
        )
        if not result.get('ok'):
            raise RuntimeError(f"VAHAN browser form request failed: HTTP {result.get('status')}.")
        return self._bounded(result['text'])
