import unittest

import daily_report


class DailyReportTests(unittest.TestCase):
    def test_quote_summary(self):
        row = {
            "price": 100,
            "changeRate": 2.5,
            "volume": 1234,
            "tradingValue": 9999,
            "sourceTime": "2026-09-26T15:30:00+09:00",
            "fresh": True,
        }
        got = daily_report.quote_summary(row)
        self.assertEqual(got["price"], 100)
        self.assertEqual(got["changeRate"], 2.5)
        self.assertEqual(got["volume"], 1234)

    def test_enabled_universe(self):
        payload = {
            "stocks": [
                {
                    "itemCode": "000001",
                    "stockName": "A",
                    "enabled": True,
                },
                {
                    "itemCode": "000002",
                    "stockName": "B",
                    "enabled": False,
                },
            ]
        }
        got = daily_report.enabled_universe(payload)
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["itemCode"], "000001")

    def test_memberships(self):
        payload = {
            "sectors": {"섹터A": ["000001"]},
            "themes": {"테마A": ["000001"]},
            "watchlists": {"관심": ["000002"]},
        }
        got = daily_report.memberships(payload)
        self.assertEqual(len(got["000001"]), 2)
        self.assertEqual(got["000002"][0]["name"], "관심")

    def test_coverage_status_complete(self):
        self.assertEqual(
            daily_report.coverage_status(
                41, 41, 41, 41, "ok", True
            ),
            "OK",
        )

    def test_coverage_status_incomplete(self):
        self.assertEqual(
            daily_report.coverage_status(41, 36, 36, 36),
            "INCOMPLETE_MARKET_COVERAGE",
        )

    def test_coverage_status_stale(self):
        self.assertEqual(
            daily_report.coverage_status(
                41, 41, 41, 41, "stale", False
            ),
            "STALE_MARKET_DATA",
        )

    def test_coverage_status_fresh(self):
        self.assertEqual(
            daily_report.coverage_status(
                41, 41, 41, 41, "ok", True
            ),
            "OK",
        )

    def test_research_index(self):
        payload = {
            "stocks": [
                {
                    "itemCode": "005930",
                    "status": "OK",
                }
            ]
        }
        got = daily_report.research_index(payload)
        self.assertEqual(got["005930"]["status"], "OK")


if __name__ == "__main__":
    unittest.main()
