"""主流程编排 — 一天的数据采集全流程"""
import time
import logging
from datetime import date, datetime
from typing import List, Optional

from db import get_conn, CONFIG, get_stocks, init_db

logger = logging.getLogger("stock-watcher.pipeline")


def init_project():
    """系统初始化：建库建表"""
    init_db()
    logger.info("[PIPELINE] 数据库初始化完成")


def run_daily(
    ts_codes: Optional[List[str]] = None,
    trade_date=None,
    skip_price: bool = False,
    skip_news: bool = False,
    skip_macro: bool = False,
) -> dict:
    """
    对指定日期执行完整数据采集

    Args:
        ts_codes: 股票代码列表（默认从配置读取）
        trade_date: 交易日（默认今天）
        skip_price: 跳过行情采集
        skip_news: 跳过新闻采集
        skip_macro: 跳过宏观快讯采集

    Returns:
        采集统计 dict
    """
    if ts_codes is None:
        ts_codes = get_stocks()

    if trade_date is None:
        trade_date = date.today()

    stats = {
        "trade_date": str(trade_date),
        "stock_count": len(ts_codes),
        "price_records": 0,
        "news_records": 0,
        "macro_records": 0,
        "errors": [],
    }

    # 确保数据库已初始化
    init_project()

    # ─── 1. 采集行情 ───
    if not skip_price:
        logger.info(f"[PIPELINE] 开始采集行情: {len(ts_codes)} 只股票")
        from scraper import price

        for i, ts_code in enumerate(ts_codes):
            try:
                count = price.run(ts_code, trade_date)
                stats["price_records"] += count
                logger.info(f"[PIPELINE] [{i+1}/{len(ts_codes)}] {ts_code} 行情: {count} 条")
            except Exception as e:
                logger.error(f"[PIPELINE] {ts_code} 行情异常: {e}")
                stats["errors"].append(f"{ts_code} 行情: {e}")

    # ─── 2. 采集个股新闻 ───
    if not skip_news:
        logger.info(f"[PIPELINE] 开始采集新闻: {len(ts_codes)} 只股票")
        from scraper import news_sina, news_yf

        for i, ts_code in enumerate(ts_codes):
            try:
                if "." in ts_code:
                    # A股 → 新浪财经
                    c = news_sina.run(ts_code, trade_date)
                    stats["news_records"] += c
                    logger.info(f"[PIPELINE] [{i+1}/{len(ts_codes)}] {ts_code} 新闻: 新浪={c}")
                else:
                    # 美股/港股 → yfinance 新闻
                    c = news_yf.run(ts_code, trade_date)
                    stats["news_records"] += c
                    logger.info(f"[PIPELINE] [{i+1}/{len(ts_codes)}] {ts_code} 新闻: yf={c}")
            except Exception as e:
                logger.error(f"[PIPELINE] {ts_code} 新闻异常: {e}")
                stats["errors"].append(f"{ts_code} 新闻: {e}")

    # ─── 3. 采集宏观快讯 ───
    if not skip_macro:
        # 财联社API在当前环境不可达，跳过
        logger.info(f"[PIPELINE] 宏观快讯采集跳过（API不可达）")
        stats["macro_records"] = 0

    # ─── 4. 生成日汇总 ───
    try:
        _generate_summary(ts_codes, trade_date, stats)
    except Exception as e:
        logger.error(f"[PIPELINE] 生成汇总异常: {e}")

    logger.info(f"[PIPELINE] 完成: {stats}")
    return stats


def _generate_summary(ts_codes: List[str], trade_date, stats: dict):
    """生成每日 Markdown 汇总"""
    conn = get_conn()

    # 获取当天涨幅前5的股票
    top5 = conn.execute(
        """SELECT ts_code, close, change_pct 
           FROM stock_daily 
           WHERE trade_date=? AND ts_code IN ({})
           ORDER BY change_pct DESC 
           LIMIT 5""".format(",".join(["?"] * len(ts_codes))),
        [str(trade_date)] + ts_codes
    ).fetchall()

    # 获取当天 news 数量
    news_count = conn.execute(
        "SELECT COUNT(*) FROM stock_news WHERE news_date=?", [str(trade_date)]
    ).fetchone()[0]

    # 获取 macro 数量
    macro_count = conn.execute(
        "SELECT COUNT(*) FROM macro_events WHERE event_date=?", [str(trade_date)]
    ).fetchone()[0]

    # 生成摘要
    lines = [f"## {trade_date} 市场日报\n"]
    lines.append(f"- 采集股票: {len(ts_codes)} 只")
    lines.append(f"- 行情记录: {stats['price_records']} 条")
    lines.append(f"- 新闻记录: {news_count} 条")
    lines.append(f"- 宏观快讯: {macro_count} 条")

    if top5:
        lines.append("\n### 涨幅 TOP5\n")
        for row in top5:
            lines.append(f"- {row[0]}: 收盘 {row[1]:.2f} ({row[2]:.2f}%)")

    if stats.get("errors"):
        lines.append(f"\n### ⚠️ 错误 {len(stats['errors'])} 条\n")
        for err in stats["errors"][:10]:
            lines.append(f"- {err}")

    summary = "\n".join(lines)

    # 写入 daily_summary
    conn.execute(
        "INSERT OR REPLACE INTO daily_summary (trade_date, summary) VALUES (?, ?)",
        [str(trade_date), summary]
    )
    conn.commit()


def run_backfill(ts_codes: Optional[List[str]] = None, months: int = 12, with_news: bool = False):
    """
    历史回填：批量采集近N个月的数据（默认只跑行情，跳过新闻）

    Args:
        ts_codes: 股票列表（默认从配置读取）
        months: 回填月数
        with_news: 是否同时采集新闻（默认False）
    """
    if ts_codes is None:
        ts_codes = get_stocks()

    from datetime import date, timedelta

    end_date = date.today()
    start_date = end_date - timedelta(days=months * 30)

    logger.info(f"[BACKFILL] 回填 {start_date} ~ {end_date}, {len(ts_codes)} 只股票")

    total_price = 0
    total_news = 0
    total_macro = 0

    # 按天遍历（只跑交易日）
    current = start_date
    while current <= end_date:
        # 跳过周末
        if current.weekday() >= 5:
            current += timedelta(days=1)
            continue

        logger.info(f"[BACKFILL] 处理 {current}")
        stats = run_daily(ts_codes, trade_date=current, skip_news=not with_news)
        total_price += stats["price_records"]
        total_news += stats["news_records"]
        total_macro += stats["macro_records"]

        # 进度
        days_done = (current - start_date).days
        days_total = (end_date - start_date).days
        pct = days_done / days_total * 100 if days_total > 0 else 0
        logger.info(f"[BACKFILL] 进度: {days_done}/{days_total} ({pct:.1f}%)")

        current += timedelta(days=1)

    logger.info(f"[BACKFILL] 完成! 行情={total_price}, 新闻={total_news}, 宏观={total_macro}")
    return {
        "start": str(start_date),
        "end": str(end_date),
        "price": total_price,
        "news": total_news,
        "macro": total_macro,
    }
