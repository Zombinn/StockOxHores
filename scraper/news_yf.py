"""美股/港股新闻采集 — 基于 yfinance 内置新闻接口

用法:
  from scraper.news_yf import run
  count = run("NVDA", "2026-06-10")   # 采集当天NVDA新闻
"""
import time
import logging
from datetime import datetime, date
from typing import Optional, List, Dict

import yfinance as yf
import warnings
warnings.filterwarnings("ignore")

from db import get_conn, stock_news_exists
from .base import log_run

logger = logging.getLogger("stock-watcher.news_yf")


def fetch_news(ts_code: str, limit: int = 30) -> List[Dict]:
    """
    通过 yfinance 获取美股/港股新闻

    Args:
        ts_code: 股票代码，如 NVDA / TSLA / 0700.HK
        limit: 最多返回条数
    """
    try:
        ticker = yf.Ticker(ts_code)
        news = ticker.news
        if not news:
            return []
    except Exception as e:
        logger.warning(f"[yf新闻] {ts_code} 获取失败: {e}")
        return []

    results = []
    for item in news[:limit]:
        try:
            content = item.get("content", {})
            title = content.get("title", "")
            if not title:
                continue

            # 解析时间
            pub_date = content.get("pubDate") or content.get("displayTime")
            news_time = None
            if pub_date:
                try:
                    news_time = datetime.fromisoformat(pub_date.replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    pass

            provider = content.get("provider", {})
            source = provider.get("profileName", "Yahoo Finance") if provider else "Yahoo Finance"

            summary = content.get("summary", "") or content.get("description", "")

            results.append({
                "id": item.get("id") or content.get("id"),
                "title": title,
                "content_abs": summary[:500] if summary else "",
                "news_time": news_time,
                "source": source,
                "url": content.get("canonicalUrl", {}).get("url", "") or content.get("previewUrl", ""),
            })
        except Exception as e:
            continue

    return results


def save_news(ts_code: str, news_list: List[Dict], trade_date) -> int:
    """写入 DuckDB（去重）"""
    if not news_list:
        return 0

    conn = get_conn()
    count = 0
    for item in news_list:
        title = item["title"][:500]
        if not title:
            continue

        # 按标题去重（yfinance可能有重复）
        if stock_news_exists(ts_code, trade_date, title):
            continue

        news_time = item.get("news_time")
        conn.execute(
            """INSERT INTO stock_news
               (ts_code, news_date, news_time, source, title, url, content_abs)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            [
                ts_code,
                str(trade_date),
                news_time if news_time else None,
                item.get("source", "Yahoo Finance"),
                title,
                item.get("url", ""),
                item.get("content_abs", ""),
            ]
        )
        count += 1

    conn.commit()
    logger.info(f"[yf新闻] {ts_code} {trade_date} 写入 {count} 条新闻")
    return count


def run(ts_code: str, trade_date) -> int:
    """单股单日新闻采集"""
    t0 = time.time()
    module = "news_yf"

    try:
        news_list = fetch_news(ts_code)
        count = save_news(ts_code, news_list, trade_date)
        log_run(module, ts_code, "success", count, "", time.time() - t0)
        return count
    except Exception as e:
        logger.error(f"[yf新闻] {ts_code} {trade_date} 异常: {e}")
        log_run(module, ts_code, "error", 0, str(e), time.time() - t0)
        return 0
