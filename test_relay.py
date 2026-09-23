import unittest
import json
from datetime import datetime
from unittest.mock import patch
import relay


class RelayTests(unittest.TestCase):
    def test_universe_legacy_and_validation(self):
        universe = relay.load_universe()
        self.assertEqual(len(universe['stocks']), 33)
        self.assertEqual(len(relay.universe_codes(universe)), 33)
        self.assertEqual(universe['watchlists']['legacy33'][-1], '051600')
        broken = json.loads(json.dumps(universe))
        broken['leaders']['sector']['원전'] = ['999999']
        with self.assertRaises(ValueError):
            relay.validate_universe(broken)

    def test_lite_payload_is_minimal(self):
        payload = {'generatedAt': 'now', 'expectedCount': 1, 'count': 1, 'freshCount': 1,
                   'missingCodes': [], 'status': 'ok', 'fresh': True,
                   'datas': [{'itemCode': '051600', 'stockName': '한전KPS', 'closePrice': 1,
                              'fluctuationsRatio': 0, 'accumulatedTradingVolume': 2,
                              'sourceTime': 'now', 'marketStatus': 'CLOSE', 'delayTime': 0,
                              'fresh': True, 'status': 'ok', 'unwanted': 'x'}]}
        result = relay.lite_payload(payload)
        self.assertEqual(set(result['datas'][0]), set(relay.LITE_FIELDS))
        self.assertNotIn('unwanted', result['datas'][0])

    def test_legacy_fresh_count_uses_legacy_codes_only(self):
        rows = {'000001': {'fresh': True, 'sourceTime': 'a'},
                '000002': {'fresh': True, 'sourceTime': 'b'}}
        result = relay.quote_payload(rows, ['000001'], 1, [], datetime.now(relay.KST))
        self.assertEqual(result['freshCount'], 1)
    def test_freshness(self):
        current = datetime(2026, 9, 23, 10, 40, tzinfo=relay.KST)
        for minute, expected in [(35, True), (29, False), (42, False)]:
            traded = current.replace(minute=minute)
            self.assertEqual(relay.quote_freshness(traded, current, 'OPEN', 0)[0], expected)
        self.assertFalse(relay.quote_freshness(current, current, 'OPEN', 20)[0])
        self.assertFalse(relay.quote_freshness(current, current, 'OPEN', None)[0])
        monday = datetime(2026, 9, 21, 8, 35, tzinfo=relay.KST)
        friday = datetime(2026, 9, 18, 15, 30, tzinfo=relay.KST)
        self.assertTrue(relay.quote_freshness(friday, monday, 'CLOSE', 0)[0])
        self.assertFalse(relay.quote_freshness(friday, monday, 'OPEN', 0)[0])

    def test_numeric_units_and_direction(self):
        current = datetime(2026, 9, 23, 10, 35, tzinfo=relay.KST)
        row = dict(itemCode='005930', stockName='삼성전자', localTradedAt=current.isoformat(),
                   marketStatus='OPEN', stockExchangeType={'delayTime': 0},
                   closePrice='100,000', compareToPreviousClosePrice='1,000',
                   compareToPreviousPrice={'code': '5'}, fluctuationsRatio='-1.0',
                   openPrice='101,000', highPrice='102,000', lowPrice='99,000',
                   accumulatedTradingVolume='1,234', accumulatedTradingValue='1조 2,345억',
                   accumulatedTradingValueRaw='1234500000000')
        result = relay.normalize_quote(row, current)
        self.assertEqual(result['compareToPreviousClosePrice'], -1000)
        self.assertEqual(result['accumulatedTradingValue'], 1234500000000)
        self.assertEqual(result['accumulatedTradingVolume'], 1234)
        self.assertTrue(result['fresh'])

    def test_sector_then_individual_fallback(self):
        calls = []
        def fetch(url):
            codes = url.rsplit('/', 1)[-1].split(',')
            calls.append(codes)
            if len(codes) > 1:
                raise ValueError('batch rejected')
            return {'datas': [{'itemCode': codes[0]}]}
        def normalize(row, current):
            return dict(itemCode=row['itemCode'], fresh=True, sourceTime=current.isoformat())
        with patch.object(relay, 'fetch', fetch), patch.object(relay, 'normalize_quote', normalize), patch.object(relay, 'save') as save:
            result = relay.collect_quotes()
        self.assertEqual(result['count'], 33)
        self.assertEqual(len(set(r['itemCode'] for r in result['datas'])), 33)
        self.assertEqual(len(calls[0]), 33)
        self.assertEqual(len(calls), 1 + 11 + 33)
        written = {call.args[0]: call.args[1] for call in save.call_args_list}
        self.assertEqual(written['data/core33-lite.json']['count'], 33)
        self.assertEqual(written['data/core33-lite.json']['datas'][-1]['itemCode'], '051600')
        self.assertEqual(set(written['data/core33-lite.json']['datas'][0]), set(relay.LITE_FIELDS))
        self.assertIn('data/quotes.json', written)
        self.assertIn('data/quotes-lite.json', written)
        self.assertIn('data/groups/원전.json', written)

    def test_failure_replaces_old_data_with_error(self):
        with patch.object(relay, 'fetch', side_effect=ValueError('upstream unavailable')), patch.object(relay, 'save') as save:
            result = relay.collect_daily('005930')
        self.assertEqual(result['status'], 'error')
        payload = save.call_args.args[1]
        self.assertFalse(payload['fresh'])
        self.assertEqual(payload['datas'], [])
        self.assertTrue(payload['errors'])


if __name__ == '__main__':
    unittest.main()
