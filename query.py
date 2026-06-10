#!/usr/bin/env python3
"""数据查询工具 — 快速查看已采集的数据

用法:
  python query.py stock 000001.SZ            # 查看个股行情
  python query.py stock 000001.SZ --days 30  # 最近30天
  python query.py news 000001.SZ             # 查看个股新闻
  python query.py news 000001.SZ --date 2025-06-01
  python query.py macro                      # 查看宏观快讯
  python query.py macro --date 2025-06-01
  python query.py stats                      # 数据统计
  python query.py top 2025-06-01             # 当日涨幅TOP
"""

import sys
import argparse
from datetime import date, timedelta
from db import get_conn


def cmd_stock(args):
    conn = get_conn()
    days = args.days or 60
    end = date.today()
    start = end - timedelta(days=days)

    rows = conn.execute(
        """SELECT trade_date, open, close, high, low, change_pct, vol, turn
           FROM stock_daily
           WHERE ts_code=? AND trade_date BETWEEN ? AND ?
           ORDER BY trade_date DESC
           LIMIT 50""",
        [args.code, str(start), str(end)]
    ).fetchall()

    if not rows:
        print(f"无数据: {args.code}")
        return

    print(f"\n{'='*60}")
    print(f"  {args.code} 近{days}天行情")
    print(f"{'='*60}")
    print(f"{'日期':<12} {'开盘':>8} {'收盘':>8} {'最高':>8} {'最低':>8} {'涨跌%':>7} {'成交量':>10}")
    print("-" * 60)
    for r in rows:
        print(f"{str(r[0]):<12} {r[1]:>8.2f} {r[2]:>8.2f} {r[3]:>8.2f} {r[4]:>8.2f} {r[5]:>7.2f} {r[6]:>10.0f}")


def cmd_news(args):
    conn = get_conn()
    if args.date:
        rows = conn.execute(
            """SELECT news_time, source, title, url
               FROM stock_news
               WHERE ts_code=? AND news_date=?
               ORDER BY news_time NULLS LAST
               LIMIT 30""",
            [args.code, args.date]
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT news_date, news_time, source, title
               FROM stock_news
               WHERE ts_code=?
               ORDER BY news_date DESC, news_time NULLS LAST
               LIMIT 30""",
            [args.code]
        ).fetchall()

    if not rows:
        print(f"无新闻: {args.code} {' at ' + args.date if args.date else ''}")
        return

    print(f"\n{'='*70}")
    print(f"  {args.code} 新闻 ({len(rows)} 条)")
    print(f"{'='*70}")
    for r in rows:
        if args.date:
            t = str(r[0])[:16] if r[0] else "???"
            print(f"  [{r[1]:<6}] {t}  {r[2][:60]}")
        else:
            print(f"  {r[0]} [{r[2]:<6}] {r[3][:60]}")


def cmd_macro(args):
    conn = get_conn()
    if args.date:
        rows = conn.execute(
            """SELECT event_time, category, importance, title
               FROM macro_events
               WHERE event_date=?
               ORDER BY importance DESC, event_time NULLS LAST
               LIMIT 50""",
            [args.date]
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT event_date, category, importance, title
               FROM macro_events
               ORDER BY event_date DESC, importance DESC
               LIMIT 30""",
        ).fetchall()

    if not rows:
        print(f"无宏观快讯")
        return

    print(f"\n{'='*70}")
    print(f"  宏观快讯 ({len(rows)} 条)")
    print(f"{'='*70}")
    for r in rows:
        if args.date:
            imp = "⭐" * r[2] if r[2] else "·"
            t = str(r[0])[:16] if r[0] else "???"
            print(f"  {imp} [{r[1]:<6}] {t}  {r[3][:60]}")
        else:
            imp = "⭐" * r[2] if r[2] else "·"
            print(f"  {r[0]} {imp} [{r[1]:<6}] {r[3][:60]}")


def cmd_stats(args):
    conn = get_conn()

    stocks = conn.execute("SELECT COUNT(DISTINCT ts_code) FROM stock_daily").fetchone()[0]
    price = conn.execute("SELECT COUNT(*) FROM stock_daily").fetchone()[0]
    news = conn.execute("SELECT COUNT(*) FROM stock_news").fetchone()[0]
    macro = conn.execute("SELECT COUNT(*) FROM macro_events").fetchone()[0]
    date_range = conn.execute(
        "SELECT MIN(trade_date), MAX(trade_date) FROM stock_daily"
    ).fetchone()

    print(f"\n{'='*50}")
    print(f"  数据统计")
    print(f"{'='*50}")
    print(f"  股票数量: {stocks} 只")
    print(f"  行情记录: {price} 条")
    print(f"  新闻记录: {news} 条")
    print(f"  宏观快讯: {macro} 条")
    if date_range[0]:
        print(f"  数据范围: {date_range[0]} ~ {date_range[1]}")


def cmd_top(args):
    conn = get_conn()
    trade_date = args.date or str(date.today())

    rows = conn.execute(
        """SELECT ts_code, close, change_pct
           FROM stock_daily
           WHERE trade_date=?
           ORDER BY change_pct DESC
           LIMIT 10""",
        [trade_date]
    ).fetchall()

    if not rows:
        print(f"无 {trade_date} 行情数据")
        return

    print(f"\n{'='*50}")
    print(f"  {trade_date} 涨幅 TOP10")
    print(f"{'='*50}")
    print(f"{'股票':<12} {'收盘':>8} {'涨幅%':>8}")
    print("-" * 30)
    for r in rows:
        arrow = "🟢" if r[2] > 0 else "🔴" if r[2] < 0 else "⚪"
        print(f"{arrow} {r[0]:<10} {r[1]:>8.2f} {r[2]:>8.2f}")


def main():
    parser = argparse.ArgumentParser(description="股票数据查询工具")
    sub = parser.add_subparsers(dest="command", required=True)

    # stock
    p_stock = sub.add_parser("stock", help="查看个股行情")
    p_stock.add_argument("code")
    p_stock.add_argument("--days", type=int, default=60)

    # news
    p_news = sub.add_parser("news", help="查看个股新闻")
    p_news.add_argument("code")
    p_news.add_argument("--date", type=str)

    # macro
    p_macro = sub.add_parser("macro", help="查看宏观快讯")
    p_macro.add_argument("--date", type=str)

    # stats
    sub.add_parser("stats", help="数据统计")

    # top
    p_top = sub.add_parser("top", help="当日涨幅排行")
    p_top.add_argument("--date", type=str)

    args = parser.parse_args()

    if args.command == "stock":
        cmd_stock(args)
    elif args.command == "news":
        cmd_news(args)
    elif args.command == "macro":
        cmd_macro(args)
    elif args.command == "stats":
        cmd_stats(args)
    elif args.command == "top":
        cmd_top(args)


if __name__ == "__main__":
    main()
