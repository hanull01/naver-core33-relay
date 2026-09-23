"""Public NAVER KRX quotes and daily candles. No credentials required."""
import argparse
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, time as dtime
from pathlib import Path
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

KST = ZoneInfo('Asia/Seoul')
ROOT = Path(__file__).resolve().parent
SECTORS = [
    ('반도체', '005930 000660 042700'),
    ('반도체 소부장', '240810 036930 058470'),
    ('AI·IT하드웨어', '009150 007660 353200'),
    ('전력기기', '267260 010120 298040'),
    ('조선', '329180 042660 010140'),
    ('방산', '012450 064350 079550'),
    ('자동차', '005380 000270 012330'),
    ('금융', '105560 086790 055550'),
    ('바이오', '207940 068270 196170'),
    ('2차전지', '373220 006400 096770'),
    ('원전', '034020 052690 051600'),
]
CODES = [code for _, group in SECTORS for code in group.split()]
SECTOR = {code: sector for sector, group in SECTORS for code in group.split()}
QUOTE_URL = 'https://polling.finance.naver.com/api/realtime/domestic/stock/'
DAILY_URL = 'https://api.stock.naver.com/chart/domestic/item/{code}/day'


def now():
    return datetime.now(KST)


def fetch(url):
    for attempt in range(3):
        try:
            req = Request(url, headers={'User-Agent': 'Mozilla/5.0',
                                        'Accept': 'application/json',
                                        'Referer': 'https://stock.naver.com/'})
            with urlopen(req, timeout=20) as response:
                return json.load(response)
        except Exception:
            if attempt == 2:
                raise
            time.sleep(attempt + 1)


def save(path, payload):
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix('.tmp')
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2,
                               allow_nan=False) + '\n', encoding='utf-8')
    temp.replace(target)


def number(value):
    if value is None or isinstance(value, bool):
        raise ValueError('missing numeric field')
    value = str(value).replace(',', '').strip()
    if not re.fullmatch(r'[+-]?\d+(?:\.\d+)?', value):
        raise ValueError('invalid numeric field')
    result = float(value)
    return int(result) if result.is_integer() else result


def previous_weekday(day):
    day -= timedelta(days=1)
    while day.weekday() > 4:
        day -= timedelta(days=1)
    return day


def quote_freshness(traded, current, market, delay):
    age = (current - traded).total_seconds()
    if age < -60:
        return False, 'future_source_time'
    if delay != 0:
        return False, 'delayed_or_unknown_delay'
    if current.weekday() > 4:
        return False, 'non_weekday'
    if current.time() < dtime(9):
        valid = (traded.date() == previous_weekday(current.date())
                 and traded.time() >= dtime(15, 30) and market == 'CLOSE')
        return valid, 'previous_close' if valid else 'stale_or_unconfirmed_close'
    if current.time() < dtime(15, 30):
        valid = traded.date() == current.date() and -60 <= age <= 600 and market == 'OPEN'
        return valid, 'live' if valid else 'stale_or_not_open'
    valid = (traded.date() == current.date() and traded.time() >= dtime(15, 30)
             and market == 'CLOSE')
    return valid, 'closing_snapshot' if valid else 'stale_or_unconfirmed_close'


def normalize_quote(row, current):
    code = row['itemCode']
    traded = datetime.fromisoformat(row['localTradedAt'])
    if traded.tzinfo is None:
        traded = traded.replace(tzinfo=KST)
    traded = traded.astimezone(KST)
    result = {'itemCode': code, 'stockName': row['stockName'], 'sector': SECTOR[code]}
    fields = ['closePrice', 'compareToPreviousClosePrice', 'fluctuationsRatio',
              'openPrice', 'highPrice', 'lowPrice', 'accumulatedTradingVolume',
              'accumulatedTradingValue']
    for field in fields:
        result[field] = number(row.get(field + 'Raw', row.get(field)))
    # NAVER sometimes gives an unsigned change plus a separate direction enum.
    direction = str(row.get('compareToPreviousPrice', {}).get('code', ''))
    if direction in ('4', '5') or result['fluctuationsRatio'] < 0:
        result['compareToPreviousClosePrice'] = -abs(result['compareToPreviousClosePrice'])
    if result['closePrice'] <= 0 or result['accumulatedTradingVolume'] < 0:
        raise ValueError('invalid price or volume')
    delay = row.get('stockExchangeType', {}).get('delayTime')
    delay = number(delay) if delay is not None else None
    fresh, reason = quote_freshness(traded, current, row.get('marketStatus'), delay)
    result.update(source='NAVER_KRX', sourceTime=traded.isoformat(),
                  localTradedAt=traded.isoformat(), marketStatus=row.get('marketStatus'),
                  delayTime=delay, stockExchangeType={'delayTime': delay},
                  ageSeconds=round((current - traded).total_seconds()), fresh=fresh,
                  status='ok' if fresh else 'stale', freshnessReason=reason)
    return result


