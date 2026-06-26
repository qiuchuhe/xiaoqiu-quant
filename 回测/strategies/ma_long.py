# -*- coding: utf-8 -*-
"""
策略1：均线多头 + 温和放量
条件: MA5>MA10>MA20 | 股价<20 | 量比1.0-10.0x
买点A: 回调MA10不破 + 收阳
买点B: 放量站稳MA5 + 量比≥1.5
止损: -5% | 止盈: +10% | 100股/笔
"""
import backtrader as bt


class MALongStrategy(bt.Strategy):
    params = (
        ('ma_short', 5),
        ('ma_mid', 10),
        ('ma_long', 20),
        ('max_price', 20),
        ('vr_min', 1.0),
        ('vr_max', 10.0),
        ('vr_avg_period', 20),
        ('stop_loss', -0.05),
        ('take_profit', 0.10),
        ('shares', 100),
    )

    def __init__(self):
        # 均线
        self.ma5 = bt.indicators.SMA(self.data.close, period=self.p.ma_short)
        self.ma10 = bt.indicators.SMA(self.data.close, period=self.p.ma_mid)
        self.ma20 = bt.indicators.SMA(self.data.close, period=self.p.ma_long)

        # 量比 = 当日量 / N日均量
        self.avg_vol = bt.indicators.SMA(self.data.volume, period=self.p.vr_avg_period)
        self.volume_ratio = self.data.volume / self.avg_vol

        # 状态
        self.order = None
        self.entry_price = 0
        self.entry_type = None  # 'A' or 'B'

    def log(self, txt):
        dt = self.datas[0].datetime.date(0)
        print(f'  [{dt}] {txt}')

    def notify_order(self, order):
        if order.status in [order.Completed]:
            if order.isbuy():
                self.entry_price = order.executed.price
                self.log(f'买入 {order.executed.price:.2f} ({self.entry_type})')
            else:
                pnl = (order.executed.price - self.entry_price) / self.entry_price * 100
                self.log(f'卖出 {order.executed.price:.2f} P&L:{pnl:+.1f}%')
                self.entry_price = 0
                self.entry_type = None
        self.order = None

    def next(self):
        # 有挂单中，不重复下单
        if self.order:
            return

        # ---- 无持仓：找买点 ----
        if not self.position:
            # 前置过滤
            if self.data.close[0] > self.p.max_price:
                return
            if self.ma5[0] < self.ma10[0] or self.ma10[0] < self.ma20[0]:
                return
            # 量比过滤
            vr = self.volume_ratio[0]
            if vr < self.p.vr_min or vr > self.p.vr_max:
                return

            # 买点A：回调MA10不破 + 收阳
            if (self.data.low[0] >= self.ma10[0] and
                self.data.close[0] > self.data.open[0]):
                self.entry_type = 'A'
                self.order = self.buy(size=self.p.shares)

            # 买点B：放量站稳MA5 + 量比≥1.5
            elif (self.data.close[0] > self.ma5[0] and vr >= 1.5):
                self.entry_type = 'B'
                self.order = self.buy(size=self.p.shares)

        # ---- 有持仓：止损/止盈 ----
        else:
            pnl_pct = (self.data.close[0] - self.entry_price) / self.entry_price

            if pnl_pct <= self.p.stop_loss:
                self.order = self.sell(size=self.p.shares)
            elif pnl_pct >= self.p.take_profit:
                self.order = self.sell(size=self.p.shares)
