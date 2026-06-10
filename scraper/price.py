"""A股日线行情采集模块 — 基于 yfinance

A股代码格式: 000001.SZ 直接可用
返回字段: Open, High, Low, Close, Volume, Dividends, Stock Splits
涨跌幅通过 Close/prevClose 自行计算
"""
import time
import logging
import pandas as pd
from datetime import date, timedelta
from typing import Optional, List

import yfinance as yf
import warnings
warnings.filterwarnings("ignore")

from db import get_conn, stock_exists
from .base import log_run as log_run_db

logger = logging.getLogger("stock-watcher.price")


def _yf_code(ts_code: str) -> str:
    """将 Hermes 代码转为 yfinance 格式
    000001.SZ → 000001.SZ (深交所不变)
    600519.SH → 600519.SS (上交所改 .SS)
    """
    code = ts_code.split(".")[0]
    suffix = ts_code.split(".")[-1].upper()
    if suffix == "SH":
        return code + ".SS"
    return ts_code


def fetch_daily(ts_code: str, start_date, end_date=None) -> Optional[pd.DataFrame]:
    """
    用 yfinance 获取个股日线行情

    Args:
        ts_code: 股票代码 如 000001.SZ / 600519.SH
        start_date: str "2025-01-01" 或 date 对象
        end_date: 同上，默认为今天
    Returns:
        DataFrame 或 None
    """
    if end_date is None:
        end_date = date.today()

    # yfinance 单日查询经常失败，至少扩到前后各1天
    yf_start = pd.Timestamp(start_date) - pd.Timedelta(days=2)
    yf_end = pd.Timestamp(end_date) + pd.Timedelta(days=1)
    yf_code = _yf_code(ts_code)

    try:
        ticker = yf.Ticker(yf_code)
        df = ticker.history(start=yf_start.strftime('%Y-%m-%d'), end=yf_end.strftime('%Y-%m-%d'))

        if df is None or df.empty:
            logger.info(f"[价格] {ts_code} {start_date}~{end_date} 无数据")
            return None

        # 清洗和标准化
        df = df.rename(columns={
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "vol",
        })

        # yfinance 返回的时间索引有时区，转为 date
        df["trade_date"] = df.index.date if hasattr(df.index, "date") else pd.to_datetime(df.index).date

        # 计算涨跌幅
        df["change_pct"] = df["close"].pct_change() * 100

        # 添加股票代码
        df["ts_code"] = ts_code

        # 确保数值列
        numeric_cols = ["open", "close", "high", "low", "vol", "change_pct"]
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        # 选要写入的列
        target_cols = ["ts_code", "trade_date", "open", "high", "low", "close",
                       "vol", "change_pct"]
        available = [c for c in target_cols if c in df.columns]
        result = df[available].copy()

        # 第一条的 change_pct 是 NaN（没有前一天数据），补0
        result["change_pct"] = result["change_pct"].fillna(0)

        return result

    except Exception as e:
        logger.error(f"[价格] {ts_code} 获取失败: {e}")
        return None


def save_daily(df: pd.DataFrame) -> int:
    """将行情数据写入 DuckDB（INSERT OR REPLACE）"""
    if df is None or len(df) == 0:
        return 0

    conn = get_conn()
    conn.register("_price_df", df)

    conn.execute("""
        INSERT OR REPLACE INTO stock_daily
        (ts_code, trade_date, open, high, low, close, change_pct, vol, amount, turn)
        SELECT ts_code, trade_date, open, high, low, close, change_pct, vol,
               NULL AS amount,
               NULL AS turn
        FROM _price_df
    """)
    affected = conn.execute("SELECT COUNT(*) FROM _price_df").fetchone()[0]
    conn.commit()
    conn.execute("DROP VIEW IF EXISTS _price_df")
    logger.info(f"[价格] 写入 {affected} 条记录")
    return affected


def run(ts_code: str, trade_date) -> int:
    """单股单日行情采集入库"""
    t0 = time.time()
    try:
        if stock_exists(ts_code, trade_date):
            logger.info(f"[价格] {ts_code} {trade_date} 已存在，跳过")
            log_run_db("price", ts_code, "skipped", 0, "already exists", time.time() - t0)
            return 0

        df = fetch_daily(ts_code, trade_date, trade_date)
        if df is None or len(df) == 0:
            log_run_db("price", ts_code, "empty", 0, "no data", time.time() - t0)
            return 0

        # yfinance 返回多日的，只保留目标日期
        target = str(trade_date)
        df = df[df["trade_date"].astype(str) == target]
        if len(df) == 0:
            log_run_db("price", ts_code, "empty", 0, f"no data for {trade_date}", time.time() - t0)
            return 0

        count = save_daily(df)
        log_run_db("price", ts_code, "success", count, "", time.time() - t0)
        return count

    except Exception as e:
        logger.error(f"[价格] {ts_code} {trade_date} 异常: {e}")
        log_run_db("price", ts_code, "error", 0, str(e), time.time() - t0)
        return 0


def run_batch(ts_codes: List[str], start_date, end_date=None) -> int:
    """批量采集多只股票多日行情"""
    total = 0
    for ts_code in ts_codes:
        df = fetch_daily(ts_code, start_date, end_date)
        if df is not None and len(df) > 0:
            conn = get_conn()
            existing = conn.execute(
                "SELECT trade_date FROM stock_daily WHERE ts_code=?",
                [ts_code]
            ).fetchall()
            existing_dates = set(r[0] for r in existing)

            new_df = df[~df["trade_date"].isin(existing_dates)]
            if len(new_df) > 0:
                total += save_daily(new_df)
                logger.info(f"[价格] {ts_code} 新增 {len(new_df)} 条")
            else:
                logger.info(f"[价格] {ts_code} 全部已存在，跳过")
        time.sleep(0.3)

    logger.info(f"[价格] 批量完成，共新增 {total} 条记录")
    return total
