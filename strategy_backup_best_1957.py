#!/usr/bin/env python3
"""
strategy.py — THE AGENT MODIFIES THIS FILE

This is the only file the autonomous agent touches.
It defines a trading strategy that the backtest engine calls.

The strategy receives historical price data and must return
a series of signals: 1 (buy/long), -1 (sell/short), 0 (flat/hold).

Current baseline: Simple dual moving average crossover.
"""

import pandas as pd
import numpy as np

# ─── Strategy Parameters ─────────────────────────────────────────────────────

FAST_MA = 10       # Fast moving average period
SLOW_MA = 30       # Slow moving average period
RSI_PERIOD = 14    # RSI lookback
RSI_OVERSOLD = 30  # RSI buy threshold
RSI_OVERBOUGHT = 70  # RSI sell threshold

# Position sizing: fraction of portfolio per trade
POSITION_SIZE = 0.545   # 54.5% per position
MAX_POSITIONS = 5     # max concurrent positions
STOP_LOSS = -0.08     # -8% stop loss
TAKE_PROFIT = 0.08    # +8% take profit


# ─── Signal Generation ───────────────────────────────────────────────────────

def compute_signals(df: pd.DataFrame) -> pd.Series:
    """
    Given a DataFrame with columns [Open, High, Low, Close, Volume],
    return a Series of signals: 1 (buy), -1 (sell), 0 (hold).

    The agent should modify this function to improve the strategy.
    """
    close = df["Close"].copy()

    # MACD
    exp1 = close.ewm(span=12, adjust=False).mean()
    exp2 = close.ewm(span=26, adjust=False).mean()
    macd = exp1 - exp2
    signal_line = macd.ewm(span=9, adjust=False).mean()

    # Signals
    signals = pd.Series(0, index=df.index)

    # Buy: MACD crosses above signal line
    buy_condition = (macd > signal_line) & (macd.shift(1) <= signal_line.shift(1))
    signals[buy_condition] = 1

    # Sell: MACD crosses below signal line
    sell_condition = (macd < signal_line) & (macd.shift(1) >= signal_line.shift(1))
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
