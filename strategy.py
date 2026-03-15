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
POSITION_SIZE = 0.1   # 10% per position
MAX_POSITIONS = 5     # max concurrent positions
STOP_LOSS = -0.05     # -5% stop loss
TAKE_PROFIT = 0.15    # +15% take profit


# ─── Signal Generation ───────────────────────────────────────────────────────

def compute_signals(df: pd.DataFrame) -> pd.Series:
    """
    Given a DataFrame with columns [Open, High, Low, Close, Volume],
    return a Series of signals: 1 (buy), -1 (sell), 0 (hold).

    The agent should modify this function to improve the strategy.
    """
    close = df["Close"].copy()

    # Moving averages
    fast_ma = close.rolling(FAST_MA).mean()
    slow_ma = close.rolling(SLOW_MA).mean()

    # RSI
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0).rolling(RSI_PERIOD).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(RSI_PERIOD).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))

    # Signals
    signals = pd.Series(0, index=df.index)

    # Buy: fast MA crosses above slow MA AND RSI not overbought
    buy_condition = (fast_ma > slow_ma) & (fast_ma.shift(1) <= slow_ma.shift(1)) & (rsi < RSI_OVERBOUGHT)
    signals[buy_condition] = 1

    # Sell: fast MA crosses below slow MA OR RSI overbought
    sell_condition = (fast_ma < slow_ma) & (fast_ma.shift(1) >= slow_ma.shift(1)) | (rsi > RSI_OVERBOUGHT)
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
