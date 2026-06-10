-- Stock Watcher 数据库 Schema (DuckDB)

-- 个股日线行情
CREATE TABLE IF NOT EXISTS stock_daily (
    ts_code      VARCHAR,
    trade_date   DATE,
    open         DOUBLE,
    high         DOUBLE,
    low          DOUBLE,
    close        DOUBLE,
    pre_close    DOUBLE,
    change_pct   DOUBLE,
    vol          DOUBLE,
    amount       DOUBLE,
    turn         DOUBLE,
    PRIMARY KEY (ts_code, trade_date)
);

-- 个股新闻（去重靠 UNIQUE 约束）
CREATE TABLE IF NOT EXISTS stock_news (
    ts_code      VARCHAR,
    news_date    DATE,
    news_time    TIMESTAMP,
    source       VARCHAR,
    title        VARCHAR,
    url          VARCHAR,
    content_abs  VARCHAR,
    sentiment    INTEGER DEFAULT 0,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(ts_code, news_date, title)
);

-- 宏观/行业事件
CREATE TABLE IF NOT EXISTS macro_events (
    event_date   DATE,
    event_time   TIMESTAMP,
    category     VARCHAR,
    title        VARCHAR,
    content      VARCHAR,
    source       VARCHAR,
    importance   INTEGER DEFAULT 3,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(event_date, title)
);

-- 每日汇总
CREATE TABLE IF NOT EXISTS daily_summary (
    trade_date   DATE PRIMARY KEY,
    summary      VARCHAR,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 运行日志
CREATE TABLE IF NOT EXISTS run_log (
    run_date     DATE,
    module       VARCHAR,
    ts_code      VARCHAR,
    status       VARCHAR,
    records      INTEGER DEFAULT 0,
    message      VARCHAR,
    duration_s   DOUBLE,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
