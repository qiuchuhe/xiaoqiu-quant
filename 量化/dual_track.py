# -*- coding: utf-8 -*-
"""
双轨并行 —— 两套独立策略，各跑各的，一个月后PK

  轨道A：策略1 均线多头扫描 → 信号全收 → 独立买卖
  轨道B：朋友逻辑 裸K+龙头+热门 → 独立买卖

用法:
    python dual_track.py                        # 看板
    python dual_track.py --report               # 双轨盈亏对比
    python dual_track.py --import-a             # 导入策略1信号→轨道A自动入场
    python dual_track.py --add-b CODE --price X --reason "裸K回调企稳"
    python dual_track.py --close-a CODE --pnl 8.5
    python dual_track.py --close-b CODE --pnl -5.0
    python dual_track.py --history              # 完整交易记录
"""
import json, os, sys
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TRACK_FILE = os.path.join(BASE_DIR, 'dual_track.json')
STRATEGY_RESULT = os.path.join(os.path.dirname(BASE_DIR), '策略量化', '策略1', '策略一_result.json')


def _today():
    return datetime.now().strftime('%Y-%m-%d')


def _now():
    return datetime.now().strftime('%H:%M')


def load():
    if os.path.exists(TRACK_FILE):
        with open(TRACK_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        "start_date": _today(),
        "track_a": {"positions": [], "history": []},
        "track_b": {"positions": [], "history": []},
    }


