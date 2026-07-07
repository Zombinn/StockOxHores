"""DuckDB 数据库工具模块"""
import os
import duckdb
import yaml
from pathlib import Path
from typing import Optional, List


def normalize_code(code: str) -> str:
    """
    智能标准化股票代码为内部格式:
      300750      → 300750.SZ  (纯数字6位 → A股深交所)
      600519      → 600519.SH  (纯数字6位以6开头 → 上交所)
      SH600519    → 600519.SH  (SH前缀去前缀)
      SZ300750    → 300750.SZ  (SZ前缀去前缀)
      NVDA/TSLA/AAPL → NVDA/TSLA/AAPL (字母 → 美股原样)
      300750.SZ   → 300750.SZ  (已有后缀不变)
    """
    c = code.strip().upper()

    # 已有正确后缀
    if c.endswith(".SZ") or c.endswith(".SH") or c.endswith(".SS"):
        return c

    # 去掉 SH/SZ 前缀
    if c.startswith("SH"):
        return c[2:] + ".SH"
    if c.startswith("SZ"):
        return c[2:] + ".SZ"

    # 纯数字6位 → A股
    if c.isdigit() and len(c) == 6:
        if c.startswith("6") or c.startswith("9"):
            return c + ".SH"
        return c + ".SZ"

    # 纯字母 → 美股，原样
    if c.isalpha():
        return c

    # 其他 → 原样
    return code.strip()


def get_stocks() -> List[str]:
    """读取并标准化配置中的股票列表"""
    try:
        import yaml
        cfg = yaml.safe_load((PROJECT_ROOT / "config.yaml").read_text())
        return [normalize_code(s) for s in cfg.get("stocks", [])]
    except Exception:
        return []


def get_stock_names() -> dict:
    """实时读取股票名称映射"""
    try:
        from pathlib import Path
        import yaml
        cfg = yaml.safe_load((PROJECT_ROOT / "config.yaml").read_text())
        return cfg.get("stock_names", {})
    except Exception:
        return {}

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 加载配置
with open(PROJECT_ROOT / "config.yaml") as f:
    CONFIG = yaml.safe_load(f)
# 数据库路径
DB_PATH = PROJECT_ROOT / CONFIG["db_path"]


def get_conn(read_only: bool = False) -> duckdb.DuckDBPyConnection:
    """获取数据库连接"""
    conn = duckdb.connect(str(DB_PATH), read_only=read_only)
    if not read_only:
        conn.execute("SET enable_progress_bar=false")
    return conn


def init_db():
    """初始化数据库：执行建表 DDL"""
    conn = get_conn()
    schema_path = PROJECT_ROOT / "db" / "schema.sql"
    ddl = schema_path.read_text()
    conn.execute(ddl)
    conn.commit()
    # print(f"[DB] 数据库已初始化: {DB_PATH}")


def insert_df(df, table: str):
    """将 DataFrame 写入指定表（upsert 语义：INSERT OR REPLACE）"""
    if df is None or len(df) == 0:
        return 0
    conn = get_conn()
    # 使用 DuckDB 的 CREATE OR REPLACE TEMP TABLE + INSERT 来模拟 upsert
    # 更好的做法是用 DuckDB 的 INSERT OR REPLACE
    conn.execute(f"CREATE TEMP SEQUENCE IF NOT EXISTS tmp_seq")
    conn.register("_tmp_df", df)
    
    # 获取表的所有列（排除自增的 id 和 created_at）
    cols = conn.execute(f"""
        SELECT column_name FROM information_schema.columns 
        WHERE table_name = '{table}' 
          AND column_name NOT IN ('id', 'created_at')
        ORDER BY ordinal_position
    """).fetchall()
    col_names = ", ".join(c[0] for c in cols if c[0] not in ('id', 'created_at'))
    
    # 检查表是否有主键/唯一约束来决定是 INSERT 还是 INSERT OR REPLACE
    try:
        conn.execute(f"""
            INSERT OR REPLACE INTO {table}
            SELECT {col_names} FROM _tmp_df
        """)
        count = conn.execute("SELECT COUNT(*) FROM _tmp_df").fetchone()[0]
        conn.commit()
        return count
    finally:
        conn.execute("DROP VIEW IF EXISTS _tmp_df")


def execute(query: str, params=None):
    """执行 SQL 查询"""
    conn = get_conn()
    if params:
        return conn.execute(query, params)
    return conn.execute(query)


def fetch_all(query: str, params=None):
    """查询并返回所有结果"""
    return execute(query, params).fetchall()


def fetch_one(query: str, params=None):
    """查询并返回单条结果"""
    return execute(query, params).fetchone()


def close():
    """关闭数据库连接"""
    global _conn
    if _conn:
        _conn.close()
        _conn = None


def stock_exists(ts_code: str, trade_date) -> bool:
    """检查某日行情是否已存在"""
    row = fetch_one(
        "SELECT 1 FROM stock_daily WHERE ts_code=? AND trade_date=?",
        [ts_code, str(trade_date)]
    )
    return row is not None


def stock_news_exists(ts_code: str, trade_date, title: str) -> bool:
    """检查某条新闻是否已存在"""
    row = fetch_one(
        "SELECT 1 FROM stock_news WHERE ts_code=? AND news_date=? AND title=?",
        [ts_code, str(trade_date), title]
    )
    return row is not None
