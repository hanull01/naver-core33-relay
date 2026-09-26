#!/usr/bin/env python3

import argparse
import json
import statistics
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path


REPORT_DIR = Path("data/research/reports")

TOPIC_RULES = {
    "HBM": ["HBM", "hbm"],
    "파운드리": ["파운드리", "foundry"],
    "DRAM": ["DRAM", "dram", "디램"],
    "NAND": ["NAND", "nand", "낸드"],
    "메모리": ["메모리", "memory"],
    "메모리 가격": [
        "메모리 가격",
        "DRAM 가격",
        "디램 가격",
        "NAND 가격",
        "낸드 가격",
    ],
    "AI": ["AI", "인공지능"],
    "CAPEX/생산능력": [
        "CAPEX",
        "capex",
        "생산능력",
        "생산 능력",
        "증설",
        "투자 확대",
    ],
    "수율": ["수율", "yield"],
    "재고": ["재고", "inventory"],
    "수요": ["수요", "demand"],
    "환율": ["환율", "원달러", "원/달러"],
    "중국": ["중국", "China", "china"],
    "주주환원": ["주주환원", "배당", "자사주"],
    "원가": ["원가", "cost"],
    "사이클": ["사이클", "cycle"],
}


def parse_args():
    parser = argparse.ArgumentParser(
        description="NAVER stock research intelligence analyzer"
    )

    parser.add_argument(
        "--code",
        required=True,
        help="종목코드 (예: 005930)",
    )

    parser.add_argument(
        "--name",
        default=None,
        help="종목명",
    )

    parser.add_argument(
        "--as-of",
        default=date.today().isoformat(),
        help="분석 기준일 YYYY-MM-DD",
    )

    parser.add_argument(
        "--recent-days",
        type=int,
        default=30,
        help="최근 비교 구간 일수",
    )

    parser.add_argument(
        "--output",
        default=None,
        help="결과 JSON 저장 경로",
    )

    return parser.parse_args()


def load_reports(code):
    reports = []

    for path in sorted(REPORT_DIR.glob("*.json")):
        with path.open("r", encoding="utf-8") as f:
            obj = json.load(f)

        for report in obj.get("reports", []):
            if report.get("itemCode") == code:
                reports.append(report)

    reports.sort(
        key=lambda x: (
            x.get("writeDate", ""),
            str(x.get("nid", "")),
        )
    )

    return reports


def report_date(report):
    return date.fromisoformat(report["writeDate"])


def target_values(rows):
    return [
        r["goalPrice"]
        for r in rows
        if isinstance(r.get("goalPrice"), (int, float))
        and r["goalPrice"] > 0
    ]


def target_stats(rows):
    values = target_values(rows)

    if not values:
        return {}

    return {
        "count": len(values),
        "min": min(values),
        "max": max(values),
        "mean": round(statistics.mean(values)),
        "median": round(statistics.median(values)),
        "stdev": (
            round(statistics.pstdev(values))
            if len(values) > 1
            else 0
        ),
        "range": max(values) - min(values),
    }


def earnings_counts(rows):
    return dict(
        Counter(
            (r.get("analysis") or {}).get(
                "earningsTextDirection",
                "UNKNOWN",
            )
            for r in rows
        )
    )


def text_signal(rows):
    positive = 0
    negative = 0

    for report in rows:
        balance = (
            (report.get("analysis") or {}).get(
                "textSignalBalance"
            )
            or {}
        )

        positive += int(balance.get("positive") or 0)
        negative += int(balance.get("negative") or 0)

    net = positive - negative

    return {
        "positive": positive,
        "negative": negative,
        "net": net,
        "netPerReport": (
            round(net / len(rows), 3)
            if rows
            else 0
        ),
    }


def searchable_text(report):
    parts = [
        report.get("title") or "",
    ]

    existing_topics = (
        (report.get("analysis") or {}).get("topics")
        or {}
    )

    parts.extend(existing_topics.keys())

    return " ".join(parts)


def extracted_topics(report):
    text = searchable_text(report)
    found = Counter()

    for topic, keywords in TOPIC_RULES.items():
        for keyword in keywords:
            count = text.count(keyword)

            if count:
                found[topic] += count

    return found


def topic_stats(rows):
    total = Counter()

    for report in rows:
        total.update(extracted_topics(report))

    n = len(rows)

    return {
        topic: {
            "count": count,
            "perReport": (
                round(count / n, 3)
                if n
                else 0
            ),
        }
        for topic, count in total.most_common()
    }


def period_summary(rows):
    brokers = {
        r.get("brokerName")
        for r in rows
        if r.get("brokerName")
    }

    return {
        "reportCount": len(rows),
        "brokerCount": len(brokers),
        "targetPrice": target_stats(rows),
        "earningsDirection": earnings_counts(rows),
        "textSignal": text_signal(rows),
        "topics": topic_stats(rows),
    }


def compare_topics(current_rows, previous_rows):
    current = topic_stats(current_rows)
    previous = topic_stats(previous_rows)

    topics = sorted(set(current) | set(previous))

    result = []

    for topic in topics:
        cur = current.get(
            topic,
            {"count": 0, "perReport": 0},
        )

        prev = previous.get(
            topic,
            {"count": 0, "perReport": 0},
        )

        delta = round(
            cur["perReport"] - prev["perReport"],
            3,
        )

        ratio = None

        if prev["perReport"] > 0:
            ratio = round(
                cur["perReport"] / prev["perReport"],
                2,
            )

        result.append(
            {
                "topic": topic,
                "currentCount": cur["count"],
                "currentPerReport": cur["perReport"],
                "previousCount": prev["count"],
                "previousPerReport": prev["perReport"],
                "perReportDelta": delta,
                "ratio": ratio,
            }
        )

    result.sort(
        key=lambda x: (
            x["perReportDelta"],
            x["currentPerReport"],
        ),
        reverse=True,
    )

    return result


