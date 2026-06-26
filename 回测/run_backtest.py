# -*- coding: utf-8 -*-
"""
策略1回测 —— 简化版（均线+量比+价格过滤，不含换手率）
用法:
    python run_backtest.py                          # 默认测试中科三环 近1年
    python run_backtest.py --code 000970 --days 365
    python run_backtest.py --code 600226,000970,002185 --days 180
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import backtrader as bt
import akshare as ak
from datetime import datetime, timedelta

from strategies.ma_long import MALongStrategy


class AKShareData(bt.feeds.PandasData):
    """适配akshare的K线数据"""
    params = (
        ('datetime', None),
        ('open', 'open'),
        ('high', 'high'),
        ('low', 'low'),
        ('close', 'close'),
        ('volume', 'volume'),
        ('openinterest', -1),
    )


def fetch_kline(code, days=365):
    """从akshare获取历史日K（强制绕过VPN代理）"""
    import urllib.request, json, ssl

    end = datetime.now().strftime('%Y%m%d')
    start = (datetime.now() - timedelta(days=days)).strftime('%Y%m%d')

    # 直接调东方财富K线API，强制不走代理
    secid = f'0.{code}' if code.startswith('0') else f'1.{code}'
    url = (
        f'https://push2his.eastmoney.com/api/qt/stock/kline/get?'
        f'fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f116'
        f'&ut=7eea3edcaed734bea9cbfc24409ed989&klt=101&fqt=1'
        f'&secid={secid}&beg={start}&end={end}'
    )

    # 创建不使用任何代理的opener
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    proxy_handler = urllib.request.ProxyHandler({})
    https_handler = urllib.request.HTTPSHandler(context=ctx)
    opener = urllib.request.build_opener(proxy_handler, https_handler)
    opener.addheaders = [
        ('User-Agent', 'Mozilla/5.0'),
        ('Referer', 'https://quote.eastmoney.com/'),
    ]

    with opener.open(url, timeout=15) as resp:
        data = json.loads(resp.read().decode('utf-8'))

    klines = data.get('data', {}).get('klines', [])
    if not klines:
        raise ValueError(f'{code} 无K线数据')

    rows = []
    for line in klines:
        parts = line.split(',')
        rows.append({
            'datetime': parts[0],
            'open': float(parts[1]),
            'close': float(parts[2]),
            'high': float(parts[3]),
            'low': float(parts[4]),
            'volume': float(parts[5]),
        })

    df = pd.DataFrame(rows)
    df['datetime'] = pd.to_datetime(df['datetime'])
    df = df.set_index('datetime')
    return df


def run_single(code, days=365, cash=3000, plot=False):
    """单只股票回测"""
    print(f'\n{"="*50}')
    print(f'  {code} | 回测{days}天 | 本金{cash}')
    print(f'{"="*50}')

    df = fetch_kline(code, days)
    print(f'  数据: {len(df)}根K线 ({df.index[0].strftime("%Y-%m-%d")} ~ {df.index[-1].strftime("%Y-%m-%d")})')

    cerebro = bt.Cerebro()
    cerebro.addstrategy(MALongStrategy)
    cerebro.adddata(AKShareData(dataname=df))
    cerebro.broker.setcash(cash)
    cerebro.broker.setcommission(commission=0.00025)  # 万2.5
    cerebro.addsizer(bt.sizers.FixedSize, stake=100)

    start_val = cerebro.broker.getvalue()
    print(f'  初始: {start_val:.0f}')

    cerebro.run()

    end_val = cerebro.broker.getvalue()
    ret = (end_val - start_val) / start_val * 100
    print(f'  最终: {end_val:.0f} | 收益: {ret:+.2f}%')

    return {
        'code': code,
        'start': start_val,
        'end': end_val,
        'return': ret,
        'bars': len(df),
    }


def run_batch(codes, days=365, cash=3000):
    """批量回测"""
    results = []
    for code in codes:
        code = code.strip()
        try:
            r = run_single(code, days, cash)
            results.append(r)
        except Exception as e:
            print(f'  {code} 失败: {e}')

    # 汇总
    print(f'\n{"="*60}')
    print(f'  回测汇总 | {len(results)}只 | 本金{cash}')
    print(f'{"="*60}')
    total_ret = sum(r['return'] for r in results)
    wins = sum(1 for r in results if r['return'] > 0)
    print(f'  总收益: {total_ret:+.2f}% | 胜率: {wins}/{len(results)}')
    print(f'  平均: {total_ret/len(results):+.2f}%')
    for r in sorted(results, key=lambda x: -x['return']):
        print(f'  {r["code"]}: {r["bars"]}K  {r["return"]:+.2f}%')

    return results


def load_watchlist():
    """从小秋看盘加载自选股"""
    wl_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           '量化', '.my_watchlist.json')
    if os.path.exists(wl_path):
        import json as j
        with open(wl_path, encoding='utf-8') as f:
            wl = j.load(f)
        # 去掉 sh/sz 前缀
        codes = [c.replace('sh','').replace('sz','') for c in wl.keys()]
        return codes
    return []


if __name__ == '__main__':
    import argparse, pandas as pd
    p = argparse.ArgumentParser()
    p.add_argument('--code', type=str, default='',
                   help='股票代码，多个用逗号分隔。留空=全量看盘自选股')
    p.add_argument('--days', type=int, default=365)
    p.add_argument('--cash', type=int, default=3000)
    args = p.parse_args()

    if args.code:
        codes = args.code.split(',')
    else:
        codes = load_watchlist()
        print(f'从看盘加载: {len(codes)}只')

    if len(codes) == 1:
        run_single(codes[0], args.days, args.cash)
    else:
        run_batch(codes, args.days, args.cash)
