"""财联社电报快讯爬虫

获取宏观政策、行业动态、市场快讯等影响大盘的关键事件。

接口:
  财联社电报: https://www.cls.cn/telegraph
  JSON数据接口: https://www.cls.cn/v1/roll/get_roll_list
    ?app=Cailianpress&category=all&lastTime=时间戳&limit=50
  
  备用: akshare.stock_info_global_cls()
"""
import time
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict

from db import get_conn
from .base import safe_request, log_run, get_random_ua

logger = logging.getLogger("stock-watcher.news_cls")


# 财联社分类映射
CATEGORY_MAP = {
    "all": "全部",
    "red": "重要",
    "stock": "股市",
    "industry": "行业",
    "macro": "宏观",
    "company": "公司",
    "political": "政经",
    "overseas": "海外",
}


def fetch_telegraph(category: str = "all", limit: int = 50, last_time: Optional[str] = None) -> Optional[List[Dict]]:
    """
    获取财联社电报快讯

    Args:
        category: 分类（all/red/stock/industry/macro/company/political/overseas）
        limit: 条数
        last_time: 分页游标（上次最后一条的时间戳，毫秒）
    """
    url = "https://www.cls.cn/v1/roll/get_roll_list"
    params = {
        "app": "Cailianpress",
        "category": category,
        "limit": limit,
    }
    if last_time:
        params["lastTime"] = last_time

    headers = {
        "User-Agent": get_random_ua(),
        "Referer": "https://www.cls.cn/telegraph",
    }

    resp = safe_request(url, params=params, headers=headers, json_response=True)
    if resp is None:
        return None

    try:
        data = resp.json()
        items = data.get("data", {}).get("roll_data", [])
        if not items:
            # 备用结构
            items = data.get("data", []) if isinstance(data.get("data"), list) else []

        if not items:
            return None

        results = []
        for item in items:
            title = item.get("title", "") or item.get("Title", "")
            content = item.get("content", "") or item.get("Content", "") or item.get("brief", "")
            # 如果没标题，取内容前50字当标题
            if not title and content:
                title = content[:50]

            if not title:
                continue

            # 时间解析
            ctime = item.get("ctime") or item.get("Ctime") or item.get("createTime")
            event_time = None
            if ctime:
                try:
                    # 财联社时间通常是秒级时间戳
                    event_time = datetime.fromtimestamp(int(ctime))
                except (ValueError, OSError):
                    try:
                        event_time = datetime.fromtimestamp(int(ctime) / 1000)
                    except:
                        pass

            # 重要性判断
            importance = 3  # 默认中等
            tag = item.get("tag") or item.get("Tag") or ""
            if "重磅" in title or "突发" in title or "紧急" in title:
                importance = 5
            elif "重要" in title or tag == "red":
                importance = 4
            elif tag in ("stock", "industry"):
                importance = 3
            elif tag in ("company",):
                importance = 2

            # 分类
            raw_cat = item.get("category") or item.get("Category") or category
            cat_name = CATEGORY_MAP.get(raw_cat, "其他")

            results.append({
                "id": item.get("id") or item.get("Id") or item.get("roll_id"),
                "title": title,
                "content": content[:1000] if content else "",
                "event_time": event_time,
                "category": cat_name,
                "importance": importance,
                "source": "财联社",
            })

        return results

    except (json.JSONDecodeError, KeyError, TypeError) as e:
        logger.warning(f"[财联社] 解析失败: {e}")
        return None


def fetch_news(ts_code: str = "ALL", category: str = "all", limit: int = 30) -> List[Dict]:
    """
    获取财联社快讯（不区分个股，按分类获取）

    Args:
        ts_code: 占位，保持与个股爬虫接口一致
        category: 分类
        limit: 条数
    """
    results = fetch_telegraph(category=category, limit=limit)
    if results:
        return results
    return []


def save_events(events: List[Dict], trade_date) -> int:
    """写入 macro_events 表"""
    if not events:
        return 0

    conn = get_conn()
    count = 0
    for evt in events:
        title = evt["title"][:500]
        if not title:
            continue

        # 检查是否已存在（按日期+标题去重）
        existing = conn.execute(
            "SELECT 1 FROM macro_events WHERE event_date=? AND title=?",
            [str(trade_date), title]
        ).fetchone()
        if existing:
            continue

        event_time = evt.get("event_time")
        conn.execute(
            """INSERT INTO macro_events 
               (event_date, event_time, category, title, content, source, importance)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            [
                str(trade_date),
                event_time if event_time else None,
                evt.get("category", "其他"),
                title,
                evt.get("content", ""),
                evt.get("source", "财联社"),
                evt.get("importance", 3),
            ]
        )
        count += 1

    conn.commit()
    logger.info(f"[财联社] {trade_date} 写入 {count} 条快讯")
    return count


def run(trade_date) -> int:
    """
    对某天采集财联社快讯
    Returns: 新增记录数
    """
    t0 = time.time()
    module = "news_cls"

    try:
        # 获取当天快讯
        events = fetch_telegraph(category="all", limit=50)
        if not events:
            # 再试一次重要快讯
            events = fetch_telegraph(category="red", limit=30)

        count = save_events(events or [], trade_date)
        log_run(module, "ALL", "success", count, "", time.time() - t0)
        return count

    except Exception as e:
        logger.error(f"[财联社] {trade_date} 异常: {e}")
        log_run(module, "ALL", "error", 0, str(e), time.time() - t0)
        return 0
