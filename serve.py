#!/usr/bin/env python3
"""StockOxHores HTTP Server

启动:
  python serve.py              # 开发模式, http://localhost:8765
  python serve.py --port 8080  # 指定端口
"""
import sys
import argparse
import logging
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse

from db import get_conn, CONFIG, get_stocks

logger = logging.getLogger("stock-watcher.server")
app = FastAPI(title="StockOxHores")

PROJECT_ROOT = Path(__file__).resolve().parent


@app.get("/", response_class=HTMLResponse)
async def index():
    return (PROJECT_ROOT / "templates" / "index.html").read_text(encoding="utf-8")


# ─── API: 统计 ───

@app.get("/api/stats")
async def get_stats():
    conn = get_conn()
    stocks = conn.execute("SELECT COUNT(DISTINCT ts_code) FROM stock_daily").fetchone()[0]
    price = conn.execute("SELECT COUNT(*) FROM stock_daily").fetchone()[0]
    news = conn.execute("SELECT COUNT(*) FROM stock_news").fetchone()[0]
    macro = conn.execute("SELECT COUNT(*) FROM macro_events").fetchone()[0]
    logs = conn.execute("SELECT COUNT(*) FROM run_log").fetchone()[0]
    return {
        "stocks": stocks or 0,
        "price_records": price or 0,
        "news_records": news or 0,
        "macro_records": macro or 0,
        "log_records": logs or 0,
    }


@app.get("/api/stocks")
async def get_stocks():
    conn = get_conn()
    rows = conn.execute(
        "SELECT DISTINCT ts_code FROM stock_daily ORDER BY ts_code"
    ).fetchall()
    return [r[0] for r in rows] if rows else get_stocks()


@app.get("/api/stocks/names")
async def get_stock_names_api():
    from db import get_stock_names
    return get_stock_names()


# ─── API: 看板 ───

@app.get("/api/dashboard/top")
async def get_top_movers(date_str: Optional[str] = Query(None, alias="date")):
    conn = get_conn()
    trade_date = date_str or str(date.today())
    rows = conn.execute(
        """SELECT ts_code, close, change_pct, vol
           FROM stock_daily
           WHERE trade_date = ?
           ORDER BY change_pct DESC
           LIMIT 5""",
        [trade_date]
    ).fetchall()
    return [
        {"ts_code": r[0], "close": float(r[1]), "change_pct": float(r[2]),
         "vol": float(r[3]) if r[3] else None}
        for r in rows
    ]


@app.get("/api/dashboard/summary")
async def get_latest_summary():
    conn = get_conn()
    row = conn.execute(
        "SELECT summary FROM daily_summary ORDER BY trade_date DESC LIMIT 1"
    ).fetchone()
    return row[0] if row else None


# ─── API: 个股行情 ───

@app.get("/api/stock/{ts_code}")
async def get_stock_detail(ts_code: str, days: int = Query(60, alias="days")):
    conn = get_conn()
    end = date.today()
    start = end - timedelta(days=days)
    rows = conn.execute(
        """SELECT trade_date, open, high, low, close, change_pct, vol, turn
           FROM stock_daily
           WHERE ts_code = ? AND trade_date >= ? AND trade_date <= ?
           ORDER BY trade_date ASC""",
        [ts_code, str(start), str(end)]
    ).fetchall()
    return [
        {
            "trade_date": str(r[0]),
            "open": float(r[1]) if r[1] else None,
            "high": float(r[2]) if r[2] else None,
            "low": float(r[3]) if r[3] else None,
            "close": float(r[4]) if r[4] else None,
            "change_pct": float(r[5]) if r[5] else None,
            "vol": float(r[6]) if r[6] else None,
            "turn": float(r[7]) if r[7] else None,
        }
        for r in rows
    ]


# ─── API: 个股新闻 ───

@app.get("/api/stock/{ts_code}/news")
async def get_stock_news(ts_code: str, limit: int = Query(30, alias="limit")):
    conn = get_conn()
    rows = conn.execute(
        """SELECT news_date, news_time, source, title, url
           FROM stock_news
           WHERE ts_code = ?
           ORDER BY news_date DESC, news_time DESC NULLS LAST
           LIMIT ?""",
        [ts_code, limit]
    ).fetchall()
    return [
        {
            "ts_code": ts_code,
            "news_date": str(r[0]),
            "news_time": str(r[1])[:19] if r[1] else None,
            "source": r[2],
            "title": r[3],
            "url": r[4],
        }
        for r in rows
    ]


# ─── API: 全量新闻 ───

@app.get("/api/news")
async def get_news(
    q: Optional[str] = Query(None, alias="q"),
    date_str: Optional[str] = Query(None, alias="date"),
    ts_code: Optional[str] = Query(None, alias="ts_code"),
    limit: int = Query(50, alias="limit"),
):
    conn = get_conn()
    conditions = []
    params = []

    if date_str:
        conditions.append("news_date = ?")
        params.append(date_str)
    if ts_code:
        conditions.append("ts_code = ?")
        params.append(ts_code)

    where = " AND ".join(conditions) if conditions else "1=1"
    rows = conn.execute(
        f"""SELECT ts_code, news_date, news_time, source, title, url
            FROM stock_news
            WHERE {where}
            ORDER BY news_date DESC, news_time DESC NULLS LAST
            LIMIT ?""",
        params + [limit]
    ).fetchall()

    results = []
    for r in rows:
        title = r[4]
        # Client-side search filter (SQLite FTS5 not guaranteed)
        if q and q.lower() not in title.lower():
            continue
        results.append({
            "ts_code": r[0],
            "news_date": str(r[1]),
            "news_time": str(r[2])[:19] if r[2] else None,
            "source": r[3],
            "title": title,
            "url": r[5],
        })
    return results[:limit]


