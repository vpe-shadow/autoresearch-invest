#!/usr/bin/env python3
"""
strategy.py — THE AGENT MODIFIES THIS FILE

Exp 4: Breakout (52-week high)
"""

import pandas as pd
import numpy as np

# ─── Strategy Parameters ─────────────────────────────────────────────────────

BREAKOUT_PERIOD = 252  # ~1 year
LOOKBACK_PERIOD = 20   # Exit if below 20-day low

# Position sizing: fraction of portfolio per trade
POSITION_SIZE = 0.12   # 12% per position
MAX_POSITIONS = 5     # max concurrent positions
STOP_LOSS = -0.08     # -8% stop loss
TAKE_PROFIT = 0.20    # +20% take profit


# ─── Signal Generation ───────────────────────────────────────────────────────

def compute_signals(df: pd.DataFrame) -> pd.Series:
    """
    Breakout strategy: buy on new highs
    """
    close = df["Close"].copy()
    high = df["High"].copy()
    low = df["Low"].copy()

    # Rolling highs/lows
    rolling_high = high.rolling(BREAKOUT_PERIOD).max()
    rolling_low = low.rolling(LOOKBACK_PERIOD).min()

    # Signals
    signals = pd.Series(0, index=df.index)

    # Buy: new 252-day high
    buy_condition = close >= rolling_high
    signals[buy_condition] = 1

    # Sell: below 20-day low
    sell_condition = close <= rolling_low
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
