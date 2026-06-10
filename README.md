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
├── config.yaml          # 自选股（支持多种格式）
├── daily.py             # 每日采集入口（Hermes cronjob 调用）
├── backfill.py          # 历史回填
├── pipeline.py          # 主编排
├── query.py             # CLI 查询
├── serve.py             # Web 管理前端（FastAPI）
├── db/
│   ├── schema.sql       # DuckDB 5张表
│   └── __init__.py      # DB 连接 + 代码标准化
├── scraper/
│   ├── price.py         # yfinance 行情（仅关联用）
│   ├── news_sina.py     # 新浪财经新闻爬虫
│   ├── news_eastmoney.py# 东方财富（待修复）
│   └── news_cls.py      # 财联社宏观快讯（待修复）
└── templates/
    └── index.html       # 前端（时间线式信息流）
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
python3 backfill.py --months 12           # 回填历史
python3 backfill.py --months 12 --with-news  # 带新闻回填
```

## 前端

```bash
python3 serve.py          # http://127.0.0.1:8766
```

| Tab | 内容 |
|-----|------|
| 今 | 今日新闻按标的分组 + 宏观时间线 |
| 标的 | 选中标的的全部新闻时间线 |
| 新闻 | 全局搜索（关键词/日期/标的过滤） |
| 宏观 | 政策/宏观快讯时间线 |
| 日志 | 采集运行日志 |

## Roadmap

- [x] 新闻采集（新浪财经）
- [x] 宏观快讯采集
- [x] 管理前端
- [x] 每日定时任务
- [ ] 新闻情感分析（sentiment scoring）
- [ ] 事件-股价关联匹配
- [ ] 历史模式识别
- [ ] 趋势预测
- [ ] 与 StockWatcher 数据互通

## 设计

基于 [design-taste-frontend](https://github.com) 反AI默认设计理念。
- 深色 Terminal 风，单强调色 cyan
- 信息密度优先（DENSITY=7）
- 时间线式信息流阅读
- 无 emoji、无 AI 紫色渐变
