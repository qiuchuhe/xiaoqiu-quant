# -*- coding: utf-8 -*-
"""
策略1 组合回测 — 3000总本金，最多同时持2只，100股/笔
逻辑: 收集所有票的信号 → 按时间排序 → 模拟真实交易
"""
import sys, os, json
from datetime import datetime, timedelta
from collections import defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from run_backtest import fetch_kline, load_watchlist

# 策略参数
MAX_POSITIONS = 2
SHARES_PER_TRADE = 100
STOP_LOSS = -0.05
TAKE_PROFIT = 0.10
MAX_PRICE = 20
MA_SHORT, MA_MID, MA_LONG = 5, 10, 20
VR_MIN, VR_MAX = 1.0, 10.0


def detect_signals(df, code, name):
    """从K线数据中检测所有买卖信号点"""
    if len(df) < 60:
        return []

    # 计算指标
    df = df.copy()
    df['ma5'] = df['close'].rolling(MA_SHORT).mean()
    df['ma10'] = df['close'].rolling(MA_MID).mean()
    df['ma20'] = df['close'].rolling(MA_LONG).mean()
    df['avg_vol'] = df['volume'].rolling(20).mean()
    df['vr'] = df['volume'] / df['avg_vol']

    signals = []
    in_position = False
    entry_price = 0
    entry_type = None
    entry_date = None

    for i in range(MA_LONG + 5, len(df)):
        row = df.iloc[i]
        price = row['close']
        high = row['high']
        low = row['low']
        vr = row['vr'] if pd.notna(row['vr']) else 0

        if not in_position:
            # 前置过滤
            if price > MAX_PRICE:
                continue
            if not (row['ma5'] > row['ma10'] > row['ma20']):
                continue
            if vr < VR_MIN or vr > VR_MAX:
                continue

            # 买点A: 回调MA10不破+收阳
            if low >= row['ma10'] and row['close'] > row['open']:
                in_position = True
                entry_price = price
                entry_type = 'A'
                entry_date = df.index[i]
                signals.append({
                    'code': code, 'name': name,
                    'date': entry_date, 'type': 'BUY',
                    'buy_type': 'A', 'price': price,
                })

            # 买点B: 放量站稳MA5+量比≥1.5
            elif price > row['ma5'] and vr >= 1.5:
                in_position = True
                entry_price = price
                entry_type = 'B'
                entry_date = df.index[i]
                signals.append({
                    'code': code, 'name': name,
                    'date': entry_date, 'type': 'BUY',
                    'buy_type': 'B', 'price': price,
                })

        else:
            # 持仓中，检查止损/止盈
            pnl = (price - entry_price) / entry_price
            sell_reason = None
            if pnl <= STOP_LOSS:
                sell_reason = 'STOP'
            elif pnl >= TAKE_PROFIT:
                sell_reason = 'TAKE'
            # 均线走坏也卖（MA5<MA10死叉）
            elif row['ma5'] < row['ma10']:
                sell_reason = 'MA_DEAD'

            if sell_reason:
                signals.append({
                    'code': code, 'name': name,
                    'date': df.index[i], 'type': 'SELL',
                    'reason': sell_reason,
                    'price': price,
                    'entry_price': entry_price,
                    'entry_date': entry_date,
                    'pnl_pct': pnl * 100,
                })
                in_position = False
                entry_price = 0

    # 如果最后还持仓，按最后收盘价平仓
    if in_position:
        signals.append({
            'code': code, 'name': name,
            'date': df.index[-1], 'type': 'SELL',
            'reason': 'EOD',
            'price': df.iloc[-1]['close'],
            'entry_price': entry_price,
            'entry_date': entry_date,
            'pnl_pct': (df.iloc[-1]['close'] - entry_price) / entry_price * 100,
        })

    return signals


