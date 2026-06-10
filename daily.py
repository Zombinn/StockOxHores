#!/usr/bin/env python3
"""每日运行入口 — 被 Hermes cronjob 调用

python daily.py [--date 2025-06-10] [--stocks 000001.SZ ...]

正常运行（采集当天）:
  python daily.py

指定日期回补:
  python daily.py --date 2025-06-09

"""
import sys
import argparse
import logging
from datetime import date

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)


def main():
    parser = argparse.ArgumentParser(description="每日股票数据采集")
    parser.add_argument("--date", type=str, help="指定日期 YYYY-MM-DD（默认今天）")
    parser.add_argument("--stocks", nargs="+", help="指定股票列表，默认用 config.yaml")
    args = parser.parse_args()

    from pipeline import run_daily, init_project
    from db import get_stocks

    # 确保数据库就绪
    init_project()

    trade_date = date.fromisoformat(args.date) if args.date else date.today()
    stocks = args.stocks or get_stocks()

    print(f"\n{'='*50}")
    print(f"  股票数据采集  {trade_date}")
    print(f"  股票数量: {len(stocks)} 只")
    print(f"{'='*50}\n")

    stats = run_daily(stocks, trade_date=trade_date)

    print(f"\n{'='*50}")
    print(f"  采集完成!")
    print(f"  行情: {stats['price_records']} 条")
    print(f"  新闻: {stats['news_records']} 条")
    print(f"  宏观: {stats['macro_records']} 条")
    if stats['errors']:
        print(f"  错误: {len(stats['errors'])} 条")
        for err in stats['errors'][:5]:
            print(f"    ⚠ {err}")
    print(f"{'='*50}\n")

    # 输出每日汇总文字
    from db import get_conn
    conn = get_conn()
    summary = conn.execute(
        "SELECT summary FROM daily_summary WHERE trade_date=?",
        [str(trade_date)]
    ).fetchone()
    if summary:
        print(summary[0])


if __name__ == "__main__":
    main()
