# NAVER Market Data Layer

`naver_market.py` is an independent, read-only collector for validated NAVER domestic-market APIs. It does not use or modify the existing Universe, quote, technical, state, or legacy compatibility outputs.

## Supported datasets

- Rankings: seven top-20 KRX/ALL snapshots.
- Industries: the full category list, stopping at the first empty PAGE_INDEX page.
- Investor flow: `FOREIGNER` and `ORGANIZATION`, `DAY` period, top-20 buy and sell lists.

Theme collection is **DISABLED_PENDING_RESEARCH_GATE**. The observed theme-list duplicate means production code must not call a theme endpoint yet.

## Outputs

- `data/market/manifest.json`
- `data/market/rankings.json`
- `data/market/industries.json`
- `data/market/investor-flow.json`

Every root records `generatedAt` (collector time in KST), `source: "NAVER"`, and `status`. `generatedAt` is not a source market timestamp. NAVER fields such as `thistime`, `tradableStatusUpdatedAt`, `bizdateFrom`, `bizdateTo`, and `toRankingAt` are preserved in `source` without timezone interpretation.

## Normalization and preservation

Normalized rows use `code`/`name` and parsed numeric values without unit conversion. Each row also retains the complete NAVER source row in `source`. Investor `accTradeVolume` and `accTradeAmount` retain their original names: buy/sell direction is represented only by the parent container, because field semantics remain partial.

Industry identifiers use NAVER `no`, never list position. Industry and member lists use `startIdx` as a PAGE_INDEX and terminate on an empty array. Ranking `startIdx` is an offset. Investor `startIdx` is a PAGE_INDEX; its full end condition is not currently available because the endpoint returns no total metadata.

## CLI

```bash
python3 naver_market.py rankings
python3 naver_market.py industries
python3 naver_market.py investors
python3 naver_market.py industry-members 297
python3 naver_market.py industry-info 297
python3 naver_market.py all
python3 naver_market.py all --no-write
```

`all` calls rankings, the industry list, and DAY investor flow only. It never collects all industry members and never calls theme APIs. Failed current runs write `ERROR`/`PARTIAL` results atomically rather than presenting a stale successful file as current.

## External Integration Research Gate

Before adding an external service or endpoint: research existing public implementations and official material, compare candidates, make small current read-only validation requests, establish the response/pagination contract, then design and implement. A newly proposed theme collector must restart this gate.