def collect_quotes():
    current = now()
    rows, errors = {}, []

    def batch(codes, stage):
        try:
            payload = fetch(QUOTE_URL + ','.join(codes))
            if not isinstance(payload.get('datas'), list):
                raise ValueError('missing datas array')
            for row in payload['datas']:
                code = row.get('itemCode')
                if code not in codes:
                    continue
                try:
                    rows[code] = normalize_quote(row, now())
                except Exception as exc:
                    errors.append({'stage': stage, 'code': code, 'error': str(exc)})
        except Exception as exc:
            errors.append({'stage': stage, 'codes': codes, 'error': str(exc)})

    batch(CODES, 'all_batch')
    for _, group in SECTORS:
        missing = [c for c in group.split() if c not in rows]
        if missing:
            batch(missing, 'sector_batch')
    for code in CODES:
        if code not in rows:
            batch([code], 'individual')
    missing = [c for c in CODES if c not in rows]
    for code in missing:
        errors.append({'code': code, 'error': 'no_valid_quote'})
    fresh_count = sum(row['fresh'] for row in rows.values())
    status = 'error' if not rows else 'partial' if missing else 'ok' if fresh_count == 33 else 'stale'
    times = [row['sourceTime'] for row in rows.values()]
    payload = {'schemaVersion': 1, 'generatedAt': now().isoformat(),
               'collectionStartedAt': current.isoformat(), 'source': 'NAVER_KRX',
               'count': len(rows), 'expectedCount': 33, 'freshCount': fresh_count,
               'status': status, 'fresh': status == 'ok', 'errors': errors,
               'missingCodes': missing, 'sourceTime': min(times) if times else None,
               'sourceTimeLatest': max(times) if times else None,
               'freshnessPolicy': '600 seconds intraday; conservative weekday close check; consumer must verify KRX trading calendar and final close',
               'datas': [rows[c] for c in CODES if c in rows]}
    save('data/core33.json', payload)
    print(json.dumps({k: payload[k] for k in ('count', 'freshCount', 'status', 'sourceTime')}))
    return payload


def collect_daily(code):
    current = now()
    start = (current - timedelta(days=550)).strftime('%Y%m%d')
    url = DAILY_URL.format(code=code) + f'?startDateTime={start}&endDateTime={current:%Y%m%d}'
    payload = {'schemaVersion': 1, 'itemCode': code, 'generatedAt': current.isoformat(),
               'source': 'NAVER_KRX', 'sourceUrl': url, 'status': 'error',
               'fresh': False, 'errors': [], 'count': 0, 'completedCount': 0, 'datas': []}
    try:
        response = fetch(url)
        if not isinstance(response, list):
            raise ValueError('daily endpoint did not return array')
        bars = {}
        for row in response:
            date = datetime.strptime(row['localDate'], '%Y%m%d').date()
            if date > current.date():
                raise ValueError('future candle date')
            bar = {'date': date.isoformat()}
            for out, field in [('open', 'openPrice'), ('high', 'highPrice'),
                               ('low', 'lowPrice'), ('close', 'closePrice'),
                               ('volume', 'accumulatedTradingVolume')]:
                bar[out] = number(row[field])
            bar['noTrading'] = (bar['open'] == bar['high'] == bar['low'] == bar['volume'] == 0
                                and bar['close'] > 0)
            # Adjusted historical prices can differ by one KRW from rounding.
            bar['roundingMismatch'] = not bar['noTrading'] and (
                bar['low'] > min(bar['open'], bar['close']) or
                max(bar['open'], bar['close']) > bar['high'])
            if not bar['noTrading'] and (not (0 < bar['low'] <= bar['high']
                    and bar['low'] - 1 <= min(bar['open'], bar['close'])
                    <= max(bar['open'], bar['close']) <= bar['high'] + 1) or bar['volume'] < 0):
                raise ValueError('invalid OHLCV')
            # Conservatively keep today's candle provisional until 16:30 KST.
            bar['complete'] = date < current.date() or current.time() >= dtime(16, 30)
            bars[bar['date']] = bar
        ordered = [bars[d] for d in sorted(bars)]
        completed = [b for b in ordered if b['complete']]
        latest = completed[-1]['date'] if completed else None
        expected = current.date() if current.weekday() < 5 and current.time() >= dtime(16, 30) else previous_weekday(current.date())
        fresh = latest == expected.isoformat()
        status = 'insufficient' if len(completed) < 60 else 'ok' if fresh else 'stale'
        payload.update(count=len(ordered), completedCount=len(completed), datas=ordered,
                       sourceTime=latest, latestDate=ordered[-1]['date'] if ordered else None,
                       fresh=fresh and len(completed) >= 60, status=status,
                       freshnessPolicy='latest completed date must equal conservative expected weekday; consumer must verify actual KRX calendar')
        if status != 'ok':
            payload['errors'].append({'error': status, 'expectedCompletedDate': expected.isoformat()})
    except Exception as exc:
        payload['errors'].append({'error': str(exc)})
    save(f'data/daily/{code}.json', payload)
    return {k: payload[k] for k in ('itemCode', 'status', 'completedCount')}


def collect_all_daily():
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(collect_daily, CODES))
    save('data/daily-status.json', {'generatedAt': now().isoformat(), 'results': results})
    print(json.dumps(results, ensure_ascii=False))
    return results


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['quotes', 'daily', 'all'], default='all', nargs='?')
    args = parser.parse_args()
    failed = False
    if args.mode in ('daily', 'all'):
        failed |= any(r['status'] in ('error', 'insufficient') for r in collect_all_daily())
    if args.mode in ('quotes', 'all'):
        failed |= collect_quotes()['count'] != 33
    raise SystemExit(1 if failed else 0)
