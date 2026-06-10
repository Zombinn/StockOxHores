"""东方财富个股新闻爬虫

接口说明:
  使用 East Money 内部 API 获取个股相关新闻
  API:
    GET https://search-api-web.eastmoney.com/search/jsonp
      ?param={"uid":"","keyword":"股票名 代码","type":["cmsArticleWebOld"]}
    GET https://push2ex.eastmoney.com/getStockNews
      ?code=000001&market=0&pageIndex=1&pageSize=20

  双接口策略: 主用 push2ex，备用 search-api-web
"""
import time
import json
import logging
import requests
from datetime import date, datetime
from typing import Optional, List, Dict

from db import get_conn, stock_news_exists
from .base import safe_request, log_run, get_random_ua

logger = logging.getLogger("stock-watcher.news_eastmoney")


def _code_to_secid(ts_code: str) -> str:
    """将 000001.SZ 转为东方财富内部编码格式"""
    code = ts_code.split(".")[0]
    suffix = ts_code.split(".")[-1].upper()
    market = "0" if suffix == "SZ" else "1"  # 0=深圳, 1=上海
    return f"{market}.{code}"


def _code_to_market_code(ts_code: str) -> tuple:
    """返回 (code, market) 元组"""
    code = ts_code.split(".")[0]
    suffix = ts_code.split(".")[-1].upper()
    market = "0" if suffix == "SZ" else "1"
    return code, market


def _ts_to_datetime(ts: int) -> Optional[datetime]:
    """将毫秒时间戳转为 datetime"""
    if not ts or ts == 0:
        return None
    try:
        return datetime.fromtimestamp(ts / 1000)
    except (ValueError, OSError):
        return None


def fetch_news_push2ex(ts_code: str, page: int = 1, page_size: int = 20) -> Optional[List[Dict]]:
    """
    通过 push2ex 接口获取个股新闻
    
    接口格式: GET https://push2ex.eastmoney.com/getStockNews
    ?code=000001&market=0&pageIndex=1&pageSize=20&type=1
    """
    code, market = _code_to_market_code(ts_code)
    url = "https://push2ex.eastmoney.com/getStockNews"
    params = {
        "code": code,
        "market": market,
        "pageIndex": page,
        "pageSize": page_size,
        "type": "1",  # 1=全部
    }
    headers = {
        "User-Agent": get_random_ua(),
        "Referer": "https://guba.eastmoney.com/",
    }

    resp = safe_request(url, params=params, headers=headers, json_response=True, method="GET")
    if resp is None:
        return None

    try:
        data = resp.json()
        # 解析格式: {data: {list: [...]}}
        if "data" not in data:
            return None
        news_list = data["data"].get("list", [])
        if not news_list:
            return None

        results = []
        for item in news_list:
            title = item.get("title", "") or item.get("Art_Title", "")
            if not title:
                continue

            pub_time = None
            # 尝试多个时间字段
            for t_key in ["Art_CreateTime", "CreateTime", "showDate", "date"]:
                t_val = item.get(t_key)
                if t_val:
                    if isinstance(t_val, int) and t_val > 1000000000000:
                        pub_time = _ts_to_datetime(t_val)
                    elif isinstance(t_val, str):
                        try:
                            pub_time = datetime.fromisoformat(t_val.replace("T", " "))
                        except:
                            pass
                    if pub_time:
                        break

            news_id = item.get("Art_Id") or item.get("Art_ID") or item.get("id")
            content = item.get("Art_Content") or item.get("content") or item.get("summary", "")
            url_link = item.get("Art_Url") or item.get("url") or item.get("Art_Link", "")

            results.append({
                "id": news_id,
                "title": title,
                "content_abs": content[:500] if content else "",
                "news_time": pub_time,
                "url": url_link,
                "source": "东方财富",
            })
        return results

    except (json.JSONDecodeError, KeyError, TypeError) as e:
        logger.warning(f"[东财push2ex] 解析失败: {e}")
        return None


