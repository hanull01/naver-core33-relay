#!/usr/bin/env python3

import argparse
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
UNIVERSE_PATH = ROOT / "config" / "universe.json"

QUOTES_PATH = DATA / "quotes.json"
TECHNICALS_PATH = DATA / "technicals.json"
STATES_PATH = DATA / "states.json"
GROUP_STATES_PATH = DATA / "group-states.json"
RESEARCH_PATH = DATA / "research" / "intelligence" / "latest.json"


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def stock_code(row):
    return (
        row.get("itemCode")
        or row.get("code")
        or row.get("symbol")
        or row.get("stockCode")
    )


def stock_name(row):
    return (
        row.get("stockName")
        or row.get("itemName")
        or row.get("name")
        or row.get("stockNameKo")
    )


def extract_rows(payload):
    if isinstance(payload, list):
        return payload

    if not isinstance(payload, dict):
        return []

    for key in (
        "stocks",
        "rows",
        "items",
        "quotes",
        "technicals",
        "states",
        "datas",
        "data",
    ):
        value = payload.get(key)
        if isinstance(value, list):
            return value

    return []


def index_rows(payload):
    result = {}
    for row in extract_rows(payload):
        if not isinstance(row, dict):
            continue
        code = stock_code(row)
        if code:
            result[str(code)] = row
    return result


def enabled_universe(payload):
    rows = []
    for row in payload.get("stocks", []):
        if row.get("enabled"):
            rows.append(
                {
                    "itemCode": str(row["itemCode"]),
                    "stockName": row.get("stockName"),
                }
            )
    return rows


def safe_number(value):
    if isinstance(value, (int, float)):
        return value
    try:
        if value is None:
            return None
        return float(str(value).replace(",", ""))
    except Exception:
        return None


def first_number(row, keys):
    if not isinstance(row, dict):
        return None
    for key in keys:
        value = safe_number(row.get(key))
        if value is not None:
            return value
    return None


def quote_summary(row):
    if not row:
        return {
            "price": None,
            "changeRate": None,
            "volume": None,
            "tradingValue": None,
            "sourceTime": None,
            "fresh": None,
        }

    return {
        "price": first_number(
            row,
            ["price", "closePrice", "nowPrice", "close", "currentPrice"],
        ),
        "changeRate": first_number(
            row,
            ["changeRate", "fluctuationsRatio", "changePercent", "rate"],
        ),
        "volume": first_number(
            row,
            ["volume", "accumulatedTradingVolume", "tradeVolume"],
        ),
        "tradingValue": first_number(
            row,
            [
                "tradingValue",
                "accumulatedTradingValueRaw",
                "accumulatedTradingValue",
                "tradeAmount",
            ],
        ),
        "sourceTime": row.get("sourceTime") or row.get("localTradedAt"),
        "fresh": row.get("fresh"),
    }


def compact_dict(row, preferred_keys):
    if not isinstance(row, dict):
        return {}

    out = {}
    for key in preferred_keys:
        if key in row:
            out[key] = row[key]
    return out


def research_index(payload):
    result = {}
    for row in payload.get("stocks", []):
        code = row.get("itemCode")
        if code:
            result[str(code)] = row
    return result


def memberships(universe):
    result = {}

    for group_type in ("sectors", "themes", "watchlists"):
        for group_name, codes in universe.get(group_type, {}).items():
            for code in codes:
                result.setdefault(str(code), []).append(
                    {
                        "type": group_type,
                        "name": group_name,
                    }
                )

    return result


def coverage_status(enabled_count, quote_count, technical_count, state_count):
    complete = (
        quote_count >= enabled_count
        and technical_count >= enabled_count
        and state_count >= enabled_count
    )
    return "OK" if complete else "INCOMPLETE_MARKET_COVERAGE"


