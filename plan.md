# Stock Watcher 数据采集系统 — 实施计划

> **目标:** 构建一个每天自动采集 A股 个股行情 + 对应新闻 + 宏观事件的爬虫系统，存入 DuckDB，支持查询和历史回填。

**架构:** Hermes Agent 驱动的 Python 数据管道。价格用 akshare（免费稳定），新闻自建爬虫（东方财富 + 新浪财经 + 财联社），存储用 DuckDB，定时用 Hermes cronjob。

**Tech Stack:** Python 3.11+, DuckDB, akshare, requests, BeautifulSoup4, lxml, schedule

**项目根目录:** `/Users/zombin/Public/yubin_boxes/hermes_cave/stock-watcher/`

---

## 数据库 Schema（DuckDB）

```sql
-- 个股日线行情
CREATE TABLE stock_daily (
    ts_code      VARCHAR,       -- 股票代码（如 000001.SZ）
    trade_date   DATE,
    open         DOUBLE,
    high         DOUBLE,
    low          DOUBLE,
    close        DOUBLE,
    pre_close    DOUBLE,
    change_pct   DOUBLE,        -- 涨跌幅 %
    vol          DOUBLE,        -- 成交量（手）
    amount       DOUBLE,        -- 成交额（万元）
    turn         DOUBLE,        -- 换手率 %
    PRIMARY KEY (ts_code, trade_date)
);

-- 个股新闻（每条新闻一条记录）
CREATE TABLE stock_news (
    id           BIGINT PRIMARY KEY,  -- 自增或外部ID
    ts_code      VARCHAR,             -- 相关股票
    news_date    DATE,
    news_time    TIMESTAMP,           -- 精确时间（可能为空）
    source       VARCHAR,             -- 来源（东财/新浪/财联社）
    title        VARCHAR,
    url          VARCHAR,
    content_abs  VARCHAR,             -- 摘要
    sentiment    INTEGER,             -- 情感：-2~2（后续NLP）
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 宏观/行业事件（政策、数据、外盘等）
CREATE TABLE macro_events (
    id           BIGINT PRIMARY KEY,
    event_date   DATE,
    event_time   TIMESTAMP,
    category     VARCHAR,       -- 宏观/行业/政策/资金
    title        VARCHAR,
    content      VARCHAR,
    source       VARCHAR,       -- 财联社/华尔街见闻/央行
    importance   INTEGER,       -- 1-5 重要程度
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 每日汇总（Markdown简报留档）
CREATE TABLE daily_summary (
    trade_date   DATE PRIMARY KEY,
    summary      VARCHAR,       -- Markdown 格式的一天总结
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## 项目文件结构

```
stock-watcher/
├── config.yaml                # 配置（股票列表、DB路径、爬虫间隔）
├── requirements.txt           # Python 依赖
├── db/
│   ├── __init__.py
│   └── schema.sql             # 建表 DDL
├── scraper/
│   ├── __init__.py
│   ├── price.py               # akshare → stock_daily
│   ├── news_eastmoney.py      # 东方财富个股新闻爬虫
│   ├── news_sina.py           # 新浪财经个股新闻爬虫
│   ├── news_cls.py            # 财联社快讯爬虫（宏观+行业）
│   └── base.py                # 爬虫基类（请求、重试、日志）
├── pipeline.py                # 主流程编排
├── backfill.py                # 历史回填入口
├── daily.py                   # cronjob 每日入口
└── query.py                   # 查询工具
```

---

## Phase 1 — 基础基建（本次实施）

### Task 1: 初始化项目结构
- 创建目录树
- 写 `requirements.txt`（duckdb, akshare>=1.14, requests, beautifulsoup4, lxml, pyyaml, httpx）
- 写 `config.yaml`（自选股列表、DB路径、爬虫设置）
- 写 `db/schema.sql`

### Task 2: 实现 DuckDB 工具模块
- `db/__init__.py` — 连接管理、建表、批量 insert 的公共函数

### Task 3: 价格模块 (scraper/price.py)
- 用 `akshare.stock_zh_a_hist()` 获取指定个股指定日期范围的日线
- 字段清洗、类型转换、写入 DuckDB

### Task 4: 东方财富新闻爬虫 (scraper/news_eastmoney.py)
- 接口：`https://search-api-web.eastmoney.com/search/jsonp`
- 按股票代码 + 日期范围搜索新闻
- 解析返回的 JSON，提取标题、摘要、发布时间、URL
- 去重写入 DuckDB

### Task 5: 新浪财经新闻爬虫 (scraper/news_sina.py)
- 接口：新浪财经个股新闻页
- 备用/补充新闻源

### Task 6: 财联社快讯爬虫 (scraper/news_cls.py)
- 爬取财联社电报快讯（宏观政策、行业动态）
- 时间线格式，每条快讯有时间戳

### Task 7: 主编排 (pipeline.py)
- `run_daily(ts_codes, date)` — 一天的数据采集流程
  - 1. 拉行情
  - 2. 拉个股新闻（多源）
  - 3. 拉宏观快讯
  - 4. 生成 daily_summary
- 去重逻辑：已有数据跳过

### Task 8: 历史回填 (backfill.py)
- 遍历每个股票、每个交易日的范围
- 分批调用 pipeline.run_daily()
- 进度显示 + 断点续传（检查 DB 已有数据）

### Task 9: 每日 cronjob
- Hermes `cronjob` 设定：每个交易日 15:30 运行
- 入口：`daily.py`
- 推送到用户（可选）

---

## Phase 2 — 增强（后续）
- 情感分析（sentiment on news）
- 龙虎榜数据
- 北向资金流向
- 研报摘要
- Web 查询界面

---

## 爬虫注意事项

1. **请求频率限制:** 东方财富 1 req/2s，新浪财经 1 req/1s，财联社 1 req/3s
2. **User-Agent 轮换:** 内置常见 UA 列表
3. **重试机制:** 失败自动重试 3 次，指数退避
4. **去重:** 按 (ts_code, news_date, title) 做唯一约束
5. **断点续传:** backfill 自动跳过已有数据
6. **节假日处理:** 跳过非交易日（利用 akshare.trade_cal 或自行判断）
