# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════╗
║   🔥 短线打板 —— 3进4连板擒龙策略 v1.0             ║
║   客户需求：连板股3进4筛选 + 量能分析 + 评分排序   ║
║   数据源：东方财富 (免费, 无需API key, 不用梯子)    ║
╚══════════════════════════════════════════════════════╝

策略逻辑：
  第1步 → 获取今日涨停板股票池（含封板时间/炸板次数/封单量等）
  第2步 → 筛选出"连续3天涨停"的股票（3板股）
  第3步 → 对每只3板股做第3板质量评分（5维度加权）
  第4步 → 输出排名 + 明日操作建议（哪些值得博弈4板）

评分模型（满分100）：
  ┌──────────────┬──────┬──────────────────────────────┐
  │ 维度          │ 权重  │ 评分规则                     │
  ├──────────────┼──────┼──────────────────────────────┤
  │ 封板速度      │ 25分  │ 越早越好(一字板=满分)       │
  │ 封板稳定性    │ 20分  │ 炸板次数越少越好            │
  │ 量能健康度    │ 20分  │ 换手率适中+量价配合         │
  │ 封单强度      │ 20分  │ 封单/流通市值比值           │
  │ 板块梯队      │ 15分  │ 同板块有无涨停梯队支撑      │
  └──────────────┴──────┴──────────────────────────────┘

用法：
  python three_to_four.py                分析今日3进4候选
  python three_to_four.py --date 20260605  指定日期分析
  python three_to_four.py --backtest 30    回测近30天3进4成功率
  python three_to_four.py --watch          盘中监控模式(10s刷新)
