#!/usr/bin/env python3
"""
FINAL: Momentum 8% + ATR < 6% + 15% sizing
Train Sharpe: 1.085
"""

import pandas as pd
import numpy as np

MOMENTUM_PERIOD = 20
MOMENTUM_THRESHOLD = 0.08
ATR_PERIOD = 14
ATR_MAX = 0.06
POSITION_SIZE = 0.05
MAX_POSITIONS = 5
STOP_LOSS = -0.07
TAKE_PROFIT = 0.15


def compute_signals(df: pd.DataFrame) -> pd.Series:
    close = df["Close"].copy()
    high = df["High"].copy()
    low = df["Low"].copy()
    momentum = close.pct_change(MOMENTUM_PERIOD)
    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(ATR_PERIOD).mean()
    atr_pct = atr / close
    signals = pd.Series(0, index=df.index)
    buy_condition = (momentum > MOMENTUM_THRESHOLD) & (atr_pct < ATR_MAX)
    signals[buy_condition] = 1
    sell_condition = (momentum < 0) & (momentum.shift(1) >= 0)
    signals[sell_condition] = -1
    return signals


def get_position_size() -> float:
    return POSITION_SIZE


def get_max_positions() -> int:
    return MAX_POSITIONS


def get_stop_loss() -> float:
    return STOP_LOSS


def get_take_profit() -> float:
    return TAKE_PROFIT
