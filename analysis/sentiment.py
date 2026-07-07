"""新闻情感分析 — 中英文双语情感词典

自动检测新闻标题语言，使用对应的情感词典评分。

用法:
  from analysis.sentiment import score_title, batch_score
  score_title("宁德时代三季度净利润同比增长67%")  # → 2 (中文正面)
  score_title("NVIDIA Stock Surges on Strong Earnings")  # → 2 (英文正面)
"""
import re
import logging
from typing import Optional

from db import get_conn

logger = logging.getLogger("stock-whisper.sentiment")

# ─── 中文金融情感词典 ───

CN_POSITIVE = {
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
    "看好后市", "乐观", "积极", "正面", "利好",
    "龙头", "领军", "领先", "优势", "核心竞争力",
    # 通用正面词
    "增长", "上升", "提高", "增加", "向好",
}

CN_NEGATIVE = {
    # 下跌/大跌
    "跌停", "大跌", "暴跌", "狂跌", "跳水", "走弱", "疲软", "低迷",
    "破位", "新低", "创新低", "腰斩", "阴跌", "下挫",
    "缩量", "缩量下跌", "放量下跌", "量价背离",
    # 业绩/亏损
    "亏损", "净亏损", "净利润下降", "营收下降", "利润下滑", "大幅下降",
    "不及预期", "低于预期", "同比大跌", "环比下降", "盈警", "预亏",
    "预减", "业绩预减", "业绩变脸", "财务造假", "暴雷",
    "退市", "暂停上市", "戴帽",  # 注意: 不用 "st" — 会误匹配英文单词
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

# ─── 英文金融情感词典（子串匹配，注意避免短词误匹配）───

EN_POSITIVE = {
    # 上涨/大涨
    "surge", "soar", "rally", "rallied", "rallies", "skyrocket",
    "jump", "jumped", "jumping", "climb", "climbed", "climbing",
    "rise", "rose", "rising", "gain", "gained", "gaining",
    "boost", "boosted", "boosting", "pop", "popped",
    "upgrade", "upgraded", "upgrading", "upbeat", "uptick", "upside",
    "outperform", "outperformed", "outperforming",
    "bullish", "bull run", "bull market",
    "breakout", "break out",
    "record high", "all-time high", "new high", "新高",
    "recovery", "recover", "rebound", "rebounded",
    # 业绩/盈利
    "beat earnings", "earnings beat", "profit beat",
    "strong earnings", "strong quarter", "strong results",
    "profit", "profitable", "profitability",
    "grow", "grew", "growth", "growing",
    "margin expansion", "revenue growth", "sales growth",
    "dividend", "buyback", "share buyback",
    "exceed expectations", "above expectations",
    "record profit", "record revenue", "record sales",
    # 利好事件
    "approval", "approved", "cleared", "greenlight",
    "positive outlook", "positive rating",
    "overweight", "buy rating", "strong buy",
    "upgraded to", "upgrade to",
    "synergy", "synergies",
    "expansion", "expand", "expanding",
    "innovate", "innovation", "innovative",
    "leader", "leading", "leadership",
    "momentum", "accelerate", "accelerating",
    # 通用正面词
    "record", "high", "strong", "stronger",
    "rise", "rose", "rising", "gain", "gained", "gaining",
}

EN_NEGATIVE = {
    # 下跌/大跌
    "plummet", "plummeted", "plummeting",
    "plunge", "plunged", "plunging",
    "slump", "slumped", "slumping",
    "tumble", "tumbled", "tumbling",
    "crash", "crashed", "crashing", "meltdown",
    "drop", "dropped", "dropping", "fall", "fell", "falling",
    "decline", "declined", "declining",
    "slide", "slid", "sliding", "sink", "sank", "sinking",
    "dip", "dipped",
    "downgrade", "downgraded", "downgrading",
    "downturn", "downbeat", "downside",
    "underperform", "underperformed",
    "bearish", "bear market", "bear run",
    "correction", "correcting",
    "lowest", "new low", "all-time low", "52-week low",
    # 业绩/亏损
    "miss earnings", "earnings miss",
    "weak earnings", "weak quarter", "weak results",
    "loss", "losses", "unprofitable",
    "deficit", "net loss", "operating loss",
    "revenue miss", "sales miss",
    "below expectations", "fall short",
    "cut forecast", "cut guidance", "lower guidance",
    "layoff", "lay off", "firing", "fired",
    # 利空事件
    "lawsuit", "lawsuit filed", "legal challenge",
    "investigation", "probe", "inquiry",
    "sanction", "sanctions", "penalty", "fine",
    "downgraded to", "downgrade to",
    "underweight", "sell rating", "reduce rating",
    "risk", "risks", "risky",
    "uncertainty", "uncertain",
    "bankruptcy", "insolvency", "default",
    "volatility", "volatile",
    "slowdown", "slow down", "slowing",
    "recession", "recessionary",
    "inflation", "inflationary",
    "tariff", "tariffs", "trade war",
    "delist", "delisting",
    "selloff", "sell-off", "sell off",
    "intensify", "intensifies", "intensified",
}

# ─── 通用强化词（中英文都有效）───

INTENSIFIERS_CN = {"大幅", "显著", "极度", "严重", "剧烈", "暴涨", "暴跌",
                   "历史", "空前", "惊人", "罕见", "疯狂"}
INTENSIFIERS_EN = {"sharply", "dramatically", "significantly", "massive",
                   "massively", "steep", "steeply", "historic", "record",
                   "huge", "enormous", "severe", "severely"}

# 反转词
CN_NEGATORS = {"不", "未", "无", "没有", "并非"}
EN_NEGATORS = {"not", "no", "without", "unlikely", "unable"}


def is_english(title: str) -> bool:
    """检测标题是否为英文（基于字符集判断）"""
    if not title:
        return True
    # 统计 ASCII 字母和 CJK 字符的比例
    ascii_chars = sum(1 for c in title if 'a' <= c.lower() <= 'z')
    cjk_chars = sum(1 for c in title if '\u4e00' <= c <= '\u9fff')
    total = ascii_chars + cjk_chars
    if total == 0:
        return True  # 纯数字/符号 → 当英文处理
    return ascii_chars >= cjk_chars


def score_title(title: str) -> int:
    """
    对新闻标题进行情感评分（自动检测语言）

    Returns:
        -2 非常负面
        -1 负面
         0 中性/无情绪
        +1 正面
        +2 非常正面
    """
    if not title:
        return 0

    text = title.lower()
    english = is_english(title)

    if english:
        pos_set = EN_POSITIVE
        neg_set = EN_NEGATIVE
        intensifiers = INTENSIFIERS_EN
        negators = EN_NEGATORS
    else:
        pos_set = CN_POSITIVE
        neg_set = CN_NEGATIVE
        intensifiers = INTENSIFIERS_CN
        negators = CN_NEGATORS

    if english:
        # 英文：去标点、分词
        clean = re.sub(r'[^\w\s\'-]', ' ', text)
        tokens = clean.split()
        bigrams = set(f"{a} {b}" for a, b in zip(tokens, tokens[1:]))

        def stem_match(tokens_list, keyword_set):
            matched = set()
            for token in tokens_list:
                for kw in keyword_set:
                    if kw in token:
                        matched.add(kw)
            return matched

        pos_matches = stem_match(tokens, pos_set) | (bigrams & pos_set)
        neg_matches = stem_match(tokens, neg_set) | (bigrams & neg_set)

        pos_count = 0
        neg_count = 0
        pos_intense = False
        neg_intense = False

        for w in pos_matches:
            idx = text.find(w)
            prefix_words = text[:idx].strip().split()
            has_neg = prefix_words[-1] in negators if prefix_words else False
            if has_neg:
                neg_count += 1
            else:
                pos_count += 1
                pos_intense = pos_intense or (w in intensifiers)

        for w in neg_matches:
            idx = text.find(w)
            prefix_words = text[:idx].strip().split()
            has_neg = prefix_words[-1] in negators if prefix_words else False
            if has_neg:
                pos_count += 1
            else:
                neg_count += 1
                neg_intense = neg_intense or (w in intensifiers)

    else:
        # 中文：子串匹配
        pos_count = 0
        neg_count = 0
        pos_intense = False
        neg_intense = False

        for word in pos_set:
            if word in text:
                idx = text.find(word)
                prefix = text[max(0, idx - 3):idx].strip()
                if any(neg in prefix for neg in negators):
                    neg_count += 1
                else:
                    pos_count += 1
                    if word in intensifiers:
                        pos_intense = True

        for word in neg_set:
            if word in text:
                idx = text.find(word)
                prefix = text[max(0, idx - 3):idx].strip()
                if any(neg in prefix for neg in negators):
                    pos_count += 1
                else:
                    neg_count += 1
                    if word in intensifiers:
                        neg_intense = True

    # 计算净情感
    net = pos_count - neg_count

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
    """批量回填 stock_news 表中未评分新闻的情感分数"""
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
        conn.execute("UPDATE stock_news SET sentiment = ? WHERE rowid = ?", [score, rowid])
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
    tests = [
        # 中文
        ("宁德时代三季度净利润同比增长67%", 2),
        ("贵州茅台股价大跌5%，创年内新低", -2),
        ("公司发布公告，召开股东大会", 0),
        ("央行降息0.25个百分点，利好股市", 2),
        ("股东减持计划引发市场担忧", -2),
        ("中兴通讯中标5G大单", 2),
        ("公司涉嫌财务造假被立案调查", -2),
        ("今日收盘持平", 0),
        # 英文
        ("NVIDIA Stock Surges on Strong Earnings Beat", 2),
        ("Oracle Stock Is Plummeting. Is This an Opportunity or a Red Flag?", -2),
        ("Tesla Shares Hit All-Time High After Record Deliveries", 2),
        ("Fed Rate Cut Boosts Market Sentiment", 1),
        ("Apple Faces Lawsuit Over Antitrust Violations", -1),
        ("Microsoft Reports Strong Quarterly Results, Shares Rise", 2),
        ("Company Announces Share Buyback Program", 2),
        ("Oil Prices Crash on Recession Fears", -2),
        ("Bitcoin Falls Below $80000 as Selloff Intensifies", -2),
        ("Market Rally Continues for Third Straight Week", 1),
        ("Palantir Stock Ripe for a Rebound?", 1),
    ]
    ok, fail = 0, 0
    for title, expected in tests:
        result = score_title(title)
        status = "✅" if result == expected else "❌"
        lang = "EN" if is_english(title) else "CN"
        if status == "✅":
            ok += 1
        else:
            fail += 1
            print(f"{status} [{lang}] '{title[:60]}...' → {result} (expect {expected})")
    print(f"\n=== {ok}/{len(tests)} passed, {fail} failed ===")