"""

import sys, os, time, json, re
from datetime import datetime, timedelta
from collections import defaultdict

# ─── 编码 ───
if sys.platform == "win32":
    try: sys.stdout.reconfigure(encoding="utf-8")
    except: pass

# ═══════════════════════════════════════════
# 环境检查
# ═══════════════════════════════════════════

try:
    import akshare as ak
    import pandas as pd
except ImportError:
    print("❌ 需要安装 akshare 和 pandas")
    print("   pip install akshare pandas")
    sys.exit(1)

# ─── 路径 ───
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = BASE_DIR  # 输出到同级目录

# ═══════════════════════════════════════════
# 颜色
# ═══════════════════════════════════════════

class C:
    R = "\033[1;31m"; G = "\033[1;32m"; Y = "\033[1;33m"
    B = "\033[1;36m"; M = "\033[1;35m"; D = "\033[2;37m"; Z = "\033[0m"


# ═══════════════════════════════════════════
# 第一部分：数据获取
# ═══════════════════════════════════════════

def fetch_limit_up_pool(date_str=None):
    """
    获取涨停板股票池（含详细封板数据）

    返回字段：
      - 代码, 名称, 最新价, 涨跌幅
      - 首次封板时间, 最后封板时间, 炸板次数
      - 换手率, 成交额, 流通市值
      - 封单资金, 涨停统计, 连板数, 所属行业
    """
    if date_str is None:
        date_str = datetime.now().strftime("%Y%m%d")

    print(f"{C.B}📡 获取涨停板数据: {date_str}{C.Z}")

    try:
        df = ak.stock_zt_pool_em(date=date_str)
        if df is None or df.empty:
            print(f"{C.Y}⚠️  {date_str} 无涨停板数据（可能非交易日）{C.Z}")
            return None
        print(f"   ✅ 获取到 {len(df)} 只涨停股")
        return df
    except Exception as e:
        print(f"{C.R}❌ 获取涨停板数据失败: {e}{C.Z}")
        return None


def fetch_yesterday_limit_up():
    """获取昨日涨停池（用于回测验证）"""
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
    try:
        df = ak.stock_zt_pool_previous_em(date=yesterday)
        return df
    except:
        return None


def fetch_strong_pool(date_str=None):
    """获取强势股池（连板潜力股）"""
    if date_str is None:
        date_str = datetime.now().strftime("%Y%m%d")
    try:
        df = ak.stock_zt_pool_strong_em(date=date_str)
        return df
    except:
        return None


# ═══════════════════════════════════════════
# 第二部分：3连板筛选
# ═══════════════════════════════════════════

def filter_three_board_stocks(df):
    """
    从涨停池中筛选出连板数 >= 3 的股票

    参数:
      df: stock_zt_pool_em 返回的 DataFrame
    返回:
      list[dict]: 3连板候选股列表
    """
    if df is None or df.empty:
        return []

    # 列名映射（处理可能的列名变化）
    col_map = _detect_columns(df)

    candidates = []
    for _, row in df.iterrows():
        try:
            code = str(row.get(col_map.get('code', '代码'), '')).zfill(6)
            name = str(row.get(col_map.get('name', '名称'), ''))
            price = float(row.get(col_map.get('price', '最新价'), 0))
            pct = float(row.get(col_map.get('pct', '涨跌幅'), 0))
            turnover = float(row.get(col_map.get('turnover', '换手率'), 0))
            seal_money = float(row.get(col_map.get('seal_money', '封单资金'), 0))
            float_mv = float(row.get(col_map.get('float_mv', '流通市值'), 0))
            first_seal = str(row.get(col_map.get('first_seal', '首次封板时间'), ''))
            last_seal = str(row.get(col_map.get('last_seal', '最后封板时间'), ''))
            break_times = int(row.get(col_map.get('break_times', '炸板次数'), 0))
            board_stat = str(row.get(col_map.get('board_stat', '涨停统计'), ''))
            cons_board = int(row.get(col_map.get('cons_board', '连板数'), 0))
            industry = str(row.get(col_map.get('industry', '所属行业'), ''))

            # 过滤：只要3连板及以上的
            if cons_board < 3:
                continue

            # 过滤：排除ST
            if 'ST' in name.upper():
                continue

            # 过滤：排除创业板（20%涨跌幅规则不同）
            if code.startswith('30'):
                continue

            candidates.append({
                'code': code,
                'name': name,
                'price': price,
                'pct': pct,
                'turnover': turnover,
                'seal_money': seal_money,
                'float_mv': float_mv,
                'first_seal': first_seal,
                'last_seal': last_seal,
                'break_times': break_times,
                'board_stat': board_stat,
                'cons_board': cons_board,
                'industry': industry,
            })
        except Exception as e:
            continue

    return candidates


def _detect_columns(df):
    """智能检测列名（兼容不同版本的 akshare）"""
    cols = df.columns.tolist()

    # 可能的列名映射
    patterns = {
        'code': ['代码', 'code', '股票代码'],
        'name': ['名称', 'name', '股票名称'],
        'price': ['最新价', 'price', '现价'],
        'pct': ['涨跌幅', 'pct_chg', '涨幅'],
        'turnover': ['换手率', 'turnover', '换手'],
        'seal_money': ['封板资金', '封单资金', 'seal_amount', '封单额'],
        'float_mv': ['流通市值', 'float_mv', '流通市值'],
        'first_seal': ['首次封板时间', 'first_time', '首次涨停时间'],
        'last_seal': ['最后封板时间', 'last_time', '最后涨停时间'],
        'break_times': ['炸板次数', 'break_times', '开板次数'],
        'board_stat': ['涨停统计', 'board_stat', '涨停统计'],
        'cons_board': ['连板数', 'cons_board', '连板天数'],
        'industry': ['所属行业', 'industry', '行业'],
    }

    result = {}
    for key, names in patterns.items():
        for name in names:
            if name in cols:
                result[key] = name
                break

    return result


# ═══════════════════════════════════════════
# 第三部分：第3板质量评分模型
# ═══════════════════════════════════════════

def score_seal_speed(first_seal, last_seal):
    """
    维度1：封板速度评分（满分25）

    评分逻辑：
      - 09:25 一字板（集合竞价封死）→ 25分
      - 09:30-09:45 秒板 → 22-24分
      - 09:45-10:00 早盘封板 → 18-21分
      - 10:00-10:30 上午封板 → 14-17分
      - 10:30-11:30 午前封板 → 10-13分
      - 13:00-14:00 下午封板 → 5-9分
      - 14:00-15:00 尾盘偷鸡 → 0-4分
      - 未封板 → 0分
    """
    if not first_seal or first_seal in ('', 'nan', 'None'):
        return 0

    try:
        # 解析时间: "092501" → 9:25:01
        t = first_seal.strip().zfill(6)
        hh = int(t[:2])
        mm = int(t[2:4])
        ss = int(t[4:6])
        total_seconds = hh * 3600 + mm * 60 + ss

        # 9:25 集合竞价 = 33900秒
        market_open = 9 * 3600 + 30 * 60  # 34200

        if total_seconds <= 9 * 3600 + 25 * 60 + 30:
            return 25  # 一字板
        elif total_seconds <= 9 * 3600 + 30 * 60 + 30:
            return 25  # 开盘秒板
        elif total_seconds <= 9 * 3600 + 45 * 60:
            return 24  # 9:30-9:45
        elif total_seconds <= 10 * 3600:
            return 21  # 9:45-10:00
        elif total_seconds <= 10 * 3600 + 30 * 60:
            return 17  # 10:00-10:30
        elif total_seconds <= 11 * 3600 + 30 * 60:
            return 13  # 10:30-11:30
        elif total_seconds <= 14 * 3600:
            return 8   # 13:00-14:00
        else:
            # 越临近收盘越低
            remaining = 15 * 3600 - total_seconds
            return max(1, int(remaining / 3600 * 4))
    except:
        return 10


def score_seal_stability(break_times):
    """
    维度2：封板稳定性评分（满分20）

    评分逻辑：
      - 0次炸板 → 20分（最强）
      - 1次炸板后回封 → 14分
      - 2次炸板后回封 → 8分
      - 3次炸板 → 3分
      - ≥4次 → 0分（烂板）
    """
    if break_times == 0:
        return 20
    elif break_times == 1:
        return 14
    elif break_times == 2:
        return 8
    elif break_times == 3:
        return 3
    else:
        return 0


def score_volume_health(turnover, cons_board):
    """
    维度3：量能健康度评分（满分20）

    对于3进4打板，量能逻辑特殊：
      - 第3板缩量加速 → 好（锁仓意愿强，抛压轻）
      - 第3板平量 → 可以接受
      - 第3板放巨量 → 差（分歧大，第4天抛压重）

    参考换手率区间（第3板）：
      - 3%-8%：缩量加速，筹码锁定好 → 18-20分
      - 8%-15%：正常换手 → 14-17分
      - 15%-25%：偏高（可能是出货）→ 8-13分
      - <3%：一字板无换手 → 看第4天是否给机会
      - >25%：死亡换手，极度危险 → 0-5分
    """
    if turnover < 1:
        # 一字板无成交量，给15分（没机会买但有强度）
        return 15
    elif turnover < 3:
        return 18
    elif turnover <= 8:
        return 20  # 最佳区间：缩量加速
    elif turnover <= 12:
        return 17
    elif turnover <= 15:
        return 14
    elif turnover <= 20:
        return 10
    elif turnover <= 25:
        return 6
    else:
        return 2  # 死亡换手


def score_seal_strength(seal_money, float_mv):
    """
    维度4：封单强度评分（满分20）

    封单资金 / 流通市值：
      - ≥5%：极度强势 → 20分
      - 3%-5%：强势 → 16-19分
      - 1%-3%：正常 → 10-15分
      - 0.5%-1%：偏弱 → 5-9分
      - <0.5%：弱封（可能炸板）→ 0-4分
    """
    if float_mv <= 0:
        return 5

    ratio = (seal_money / float_mv) * 100

    if ratio >= 5:
        return 20
    elif ratio >= 3:
        return 16 + int((ratio - 3) / 2 * 4)
    elif ratio >= 1:
        return 10 + int((ratio - 1) / 2 * 5)
    elif ratio >= 0.5:
        return 5 + int((ratio - 0.5) / 0.5 * 5)
    else:
        return max(1, int(ratio / 0.5 * 5))


def score_sector_support(industry, all_candidates):
    """
    维度5：板块梯队评分（满分15）

    逻辑：同板块有其他涨停股 → 板块效应强 → 龙头有溢价
      - 同板块≥5只涨停 → 15分（强板块效应）
      - 3-4只 → 10-14分
      - 1-2只 → 5-9分
      - 独立行情 → 3分
    """
    if not industry:
        return 5

    # 统计同板块涨停股数
    same_industry_count = sum(
        1 for c in all_candidates
        if c.get('industry', '') == industry
    )

    # 简化：用所有候选中的同行业数量近似
    if same_industry_count >= 5:
        return 15
    elif same_industry_count >= 3:
        return 12
    elif same_industry_count >= 2:
        return 8
    else:
        return 4  # 独立行情，没有板块保护


# ═══════════════════════════════════════════
# 第四部分：综合评分引擎
# ═══════════════════════════════════════════

def score_candidate(stock, all_candidates):
    """
    对单只3板候选股做综合评分

    返回：带分数的完整 dict
    """
    scores = {
        'seal_speed': score_seal_speed(
            stock.get('first_seal', ''), stock.get('last_seal', '')),
        'seal_stability': score_seal_stability(stock.get('break_times', 0)),
        'volume_health': score_volume_health(
            stock.get('turnover', 0), stock.get('cons_board', 3)),
        'seal_strength': score_seal_strength(
            stock.get('seal_money', 0), stock.get('float_mv', 1)),
        'sector_support': score_sector_support(
            stock.get('industry', ''), all_candidates),
    }

    total = sum(scores.values())
    result = {**stock, 'scores': scores, 'total_score': total}
    return result


def rank_candidates(candidates):
    """对所有候选股评分并排序"""
    scored = [score_candidate(c, candidates) for c in candidates]
    scored.sort(key=lambda x: x['total_score'], reverse=True)
    return scored


# ═══════════════════════════════════════════
# 第五部分：操作建议生成
# ═══════════════════════════════════════════

def generate_advice(stock):
    """根据评分生成操作建议"""
    total = stock['total_score']
    scores = stock['scores']
    cons_board = stock.get('cons_board', 3)

    advice = {}
    advice['stock'] = stock

    # 分级建议
    if total >= 85:
        advice['level'] = 'S'
        advice['label'] = '🔥 强烈关注'
        advice['action'] = '第4天竞价高开3%以内可轻仓博弈，止损设在-5%'
        advice['confidence'] = '高'
    elif total >= 70:
        advice['level'] = 'A'
        advice['label'] = '🟢 可以博弈'
        advice['action'] = '第4天观察开盘强度，高开不追等回踩，-5%止损'
        advice['confidence'] = '中高'
    elif total >= 55:
        advice['level'] = 'B'
        advice['label'] = '🟡 谨慎参与'
        advice['action'] = '只做观察，除非第4天超预期弱转强，不主动追'
        advice['confidence'] = '中'
    elif total >= 40:
        advice['level'] = 'C'
        advice['label'] = '🟠 不建议'
        advice['action'] = '第3板质量一般，大概率第4天冲高回落或直接低开'
        advice['confidence'] = '低'
    else:
        advice['level'] = 'D'
        advice['label'] = '🔴 避开'
        advice['action'] = '烂板/尾盘板/死亡换手，第4天大概率大面，坚决不碰'
        advice['confidence'] = '极低'

    # 风险点
    risks = []
    if stock.get('break_times', 0) >= 2:
        risks.append(f"炸板{stock['break_times']}次，封板不稳")
    if stock.get('turnover', 0) > 25:
        risks.append(f"换手率{stock['turnover']:.1f}%，死亡换手风险")
    if stock.get('turnover', 0) < 1:
        risks.append("一字板无换手，第4天可能继续一字或高开低走")
    if scores.get('seal_speed', 25) < 10:
        risks.append("尾盘封板，偷鸡嫌疑")
    if scores.get('seal_strength', 20) < 5:
        risks.append("封单太弱，次日竞价可能被砸")
    if scores.get('sector_support', 15) < 5:
        risks.append("无板块支撑，独立行情风险大")

    advice['risks'] = risks

    # 第4天预期
    if total >= 70 and stock.get('turnover', 0) < 8:
        advice['expectation'] = '大概率高开3-5%，有机会冲击第4板'
    elif total >= 55:
        advice['expectation'] = '可能小幅高开，盘中震荡后决定方向'
    else:
        advice['expectation'] = '大概率低开或平开，冲高是卖点不是买点'

    return advice


# ═══════════════════════════════════════════
# 第六部分：回测系统
# ═══════════════════════════════════════════

def backtest_3to4(lookback_days=30):
    """
    回测近N天3进4策略成功率

    逻辑：
      1. 对于过去N天，每天找出3连板股
      2. 跟踪第4天表现（是否涨停/溢价）
      3. 统计成功率
    """
    print(f"\n{C.M}╔══════════════════════════════════════════════╗")
    print(f"║   📊 3进4策略回测 (近{lookback_days}个交易日)")
    print(f"╚══════════════════════════════════════════════╝{C.Z}\n")

    # 注：完整回测需要遍历历史每个交易日，这里采用简化方案
    # 用 akshare 的 stock_zt_pool_previous_em 逐日回看

    # akshare 的 stock_zt_pool_em 支持指定日期
    # 但逐日调用太慢，这里采用采样方案：回看最近几个交易日

    trade_days = _get_recent_trade_days(lookback_days)

    all_results = []
    for day in trade_days:
        try:
            df = ak.stock_zt_pool_em(date=day)
            if df is None or df.empty:
                continue

            three_board = filter_three_board_stocks(df)
            if not three_board:
                continue

            # 对每只3板股，获取第4天的K线
            for stock in three_board:
                code = stock['code']
                # 获取接下来几天的K线数据
                kl = _get_kline_tencent(code, days=10)
                if not kl or len(kl) < 5:
                    continue

                # 找到涨停日之后的第1天（即第4天）
                result = _check_next_day_performance(kl, stock)
                if result:
                    all_results.append(result)

            print(f"  {day}: {len(three_board)}只3板 → "
                  f"{sum(1 for r in all_results[-len(three_board):] if r.get('hit_4th'))}只4板成功")

        except Exception as e:
            continue

    # 统计
    if all_results:
        total = len(all_results)
        hit_4th = sum(1 for r in all_results if r.get('hit_4th'))
        avg_return = sum(r.get('next_day_return', 0) for r in all_results) / total
        hit_rate = hit_4th / total * 100

        print(f"\n{C.Y}📊 回测统计 (近{len(trade_days)}个交易日):{C.Z}")
        print(f"  3板股票数: {total}只")
        print(f"  成功4板: {hit_4th}只 ({hit_rate:.1f}%)")
        print(f"  次日平均收益: {avg_return:+.2f}%")
        print(f"\n{C.D}⚠️ 回测仅供参考，历史不代表未来{C.Z}")
    else:
        print(f"  {C.Y}无足够回测数据{C.Z}")

    return all_results


def _get_recent_trade_days(lookback_days):
    """获取最近N个交易日列表"""
    days = []
    current = datetime.now()
    count = 0
    max_iter = lookback_days * 3  # 防止无限循环

    while len(days) < min(lookback_days, 20) and count < max_iter:
        count += 1
        current = current - timedelta(days=1)
        # 跳过周末
        if current.weekday() >= 5:
            continue
        days.append(current.strftime("%Y%m%d"))

    return list(reversed(days))


def _get_kline_tencent(code, days=60):
    """获取K线数据 (腾讯财经, 无需梯子)"""
    import urllib.request
    raw_code = code.replace("sh","").replace("sz","").zfill(6)
    m = "sh" if raw_code.startswith(("6","9")) else "sz"
    url = f"http://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={m}{raw_code},day,,,{days},qfq"
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8")
        data = json.loads(raw)
        kl = data["data"][f"{m}{raw_code}"].get("day",[])
        return [{"date": it[0], "open": float(it[1]), "close": float(it[2]),
                 "high": float(it[3]), "low": float(it[4]), "volume": float(it[5])}
                for it in kl] if kl else None
    except:
        return None


def _check_next_day_performance(kl, stock):
    """检查3板后第4天的表现"""
    if not kl or len(kl) < 2:
        return None

    # 简化：用最新K线的前一天模拟"第3板日"
    # 实际使用时需要精确匹配涨停日
    if len(kl) < 4:
        return None

    # 检查倒数第2天是否有涨停特征(收盘≈最高, 涨幅>9.5%)
    day3 = kl[-2]
    day4 = kl[-1]

    pct_day3 = (day3['close'] - kl[-3]['close']) / kl[-3]['close'] * 100 if len(kl) >= 4 else 0
    if pct_day3 < 9.5:
        return None

    pct_day4 = (day4['close'] - day3['close']) / day3['close'] * 100
    hit_4th = pct_day4 >= 9.5

    return {
        'code': stock.get('code', ''),
        'name': stock.get('name', ''),
        'third_day': day3['date'],
        'fourth_day': day4['date'],
        'day4_pct': round(pct_day4, 2),
        'hit_4th': hit_4th,
        'next_day_return': round(pct_day4, 2),
    }


# ═══════════════════════════════════════════
# 第七部分：报告生成
# ═══════════════════════════════════════════

def generate_report(scored_candidates, date_str):
    """生成 Markdown 格式的3进4分析报告"""
    now = datetime.now()
    lines = []

    lines.append(f"# 🔥 3进4连板擒龙 —— 每日分析报告")
    lines.append(f"")
    lines.append(f"**分析日期**: {date_str} | 生成时间: {now.strftime('%H:%M:%S')}")
    lines.append(f"**策略**: 3连板筛选 → 第3板质量评分 → 第4板博弈建议")
    lines.append(f"")
    lines.append(f"---")
    lines.append(f"")

    if not scored_candidates:
        lines.append(f"## ⭕ 今日无3连板候选股")
        lines.append(f"")
        lines.append(f"> 市场没有符合条件的3进4标的，建议休息观望。")
    else:
        # 分级统计
        s级 = [c for c in scored_candidates if c['total_score'] >= 85]
        a级 = [c for c in scored_candidates if 70 <= c['total_score'] < 85]
        b级 = [c for c in scored_candidates if 55 <= c['total_score'] < 70]
        其他 = [c for c in scored_candidates if c['total_score'] < 55]

        lines.append(f"## 📊 概览")
        lines.append(f"")
        lines.append(f"| 级别 | 数量 | 含义 |")
        lines.append(f"|------|------|------|")
        lines.append(f"| 🔥 S级 (≥85分) | {len(s级)}只 | 强烈关注，第3板质量极高 |")
        lines.append(f"| 🟢 A级 (70-84分) | {len(a级)}只 | 可以博弈，注意仓位 |")
        lines.append(f"| 🟡 B级 (55-69分) | {len(b级)}只 | 谨慎参与，观察为主 |")
        lines.append(f"| 🟠 C/D级 (<55分) | {len(其他)}只 | 不建议参与 |")
        lines.append(f"")

        # 详细分析表
        lines.append(f"## 🏆 候选股详细评分")
        lines.append(f"")
        lines.append(f"| 排名 | 代码 | 名称 | 连板 | 现价 | 得分 | 封板 | 炸板 | 换手 | 封单/市值 | 板块 | 建议 |")
        lines.append(f"|------|------|------|------|------|------|------|------|------|------------|------|------|")

        for i, c in enumerate(scored_candidates):
            s = c['scores']
            adv = generate_advice(c)
            first_seal = c.get('first_seal', '--')
            if first_seal and len(str(first_seal)) >= 4:
                first_seal = f"{str(first_seal)[:2]}:{str(first_seal)[2:4]}"
            seal_ratio = (c['seal_money'] / c['float_mv'] * 100) if c['float_mv'] > 0 else 0

            lines.append(
                f"| {i+1} | {c['code']} | {c['name']} | "
                f"{c['cons_board']}板 | {c['price']:.2f} | "
                f"{c['total_score']}分 | {first_seal} | "
                f"{c['break_times']}次 | {c['turnover']:.1f}% | "
                f"{seal_ratio:.1f}% | {c.get('industry','')[:6]} | "
                f"{adv['label']} |"
            )

        lines.append(f"")

        # Top3 详细分析
        lines.append(f"## 🎯 TOP3 深度分析")
        lines.append(f"")

        for i, c in enumerate(scored_candidates[:3]):
            s = c['scores']
            adv = generate_advice(c)

            lines.append(f"### {'🥇' if i==0 else '🥈' if i==1 else '🥉'} "
                        f"{c['name']}({c['code']}) — {c['total_score']}分 {adv['label']}")
            lines.append(f"")

            # 评分雷达
            lines.append(f"| 维度 | 得分 | 满分 | 说明 |")
            lines.append(f"|------|------|------|------|")
            lines.append(f"| ⚡ 封板速度 | {s['seal_speed']} | 25 | "
                        f"首次封板 {c.get('first_seal','?')} |")
            lines.append(f"| 🔒 封板稳定性 | {s['seal_stability']} | 20 | "
                        f"炸板{c['break_times']}次 |")
            lines.append(f"| 📊 量能健康度 | {s['volume_health']} | 20 | "
                        f"换手率{c['turnover']:.1f}% |")
            lines.append(f"| 💰 封单强度 | {s['seal_strength']} | 20 | "
                        f"封单{c['seal_money']/1e8:.1f}亿 |")
            lines.append(f"| 🏭 板块梯队 | {s['sector_support']} | 15 | "
                        f"{c.get('industry', '?')} |")
            lines.append(f"")

            lines.append(f"**💡 操作建议**: {adv['action']}")
            lines.append(f"")
            lines.append(f"**📈 第4天预期**: {adv.get('expectation', '待观察')}")
            lines.append(f"")

            if adv.get('risks'):
                lines.append(f"**⚠️ 风险提示**:")
                for r in adv['risks']:
                    lines.append(f"  - {r}")
                lines.append(f"")

            lines.append(f"---")
            lines.append(f"")

    # 风控提醒
    lines.append(f"## ⚠️ 打板风控铁律")
    lines.append(f"")
    lines.append(f"1. **仓位**: 单票不超过总资金 **20%**，打板是高风险操作")
    lines.append(f"2. **止损**: 第4天开盘利润跌破 **-5%** 无条件割，不幻想")
    lines.append(f"3. **止盈**: 封住第4板持有，**炸板即卖**，不贪第5板")
    lines.append(f"4. **纪律**: 连续亏损2次 → 休息3天，等待情绪回暖")
    lines.append(f"5. **时段**: 尽量在 **9:30-10:00** 确认强度后再动手，竞价不追高")
    lines.append(f"")
    lines.append(f"> 🦀 小秋提醒：打板的本质是概率游戏。S级不等于必赚，C级也可能走妖。仓位管理才是活下来的关键。")

    return "\n".join(lines)


def print_console_report(scored_candidates, date_str):
    """终端彩色输出报告摘要"""
    print(f"\n{C.M}╔══════════════════════════════════════════════════════╗")
    print(f"║  🔥 3进4连板擒龙 —— {date_str}                      ║")
    print(f"╚══════════════════════════════════════════════════════╝{C.Z}\n")

    if not scored_candidates:
        print(f"  {C.Y}⭕ 今日无3连板候选股，建议休息{C.Z}")
        return

    for i, c in enumerate(scored_candidates, 1):
        adv = generate_advice(c)
        level_color = {
            'S': C.R, 'A': C.G, 'B': C.Y, 'C': C.Y, 'D': C.D
        }.get(adv['level'], C.Z)

        first_seal = str(c.get('first_seal', '--'))
        if len(first_seal) >= 4:
            first_seal = f"{first_seal[:2]}:{first_seal[2:4]}"

        print(f"  {i}. {level_color}{adv['label']}{C.Z} {c['name']}({c['code']}) "
              f"{c['total_score']}分 | {c['cons_board']}板 | "
              f"封{first_seal} | 炸{c['break_times']}次 | 换手{c['turnover']:.1f}%")

        if i <= 3:
            print(f"     {C.D}{adv['action'][:80]}{C.Z}")
            if adv.get('risks'):
                print(f"     {C.Y}⚠️ {'; '.join(adv['risks'][:2])}{C.Z}")
        print()

    # 统计
    s_count = sum(1 for c in scored_candidates if c['total_score'] >= 85)
    a_count = sum(1 for c in scored_candidates if 70 <= c['total_score'] < 85)
    print(f"  {C.R}S级:{s_count}只{C.Z} | {C.G}A级:{a_count}只{C.Z} | "
          f"{C.Y}B级:{len(scored_candidates)-s_count-a_count}只{C.Z}")
    print(f"  {C.D}完整报告已保存到 three_to_four_report.md{C.Z}")


# ═══════════════════════════════════════════
# 第八部分：盘中监控模式
# ═══════════════════════════════════════════

def watch_mode(interval=10):
    """盘中实时监控3进4动态"""
    print(f"{C.M}📡 3进4盘中监控模式 (刷新间隔: {interval}s, Ctrl+C 退出){C.Z}\n")
    last_codes = set()

    try:
        while True:
            now = datetime.now()
            date_str = now.strftime("%Y%m%d")

            df = fetch_limit_up_pool(date_str)
            if df is not None:
                candidates = filter_three_board_stocks(df)
                if candidates:
                    scored = rank_candidates(candidates)
                    current_codes = {c['code'] for c in scored}

                    # 新出现的3板股
                    new_codes = current_codes - last_codes
                    if new_codes:
                        new_stocks = [c for c in scored if c['code'] in new_codes]
                        print(f"\n{C.R}🆕 新晋3板股: "
                              f"{', '.join(s['name'] for s in new_stocks)}{C.Z}")

                    # 评分变化
                    for c in scored[:5]:
                        adv = generate_advice(c)
                        lc = {'S': C.R, 'A': C.G, 'B': C.Y}.get(adv['level'], C.Z)
                        print(f"  [{now.strftime('%H:%M:%S')}] "
                              f"{lc}{adv['level']}级{C.Z} "
                              f"{c['name']}({c['code']}) "
                              f"{c['total_score']}分 | "
                              f"封单{c['seal_money']/1e8:.1f}亿 | "
                              f"换手{c['turnover']:.1f}%")

                    last_codes = current_codes
                else:
                    print(f"  [{now.strftime('%H:%M:%S')}] {C.D}暂无3连板候选{C.Z}")
            else:
                print(f"  [{now.strftime('%H:%M:%S')}] {C.D}等待开盘...{C.Z}")

            time.sleep(interval)

    except KeyboardInterrupt:
        print(f"\n{C.Y}👋 监控结束{C.Z}")


# ═══════════════════════════════════════════
# 第九部分：主入口
# ═══════════════════════════════════════════

def main():
    print(f"""
{C.M}╔══════════════════════════════════════════════════════╗
║  🔥 短线打板 —— 3进4连板擒龙策略 v1.0              ║
║  数据源: 东方财富 (免费/国内/无需梯子)              ║
╚══════════════════════════════════════════════════════╝{C.Z}
""")

    # 解析参数
    date_str = datetime.now().strftime("%Y%m%d")
    do_backtest = False
    do_watch = False
    lookback = 30

    for i, arg in enumerate(sys.argv):
        if arg == "--date" and i+1 < len(sys.argv):
            date_str = sys.argv[i+1]
        elif arg == "--backtest":
            do_backtest = True
            if i+1 < len(sys.argv):
                try: lookback = int(sys.argv[i+1])
                except: pass
        elif arg == "--watch":
            do_watch = True

    # 盘中监控模式
    if do_watch:
        watch_mode(interval=10)
        return

    # 回测模式
    if do_backtest:
        backtest_3to4(lookback_days=lookback)
        return

    # ─── 正常模式：今日分析 ───

    # 1. 获取涨停池
    df = fetch_limit_up_pool(date_str)
    if df is None:
        print(f"{C.Y}⏸️  无法获取涨停板数据，可能非交易日或网络问题{C.Z}")
        return

    # 2. 筛选3连板
    print(f"{C.B}🔍 筛选3连板及以上股票...{C.Z}")
    candidates = filter_three_board_stocks(df)
    print(f"   ✅ 3板候选: {len(candidates)}只")

    if not candidates:
        print(f"\n{C.Y}⭕ 今日无3连板候选股{C.Z}")
        print(f"{C.D}💡 打板选手今天可以休息，空仓也是一种策略{C.Z}")
        return

    # 打印候选列表
    for c in candidates:
        print(f"   {c['name']}({c['code']}) {c['cons_board']}板 "
              f"| 封{c.get('first_seal','?')} | 炸{c['break_times']}次 "
              f"| 换手{c['turnover']:.1f}% | {c.get('industry','')}")

    # 3. 评分排序
    print(f"\n{C.B}📊 第3板质量评分中...{C.Z}")
    scored = rank_candidates(candidates)

    # 4. 终端输出
    print_console_report(scored, date_str)

    # 5. 保存报告
    report = generate_report(scored, date_str)
    report_path = os.path.join(OUTPUT_DIR, "three_to_four_report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\n{C.G}📄 完整报告已保存: {report_path}{C.Z}")

    # 同时保存JSON（方便程序读取）
    json_path = os.path.join(OUTPUT_DIR, "three_to_four_result.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({
            "date": date_str,
            "candidates": scored,
            "top_pick": scored[0] if scored else None,
            "s_level": [c for c in scored if c['total_score'] >= 85],
            "a_level": [c for c in scored if 70 <= c['total_score'] < 85],
        }, f, ensure_ascii=False, indent=2)
    print(f"{C.G}📄 JSON结果已保存: {json_path}{C.Z}")


if __name__ == "__main__":
    main()