# ─── API: 宏观快讯 ───

@app.get("/api/macro")
async def get_macro(
    date_str: Optional[str] = Query(None, alias="date"),
    limit: int = Query(50, alias="limit"),
):
    conn = get_conn()
    if date_str:
        rows = conn.execute(
            """SELECT event_date, event_time, category, title, content, importance
               FROM macro_events
               WHERE event_date = ?
               ORDER BY importance DESC, event_time DESC NULLS LAST
               LIMIT ?""",
            [date_str, limit]
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT event_date, event_time, category, title, content, importance
               FROM macro_events
               ORDER BY event_date DESC, importance DESC
               LIMIT ?""",
            [limit]
        ).fetchall()

    return [
        {
            
            "event_date": str(r[0]),
            "event_time": str(r[1])[:19] if r[1] else None,
            "category": r[2],
            "title": r[3],
            "content": r[4][:500] if r[4] else None,
            "importance": r[5],
        }
        for r in rows
    ]


# ─── API: 运行日志 ───

@app.get("/api/logs")
async def get_logs(limit: int = Query(100, alias="limit")):
    conn = get_conn()
    rows = conn.execute(
        """SELECT run_date, module, ts_code, status, records, message, duration_s
           FROM run_log
           ORDER BY created_at DESC
           LIMIT ?""",
        [limit]
    ).fetchall()
    return [
        {
            "run_date": str(r[0]),
            "module": r[1],
            "ts_code": r[2],
            "status": r[3],
            "records": r[4] or 0,
            "message": r[5],
            "duration_s": float(r[6]) if r[6] else None,
        }
        for r in rows
    ]


# ─── API: 情感分析 ───

@app.get("/api/analysis/sentiment-summary")
async def get_sentiment_summary(days: int = Query(7, alias="days")):
    from analysis.correlation import sentiment_summary
    return sentiment_summary(days=days)


@app.get("/api/analysis/day/{date_str}")
async def get_day_analysis(date_str: str):
    from analysis.correlation import day_correlation
    return day_correlation(date_str)


@app.get("/api/analysis/stock/{ts_code}")
async def get_stock_analysis(ts_code: str, days: int = Query(30, alias="days")):
    from analysis.correlation import stock_correlation
    return stock_correlation(ts_code, days=days)


# ─── API: 任务管理 ───

import subprocess
import json as json_mod

HERMES = "/Users/zombin/.hermes/hermes-agent/venv/bin/hermes"


def _hermes_cron(args: list) -> dict:
    try:
        r = subprocess.run([HERMES, "cron"] + args, capture_output=True, text=True, timeout=15)
        output = r.stdout
        # Parse formatted table into structured data
        jobs = []
        current = {}
        for line in output.split("\n"):
            line = line.strip()
            if not line or line.startswith("─") or line.startswith("┌") or line.startswith("└") or line.startswith("│"):
                continue
            if "Scheduled Jobs" in line or "No jobs" in line:
                continue
            if line.startswith("⚠"):
                continue
            # Job ID line
            parts = line.split()
            if len(parts) >= 2 and len(parts[0]) == 12 and all(c in "0123456789abcdef" for c in parts[0].lower()):
                if current:
                    jobs.append(current)
                current = {"job_id": parts[0], "state": parts[1].strip("[]")}
            elif current:
                for prefix in ["Name:", "Schedule:", "Repeat:", "Next run:", "Deliver:", "Script:", "Last run:"]:
                    if line.startswith(prefix):
                        val = line[len(prefix):].strip()
                        key = prefix.lower().replace(" ", "_").replace(":", "")
                        if key == "last_run":
                            # Parse "2026-06-11T17:09:21.454762+10:00  error: ..."
                            if "  error:" in val:
                                ts, err = val.split("  error:", 1)
                                current["last_run_at"] = ts.strip()
                                current["last_status"] = "error"
                                current["last_error"] = err.strip()
                            else:
                                current["last_run_at"] = val
                                current["last_status"] = "success"
                        elif key == "next_run":
                            current["next_run_at"] = val
                        elif key == "repeat":
                            current["repeat"] = "forever" if val in ("∞", "forever") else val
                        else:
                            current[key] = val
        if current:
            jobs.append(current)
        return {"ok": r.returncode == 0, "output": output, "jobs": jobs, "error": r.stderr}
    except Exception as e:
        return {"ok": False, "error": str(e), "jobs": []}


@app.get("/api/cron")
async def list_cron():
    return _hermes_cron(["list"])


@app.get("/api/cron/{job_id}/run")
async def run_cron(job_id: str):
    return _hermes_cron(["run", job_id])


@app.get("/api/cron/{job_id}/pause")
async def pause_cron(job_id: str):
    return _hermes_cron(["pause", job_id])


@app.get("/api/cron/{job_id}/resume")
async def resume_cron(job_id: str):
    return _hermes_cron(["resume", job_id])


@app.get("/api/cron/{job_id}/update")
async def update_cron(job_id: str, name: str = "", schedule: str = ""):
    args = ["update", job_id]
    if name:
        args += ["--name", name]
    if schedule:
        args += ["--schedule", schedule]
    return _hermes_cron(args)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="StockOxHores Server")
    parser.add_argument("--port", type=int, default=8767, help="监听端口（默认 8767）")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="监听地址（默认 127.0.0.1）")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    print(f"  ┌────────────────────────────────────┐")
    print(f"  │  📈 StockOxHores                  │")
    print(f"  │  http://{args.host}:{args.port}                │")
    print(f"  └────────────────────────────────────┘")

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
