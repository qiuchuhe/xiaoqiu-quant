# -*- coding: utf-8 -*-
"""
更新 dashboard.html 里的持仓和自选股数据
每次换股后运行一次即可：python update_dashboard.py
"""
import json, re, os

BASE = os.path.dirname(os.path.abspath(__file__))
HTML = os.path.join(BASE, 'dashboard.html')
POS = os.path.join(BASE, '量化', '.position.json')
WL = os.path.join(BASE, '量化', '.my_watchlist.json')

# 读取所有持仓
positions = []
if os.path.exists(POS):
    with open(POS, encoding='utf-8') as f:
        p = json.load(f)
    for h in p.get('holdings', []):
        positions.append({
            'code': h['code'],
            'name': h['name'],
            'cost': h.get('buy_price', 0),
            'shares': h.get('shares', 100),
            'stop': h.get('stop_loss', 0),
            'tp': h.get('take_profit', 0),
        })

# 读取自选股
watch = []
wnames = {}
if os.path.exists(WL):
    with open(WL, encoding='utf-8') as f:
        wl = json.load(f)
    watch = list(wl.keys())
    wnames = wl

with open(HTML, encoding='utf-8') as f:
    html = f.read()

# 替换持仓数组
pos_js = json.dumps(positions, ensure_ascii=False)
html = re.sub(r'var POSITIONS = \[[^\]]*\];', f'var POSITIONS = {pos_js};', html)

# 替换自选股列表
watch_js = json.dumps(watch)
wnames_js = json.dumps(wnames, ensure_ascii=False)
html = re.sub(r'var WATCH = \[[^\]]*\];', f'var WATCH = {watch_js};', html)
html = re.sub(r'var WNAMES = \{[^}]*\};', f'var WNAMES = {wnames_js};', html)

with open(HTML, 'w', encoding='utf-8') as f:
    f.write(html)

print(f'Dashboard updated: {len(positions)} positions, {len(watch)} watchlist')
for pos in positions:
    print(f'  {pos["name"]}({pos["code"]}) x{pos["shares"]} @{pos["cost"]}')