def broker_trajectories(reports):
    grouped = defaultdict(list)

    for report in reports:
        broker = report.get("brokerName") or "UNKNOWN"
        grouped[broker].append(report)

    output = {}

    for broker, rows in sorted(grouped.items()):
        rows.sort(
            key=lambda x: (
                x.get("writeDate", ""),
                str(x.get("nid", "")),
            )
        )

        points = []

        for row in rows:
            price = row.get("goalPrice")

            if (
                isinstance(price, (int, float))
                and price > 0
            ):
                points.append(
                    {
                        "date": row["writeDate"],
                        "goalPrice": price,
                        "title": row.get("title"),
                    }
                )

        if not points:
            continue

        first_price = points[0]["goalPrice"]
        latest_price = points[-1]["goalPrice"]

        output[broker] = {
            "reportCount": len(rows),
            "targetPricePointCount": len(points),
            "firstGoalPrice": first_price,
            "latestGoalPrice": latest_price,
            "changeAmount": latest_price - first_price,
            "changePct": (
                round(
                    (
                        latest_price / first_price
                        - 1
                    )
                    * 100,
                    2,
                )
                if first_price
                else None
            ),
            "trajectory": points,
        }

    return output


def monthly_summary(reports):
    grouped = defaultdict(list)

    for report in reports:
        grouped[
            report["writeDate"][:7]
        ].append(report)

    return {
        month: period_summary(rows)
        for month, rows in sorted(grouped.items())
    }


def main():
    args = parse_args()

    as_of = date.fromisoformat(args.as_of)
    recent_start = (
        as_of - timedelta(days=args.recent_days)
    )
    previous_start = (
        recent_start
        - timedelta(days=args.recent_days)
    )

    reports = load_reports(args.code)

    if not reports:
        raise SystemExit(
            f"No research reports found for {args.code}"
        )

    recent = [
        r
        for r in reports
        if recent_start <= report_date(r) <= as_of
    ]

    previous = [
        r
        for r in reports
        if (
            previous_start
            <= report_date(r)
            < recent_start
        )
    ]

    revisions = []

    for report in reports:
        change = report.get("goalPriceChange")

        if (
            change
            and isinstance(
                change.get("amount"),
                (int, float),
            )
        ):
            revisions.append(
                {
                    "date": report["writeDate"],
                    "broker": report.get("brokerName"),
                    "from": change.get("from"),
                    "to": change.get("to"),
                    "amount": change.get("amount"),
                    "pct": change.get("pct"),
                    "title": report.get("title"),
                }
            )

    result = {
        "status": "OK",
        "version": "research-intelligence-v1",
        "asOf": as_of.isoformat(),
        "itemCode": args.code,
        "itemName": args.name,
        "reportCount": len(reports),
        "brokerCount": len(
            {
                r.get("brokerName")
                for r in reports
                if r.get("brokerName")
            }
        ),
        "dateRange": {
            "from": reports[0]["writeDate"],
            "to": reports[-1]["writeDate"],
        },

        "allPeriod": period_summary(reports),

        "recentVsPrevious": {
            "recent": {
                "from": recent_start.isoformat(),
                "to": as_of.isoformat(),
                **period_summary(recent),
            },
            "previous": {
                "from": previous_start.isoformat(),
                "to": (
                    recent_start
                    - timedelta(days=1)
                ).isoformat(),
                **period_summary(previous),
            },
            "topicAcceleration": compare_topics(
                recent,
                previous,
            ),
        },

        "goalPriceRevisions": {
            "total": len(revisions),
            "up": sum(
                1
                for x in revisions
                if x["amount"] > 0
            ),
            "down": sum(
                1
                for x in revisions
                if x["amount"] < 0
            ),
            "flat": sum(
                1
                for x in revisions
                if x["amount"] == 0
            ),
            "items": revisions,
        },

        "monthly": monthly_summary(reports),
        "brokerTrajectory": broker_trajectories(
            reports
        ),

        "methodology": {
            "rawContentStored": False,
            "topicSource": (
                "report title + stored rule-based "
                "topic keys only"
            ),
            "topicCountsAreFullTextCounts": False,
            "buySellUsedAsRecommendationScore": False,
        },
    }

    output_path = (
        Path(args.output)
        if args.output
        else Path(
            f"/tmp/research_intelligence_"
            f"{args.code}.json"
        )
    )

    with output_path.open(
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            result,
            f,
            ensure_ascii=False,
            indent=2,
        )

    print(
        json.dumps(
            {
                "status": "OK",
                "itemCode": args.code,
                "itemName": args.name,
                "reportCount": result[
                    "reportCount"
                ],
                "brokerCount": result[
                    "brokerCount"
                ],
                "dateRange": result[
                    "dateRange"
                ],
                "recentVsPrevious": result[
                    "recentVsPrevious"
                ],
                "goalPriceRevisions": {
                    "total": result[
                        "goalPriceRevisions"
                    ]["total"],
                    "up": result[
                        "goalPriceRevisions"
                    ]["up"],
                    "down": result[
                        "goalPriceRevisions"
                    ]["down"],
                    "flat": result[
                        "goalPriceRevisions"
                    ]["flat"],
                },
                "output": str(output_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
