#!/usr/bin/env python3
"""
strategy.py — Hybrid: fixed % stops with asymmetric risk/reward

Combines the robustness of fixed stops with the ADR insight:
tight stop + wide target (cut losers fast, let winners run).

THE AGENT MODIFIES THIS FILE.
"""

import pandas as pd
import numpy as np

# ─── Signal Parameters ───────────────────────────────────────────────────────

MOMENTUM_PERIOD = 20
MOMENTUM_THRESHOLD = 0.08
ATR_PERIOD = 14
ATR_MAX = 0.06

# ─── Macro Regime Filter ─────────────────────────────────────────────────────
# Suppress BUY signals when broad market is in downtrend
# SPY must be above its 50-day MA AND VIX must be below threshold

REGIME_ENABLED = True
REGIME_BENCHMARK = "SPY"       # S&P 500 ETF
REGIME_MA_PERIOD = 50          # 50-day moving average
REGIME_VIX_MAX = 28.0          # Suppress buys when VIX > 28 (elevated fear)

# ─── Asymmetric Fixed Stops (inspired by ADR 1:5 finding) ────────────────────

STOP_LOSS = -0.07      # Tight -3% stop (cut losers fast)
TAKE_PROFIT = 0.1     # Wide +15% target (let winners run)

# ─── Position Sizing ─────────────────────────────────────────────────────────

POSITION_SIZE = 0.05
MAX_POSITIONS = 5


# ─── Signal Generation ───────────────────────────────────────────────────────

def compute_signals(df: pd.DataFrame, regime_ok: bool = True) -> pd.Series:
    """Compute buy/sell signals. If regime_ok=False, suppress BUY signals."""
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
    if regime_ok:
        signals[buy_condition] = 1
    # If regime_ok=False, no BUY signals are generated (risk-off mode)

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

def uses_adr_stops() -> bool:
    return False

def uses_trailing_stop() -> bool:
    return False
