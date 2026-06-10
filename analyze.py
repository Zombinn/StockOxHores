#!/usr/bin/env python3
"""StockOxHores 分析工具

用法:
  python analyze.py sentiment                     # 回填所有新闻情感分
  python analyze.py sentiment --limit 100         # 只评前100条
  python analyze.py day 2026-06-09               # 某天关联分析
  python analyze.py stock 300750.SZ --days 60     # 某只股票关联时间线
  python analyze.py summary --days 7              # 情感总览
"""
import sys
import json
import argparse
import logging
from datetime import date

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)


def main():
    parser = argparse.ArgumentParser(description="StockOxHores 分析工具")
    sub = parser.add_subparsers(dest="command", required=True)

    p_sent = sub.add_parser("sentiment", help="回填新闻情感评分")
    p_sent.add_argument("--limit", type=int, help="最多处理N条")

    p_day = sub.add_parser("day", help="某天关联分析")
    p_day.add_argument("date", type=str, help="日期 YYYY-MM-DD")
    p_day.add_argument("--json", action="store_true", help="JSON 格式输出")

    p_stock = sub.add_parser("stock", help="某只股票关联时间线")
    p_stock.add_argument("code", type=str)
    p_stock.add_argument("--days", type=int, default=30)
    p_stock.add_argument("--json", action="store_true", help="JSON 格式输出")

    p_sum = sub.add_parser("summary", help="情感总览")
    p_sum.add_argument("--days", type=int, default=7)

    args = parser.parse_args()

    if args.command == "sentiment":
        from analysis.sentiment import batch_score
        count = batch_score(limit=args.limit)
        print(f"\n✅ 已评分 {count} 条新闻")

    elif args.command == "day":
        from analysis.correlation import day_correlation
        results = day_correlation(args.date)
        if args.json:
            print(json.dumps(results, ensure_ascii=False, indent=2))
        else:
            print(f"\n📊 {args.date} 关联分析")
            print(f"{'='*50}")
            for r in results:
                arrow = "🟢" if (r["change_pct"] or 0) >= 0 else "🔴"
                sent_icon = {2: "👍", 1: "👍", 0: "➖", -1: "👎", -2: "👎"}
                avg_s = r["avg_sentiment"]
                icon = sent_icon.get(1 if avg_s > 0.3 else -1 if avg_s < -0.3 else 0, "➖")
                print(f"\n{arrow} {r['ts_code']:12s}  {r['change_pct']:+.2f}%  {icon} {avg_s:+.2f}  ({r['news_count']}篇)")
                for n in r["news"][:3]:
                    print(f"     {n['source']} {n['title'][:50]}")

    elif args.command == "stock":
        from analysis.correlation import stock_correlation
        results = stock_correlation(args.code, days=args.days)
        if args.json:
            print(json.dumps(results, ensure_ascii=False, indent=2))
        else:
            print(f"\n📈 {args.code} 近{args.days}天关联时间线")
            print(f"{'='*50}")
            for r in results[:20]:
                arrow = "🟢" if (r["change_pct"] or 0) >= 0 else "🔴"
                print(f"\n{r['trade_date']}  {arrow} {r['change_pct']:+.2f}%  sentiment={r['avg_sentiment']:+.2f}  news={r['news_count']}")
                for n in r["news"][:2]:
                    print(f"   {n['source']} {n['title'][:40]}")

    elif args.command == "summary":
        from analysis.correlation import sentiment_summary
        s = sentiment_summary(days=args.days)
        print(f"\n📊 情感总览 ({s['period']})")
        print(f"{'='*40}")
        print(f"  分析总数: {s['total_analyzed']} 条")
        print(f"  正面: {s['positive']} (非常正面: {s['very_positive']})")
        print(f"  负面: {s['negative']} (非常负面: {s['very_negative']})")
        print(f"  中性: {s['neutral']}")
        if s['total_analyzed'] > 0:
            ratio = s['positive'] / s['negative'] if s['negative'] > 0 else float('inf')
            print(f"  正负比: {ratio:.2f}")


if __name__ == "__main__":
    main()