def build_report(as_of=None):
    universe = load_json(UNIVERSE_PATH)
    quotes = load_json(QUOTES_PATH)
    technicals = load_json(TECHNICALS_PATH)
    states = load_json(STATES_PATH)
    research = load_json(RESEARCH_PATH)

    group_states = {}
    if GROUP_STATES_PATH.exists():
        group_states = load_json(GROUP_STATES_PATH)

    quote_idx = index_rows(quotes)
    tech_idx = index_rows(technicals)
    state_idx = index_rows(states)
    research_idx = research_index(research)

    enabled = enabled_universe(universe)
    member_idx = memberships(universe)

    rows = []

    for item in enabled:
        code = item["itemCode"]

        q = quote_summary(quote_idx.get(code))
        t = tech_idx.get(code, {})
        s = state_idx.get(code, {})
        r = research_idx.get(code, {})

        rows.append(
            {
                "itemCode": code,
                "itemName": item["stockName"],
                "groups": member_idx.get(code, []),
                "market": q,
                "technical": compact_dict(
                    t,
                    [
                        "ma5",
                        "ma20",
                        "ma60",
                        "high20",
                        "high52w",
                        "high60",
                        "avgVolume20",
                        "volumeRatio20",
                    ],
                ),
                "state": compact_dict(
                    s,
                    [
                        "priceVsMA20",
                        "priceVsMA60",
                        "maAlignment",
                        "distanceMA20Pct",
                        "distanceMA60Pct",
                        "priorHigh20",
                        "priorHigh60",
                        "distancePriorHigh20Pct",
                        "distancePriorHigh60Pct",
                        "breakout20",
                        "breakout60",
                        "volumeRatio20",
                        "volumeState",
                        "pullbackState",
                    ],
                ),
                "research": {
                    "status": r.get("status"),
                    "rankingEligible": r.get("rankingEligible", False),
                    "recentReportCount": r.get("recentReportCount", 0),
                    "previousReportCount": r.get("previousReportCount", 0),
                    "recentTargetMean": r.get("recentTargetMean"),
                    "targetMeanChangePct": r.get("targetMeanChangePct"),
                    "targetDispersionChangePct": r.get(
                        "targetDispersionChangePct"
                    ),
                    "revisionUp": r.get("revisionUp", 0),
                    "revisionDown": r.get("revisionDown", 0),
                    "risingTopics": r.get("risingTopics", [])[:5],
                },
            }
        )

    market_movers = sorted(
        [
            row
            for row in rows
            if row["market"]["changeRate"] is not None
        ],
        key=lambda row: row["market"]["changeRate"],
        reverse=True,
    )

    research_active = sorted(
        [
            row
            for row in rows
            if row["research"]["rankingEligible"]
        ],
        key=lambda row: (
            row["research"]["recentReportCount"],
            abs(row["research"]["targetMeanChangePct"] or 0),
        ),
        reverse=True,
    )

    report_date = as_of or datetime.now(KST).date().isoformat()

    missing_market = [
        {
            "itemCode": item["itemCode"],
            "itemName": item["stockName"],
        }
        for item in enabled
        if (
            item["itemCode"] not in quote_idx
            or item["itemCode"] not in tech_idx
            or item["itemCode"] not in state_idx
        )
    ]

    coverage_state = coverage_status(
        len(enabled),
        len(quote_idx),
        len(tech_idx),
        len(state_idx),
    )

    return {
        "status": "OK" if coverage_state == "OK" else "DEGRADED",
        "coverageStatus": coverage_state,
        "version": "daily-market-research-report-v1",
        "asOf": report_date,
        "generatedAt": datetime.now(KST).isoformat(),
        "sources": {
            "quotes": {
                "path": "data/quotes.json",
                "generatedAt": quotes.get("generatedAt"),
                "sourceTime": quotes.get("sourceTime"),
                "status": quotes.get("status"),
            },
            "technicals": {
                "path": "data/technicals.json",
                "generatedAt": technicals.get("generatedAt"),
                "status": technicals.get("status"),
            },
            "states": {
                "path": "data/states.json",
                "generatedAt": states.get("generatedAt"),
                "status": states.get("status"),
            },
            "researchIntelligence": {
                "path": "data/research/intelligence/latest.json",
                "asOf": research.get("asOf"),
                "status": research.get("status"),
            },
        },
        "coverage": {
            "enabledStockCount": len(enabled),
            "quoteCount": len(quote_idx),
            "technicalCount": len(tech_idx),
            "stateCount": len(state_idx),
            "researchStockCount": len(research_idx),
            "missingMarketCount": len(missing_market),
            "missingMarketStocks": missing_market,
        },
        "marketSummary": {
            "topGainers": [
                {
                    "itemCode": row["itemCode"],
                    "itemName": row["itemName"],
                    "changeRate": row["market"]["changeRate"],
                    "price": row["market"]["price"],
                }
                for row in market_movers[:10]
            ],
            "topDecliners": [
                {
                    "itemCode": row["itemCode"],
                    "itemName": row["itemName"],
                    "changeRate": row["market"]["changeRate"],
                    "price": row["market"]["price"],
                }
                for row in reversed(market_movers[-10:])
            ],
        },
        "researchSummary": {
            "statusCounts": research.get("statusCounts", {}),
            "rankingEligibleCount": research.get(
                "rankingEligibleCount", 0
            ),
            "activeStocks": [
                {
                    "itemCode": row["itemCode"],
                    "itemName": row["itemName"],
                    **row["research"],
                }
                for row in research_active
            ],
        },
        "groupStates": group_states,
        "stocks": rows,
        "methodology": {
            "investmentRecommendation": False,
            "buySellScoreUsed": False,
            "researchRankingRequiresEligibleStatus": True,
            "description": (
                "Descriptive daily market and research intelligence report. "
                "Market, technical, state, group and research signals are "
                "kept separate; no automatic buy/sell recommendation is made."
            ),
        },
    }


