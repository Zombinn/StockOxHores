"""新闻情感分析 — 基于中文金融关键词

用法:
  from analysis.sentiment import score_news, batch_score
  
  score = score_news("宁德时代三季度净利润同比增长67%")  # → 2 (非常正面)
  
  # 批量回填已有新闻
  python -c "from analysis.sentiment import batch_score; batch_score()"
"""
import re
import logging
from datetime import date
from typing import Optional

from db import get_conn

logger = logging.getLogger("stock-whisper.sentiment")

# ─── 中文金融情感词典 ───

POSITIVE_WORDS = {
    # 上涨/大涨
    "涨停", "大涨", "暴涨", "飙升", "猛涨", "走强", "强势", "拉升",
    "突破", "创新高", "新高", "历史新高", "反弹", "回暖", "企稳",
    "放量", "放量上涨", "量价齐升", "触底反弹",
    # 业绩/盈利
    "盈利", "净利润", "营收增长", "利润增长", "业绩增长", "大幅增长",
    "超预期", "超出预期", "同比大增", "环比增长", "扭亏为盈", "盈喜",
    "预增", "业绩预增", "财报亮眼",
    # 利好事件
    "中标", "获得订单", "大单", "签单", "战略合作", "合作",
    "收购", "并购", "重组", "资产注入", "借壳", "股权激励",
    "增持", "回购", "分红", "派息", "高送转",
    "政策利好", "扶持", "补贴", "减税", "降息", "降准",
    "批准", "获批", "核准", "注册生效", "过会",
    # 评级
    "买入", "增持", "推荐", "看好", "给予买入", "维持买入",
    "看好后市", "乐观", "积极", "正面",
    "龙头", "领军", "领先", "优势", "核心竞争力",
}

NEGATIVE_WORDS = {
    # 下跌/大跌
    "跌停", "大跌", "暴跌", "狂跌", "跳水", "走弱", "疲软", "低迷",
    "破位", "新低", "创新低", "腰斩", "阴跌", "下挫",
    "缩量", "缩量下跌", "放量下跌", "量价背离",
    # 业绩/亏损
    "亏损", "净亏损", "净利润下降", "营收下降", "利润下滑", "大幅下降",
    "不及预期", "低于预期", "同比大跌", "环比下降", "盈警", "预亏",
    "预减", "业绩预减", "业绩变脸", "财务造假", "暴雷",
    "st", "退市", "暂停上市", "戴帽",
    # 利空事件
    "减持", "套现", "质押", "平仓", "强平", "违约", "债务",
    "违规", "处罚", "罚款", "调查", "立案", "监管", "问询",
    "警示", "通报批评", "公开谴责", "诉讼", "仲裁",
    "解禁", "限售股解禁", "减持计划",
    "利空", "黑天鹅", "灰犀牛",
    "降级", "卖出", "减持评级", "看空", "悲观", "负面",
    "下调", "调低",
    # 外部冲击
    "制裁", "禁令", "脱钩", "断供", "加税", "关税",
    "停工", "停产", "限产", "减产", "裁员",
    "事故", "爆炸", "火灾", "停产整顿",
}

# 强化词（增强情感强度）
INTENSIFIERS = {
    "大幅", "显著", "极度", "严重", "剧烈", "暴涨", "暴跌",
    "历史", "空前", "惊人", "罕见", "疯狂",
}

# 反转词（后面的正面词可能被反转）
NEGATORS = {"不", "未", "无", "没有", "并非", "并非"}


def score_title(title: str) -> int:
    """
    对新闻标题进行情感评分

    Returns:
        -2 非常负面 (有明显的强烈利空关键词)
        -1 负面 (有一个或多个利空关键词)
         0 中性/无情绪
        +1 正面 (有一个或多个利好关键词)
        +2 非常正面 (有明显的强烈利好关键词)
    """
    if not title:
        return 0

    text = title.lower()

    # 统计正面/负面词
    pos_count = 0
    neg_count = 0
    pos_intense = False
    neg_intense = False

    for word in POSITIVE_WORDS:
        if word in text:
            # 检查前面是否有否定词
            idx = text.find(word)
            prefix = text[max(0, idx - 3):idx].strip()
            if any(neg in prefix for neg in NEGATORS):
                neg_count += 1  # "没有上涨" → 负面
            else:
                pos_count += 1
                if word in INTENSIFIERS:
                    pos_intense = True

    for word in NEGATIVE_WORDS:
        if word in text:
            idx = text.find(word)
            prefix = text[max(0, idx - 3):idx].strip()
            if any(neg in prefix for neg in NEGATORS):
                pos_count += 1  # "没有下跌" → 正面
            else:
                neg_count += 1
                if word in INTENSIFIERS:
                    neg_intense = True

    # 计算净情感
    net = pos_count - neg_count

    # 映射到 -2 ~ +2
    if net > 0:
        if net >= 2 or pos_intense:
            return 2
        return 1
    elif net < 0:
        if net <= -2 or neg_intense:
            return -2
        return -1
    return 0


def batch_score(limit: Optional[int] = None):
    """
    批量回填 stock_news 表中未评分新闻的情感分数

    Args:
        limit: 最大处理条数（None = 全部）
    """
    conn = get_conn()
    
    rows = conn.execute(
        "SELECT rowid, title, ts_code, news_date FROM stock_news WHERE sentiment = 0 OR sentiment IS NULL"
    ).fetchall()
    
    if limit:
        rows = rows[:limit]

    if not rows:
        logger.info("[情感] 没有未评分的新闻")
        return 0

    updated = 0
    for row in rows:
        rowid, title, ts_code, news_date = row
        score = score_title(title)
        conn.execute(
            "UPDATE stock_news SET sentiment = ? WHERE rowid = ?",
            [score, rowid]
        )
        updated += 1
        if updated % 100 == 0:
            conn.commit()
            logger.info(f"[情感] 已处理 {updated}/{len(rows)}")

    conn.commit()
    logger.info(f"[情感] 完成: {updated} 条新闻已评分")
    return updated


def sentiment_label(score: int) -> str:
    """情感分数转标签"""
    return {2: "非常正面", 1: "正面", 0: "中性", -1: "负面", -2: "非常负面"}.get(score, "未知")


if __name__ == "__main__":
    # 测试
    tests = [
        ("宁德时代三季度净利润同比增长67%", 2),
        ("贵州茅台股价大跌5%，创年内新低", -2),
        ("公司发布公告，召开股东大会", 0),
        ("央行降息0.25个百分点，利好股市", 2),
        ("股东减持计划引发市场担忧", -1),
        ("中兴通讯中标5G大单", 2),
        ("公司涉嫌财务造假被立案调查", -2),
        ("今日收盘持平", 0),
    ]
    for title, expected in tests:
        result = score_title(title)
        status = "✅" if result == expected else "❌"
        print(f"{status} '{title[:30]}...' → {result} (expect {expected})")
