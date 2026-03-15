#!/usr/bin/env python3
"""
strategy.py — THE AGENT MODIFIES THIS FILE

Exp 10: Try even tighter momentum threshold (10% instead of 8%)
"""

import pandas as pd
import numpy as np

# ─── Strategy Parameters ─────────────────────────────────────────────────────

MOMENTUM_PERIOD = 20
MOMENTUM_THRESHOLD = 0.10  # 10% minimum return (stricter)
ATR_PERIOD = 14
ATR_MAX = 0.06  # Maximum volatility allowed

# Position sizing: fraction of portfolio per trade
POSITION_SIZE = 0.15   # 15% per position
MAX_POSITIONS = 5     # max concurrent positions
STOP_LOSS = -0.07     # -7% stop loss
TAKE_PROFIT = 0.15    # +15% take profit


# ─── Signal Generation ───────────────────────────────────────────────────────

def compute_signals(df: pd.DataFrame) -> pd.Series:
    """
    Momentum strategy with strict volatility filter
    """
    close = df["Close"].copy()
    high = df["High"].copy()
    low = df["Low"].copy()

    # Momentum = N-day return
    momentum = close.pct_change(MOMENTUM_PERIOD)

    # ATR
    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(ATR_PERIOD).mean()
    
    # Normalized ATR (as % of price)
    atr_pct = atr / close

    # Signals
    signals = pd.Series(0, index=df.index)

    # Buy: strong momentum + low volatility
    buy_condition = (momentum > MOMENTUM_THRESHOLD) & (atr_pct < ATR_MAX)
    signals[buy_condition] = 1

    # Sell: momentum fades
    sell_condition = (momentum < 0) & (momentum.shift(1) >= 0)
    signals[sell_condition] = -1

    return signals


def get_position_size() -> float:
    """Return fraction of portfolio to allocate per trade."""
    return POSITION_SIZE


def get_max_positions() -> int:
    """Return maximum number of concurrent positions."""
    return MAX_POSITIONS


def get_stop_loss() -> float:
    """Return stop loss threshold (negative float)."""
    return STOP_LOSS


def get_take_profit() -> float:
    """Return take profit threshold (positive float)."""
    return TAKE_PROFIT
