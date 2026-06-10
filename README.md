# StockOxHores 📈

A股 + 美股每日行情与新闻数据采集系统。自建爬虫 + yfinance 驱动，DuckDB 本地存储，轻量 Web 管理前端。

## 快速开始

```bash
# 1. 装依赖
pip3.12 install --break-system-packages --user -r requirements.txt

# 2. 初始化数据库
python3 -c "from db import init_db; init_db()"

# 3. 回填历史数据
python3 backfill.py --months 12

# 4. 启动管理前端
python3 serve.py
# → http://127.0.0.1:8766
```

## 项目结构

```
StockOxHores/
├── config.yaml           # 自选股配置（支持多种格式）
├── requirements.txt      # 依赖清单
├── db/
│   ├── schema.sql        # DuckDB 建表（5张表）
│   └── __init__.py       # DB 连接 + 代码标准化
├── scraper/
│   ├── base.py           # 爬虫基类（UA轮换/重试/日志）
│   ├── price.py          # yfinance 行情采集
│   ├── news_eastmoney.py # 东方财富新闻爬虫
│   ├── news_sina.py      # 新浪财经新闻爬虫
│   └── news_cls.py       # 财联社宏观快讯爬虫
├── pipeline.py           # 主编排（单日全流程）
├── backfill.py           # 历史回填入口
├── daily.py              # 每日运行入口
├── query.py              # 终端查询工具
├── serve.py              # FastAPI 服务端
└── templates/
    └── index.html        # 管理面板（深色 Terminal 风格）
```

## 股票代码格式

配置文件 `config.yaml` 支持任意格式，系统自动标准化：

| 你写的 | 自动转成 | 说明 |
|--------|---------|------|
| `300750` | `300750.SZ` | 纯数字6位→A股（3/0/2深交所，6/9上交所） |
| `SH600519` | `600519.SH` | SH/SZ前缀自动去 |
| `NVDA` | `NVDA` | 纯字母→美股原样 |
| `000001.SZ` | `000001.SZ` | 已有后缀不变 |

## 日常命令

```bash
# 采集今天
python3 daily.py

# 补某天
python3 daily.py --date 2026-06-09

# 回填历史
python3 backfill.py --months 12

# 查询数据
python3 query.py stats                    # 数据统计
python3 query.py stock 300750.SZ          # 个股行情
python3 query.py stock 300750.SZ --days 60
python3 query.py top --date 2026-06-09    # 涨跌排行
python3 query.py news 300750.SZ           # 个股新闻
python3 query.py macro                    # 宏观快讯

# 启动前端
python3 serve.py                          # → http://127.0.0.1:8766
python3 serve.py --port 8888              # 指定端口
```

## 数据来源

| 数据 | 来源 | 方式 |
|------|------|------|
| A股行情 | yfinance (Yahoo Finance) | API |
| 美股行情 | yfinance | API |
| 个股新闻 | 新浪财经 | HTML 爬虫 |
| 个股新闻 | 东方财富 | API（受限） |
| 宏观快讯 | 财联社 | API（待修复） |

## 设计风格

前端基于 [design-taste-frontend](https://github.com) 反AI默认设计理念：
- 深色 Terminal 金融风（zinc-900 + cyan 强调 + 绿涨红跌）
- 三旋钮：VARIANCE=3 / MOTION=2 / DENSITY=6
- 无 AI 默认紫色渐变
- 单一字体系统、单一强调色
- Tailwind CSS + Alpine.js（零构建、零 npm）

## License

MIT
