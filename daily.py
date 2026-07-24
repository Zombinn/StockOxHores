#!/usr/bin/env python3
"""
StockOxHores 每日情报采集

每天收集: 个股新闻 + 宏观快讯（行情只做关联匹配用，不展示）
被 Hermes cronjob 调用，自动推送到用户

用法:
  python daily.py                          # 今天
  python daily.py --date 2026-06-09        # 补某天
  python daily.py --skip-price             # 不拉行情
"""
import sys
import argparse
import logging
from datetime import date, datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)


def main():
    parser = argparse.ArgumentParser(description="StockOxHores 每日情报采集")
    parser.add_argument("--date", type=str, help="指定日期 YYYY-MM-DD（默认今天）")
    parser.add_argument("--stocks", nargs="+", help="指定股票列表")
    parser.add_argument("--skip-price", action="store_true", help="跳过行情采集")
    parser.add_argument("--quiet", action="store_true", help="只输出简报，隐藏日志")
    args = parser.parse_args()

    if args.quiet:
        logging.getLogger().setLevel(logging.ERROR)
        import os
        os.environ["LOGURU_LEVEL"] = "ERROR"

    from pipeline import run_daily, init_project
    from db import get_stocks, get_conn

    init_project()

    trade_date = date.fromisoformat(args.date) if args.date else date.today()
    stocks = args.stocks or get_stocks()

    if not args.quiet:
        print(f"\n{'='*50}")
        print(f"  StockOxHores · {trade_date}")
        print(f"  {len(stocks)} 只标的")
        print(f"{'='*50}\n")
    # 2. 采集当日情报
    stats = run_daily(ts_codes=stocks, trade_date=trade_date, skip_price=args.skip_price)

    # 3. 情感评分（新入库的新闻自动打分）
    from analysis.sentiment import batch_score
    batch_score()

    if not args.quiet:
        print(f"\n{'='*50}")
        print(f"  采集完成")
        print(f"  新闻: {stats['news_records']} 条")
        print(f"  宏观: {stats['macro_records']} 条")
        print(f"  行情: {stats['price_records']} 条（仅用于关联匹配）")
        if stats['errors']:
            print(f"  错误: {len(stats['errors'])} 条")
            for err in stats['errors'][:5]:
                print(f"    · {err}")
        print(f"{'='*50}\n")

    # 输出当日情报摘要（结构化 Markdown）
    conn = get_conn()
    news_count = conn.execute(
        "SELECT COUNT(*) FROM stock_news WHERE news_date=?", [str(trade_date)]
    ).fetchone()[0]
    macro_count = conn.execute(
        "SELECT COUNT(*) FROM macro_events WHERE event_date=?", [str(trade_date)]
    ).fetchone()[0]

    # 有新闻的股票
    active = conn.execute(
        "SELECT DISTINCT ts_code FROM stock_news WHERE news_date=? ORDER BY ts_code",
        [str(trade_date)]
    ).fetchall()

    if args.quiet:
        # 简洁格式 — 飞书推送
        active_codes = [r[0] for r in active]
        header = f"📊 StockOxHores · {trade_date}"

        lines = [f"{news_count} 条新闻 · {len(active)} 只标的 · 宏观 {macro_count} 条\n"]

        from db import get_stock_names
        stock_names = get_stock_names()
        rows = conn.execute(
            """SELECT ts_code, title, source, url, sentiment
               FROM stock_news WHERE news_date=?
               ORDER BY ABS(sentiment) DESC, news_time DESC NULLS LAST
               LIMIT 15""",
            [str(trade_date)]
        ).fetchall()
        for r in rows:
            raw_code = r[0] or ""
            code = raw_code[:6].replace(".SZ","").replace(".SH","") if "." in raw_code else raw_code
            name = stock_names.get(raw_code, code)
            tag = "📈" if (r[4] or 0) > 0 else "📉" if (r[4] or 0) < 0 else "➖"
            title = r[1][:80] if r[1] else ""
            source = r[2] or ""
            url = r[3] or ""
            # 格式: 📈 代码 名称 | 标题  | 来源
            label = f"`{code}` {name}"
            if url and url.startswith("http"):
                lines.append(f"{tag} {label} | [{title}]({url})  | {source}")
            else:
                lines.append(f"{tag} {label} | {title}  | {source}")

        msgs = []
        chunk = header + "\n" + lines[0]
        for l in lines[1:]:
            if len(chunk) + len(l) > 3500:
                msgs.append(chunk)
                chunk = l
            else:
                chunk += "\n" + l
        if chunk:
            msgs.append(chunk)

        try:
            from notify import send_feishu
            for m in msgs:
                send_feishu(m)
        except Exception:
            pass
    else:
        print(f"\n📋 情报简报  ·  {trade_date}")
        print(f"{'─'*40}")
        print(f"  新闻 {news_count} 条 · 宏观 {macro_count} 条")
        print(f"  有新闻标的: {len(active)} 只")
        for r in active[:10]:
            c = conn.execute(
                "SELECT COUNT(*) FROM stock_news WHERE ts_code=? AND news_date=?",
                [r[0], str(trade_date)]
            ).fetchone()[0]
            print(f"    {r[0]:12s} {c} 篇")

    summary_md = f"""# StockOxHores 情报简报 · {trade_date}

- **新闻:** {news_count} 条
- **宏观:** {macro_count} 条
"""
    # 写入 daily_summary
    conn.execute(
        "INSERT OR REPLACE INTO daily_summary (trade_date, summary) VALUES (?, ?)",
        [str(trade_date), summary_md]
    )
    conn.commit()

    # Telegram 推送
    try:
        from notify import send_telegram
        text = f"""📡 *StockOxHores · {trade_date}*

{len(stocks)} 只标的 · {stats['news_records']} 篇新闻 · {stats['price_records']} 行情条
"""

        # Top 10 新闻（按情感分排序，重要的在前）
        rows = conn.execute(
            """SELECT ts_code, title, url, sentiment
               FROM stock_news WHERE news_date=?
               ORDER BY ABS(sentiment) DESC, news_time DESC NULLS LAST
               LIMIT 15""",
            [str(trade_date)]
        ).fetchall()

        if rows:
            text += "\n📰 *重要新闻*\n"
            for r in rows[:12]:
                code = r[0]
                title = r[1][:80]
                url = r[2] or ""
                s = r[3] or 0
                tag = "📈" if s > 0.5 else "📊" if s > 0 else "📉" if s < -0.5 else "➖"
                link = f"[{title[:50]}]({url})" if url and url.startswith("http") else title[:50]
                text += f"\n{tag} `{code}` {link}"

        if stats.get('errors'):
            text += f"\n\n⚠️ {len(stats['errors'])} 条错误"

        send_telegram(text, parse_mode="Markdown")
    except Exception:
        pass


if __name__ == "__main__":
    main()