def save(data):
    data["updated"] = datetime.now().strftime('%Y-%m-%d %H:%M')
    with open(TRACK_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ===========================================
# 轨道A：策略1自动入场
# ===========================================

def import_track_a():
    """策略1信号 → 轨道A全部自动入场"""
    if not os.path.exists(STRATEGY_RESULT):
        print("[!] 策略1结果文件不存在")
        print("   先跑: cd 策略量化/策略1 && python scanner.py --once")
        return

    with open(STRATEGY_RESULT, 'r', encoding='utf-8') as f:
        result = json.load(f)

    # 兼容两种格式: 'signals' (旧) 或 'candidates' (策略1扫描器)
    signals = result.get('signals') or result.get('candidates', [])
    # 只导入有买点的
    signals = [s for s in signals if s.get('buy_signals')]
    if not signals:
        print("[i] 策略1今日无信号，轨道A空仓等待")
        return

    track = load()
    today = _today()
    existing = {p['code'] for p in track['track_a']['positions']}

    added = 0
    for s in signals:
        code = s.get('code', '')
        if code in existing:
            continue
        # 合并买点类型
        buy_types = [sig.get('type', '') for sig in s.get('buy_signals', [])]
        buy_type = '+'.join(buy_types) if buy_types else ''
        reason_parts = []
        for sig in s.get('buy_signals', []):
            reason_parts.append(sig.get('detail', ''))
        reason = ' | '.join(reason_parts)[:120]
        pos = {
            'code': code,
            'name': s.get('name', ''),
            'entry_price': s.get('price', 0),
            'entry_date': today,
            'entry_time': _now(),
            'buy_type': buy_type,
            'reason': reason,
            'status': 'holding',
        }
        track['track_a']['positions'].append(pos)
        added += 1

    if added:
        save(track)
        print(f"[A] 轨道A +{added} 只自动入场")
        for p in track['track_a']['positions']:
            if p['entry_date'] == today:
                print(f"    {p['name']}({p['code']})  {p['entry_price']}  {p['buy_type']}")
    else:
        print("[A] 轨道A 无新信号")


# ===========================================
# 轨道B：朋友逻辑手动入场
# ===========================================

def add_track_b(code, price, name='', reason=''):
    """朋友逻辑选股 → 轨道B入场"""
    track = load()
    code = str(code).zfill(6)
    today = _today()

    # 检查是否已持仓
    for p in track['track_b']['positions']:
        if p['code'] == code and p['status'] == 'holding':
            print(f"[!] {p['name']}({code}) 轨道B已持有")
            return

    if not name:
        try:
            from 小秋核心.data import get_quotes
            qs = get_quotes([code])
            if qs:
                name = qs[0].get('name', code)
                if not price:
                    price = qs[0].get('price', 0)
        except Exception:
            name = name or code

    pos = {
        'code': code,
        'name': name or code,
        'entry_price': price,
        'entry_date': today,
        'entry_time': _now(),
        'reason': reason[:120],
        'status': 'holding',
    }
    track['track_b']['positions'].append(pos)
    save(track)
    print(f"[B] 轨道B入场: {name}({code}) @ {price}")
    print(f"   理由: {reason}")
    return pos


# ===========================================
# 平仓
# ===========================================

def close_position(track_label, code, pnl_pct):
    """平仓并记录"""
    track = load()
    key = f'track_{track_label}'
    code = str(code).zfill(6)

    for p in track[key]['positions']:
        if p['code'] == code and p['status'] == 'holding':
            p['status'] = 'closed'
            p['exit_date'] = _today()
            p['exit_time'] = _now()
            p['pnl_pct'] = round(float(pnl_pct), 2)
            # 移到历史
            track[key]['history'].append(dict(p))
            track[key]['positions'] = [x for x in track[key]['positions'] if x['code'] != code]
            save(track)
            label = 'A' if track_label == 'a' else 'B'
            print(f"[{label}] 平仓: {p['name']}({code}) 盈亏 {pnl_pct:+.1f}%")
            return

    print(f"[!] {code} 不在轨道{track_label.upper()}持仓中")


# ===========================================
# 报告
# ===========================================

def _track_stats(track_data):
    """统计一个轨道的表现"""
    history = track_data.get('history', [])
    positions = track_data.get('positions', [])
    total_trades = len(history)
    wins = [h for h in history if h.get('pnl_pct', 0) > 0]
    losses = [h for h in history if h.get('pnl_pct', 0) <= 0]
    total_pnl = sum(h.get('pnl_pct', 0) for h in history)
    win_rate = len(wins) / total_trades * 100 if total_trades else 0
    avg_win = sum(h.get('pnl_pct', 0) for h in wins) / len(wins) if wins else 0
    avg_loss = sum(h.get('pnl_pct', 0) for h in losses) / len(losses) if losses else 0

    return {
        'total_trades': total_trades,
        'wins': len(wins),
        'losses': len(losses),
        'win_rate': win_rate,
        'total_pnl': total_pnl,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'holding': len(positions),
        'positions': positions,
        'history': history,
    }


def show_report():
    track = load()
    a = _track_stats(track['track_a'])
    b = _track_stats(track['track_b'])

    start = track.get('start_date', '?')
    print(f"\n{'='*60}")
    print(f"  双轨PK报告 | 起始: {start} | 至今: {_today()}")
    print(f"{'='*60}")

    # 对比表
    print(f"\n  {'指标':<16} {'轨道A(策略1)':<20} {'轨道B(朋友逻辑)':<20}")
    print(f"  {'-'*56}")
    print(f"  {'持仓中':<16} {a['holding']:<20} {b['holding']:<20}")
    print(f"  {'已完成交易':<16} {a['total_trades']:<20} {b['total_trades']:<20}")
    print(f"  {'胜率':<16} {a['win_rate']:.0f}%{'':<16} {b['win_rate']:.0f}%")
    print(f"  {'累计盈亏':<16} {a['total_pnl']:+.1f}%{'':<16} {b['total_pnl']:+.1f}%")
    print(f"  {'平均盈利':<16} {a['avg_win']:+.1f}%{'':<16} {b['avg_win']:+.1f}%")
    print(f"  {'平均亏损':<16} {a['avg_loss']:+.1f}%{'':<16} {b['avg_loss']:+.1f}%")

    # 当前持仓
    if a['positions']:
        print(f"\n  [A] 当前持仓:")
        for p in a['positions']:
            print(f"      {p['name']}({p['code']}) @{p['entry_price']} | {p.get('buy_type','')} | {p['entry_date']}")

    if b['positions']:
        print(f"\n  [B] 当前持仓:")
        for p in b['positions']:
            print(f"      {p['name']}({p['code']}) @{p['entry_price']} | {p.get('reason','')[:40]} | {p['entry_date']}")

    # 领先者
    if a['total_trades'] > 0 or b['total_trades'] > 0:
        print(f"\n  {'='*56}")
        diff = a['total_pnl'] - b['total_pnl']
        if diff > 0:
            print(f"  >>> 轨道A 领先 +{diff:.1f}%")
        elif diff < 0:
            print(f"  >>> 轨道B 领先 +{abs(diff):.1f}%")
        else:
            print(f"  >>> 持平")

    print()


def show_history():
    track = load()
    all_trades = []
    for h in track['track_a']['history']:
        all_trades.append({**h, 'track': 'A'})
    for h in track['track_b']['history']:
        all_trades.append({**h, 'track': 'B'})
    all_trades.sort(key=lambda x: x.get('exit_date', ''))

    if not all_trades:
        print("\n  暂无交易记录")
        return

    print(f"\n  {'='*70}")
    print(f"  完整交易记录")
    print(f"  {'='*70}")
    total_a = 0
    total_b = 0
    for t in all_trades:
        track_label = t['track']
        pnl = t.get('pnl_pct', 0)
        tag = '[+]' if pnl > 0 else '[-]'
        print(f"  {tag} [{track_label}] {t['name']}({t['code']})")
        print(f"       入场: {t['entry_date']} @{t['entry_price']}  |  出场: {t.get('exit_date','?')}  |  盈亏: {pnl:+.1f}%")
        if track_label == 'A':
            total_a += pnl
        else:
            total_b += pnl
    print(f"\n  轨道A累计: {total_a:+.1f}%  |  轨道B累计: {total_b:+.1f}%")
    print()


def show_board():
    """快速看板"""
    track = load()
    a = _track_stats(track['track_a'])
    b = _track_stats(track['track_b'])

    print(f"\n  {'='*50}")
    print(f"  双轨看板 | {_today()}")
    print(f"  {'='*50}")
    print(f"  [A] 策略1: {a['holding']}持仓 | {a['total_trades']}已平 | 累计{a['total_pnl']:+.1f}% | 胜率{a['win_rate']:.0f}%")
    if a['positions']:
        for p in a['positions']:
            print(f"      {p['name']}({p['code']}) @{p['entry_price']}  {p.get('buy_type','')}")
    else:
        print(f"      (空仓)")

    print(f"  [B] 朋友逻辑: {b['holding']}持仓 | {b['total_trades']}已平 | 累计{b['total_pnl']:+.1f}% | 胜率{b['win_rate']:.0f}%")
    if b['positions']:
        for p in b['positions']:
            print(f"      {p['name']}({p['code']}) @{p['entry_price']}  {p.get('reason','')[:50]}")
    else:
        print(f"      (空仓)")

    print(f"\n  python dual_track.py --report  查看详细PK报告")
    print()


# ===========================================
# 盘中监控：跟踪止盈 + 硬止损
# ===========================================

HARD_STOP = -0.05       # 硬止损 -5%
TRAILING_ACTIVATE = 0.03  # 盈利>3%激活跟踪
TRAILING_STOP = 0.05    # 从最高点回撤5%卖出


def _get_realtime_price(code):
    """获取单只实时价（腾讯API）"""
    try:
        import urllib.request, re
        mkt = 'sh' if code.startswith(('6', '9')) else 'sz'
        url = f'http://qt.gtimg.cn/q={mkt}{code}'
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        raw = urllib.request.urlopen(req, timeout=5).read().decode('gbk', errors='replace')
        m = re.search(r'="(.+?)"', raw)
        if m:
            f = m.group(1).split('~')
            if len(f) >= 40:
                return float(f[3]) if f[3] else 0, float(f[33]) if f[33] else 0  # price, high
    except Exception:
        pass
    return 0, 0


def check_stops():
    """检查所有持仓的止损/跟踪止盈"""
    track = load()
    alerts = []

    for label, key in [('A', 'track_a'), ('B', 'track_b')]:
        for p in track[key]['positions']:
            if p.get('status') != 'holding':
                continue
            code = p['code']
            entry = p['entry_price']
            price, high_today = _get_realtime_price(code)
            if price <= 0:
                continue

            pnl_pct = (price - entry) / entry

            # 更新最高价
            peak = p.get('peak_price', entry)
            if price > peak:
                peak = price
                p['peak_price'] = peak

            # 1. 硬止损
            if pnl_pct <= HARD_STOP:
                alerts.append({
                    'track': label, 'code': code, 'name': p['name'],
                    'price': price, 'entry': entry, 'pnl': round(pnl_pct * 100, 1),
                    'type': '🔴 硬止损', 'peak': peak,
                })

            # 2. 跟踪止盈（盈利>3%激活）
            elif pnl_pct > TRAILING_ACTIVATE:
                drawdown = (price - peak) / peak
                if drawdown <= -TRAILING_STOP:
                    alerts.append({
                        'track': label, 'code': code, 'name': p['name'],
                        'price': price, 'entry': entry, 'pnl': round(pnl_pct * 100, 1),
                        'type': f'🟡 跟踪止盈 (高{peak:.2f}→现{price:.2f}回撤{drawdown*100:.1f}%)',
                        'peak': peak,
                    })
                else:
                    alerts.append({
                        'track': label, 'code': code, 'name': p['name'],
                        'price': price, 'entry': entry, 'pnl': round(pnl_pct * 100, 1),
                        'type': f'🟢 跟踪中 (高{peak:.2f} 距止盈线{(-drawdown-TRAILING_STOP)*100:.1f}%)',
                        'peak': peak,
                    })
            else:
                # 3. 正常区间（-5%到+3%）
                alerts.append({
                    'track': label, 'code': code, 'name': p['name'],
                    'price': price, 'entry': entry, 'pnl': round(pnl_pct * 100, 1),
                    'type': '⚪ 观察中',
                    'peak': entry,
                })

    save(track)

    if not alerts:
        print("\n  无持仓")
        return alerts

    # 按紧急度排序
    order = {'🔴': 0, '🟡': 1, '🟢': 2}
    alerts.sort(key=lambda a: order.get(a['type'][:2], 9))

    print(f"\n  {'='*55}")
    print(f"  📡 盘中监控 | {_now()}")
    print(f"  {'='*55}")
    print(f"  {'轨道':<4} {'标的':<12} {'入场':>6} {'现价':>6} {'盈亏':>7} {'信号'}")
    print(f"  {'-'*55}")
    for a in alerts:
        print(f"  [{a['track']}] {a['name']:<8} {a['entry']:>6.2f} {a['price']:>6.2f} {a['pnl']:>+6.1f}% {a['type']}")
    print()

    return alerts


# ===========================================
# 主入口
# ===========================================

if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser(description='双轨PK：策略1 vs 朋友逻辑')
    p.add_argument('--import-a', action='store_true', help='导入策略1信号→轨道A入场')
    p.add_argument('--add-b', type=str, metavar='CODE', help='朋友逻辑选股→轨道B入场')
    p.add_argument('--price', type=float, help='入场价（配合--add-b）')
    p.add_argument('--name', type=str, help='股票名（配合--add-b）')
    p.add_argument('--reason', type=str, default='', help='选股理由')
    p.add_argument('--close-a', type=str, metavar='CODE', help='轨道A平仓')
    p.add_argument('--close-b', type=str, metavar='CODE', help='轨道B平仓')
    p.add_argument('--pnl', type=float, help='盈亏百分比')
    p.add_argument('--report', action='store_true', help='双轨PK报告')
    p.add_argument('--history', action='store_true', help='完整交易记录')
    p.add_argument('--check', action='store_true', help='盘中监控：检查止损/跟踪止盈')
    args = p.parse_args()

    if args.import_a:
        import_track_a()
    elif args.add_b:
        add_track_b(args.add_b, price=args.price or 0, name=args.name or '', reason=args.reason)
    elif args.close_a:
        close_position('a', args.close_a, args.pnl or 0)
    elif args.close_b:
        close_position('b', args.close_b, args.pnl or 0)
    elif args.report:
        show_report()
    elif args.history:
        show_history()
    elif args.check:
        check_stops()
    else:
        show_board()