def run_portfolio(codes_dict, days=365, cash=3000, max_pos=2):
    """组合回测：共用资金池，最多同时持N只"""
    # 收集所有信号（带本地缓存）
    CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'klines')
    os.makedirs(CACHE_DIR, exist_ok=True)

    all_signals = []
    total, done, skipped = 0, 0, 0
    for code, name in codes_dict.items():
        total += 1
        try:
            # 先读缓存
            cache_file = os.path.join(CACHE_DIR, f'{code}.pkl')
            if os.path.exists(cache_file):
                df = pd.read_pickle(cache_file)
            else:
                df = fetch_kline(code, days)
                df.to_pickle(cache_file)

            sigs = detect_signals(df, code, name)
            if sigs:
                all_signals.extend(sigs)
                buys = sum(1 for s in sigs if s['type'] == 'BUY')
                sells = sum(1 for s in sigs if s['type'] == 'SELL')
                print(f"  {name}({code}): {buys}买/{sells}卖")
        except Exception as e:
            skipped += 1
            if skipped <= 5:
                print(f"  {code} 跳过: {e}")
        done += 1
        if done % 15 == 0:
            print(f"  ... {done}/{total} (跳过{skipped})")

    # 按时间排序
    all_signals.sort(key=lambda s: s['date'])

    # 模拟组合交易
    available_cash = cash
    positions = {}  # code -> {entry_price, shares, entry_date, buy_type}
    trades = []
    equity_curve = []

    buy_events = [s for s in all_signals if s['type'] == 'BUY']
    sell_events_by_code = defaultdict(list)
    for s in all_signals:
        if s['type'] == 'SELL':
            sell_events_by_code[s['code']].append(s)

    # 模拟：按买入时间顺序处理
    for buy in buy_events:
        code = buy['code']
        # 找到对应的卖出事件
        sells_for_code = sell_events_by_code[code]
        matching_sell = None
        for s in sells_for_code:
            if s['entry_date'] == buy['date']:
                matching_sell = s
                break

        if not matching_sell:
            continue

        # 检查是否有持仓限额
        if len(positions) >= max_pos:
            # 检查能不能先平掉一个
            continue

        # 检查现金
        cost = buy['price'] * SHARES_PER_TRADE
        if available_cash < cost:
            continue

        # 执行买入
        available_cash -= cost
        positions[code] = {
            'entry_price': buy['price'],
            'shares': SHARES_PER_TRADE,
            'entry_date': buy['date'],
            'buy_type': buy['buy_type'],
        }

        # 执行卖出（用匹配的sell事件）
        sell_price = matching_sell['price']
        pnl_amount = (sell_price - buy['price']) * SHARES_PER_TRADE
        available_cash += sell_price * SHARES_PER_TRADE
        pnl_pct = (sell_price - buy['price']) / buy['price'] * 100

        trades.append({
            'code': code, 'name': buy['name'],
            'buy_date': buy['date'], 'buy_price': buy['price'],
            'sell_date': matching_sell['date'], 'sell_price': sell_price,
            'pnl': pnl_amount, 'pnl_pct': pnl_pct,
            'buy_type': buy['buy_type'], 'reason': matching_sell['reason'],
        })

        del positions[code]

    # 汇总
    total_pnl = sum(t['pnl'] for t in trades)
    wins = sum(1 for t in trades if t['pnl'] > 0)
    avg_win = sum(t['pnl_pct'] for t in trades if t['pnl'] > 0) / max(wins, 1)
    avg_loss = sum(t['pnl_pct'] for t in trades if t['pnl'] <= 0) / max(len(trades) - wins, 1)

    return {
        'trades': trades,
        'total_pnl': total_pnl,
        'final_cash': available_cash,
        'total_return': total_pnl / cash * 100,
        'win_rate': wins / max(len(trades), 1) * 100,
        'count': len(trades),
        'wins': wins,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
    }


if __name__ == '__main__':
    import argparse, pandas as pd

    p = argparse.ArgumentParser()
    p.add_argument('--days', type=int, default=365)
    p.add_argument('--cash', type=int, default=3000)
    p.add_argument('--max-pos', type=int, default=2)
    args = p.parse_args()

    # 加载看盘自选股
    wl_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           '量化', '.my_watchlist.json')
    with open(wl_path, encoding='utf-8') as f:
        wl = json.load(f)
    codes = {c.replace('sh','').replace('sz',''): n for c, n in wl.items()}
    print(f"加载看盘: {len(codes)}只\n")

    result = run_portfolio(codes, args.days, args.cash, args.max_pos)

    print(f"\n{'='*60}")
    print(f"  组合回测 | 本金{args.cash} | 最多{args.max_pos}只 | {result['count']}笔交易")
    print(f"{'='*60}")
    print(f"  总收益: {result['total_pnl']:+.0f}元 ({result['total_return']:+.2f}%)")
    print(f"  最终资金: {result['final_cash']:.0f}")
    print(f"  胜率: {result['win_rate']:.1f}% ({result['wins']}/{result['count']})")
    print(f"  均盈: {result['avg_win']:+.2f}% | 均亏: {result['avg_loss']:+.2f}%")

    print(f"\n  最近10笔:")
    for t in result['trades'][-10:]:
        print(f"  {t['buy_date'].strftime('%m-%d') if hasattr(t['buy_date'],'strftime') else str(t['buy_date'])[:10]} → "
              f"{t['sell_date'].strftime('%m-%d') if hasattr(t['sell_date'],'strftime') else str(t['sell_date'])[:10]} "
              f"{t['name']:6s} {t['buy_price']:.2f}→{t['sell_price']:.2f} "
              f"{t['pnl_pct']:+.1f}% [{t['buy_type']}/{t['reason']}]")