def write_markdown(report, path):
    lines = [
        f"# 국내증시 일일 종합 리포트 - {report['asOf']}",
        "",
        f"- 생성시각: {report['generatedAt']}",
        f"- Universe: {report['coverage']['enabledStockCount']}종목",
        (
            "- 리서치 상태: "
            + ", ".join(
                f"{k} {v}"
                for k, v in report["researchSummary"][
                    "statusCounts"
                ].items()
            )
        ),
        "",
        "## 등락 상위",
        "",
    ]

    for row in report["marketSummary"]["topGainers"][:5]:
        lines.append(
            f"- {row['itemName']} ({row['itemCode']}): "
            f"{row['changeRate']:+.2f}%"
        )

    lines.extend(
        [
            "",
            "## 등락 하위",
            "",
        ]
    )

    for row in report["marketSummary"]["topDecliners"][:5]:
        lines.append(
            f"- {row['itemName']} ({row['itemCode']}): "
            f"{row['changeRate']:+.2f}%"
        )

    lines.extend(
        [
            "",
            "## 최근 리서치 표본이 충분한 종목",
            "",
        ]
    )

    for row in report["researchSummary"]["activeStocks"]:
        change = row.get("targetMeanChangePct")
        change_text = (
            f"{change:+.2f}%"
            if isinstance(change, (int, float))
            else "N/A"
        )
        topics = ", ".join(
            topic.get("topic", "")
            for topic in row.get("risingTopics", [])[:3]
        )
        lines.append(
            f"- {row['itemName']} ({row['itemCode']}): "
            f"최근 {row['recentReportCount']}건, "
            f"목표가 평균 변화 {change_text}, "
            f"주요 상승 주제 {topics or '없음'}"
        )

    lines.extend(
        [
            "",
            "## 주의",
            "",
            (
                "이 리포트는 시장 및 리서치 데이터의 기술적·서술적 요약이며 "
                "매수·매도 추천을 생성하지 않습니다."
            ),
            "",
        ]
    )

    Path(path).write_text(
        "\n".join(lines),
        encoding="utf-8",
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--as-of")
    parser.add_argument(
        "--output-dir",
        default="data/reports",
    )
    args = parser.parse_args()

    report = build_report(args.as_of)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    latest_path = out_dir / "latest.json"
    dated_json = out_dir / f"{report['asOf']}.json"
    dated_md = out_dir / f"{report['asOf']}.md"

    payload = json.dumps(
        report,
        ensure_ascii=False,
        indent=2,
    ) + "\n"

    latest_path.write_text(payload, encoding="utf-8")
    dated_json.write_text(payload, encoding="utf-8")
    write_markdown(report, dated_md)

    print(
        json.dumps(
            {
                "status": report["status"],
                "coverageStatus": report["coverageStatus"],
                "asOf": report["asOf"],
                "enabledStockCount": report["coverage"][
                    "enabledStockCount"
                ],
                "rankingEligibleCount": report[
                    "researchSummary"
                ]["rankingEligibleCount"],
                "output": str(latest_path),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
