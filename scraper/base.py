"""爬虫基类 — 通用请求、重试、日志、延迟"""
import random
import time
import logging
import requests
from typing import Optional

from db import CONFIG

logger = logging.getLogger("stock-watcher")

scraper_cfg = CONFIG["scraper"]


def get_random_ua() -> str:
    """随机选取一个 User-Agent"""
    return random.choice(scraper_cfg["user_agents"])


def safe_request(
    url: str,
    params: Optional[dict] = None,
    headers: Optional[dict] = None,
    method: str = "GET",
    timeout: int = 15,
    json_response: bool = True,
) -> Optional[requests.Response]:
    """
    带重试和延迟的安全请求

    Args:
        json_response: 如果 True 并且返回非 JSON 失败，算作失败
    Returns:
        Response 对象或 None（彻底失败）
    """
    max_retries = scraper_cfg["max_retries"]
    delay = scraper_cfg["request_delay"]

    for attempt in range(1, max_retries + 1):
        try:
            # 请求间隔
            time.sleep(delay * (1 + random.random() * 0.5))

            req_headers = headers or {}
            if "User-Agent" not in req_headers:
                req_headers["User-Agent"] = get_random_ua()

            resp = requests.request(
                method=method,
                url=url,
                params=params,
                headers=req_headers,
                timeout=timeout,
            )
            resp.raise_for_status()

            # 如果期望 JSON，校验一下
            if json_response:
                try:
                    resp.json()
                except ValueError:
                    logger.warning(f"[请求] 非JSON响应: {url[:80]}... 尝试 {attempt}/{max_retries}")
                    if attempt < max_retries:
                        time.sleep(delay * 2 ** attempt)
                        continue
                    return None

            return resp

        except requests.RequestException as e:
            logger.warning(f"[请求] 失败: {url[:80]}... {e} 尝试 {attempt}/{max_retries}")
            if attempt < max_retries:
                time.sleep(delay * 2 ** attempt)
            else:
                logger.error(f"[请求] 彻底失败: {url[:80]}... {e}")
                return None

    return None


def log_run(module: str, ts_code: str, status: str, records: int = 0, message: str = "", duration_s: float = 0.0):
    """记录爬虫运行日志到数据库"""
    from db import execute
    from datetime import date, datetime

    if not ts_code:
        ts_code = "ALL"

    execute(
        """INSERT INTO run_log (run_date, module, ts_code, status, records, message, duration_s)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        [date.today(), module, ts_code, status, records, str(message)[:500], round(duration_s, 2)]
    )
