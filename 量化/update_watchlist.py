# -*- coding: utf-8 -*-
"""更新自选股池 — 热点板块20元以内 + 今日信号股"""
import sys, os, json, re
sys.stdout.reconfigure(encoding="utf-8")

BASE = os.path.dirname(os.path.abspath(__file__))
WL_FILE = os.path.join(BASE, ".my_watchlist.json")

# ======= 今日热点候选(需验证股价) =======
HOT_CANDIDATES = {
    # 通信/光纤/CPO方向
    "sz000586": "汇源通信",   # 通信设备 已知16.74
    "sz002897": "意华股份",   # 高速连接器+AI算力
    "sh600345": "长江通信",   # 触及涨停
    "sh600105": "永鼎股份",   # 光纤光缆
    "sz002491": "通鼎互联",   # 光纤光缆
    "sh600487": "亨通光电",   # 光纤龙头 (83元,可能超)
    "sz002583": "海能达",     # 通信设备
    "sh603803": "瑞斯康达",   # 通信设备 (已在自选)
    # 机器人方向
    "sz000700": "模塑科技",   # 人形机器人 已知15.07
    "sh603890": "春秋电子",   # 机器人 3连板
    "sz002579": "中京电子",   # 机器人 PCB 6天5板
    "sz002031": "巨轮智能",   # 机器人
    "sz002527": "新时达",     # 机器人
    "sz002747": "埃斯顿",     # 机器人
    # 半导体/芯片
    "sz002185": "华天科技",   # 半导体封装 (已在自选)
    "sh600667": "太极实业",   # 半导体 (已在自选)
    "sz002156": "通富微电",   # 半导体封装
    "sh603005": "晶方科技",   # 芯片封装
    "sh600460": "士兰微",     # 半导体
    # 5G/通信
    "sz002115": "三维通信",   # 5G (已在自选)
    "sz002369": "卓翼科技",   # 5G/物联网
    "sz002402": "和而泰",     # 5G/智能控制器
    # 电力/能源(今日筛出方向)
    "sh600575": "淮河能源",   # 今日小秋策略信号 4.38
    "sz002608": "江苏国信",   # 今日小秋策略信号 10.42
    "sh600222": "太龙药业",   # 今日用户策略信号 8.17 (中药,非热点但信号股)
    "sh600906": "财达证券",   # 今日用户策略信号 6.82 (券商)
    "sh601699": "潞安环能",   # 今日用户策略信号 17.80 (煤炭)
}

# ======= 查行情 =======
import urllib.request
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"

def http_get(url, timeout=10, decode="gbk"):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode(decode)

def get_quotes(codes):
    """批量查实时行情(收盘数据)"""
    all_r = []
    for i in range(0, len(codes), 50):
        batch = codes[i:i+50]
        url = "http://qt.gtimg.cn/q=" + ",".join(batch)
        try:
            raw = http_get(url, timeout=15)
            for line in raw.strip().split(";\n"):
                m = re.search(r'="(.+)"$', line.strip())
                if not m: continue
                f = m.group(1).split("~")
                if len(f) < 40: continue
                try:
                    price = float(f[3]) if f[3] else None
                    preclose = float(f[4]) if f[4] else None
                    pct = ((price - preclose) / preclose * 100) if (price and preclose) else None
                    all_r.append({"code": f[2], "name": f[1], "price": price, "pct": pct})
                except: continue
        except Exception as e:
            print(f"  HTTP error: {e}")
            continue
    return all_r

# ======= 加载现有自选股 =======
with open(WL_FILE, encoding="utf-8") as f:
    watchlist = json.load(f)

existing_codes = set(watchlist.keys())
existing_raw = set()
for k in existing_codes:
    raw = k.replace("sh","").replace("sz","").zfill(6)
    existing_raw.add(raw)

print("=" * 60)
print("  更新自选股池")
print("=" * 60)

# ======= 查询候选股 =======
codes_to_check = list(HOT_CANDIDATES.keys())
quotes = get_quotes(codes_to_check)

# ======= 筛选20元以内 =======
new_adds = []
for q in quotes:
    code = q['code']
    full_code = f"sh{code}" if code.startswith(('6','9')) else f"sz{code}"
    name = HOT_CANDIDATES.get(full_code, q.get('name', ''))
    price = q.get('price')
    pct = q.get('pct')

    if price is None:
        print(f"  ⚠️  {code} {name}: 无数据")
        continue
    if price >= 20:
        print(f"  ⛔ {code} {name}: {price:.2f}元 (超20元,跳过)")
        continue
    if code in existing_raw:
        print(f"  ✓  {code} {name}: {price:.2f}元 (已在自选)")
        continue

    # 排除创业板/科创板
    if code.startswith('3') or code.startswith('688'):
        print(f"  ⛔ {code} {name}: {price:.2f}元 (创业板/科创,跳过)")
        continue

    new_adds.append((full_code, name, price, pct))

# ======= 输出 =======
print(f"\n{'='*60}")
print(f"  📋 新增自选股 ({len(new_adds)}只)")
print(f"{'='*60}")

for full_code, name, price, pct in new_adds:
    pct_str = f"{pct:+.2f}%" if pct else "--"
    watchlist[full_code] = name
    arrow = "🔴" if pct and pct > 0 else "🟢"
    print(f"  {arrow} {full_code} {name:<8} {price:.2f}元  {pct_str}")

# ======= 保存 =======
with open(WL_FILE, "w", encoding="utf-8") as f:
    json.dump(watchlist, f, ensure_ascii=False, indent=2)

print(f"\n  自选股总数: {len(watchlist)} 只")
print(f"  已保存: {WL_FILE}")
print(f"\n{'='*60}")
print("  完成! 下次运行 stock_quant.py screen 将扫描新池")
print(f"{'='*60}")
