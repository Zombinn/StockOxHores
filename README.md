# StockOxHores ⊕ 情报匹配系统

信息搜集 → 新闻匹配 → 事件归因 → 趋势预测。

基于历史事件数据库，匹配新闻与股价变动，预测走向及未来影响因素。

## 定位

| 系统 | 职责 |
|------|------|
| [StockWatcher](https://github.com/Zombinn/StockWatcher) | 行情分析、股价图表、技术指标 |
| **StockOxHores** | 情报搜集、新闻匹配、事件归因、预测 |

两者互补：StockWatcher 告诉你 **发生了什么**，StockOxHores 告诉你 **为什么发生**。

## 项目结构

```
StockOxHores/
├── config.yaml           # 自选股（支持多种格式）
├── daily.py              # 每日采集入口（Hermes cronjob 调用）
├── backfill.py           # 历史回填
├── analyze.py            # CLI 分析工具
├── pipeline.py           # 主编排
├── query.py              # CLI 查询
├── serve.py              # Web 管理前端（FastAPI）
├── analysis/
│   ├── sentiment.py      # 中文金融情感分析（关键词词典）
│   └── correlation.py    # 事件-股价关联匹配
├── db/
│   ├── schema.sql        # DuckDB 5张表
│   └── __init__.py       # DB 连接 + 代码标准化
├── scraper/
│   ├── price.py          # yfinance 行情（仅关联用）
│   ├── news_sina.py      # 新浪财经新闻爬虫
│   ├── news_eastmoney.py # 东方财富（待修复）
│   └── news_cls.py       # 财联社宏观快讯（待修复）
└── templates/
    └── index.html        # 前端（时间线式信息流）
```

## 定时任务

每日 17:00（A股收盘后）自动运行，采集当日新闻+宏观快讯。

```bash
hermes cron ls                    # 查看定时任务
hermes cron run 071837a8b914      # 手动触发一次
hermes cron pause 071837a8b914    # 暂停
```

也可手动运行：

```bash
python3 daily.py                          # 采集今天
python3 daily.py --date 2026-06-09        # 补某天
python3 backfill.py --months 12           # 回填历史（仅行情）
python3 backfill.py --months 12 --with-news  # 回填含新闻
```

## 分析工具

### 情感评分

基于中文金融关键词词典（150+利好词 + 150+利空词），对新闻标题自动评分：

```bash
# 回填所有未评分新闻的情感分
python3 analyze.py sentiment

# 只评前100条
python3 analyze.py sentiment --limit 100
```

评分规则：
- **+2** 非常正面：`涨停` `超预期` `历史新高` `中标大单`
- **+1** 正面：`增长` `盈利` `回购` `战略合作`
- **0** 中性：无情感倾向
- **-1** 负面：`减持` `亏损` `违规` `立案`
- **-2** 非常负面：`跌停` `暴雷` `退市` `财务造假`

支持否定词反转（"没有下跌" → 正面）和强化词检测（"大幅增长" → 非常正面）。

### 事件-股价关联

```bash
# 某天各股新闻+涨跌幅
python3 analyze.py day 2026-06-09

# 单只股票近N天新闻价格时间线
python3 analyze.py stock 300750.SZ --days 60

# 情感总览（正负面分布）
python3 analyze.py summary --days 7

# JSON 输出
python3 analyze.py day 2026-06-09 --json
```

### API 端点

```bash
GET /api/analysis/sentiment-summary?days=7
GET /api/analysis/day/2026-06-09
GET /api/analysis/stock/300750.SZ?days=30
```

## 前端

```bash
python3 serve.py                       # http://0.0.0.0:8767 (局域网可访问)
python3 serve.py --port 8766           # 指定端口
```

| Tab | 内容 |
|-----|------|
| 今 | 今日新闻按标的分组 + 宏观时间线 |
| 标的 | 选中标的的全部新闻时间线 |
| 新闻 | 全局搜索（关键词/日期/标的过滤） |
| 宏观 | 政策/宏观快讯时间线 |
| 分析 | 情感总览 + 新闻-涨跌-成交量关联 + 个股三围时间线 |
| 日志 | 采集运行日志 |

## 数据流

```
每日 17:00 (cronjob)
    │
    ├─ ① 新浪财经 → 个股新闻 → DuckDB.stock_news
    ├─ ② yfinance → 日线行情 → DuckDB.stock_daily（关联用）
    └─ ③ 财联社 → 宏观快讯 → DuckDB.macro_events
                    │
                    ▼
             情感分析 (sentiment.py)
                    │
                    ▼
             事件-股价关联 (correlation.py)
                    │
                    ▼
             前端展示 / API 查询
```

## Roadmap

- [x] 新闻采集（新浪财经）
- [x] 宏观快讯采集
- [x] 管理前端
- [x] 每日定时任务
- [x] 新闻情感分析（关键词词典）
- [x] 事件-股价关联匹配
- [x] 情感分析接入前端 Tab
- [ ] 历史模式识别（类似事件检索）
- [ ] 趋势预测（基于历史信号）
- [ ] 与 StockWatcher 数据互通
