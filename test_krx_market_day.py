import json
import unittest
from datetime import date

import krx_market_day as calendar


class Response:
    status = 200

    def __init__(self, body): self.body = body
    def read(self): return self.body
    def getcode(self): return self.status
    def __enter__(self): return self
    def __exit__(self, *args): return False


class CalendarTests(unittest.TestCase):
    def opener(self, request, timeout):
        if request.full_url.startswith(calendar.OTP_URL): return Response(b'otp')
        return Response(json.dumps({'block1': [{'calnd_dd_dy': '2026-03-02'}]}).encode())

    def test_krx_holiday_and_open_weekday(self):
        self.assertEqual(calendar.market_day(date(2026, 3, 2), self.opener), (False, 'KRX_HOLIDAY'))
        self.assertEqual(calendar.market_day(date(2026, 3, 3), self.opener), (True, 'KRX_OPEN'))

    def test_weekend_does_not_authorize_collection(self):
        self.assertEqual(calendar.market_day(date(2026, 3, 1), self.opener), (False, 'WEEKEND'))

    def test_invalid_official_response_fails_closed(self):
        def bad(request, timeout): return Response(b'not json')
        with self.assertRaises(calendar.CalendarUnavailable):
            calendar.market_day(date(2026, 3, 3), bad)


if __name__ == '__main__': unittest.main()
