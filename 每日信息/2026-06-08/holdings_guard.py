# -*- coding: utf-8 -*-
"""持仓重点监控 v2 —— 支持分批止盈·高点回落·移动止盈·关键位突破"""
import urllib.request, re, time, sys, json, os
from datetime import datetime

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except:
        pass

UA = "Mozilla/5.0"
INTERVAL = 120  # 2分钟刷新
POSITION_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".position.json")


def load_positions():
    with open(POSITION_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_positions(data):
    data["updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    tmp = POSITION_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, POSITION_FILE)


def fetch_quotes(codes):
    """拉取腾讯行情数据"""
    tx_codes = []
    for c in codes:
        if c.startswith("6"):
            tx_codes.append(f"sh{c}")
        else:
            tx_codes.append(f"sz{c}")
    url = f"http://qt.gtimg.cn/q={','.join(tx_codes)}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    raw = urllib.request.urlopen(req, timeout=10).read().decode("gbk", errors="replace")
    results = {}
    for line in raw.strip().split(";\n"):
        m = re.search(r'="(.+)"', line.strip())
        if not m:
            continue
        f = m.group(1).split("~")
        if len(f) < 40:
            continue
        results[f[2]] = {
            "name": f[1],
            "price": float(f[3]),
            "preclose": float(f[4]),
            "high": float(f[33]),
            "low": float(f[34]),
            "time": f[30],
        }
    return results


def check_holding(cfg, quote, today, dirty):
    """检查单个持仓，返回告警列表。如果有状态变更会标记 dirty[0]=True"""
    alerts = []
    code = cfg["code"]
    name = cfg["name"]
    price = quote["price"]
    cost = cfg["buy_price"]
    stop = cfg["stop_loss"]

    # ── 更新日内最高价 ──
    if cfg.get("daily_high_date") != today:
        cfg["daily_high"] = quote["high"]
        cfg["daily_high_date"] = today
        dirty[0] = True
    elif quote["high"] > (cfg.get("daily_high") or 0):
        cfg["daily_high"] = quote["high"]
        dirty[0] = True

    # ── 分批止盈检测 ──
    if cfg.get("take_profit_strategy") == "batch":
        for i, batch in enumerate(cfg.get("take_profit_batches", [])):
            if batch.get("sold"):
                continue

            # 规则1: 固定百分比触发
            if batch.get("trigger_price") and price >= batch["trigger_price"]:
                alerts.append(
                    f">>> [{name}] 第{i+1}批止盈触发! {price:.2f} >= {batch['trigger_price']:.2f} "
                    f"(+{batch['trigger_pct']}%) 卖出{batch['shares']}股"
                )
                batch["sold"] = True
                batch["sold_time"] = datetime.now().strftime("%H:%M:%S")
                dirty[0] = True

            # 规则2: 从峰值回落2%触发
            if batch.get("rule") == "pullback_2pct_from_peak":
                peak = batch.get("peak_price")
                if peak is None or price > peak:
                    batch["peak_price"] = price
                    dirty[0] = True
                if batch.get("peak_price") and price <= batch["peak_price"] * 0.98:
                    alerts.append(
                        f">>> [{name}] 第{i+1}批回落止盈触发! "
                        f"峰值{batch['peak_price']:.2f} -> 现价{price:.2f} (-{100*(1-price/batch['peak_price']):.1f}%) "
                        f"卖出{batch['shares']}股"
                    )
                    batch["sold"] = True
                    batch["sold_time"] = datetime.now().strftime("%H:%M:%S")
                    dirty[0] = True

    # ── 移动止盈关键位突破 ──
    for ts in cfg.get("trailing_stops", []):
        if quote["high"] >= ts["price_level"] and price >= ts["price_level"] * 0.99:
            alerts.append(
                f"!!! [{name}] 突破关键位 {ts['price_level']}! "
                f"现价{price:.2f} 最高{quote['high']:.2f} "
                f"止损应上移至 {ts['stop_up_to']}"
            )

    # ── 止损距离预警 ──
    dist_stop = (price - stop) / stop * 100
    if dist_stop <= 1.5:
        level = "!!!" if dist_stop <= 0.8 else "!!"
        alerts.append(
            f"{level} [{name}] 逼近止损! 现价{price:.2f} "
            f"距止损{stop}仅{dist_stop:+.1f}%"
        )

    return alerts


def status_line(cfg, quote):
    """生成单行状态"""
    code = cfg["code"]
    name = cfg["name"]
    price = quote["price"]
    cost = cfg["buy_price"]
    stop = cfg["stop_loss"]
    pct = (price - quote["preclose"]) / quote["preclose"] * 100
    cost_pct = (price - cost) / cost * 100
    dist_stop = (price - stop) / stop * 100

    icon = "[+]" if cost_pct > 0 else ("[~]" if cost_pct > -3 else "[!]")

    # 分批止盈进度
    batch_info = ""
    if cfg.get("take_profit_strategy") == "batch":
        sold = sum(1 for b in cfg.get("take_profit_batches", []) if b.get("sold"))
        total_batches = len(cfg.get("take_profit_batches", []))
        batch_info = f" | 止盈进度 {sold}/{total_batches}"

    # 剩余股数
    shares_left = cfg["shares"]
    if cfg.get("take_profit_strategy") == "batch":
        shares_sold = sum(b["shares"] for b in cfg.get("take_profit_batches", []) if b.get("sold"))
        shares_left = cfg["shares"] - shares_sold

    return (
        f"  {icon} {name}({code}) {price:.2f} | "
        f"今日{pct:+.2f}% | 盈亏{cost_pct:+.2f}% | "
        f"距止损{dist_stop:+.1f}% | "
        f"剩余{shares_left}股"
        f"{batch_info}"
    )


def main():
    print("=" * 55)
    print("  [!] 持仓重点监控 v2")
    print("  分批止盈 · 高点回落 · 移动止盈 · 关键位突破")
    print("=" * 55)

    # 加载持仓
    data = load_positions()
    holdings = data.get("holdings", [])
    if not holdings:
        print("  [!] 无持仓数据")
        return

    codes = [h["code"] for h in holdings]
    labels = [f"{h['name']}({h['code']})" for h in holdings]
    print(f"  监控标的: {', '.join(labels)}")
    print()

    while True:
        dirty = [False]
        try:
            quotes = fetch_quotes(codes)
            now = datetime.now().strftime("%H:%M:%S")
            today = datetime.now().strftime("%Y-%m-%d")

            print(f"[{now}]")

            all_alerts = []
            for h in holdings:
                code = h["code"]
                q = quotes.get(code)
                if not q:
                    print(f"  [?] {h['name']}({code}) 无数据")
                    continue

                # 检查告警
                alerts = check_holding(h, q, today, dirty)
                all_alerts.extend(alerts)

                # 打印状态
                print(status_line(h, q))

            # 打印告警
            if all_alerts:
                print()
                for a in all_alerts:
                    bar = "=" * 50
                    print(f"  {bar}")
                    print(f"  {a}")
                    print(f"  {bar}")
                print()

            # 回写状态
            if dirty[0]:
                try:
                    save_positions(data)
                except Exception as e:
                    print(f"  [!] 状态保存失败: {e}")

        except Exception as e:
            print(f"  [!] 异常: {e}")

        time.sleep(INTERVAL)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n监控结束")
