"""Fail-closed KRX equity-market trading-day check.

The KRX holiday calendar is the authority.  Weekends are closed under KRX's
published market rules; for a weekday, a KRX calendar lookup failure is never
treated as permission to collect data.
"""
import argparse
import json
import sys
import time
from datetime import date, datetime
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

KST = ZoneInfo('Asia/Seoul')
REFERER = 'https://open.krx.co.kr/contents/MKD/01/0110/01100305/MKD01100305.jsp'
OTP_URL = 'https://open.krx.co.kr/contents/COM/GenerateOTP.jspx'
CALENDAR_URL = 'https://open.krx.co.kr/contents/OPN/99/OPN99000001.jspx'
USER_AGENT = 'Mozilla/5.0 (compatible; krx-market-day-check/1.0)'


class CalendarUnavailable(RuntimeError):
    """The official KRX calendar could not be verified."""


def request_bytes(request, opener=urlopen):
    try:
        with opener(request, timeout=20) as response:
            status = getattr(response, 'status', response.getcode())
            if not 200 <= status < 300:
                raise CalendarUnavailable(f'KRX returned HTTP {status}')
            return response.read()
    except CalendarUnavailable:
        raise
    except Exception as exc:
        raise CalendarUnavailable(f'KRX request failed: {exc}') from exc


def krx_holidays(year, opener=urlopen, now=time.time):
    """Return ISO dates from KRX's official annual holiday-calendar response."""
    otp_query = urlencode({
        'bld': 'MKD/01/0110/01100305/mkd01100305_01', 'name': 'form',
        '_': str(int(now() * 1000)),
    })
    headers = {'User-Agent': USER_AGENT, 'Referer': REFERER, 'Accept': '*/*'}
    otp = request_bytes(Request(f'{OTP_URL}?{otp_query}', headers=headers), opener).decode('utf-8').strip()
    if not otp:
        raise CalendarUnavailable('KRX returned an empty calendar OTP')
    body = urlencode({
        'search_bas_yy': str(year), 'gridTp': 'KRX', 'pagePath': '/contents/MKD/01/0110/01100305/MKD01100305.jsp',
        'code': otp, 'pageFirstCall': 'Y',
    }).encode('utf-8')
    raw = request_bytes(Request(CALENDAR_URL, data=body, headers=headers), opener)
    try:
        payload = json.loads(raw.decode('utf-8'))
        rows = payload['block1']
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise CalendarUnavailable(f'invalid KRX calendar response: {exc}') from exc
    if not isinstance(rows, list) or not rows:
        raise CalendarUnavailable('KRX calendar response has an invalid holiday list')
    try:
        holidays = {row['calnd_dd_dy'] for row in rows}
        if not all(isinstance(row, dict) and isinstance(day, str) and date.fromisoformat(day).year == year
                   for row, day in ((row, row.get('calnd_dd_dy')) for row in rows)):
            raise ValueError('invalid holiday date')
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        raise CalendarUnavailable(f'KRX calendar response has an invalid holiday list: {exc}') from exc
    return holidays


def market_day(target, opener=urlopen):
    """Return (is_open, reason).  A weekday requires a verified KRX response."""
    if target.weekday() >= 5:
        return False, 'WEEKEND'
    holidays = krx_holidays(target.year, opener)
    return target.isoformat() not in holidays, 'KRX_HOLIDAY' if target.isoformat() in holidays else 'KRX_OPEN'


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--date', help='KST date to check (YYYY-MM-DD); defaults to today')
    args = parser.parse_args(argv)
    try:
        target = date.fromisoformat(args.date) if args.date else datetime.now(KST).date()
        is_open, reason = market_day(target)
    except (ValueError, CalendarUnavailable) as exc:
        print(f'KRX calendar unavailable; skipping safely: {exc}', file=sys.stderr)
        return 2
    print(f'{target.isoformat()}: {reason}')
    return 0 if is_open else 1


if __name__ == '__main__':
    raise SystemExit(main())
