#!/usr/bin/env python3
"""历史回填入口 — python backfill.py [--months 12] [--stocks 000001.SZ 600519.SH ...]"""

import sys
import argparse
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("backfill")


def main():
    parser = argparse.ArgumentParser(description="股票数据历史回填")
    parser.add_argument("--months", type=int, default=12, help="回填月数（默认12）")
    parser.add_argument("--stocks", nargs="+", help="指定股票代码列表，默认用 config.yaml")
    parser.add_argument("--single-date", help="只回填单天，格式 2025-01-01")
    parser.add_argument("--with-news", action="store_true", help="同时采集新闻（默认只跑行情）")
    args = parser.parse_args()

    from pipeline import run_backfill, run_daily
    from db import get_stocks

    if args.single_date:
        stocks = args.stocks or get_stocks()
        from datetime import date
        trade_date = date.fromisoformat(args.single_date)
        stats = run_daily(stocks, trade_date=trade_date)
        print(f"\n完成: {stats}")
        return

    # 批量回填
    stocks = args.stocks or get_stocks()
    print(f"开始回填 {len(stocks)} 只股票，近 {args.months} 个月...")
    result = run_backfill(stocks, months=args.months, with_news=args.with_news)
    print(f"\n{'='*50}")
    print(f"回填完成!")
    print(f"  范围: {result['start']} ~ {result['end']}")
    print(f"  行情: {result['price']} 条")
    print(f"  新闻: {result['news']} 条")
    print(f"  宏观: {result['macro']} 条")


if __name__ == "__main__":
    main()