def fetch_news_search(ts_code: str, keyword: Optional[str] = None, page: int = 1) -> Optional[List[Dict]]:
    """
    通过东方财富搜索API获取新闻（备用接口）
    
    URL: https://search-api-web.eastmoney.com/search/jsonp
    """
    code = ts_code.split(".")[0]
    search_keyword = keyword or code

    url = "https://search-api-web.eastmoney.com/search/jsonp"
    params = {
        "param": json.dumps({
            "uid": "",
            "keyword": search_keyword,
            "type": ["cmsArticleWebOld"],
            "client": "web",
            "clientType": "web",
            "pageNum": page,
        }),
        "client": "web",
    }
    headers = {
        "User-Agent": get_random_ua(),
        "Referer": "https://so.eastmoney.com/",
    }

    resp = safe_request(url, params=params, headers=headers, json_response=True, method="GET")
    if resp is None:
        return None

    try:
        data = resp.json()
        articles = None
        for key in ["data", "result", "list", "articles"]:
            if key in data:
                articles = data[key]
                break

        if not articles or not isinstance(articles, list):
            # 试试嵌套结构
            if "data" in data:
                for key in ["list", "articles", "result"]:
                    if key in data["data"]:
                        articles = data["data"][key]
                        break

        if not articles:
            return None

        results = []
        for item in articles:
            title = item.get("title") or item.get("Art_Title") or ""
            if not title:
                continue

            pub_time = None
            for t_key in ["date", "createDate", "Art_CreateTime", "showDate"]:
                t_val = item.get(t_key)
                if t_val:
                    try:
                        pub_time = datetime.fromisoformat(str(t_val).replace("T", " "))
                    except:
                        pass
                    if pub_time:
                        break

            results.append({
                "id": item.get("id") or item.get("Art_Id"),
                "title": title.replace("<em>", "").replace("</em>", ""),
                "content_abs": (item.get("content") or item.get("Art_Content") or "")[:500],
                "news_time": pub_time,
                "url": item.get("url") or item.get("Art_Url") or "",
                "source": "东方财富",
            })
        return results

    except (json.JSONDecodeError, KeyError, TypeError) as e:
        logger.warning(f"[东财搜索] 解析失败: {e}")
        return None


def fetch_news(ts_code: str, page: int = 1) -> List[Dict]:
    """
    获取个股新闻，主备用双接口策略
    """
    # 主接口
    results = fetch_news_push2ex(ts_code, page=page)
    if results:
        return results

    # 备用接口
    logger.info(f"[东财] push2ex 无数据，尝试搜索接口 {ts_code}")
    results = fetch_news_search(ts_code, page=page)
    if results:
        return results

    return []


def save_news(ts_code: str, news_list: List[Dict], trade_date) -> int:
    """将新闻写入 DuckDB（去重）"""
    if not news_list:
        return 0

    conn = get_conn()
    count = 0
    for item in news_list:
        title = item["title"][:500]
        if not title:
            continue

        # 去重
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
                item.get("source", "东方财富"),
                title,
                item.get("url", ""),
                item.get("content_abs", ""),
            ]
        )
        count += 1

    conn.commit()
    logger.info(f"[东财] {ts_code} {trade_date} 写入 {count} 条新闻")
    return count


def run(ts_code: str, trade_date) -> int:
    """
    对单个股票单日采集新闻并入库
    Returns: 新增记录数
    """
    t0 = time.time()
    module = "news_eastmoney"

    try:
        news_list = fetch_news(ts_code, page=1)
        count = save_news(ts_code, news_list, trade_date)
        log_run(module, ts_code, "success", count, "", time.time() - t0)
        return count

    except Exception as e:
        logger.error(f"[东财] {ts_code} {trade_date} 异常: {e}")
        log_run(module, ts_code, "error", 0, str(e), time.time() - t0)
        return 0
