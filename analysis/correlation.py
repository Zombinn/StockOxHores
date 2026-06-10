"""事件-股价关联匹配

将每日新闻 + 股价变动关联起来，回答"这条新闻出来后股价动了多少"。

用法:
  python -c "from analysis.correlation import day_correlation; print(day_correlation('2026-06-09'))"
"""
import logging
from datetime import date, timedelta
from typing import List, Dict, Optional

from db import get_conn

logger = logging.getLogger("stock-whisper.correlation")


def day_correlation(trade_date_str: str) -> List[Dict]:
    """
    某一天的关联分析: 每只股票的新闻 + 当日涨跌幅

    Returns:
        [
            {
                "ts_code": "300750.SZ",
                "change_pct": 1.65,
                "news_count": 5,
                "avg_sentiment": 0.8,
                "news": [
                    {"title": "...", "sentiment": 1, "source": "新浪"},
                ]
            },
            ...
        ]
    """
    conn = get_conn()
    results = []

    # 有新闻的股票
    stocks_with_news = conn.execute(
        """SELECT DISTINCT n.ts_code 
           FROM stock_news n 
           WHERE n.news_date = ?
           ORDER BY n.ts_code""",
        [trade_date_str]
    ).fetchall()

    for (ts_code,) in stocks_with_news:
        # 当日涨跌幅
        price = conn.execute(
            "SELECT change_pct, close, vol FROM stock_daily WHERE ts_code=? AND trade_date=?",
            [ts_code, trade_date_str]
        ).fetchone()

        # 当日新闻（含情感）
        news_rows = conn.execute(
            """SELECT title, sentiment, source, news_time, url
               FROM stock_news 
               WHERE ts_code=? AND news_date=?
               ORDER BY news_time NULLS LAST""",
            [ts_code, trade_date_str]
        ).fetchall()

        sentiments = [r[1] or 0 for r in news_rows]
        avg_sent = sum(sentiments) / len(sentiments) if sentiments else 0

        results.append({
            "ts_code": ts_code,
            "change_pct": float(price[0]) if price and price[0] else None,
            "close": float(price[1]) if price and price[1] else None,
            "vol": float(price[2]) if price and price[2] else None,
            "news_count": len(news_rows),
            "avg_sentiment": round(avg_sent, 2),
            "news": [
                {
                    "title": r[0],
                    "sentiment": r[1] or 0,
                    "source": r[2],
                    "time": str(r[3])[:16] if r[3] else None,
                    "url": r[4],
                }
                for r in news_rows
            ],
        })

    # 按涨跌幅绝对值排序（波动大的在前）
    results.sort(key=lambda x: abs(x["change_pct"] or 0), reverse=True)
    return results


def stock_correlation(ts_code: str, days: int = 30) -> List[Dict]:
    """
    某只股票近N天的新闻-价格关联时间线

    Returns:
        [
            {
                "trade_date": "2026-06-09",
                "change_pct": 1.65,
                "news_count": 5,
                "news": [...]
            },
            ...
        ]
    """
    conn = get_conn()
    end = date.today()
    start = end - timedelta(days=days)

    price_rows = conn.execute(
        """SELECT trade_date, change_pct, close, vol
           FROM stock_daily
           WHERE ts_code=? AND trade_date>=? AND trade_date<=?
           ORDER BY trade_date DESC""",
        [ts_code, str(start), str(end)]
    ).fetchall()

    results = []
    for pr in price_rows:
        trade_date_str = str(pr[0])
        news_rows = conn.execute(
            """SELECT title, sentiment, source, news_time, url
               FROM stock_news
               WHERE ts_code=? AND news_date=?
               ORDER BY news_time NULLS LAST""",
            [ts_code, trade_date_str]
        ).fetchall()

        sentiments = [r[1] or 0 for r in news_rows]
        avg_sent = sum(sentiments) / len(sentiments) if sentiments else 0

        results.append({
            "trade_date": trade_date_str,
            "change_pct": float(pr[1]) if pr[1] else None,
            "close": float(pr[2]) if pr[2] else None,
            "news_count": len(news_rows),
            "avg_sentiment": round(avg_sent, 2),
            "news": [
                {
                    "title": r[0],
                    "sentiment": r[1] or 0,
                    "source": r[2],
                    "time": str(r[3])[:16] if r[3] else None,
                }
                for r in news_rows
            ],
        })

    return results


def sentiment_summary(days: int = 7) -> Dict:
    """
    近N天情感总览: 统计正面/负面新闻分布
    """
    conn = get_conn()
    end = date.today()
    start = end - timedelta(days=days)

    rows = conn.execute(
        """SELECT sentiment, COUNT(*) as cnt
           FROM stock_news
           WHERE news_date>=? AND news_date<=? AND sentiment != 0
           GROUP BY sentiment
           ORDER BY sentiment""",
        [str(start), str(end)]
    ).fetchall()

    total = sum(r[1] for r in rows)
    return {
        "period": f"{start} ~ {end}",
        "total_analyzed": total,
        "positive": sum(r[1] for r in rows if r[0] in (1, 2)),
        "negative": sum(r[1] for r in rows if r[0] in (-1, -2)),
        "very_positive": next((r[1] for r in rows if r[0] == 2), 0),
        "very_negative": next((r[1] for r in rows if r[0] == -2), 0),
        "neutral": total - sum(r[1] for r in rows if r[0] != 0),
    }


if __name__ == "__main__":
    import json
    # 测试
    result = day_correlation(str(date.today()))
    print(json.dumps(result, ensure_ascii=False, indent=2)[:2000])
