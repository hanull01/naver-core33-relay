# NAVER market probe

Manual, low-volume endpoint inspection only; it does not feed production data.

## Role boundary

- Production collector: `naver_market.py`
- Research and debugging fallbacks: `naver_market_probe.py`, `naver_browser_probe.py`

The probe tools are retained for API contract changes, UI regressions, and production-incident diagnosis. They are not called by the production collector. Their runtime samples belong only in ignored `probe_output/`.

```bash
python3 naver_market_probe.py --list
python3 naver_market_probe.py rankings
python3 naver_market_probe.py industries
python3 naver_market_probe.py themes
python3 naver_market_probe.py investors
```

Each command makes at most two sequential public requests and writes samples only under `probe_output/`.

## External Integration Research Gate

새 외부 서비스·API·크롤링 기능은 구현 전에 다음 순서를 따른다.

1. 기존 공개 구현과 공식 자료를 조사한다.
2. 최근 구현의 제약과 endpoint 후보를 비교한다.
3. 후보만 현재 환경에서 소량의 읽기 전용 요청으로 검증한다.
4. 응답 구조·페이징·필수 데이터가 확인된 뒤 설계를 결정한다.
5. 마지막에만 production 구현을 시작한다.

이 절차는 endpoint 추측과 불필요한 브라우저 역공학을 줄이고, 검증되지 않은 외부 계약이 운영 수집기에 들어가는 일을 막기 위한 것이다.

## Validated API Contract

검증일: 2026-09-23. 아래 내용은 비로그인 공개 GET의 소량 표본 계약이며, production 수집기는 아직 구현하지 않았다.

| 영역 | Endpoint / 필수 파라미터 | 응답·식별자 | 페이지 처리 | 기준시각 |
| --- | --- | --- | --- | --- |
| Ranking | `/api/domestic/market/stock/default`; `tradeType`, `marketType`, `orderType`, `startIdx`, `pageSize` | 배열, `itemcode`가 종목 식별자 | `startIdx` offset 표본 확인; total metadata 없음 | 명시적 전체 기준시각 없음 (`tradableStatusUpdatedAt`은 행별 상태 시각) |
| Industry list | `/api/domestic/market/upjong/list`; `startIdx`, `pageSize`, `sortType` | 배열, `no`가 category 식별자 | PAGE_INDEX. 20/20/20/19행 뒤 빈 배열 확인 | `thistime` 있음; timezone/정확한 의미는 미확정 |
| Industry member | `/api/domestic/market/upjong/{no}/stocklist`; `marketType`, `orderType`, `startIdx`, `pageSize` | 배열, `itemcode` | 대표 category에서 PAGE_INDEX 및 빈 배열 종료 확인 | 행별 `tradableStatusUpdatedAt` |
| Theme list | `/api/domestic/market/theme/list`; `startIdx`, `pageSize`, `sortType` | 배열, `no`가 category 식별자 | PAGE_INDEX로 보이나 page 6에서 중복 `no` 감지; 전체/종료 계약 미확정 | `thistime` 있음; timezone/정확한 의미는 미확정 |
| Theme member | `/api/domestic/market/theme/{no}/stocklist`; 동일 | 배열, `itemcode` | 업종 member와 동일 endpoint 형태이나 마지막 페이지는 미검증 | 행별 `tradableStatusUpdatedAt` |
| Investor | `/api/domestic/market/trend/trendForeignOrg`; `investorType`, `tradeType`, `marketType`, `periodType`, `startIdx`, `pageSize` | `sections.buyRankList`, `sections.sellRankList`; `itemcode` | PAGE_INDEX 표본 확인. total metadata 없음 | `bizdateFrom`, `bizdateTo`, `toRankingAt`(일부 null) |

N2 원본 보존 후보 필드:

- Ranking/member: `itemcode`, `itemname`, `nowPrice`, `prevChangePrice`, `prevChangeRate`, `tradeVolume`, `tradeAmount`, `marketSum`, `week52HighPrice`, `quantDiff`.
- Industry/theme list: `no`, `name`, `totalCnt`, `riseCnt`, `fallCnt`, `changeRate`, `totalAccQuant`, `totalAccAmount`, `totalMarketSum`, `leadingItem`.
- Investor: `itemcode`, `itemname`, `bizdateFrom`, `bizdateTo`, `accTradeVolume`, `accTradeAmount`, `dailyTradeVolume`, `nowPrice`, `prevChangePrice`, `prevChangeRate`, `type`, `estimated`, `toRankingAt`.

`no`와 `itemcode`는 목록 순위가 아니라 응답이 제공하는 식별자로 저장한다. 테마 목록은 중복이 관찰됐으므로 이후 구현 전에 순위가 아닌 `no` 기준으로 dedupe하고, 종료 계약을 다시 검증해야 한다.
