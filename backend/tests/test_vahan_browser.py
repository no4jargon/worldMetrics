import unittest
from unittest.mock import Mock, patch

from app.connectors.vahan_browser import VAHANBrowserConnector
from app.connectors.vahan_skill import VAHAN_DASHBOARD_URL


DASHBOARD = '''<form id="masterLayout_formlogin" action="/vahan4dashboard/">
 <input name="javax.faces.ViewState" value="state1">
 <select id="viewType_input"><option value="R">Tabular Summary</option></select>
</form>'''
REPORT = '''<form id="masterLayout_formlogin" action="/vahan4dashboard/vahan/view/reportview.xhtml">
 <input name="javax.faces.ViewState" value="state2">
 <select id="units_input"><option value="A">Actual Value</option></select>
 <button id="refresh" onclick="PrimeFaces.ab({u:&quot;combTablePnl&quot;})">Refresh</button>
</form>'''
TABLE = '''<div id="combTablePnl"><table><thead><tr><th>JAN</th></tr></thead>
 <tbody id="groupingTable_data">
 <tr><td>1</td><td>TWO WHEELER(NT)</td><td>1,000</td></tr>
 <tr><td>2</td><td>LIGHT MOTOR VEHICLE</td><td>100</td></tr>
 </tbody></table></div>'''


def response(text, *, ok=True, status=200):
    return {'ok': ok, 'status': status, 'text': text}


class VAHANBrowserTests(unittest.TestCase):
    def test_ordinary_browser_transport_reuses_existing_filters_and_table_parser(self):
        page = Mock()
        page.goto.return_value = Mock(ok=True, status=200)
        page.content.side_effect = [DASHBOARD, REPORT]
        page.evaluate.side_effect = [
            response('<partial-response><redirect url="/vahan4dashboard/vahan/view/reportview.xhtml"/></partial-response>'),
            response('<partial-response/>'), response('<partial-response/>'), response('<partial-response/>'),
            response(f'<partial-response><update id="combTablePnl"><![CDATA[{TABLE}]]></update></partial-response>'),
        ]
        with patch('playwright.sync_api.sync_playwright') as factory:
            browser = factory.return_value.__enter__.return_value.chromium.launch.return_value
            browser.new_page.return_value = page
            connector = VAHANBrowserConnector(live=True, years=[2025])
            raw = connector.fetch()
        self.assertEqual('success', raw.status)
        self.assertEqual([{'month': '2025-01', 'two_wheeler_sales': 1000.0, 'four_wheeler_sales': 100.0}], raw.payload['records'])
        parsed = connector.parse(raw)
        self.assertEqual(['two_wheeler_sales', 'four_wheeler_sales'], [obs.metric_code for obs in parsed])
        self.assertEqual([1000.0, 100.0], [obs.value for obs in parsed])
        self.assertEqual('domestic', parsed[0].segment)
        self.assertIsNone(connector._page)
        browser.close.assert_called_once()
        self.assertEqual('domcontentloaded', page.goto.call_args.kwargs['wait_until'])
        self.assertEqual('form#masterLayout_formlogin', page.wait_for_selector.call_args.args[0])
        # The same existing JSF filters are sent through Chromium, not inferred.
        last_payload = page.evaluate.call_args.args[1]['payload']
        self.assertEqual('Vehicle Category', last_payload['yaxisVar_input'])
        self.assertEqual('Month Wise', last_payload['xaxisVar_input'])
        self.assertEqual('2025', last_payload['selectedYear_input'])
        self.assertEqual('A', last_payload['units_input'])

    def test_form_post_keeps_existing_viewstate_and_partial_ajax_fields(self):
        connector = VAHANBrowserConnector(live=True)
        connector._page = Mock()
        connector._page.evaluate.return_value = response('<partial-response/>')
        result = connector._post_ajax(None, VAHAN_DASHBOARD_URL, {'javax.faces.ViewState': 'state42'},
                                      'refresh', 'masterLayout_formlogin', 'combTablePnl', command_field=True)
        self.assertEqual('<partial-response/>', result)
        script, argument = connector._page.evaluate.call_args.args
        self.assertIn("credentials: 'same-origin'", script)
        self.assertNotIn('User-Agent', script)
        self.assertEqual('state42', argument['payload']['javax.faces.ViewState'])
        self.assertEqual('true', argument['payload']['javax.faces.partial.ajax'])
        self.assertEqual('refresh', argument['payload']['refresh'])

    def test_public_portal_errors_are_reported_without_challenge_workarounds(self):
        connector = VAHANBrowserConnector(live=True)
        connector._page = Mock()
        connector._page.goto.return_value = Mock(ok=False, status=403)
        with self.assertRaisesRegex(RuntimeError, 'HTTP 403'):
            connector._read_text(None, VAHAN_DASHBOARD_URL)
        connector._page.content.assert_not_called()
        connector._page.evaluate.return_value = response('Forbidden', ok=False, status=403)
        with self.assertRaisesRegex(RuntimeError, 'HTTP 403'):
            connector._post_ajax(None, VAHAN_DASHBOARD_URL, {}, 'refresh', 'form', 'table')

    def test_browser_is_closed_when_navigation_or_parsing_fails(self):
        with patch('playwright.sync_api.sync_playwright') as factory:
            browser = factory.return_value.__enter__.return_value.chromium.launch.return_value
            browser.new_page.return_value.goto.side_effect = RuntimeError('Portal unavailable')
            connector = VAHANBrowserConnector(live=True, years=[2025])
            with self.assertRaisesRegex(RuntimeError, 'Portal unavailable'):
                connector.fetch()
            browser.close.assert_called_once()
            self.assertIsNone(connector._page)


if __name__ == '__main__':
    unittest.main()
