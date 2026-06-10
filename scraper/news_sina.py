"""新浪财经个股新闻爬虫

接口:
  新浪个股新闻API: https://vip.stock.finance.sina.com.cn/corp/go.php/vCB_AllNewsStock/symbol/SH600519.phtml
  
  更好的 JSON 接口:
  GET https://feed.mix.sina.com.cn/api/rollup
    ?catid=592  (个股新闻分类)
    &tag=股票代码
    &offset=0
    &limit=20
  
  备用: https://finance.sina.com.cn/realstock/company/SH600519/nc.shtml
"""
import time
import json
import re
import logging
from datetime import datetime
from typing import Optional, List, Dict

from db import get_conn, stock_news_exists
from .base import safe_request, log_run, get_random_ua

logger = logging.getLogger("stock-watcher.news_sina")


def _code_to_sina(ts_code: str) -> str:
    """将 000001.SZ 转为新浪格式: sz000001 / sh600519"""
    code = ts_code.split(".")[0]
    suffix = ts_code.split(".")[-1].lower()
    return f"{suffix}{code}"


def fetch_news_feed(ts_code: str, offset: int = 0, limit: int = 20) -> Optional[List[Dict]]:
    """
    通过新浪 feed API 获取个股新闻

    URL: https://feed.mix.sina.com.cn/api/rollup
    """
    sina_code = _code_to_sina(ts_code)
    url = "https://feed.mix.sina.com.cn/api/rollup"
    params = {
        "catid": "592",       # 个股新闻分类
        "tag": sina_code,
        "offset": offset,
        "limit": limit,
    }
    headers = {
        "User-Agent": get_random_ua(),
        "Referer": f"https://finance.sina.com.cn/realstock/company/{sina_code}/nc.shtml",
    }

    resp = safe_request(url, params=params, headers=headers, json_response=True)
    if resp is None:
        return None

    try:
        data = resp.json()
        items = data.get("result", {}).get("data", [])
        if not items:
            return None

        results = []
        for item in items:
            title = item.get("title", "")
            if not title:
                continue

            # 解析时间
            ctime = item.get("ctime") or item.get("intime")
            pub_time = None
            if ctime:
                try:
                    # 新浪 feed 时间单位是秒
                    pub_time = datetime.fromtimestamp(int(ctime))
                except (ValueError, OSError):
                    pass

            results.append({
                "id": item.get("id"),
                "title": title,
                "content_abs": item.get("summary", "")[:500],
                "news_time": pub_time,
                "url": item.get("url") or item.get("link", ""),
                "source": "新浪财经",
            })
        return results

    except (json.JSONDecodeError, KeyError, TypeError) as e:
        logger.warning(f"[新浪feed] 解析失败: {e}")
        return None


def fetch_news_html(ts_code: str) -> Optional[List[Dict]]:
    """
    备用方案: 爬取新浪个股新闻页面
    URL: https://vip.stock.finance.sina.com.cn/corp/go.php/vCB_AllNewsStock/symbol/SH600519.phtml
    """
    sina_code = _code_to_sina(ts_code)
    url = f"https://vip.stock.finance.sina.com.cn/corp/go.php/vCB_AllNewsStock/symbol/{sina_code.upper()}.phtml"
    headers = {
        "User-Agent": get_random_ua(),
    }

    resp = safe_request(url, headers=headers, json_response=False)
    if resp is None:
        return None

    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(resp.text, "lxml")
        results = []

        # 新浪该页面的新闻通常在表格中
        for link in soup.select("a[target=_blank]"):
            href = link.get("href", "")
            title = link.get_text(strip=True)
            if not title or len(title) < 5:
                continue
            # 过滤非新闻链接
            if not any(k in href for k in ["sina.com.cn", "finance"]):
                continue
            if "新闻" in href or "doc" in href or title:
                results.append({
                    "id": None,
                    "title": title,
                    "content_abs": "",
                    "news_time": None,
                    "url": href if href.startswith("http") else f"https:{href}",
                    "source": "新浪财经",
                })

        return results[:20] if results else None

    except Exception as e:
        logger.warning(f"[新浪HTML] 解析失败: {e}")
        return None


def fetch_news(ts_code: str) -> List[Dict]:
    """获取个股新闻 - 多接口策略"""
    # 主接口: feed API
    results = fetch_news_feed(ts_code)
    if results:
        return results

    # 备用: HTML 爬取
    logger.info(f"[新浪] feed 无数据，尝试 HTML 页面 {ts_code}")
    results = fetch_news_html(ts_code)
    return results or []


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
                item.get("source", "新浪财经"),
                title,
                item.get("url", ""),
                item.get("content_abs", ""),
            ]
        )
        count += 1

    conn.commit()
    logger.info(f"[新浪] {ts_code} {trade_date} 写入 {count} 条新闻")
    return count


def run(ts_code: str, trade_date) -> int:
    """单股单日新闻采集"""
    t0 = time.time()
    module = "news_sina"

    try:
        news_list = fetch_news(ts_code)
        count = save_news(ts_code, news_list, trade_date)
        log_run(module, ts_code, "success", count, "", time.time() - t0)
        return count

    except Exception as e:
        logger.error(f"[新浪] {ts_code} {trade_date} 异常: {e}")
        log_run(module, ts_code, "error", 0, str(e), time.time() - t0)
        return 0
