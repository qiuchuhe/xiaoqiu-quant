# -*- coding: utf-8 -*-
"""八卦六爻比分预测——世界杯6月23日"""
import random, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def coin_toss():
    s = sum(random.randint(0,1) for _ in range(3))
    return {0:6, 1:7, 2:8, 3:9}[s]

matches = [
    ('阿根廷 vs 奥地利', '01:00'),
    ('法国 vs 伊拉克', '05:00'),
    ('挪威 vs 塞内加尔', '08:00'),
    ('约旦 vs 阿尔及利亚', '11:00'),
]

random.seed()

SEP = '-' * 58
print('=' * 62)
print('  🔮 六爻比分预测 · 世界杯 6月23日')
print('=' * 62)

for mname, mtime in matches:
    lines = [coin_toss() for _ in range(6)]
    yang = sum(1 for l in lines if l in (7,9))
    yin = 6 - yang
    changes = sum(1 for l in lines if l in (6,9))

    home_power = sum(1 for l in lines[:3] if l in (7,9))
    away_power = sum(1 for l in lines[3:] if l in (7,9))

    # Base score from trigram power
    home_options = {3: [2,3,3], 2: [1,2,2], 1: [0,1,1], 0: [0,0,1]}
    away_options = {3: [2,3,3], 2: [1,2,2], 1: [0,1,1], 0: [0,0,1]}
    home_goals = random.choice(home_options[home_power])
    away_goals = random.choice(away_options[away_power])

    # Adjust by differential
    diff = home_power - away_power
    if diff >= 2:
        home_goals = max(home_goals, 2)
        away_goals = min(away_goals, 1)
    elif diff <= -2:
        away_goals = max(away_goals, 2)
        home_goals = min(home_goals, 1)

    # Half time
    ht_home = home_goals // 2 if home_goals >= 2 else (1 if home_goals >= 1 and random.random() > 0.5 else 0)
    ht_away = away_goals // 2 if away_goals >= 2 else (1 if away_goals >= 1 and random.random() > 0.5 else 0)

    # Outcomes
    if home_goals > away_goals:
        outcome = '主胜'
        emoji = '🏆'
    elif home_goals < away_goals:
        outcome = '客胜'
        emoji = '🏆'
    else:
        outcome = '平局'
        emoji = '🤝'

    if ht_home > ht_away:
        ht_outcome = '主队领先'
    elif ht_home < ht_away:
        ht_outcome = '客队领先'
    else:
        ht_outcome = '平局'

    if changes == 0:
        confidence = '⭐⭐⭐ 卦象稳定'
    elif changes == 1:
        confidence = '⭐⭐ 一爻动'
    elif changes == 2:
        confidence = '⭐ 两爻动有变数'
    else:
        confidence = '⚡ 多爻动，天机乱'

    teams = mname.split(' vs ')

    print(SEP)
    print('  ⚽ %s  ⏰ %s' % (mname, mtime))
    print(SEP)
    print('  能量: 主%d阳 vs 客%d阳  |  动爻: %d' % (home_power, away_power, changes))
    print('  半场: %s %d - %d %s  (%s)' % (teams[0], ht_home, ht_away, teams[1], ht_outcome))
    print('  全场: %s %d - %d %s  (%s %s)' % (teams[0], home_goals, away_goals, teams[1], outcome, emoji))
    print('  信心: %s' % confidence)

print('')
print('=' * 62)
print('  🎲 易经曰：信则有，不信则无。赢钱请我喝茶！')
print('=' * 62)
