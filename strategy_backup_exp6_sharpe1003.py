#!/usr/bin/env python3
"""
strategy.py — ADR-based dynamic stop-loss strategy

Uses Average Daily Range (ADR) to set stop-loss and take-profit levels
outside normal price fluctuations, avoiding premature exits.

Entry: 20-day momentum > threshold + ATR volatility filter
Exit: ADR-based trailing stop + ADR-based take profit

THE AGENT MODIFIES THIS FILE.
"""

import pandas as pd
import numpy as np

# ─── Signal Parameters ───────────────────────────────────────────────────────

MOMENTUM_PERIOD = 20
MOMENTUM_THRESHOLD = 0.08  # 8% momentum for entry
ATR_PERIOD = 14
ATR_MAX = 0.06  # Max ATR% for entry (volatility filter)

# ─── ADR Stop Parameters ─────────────────────────────────────────────────────

ADR_PERIOD = 14           # Lookback for Average Daily Range
ADR_STOP_MULTIPLIER = 0.75 # Stop loss = entry - ADR * multiplier
ADR_TP_MULTIPLIER = 4.0   # Take profit = entry + ADR * multiplier
ADR_TRAILING = True       # Use trailing stop based on ADR
ADR_TRAIL_MULTIPLIER = 2.0  # Trailing stop = highest close - ADR * multiplier

# ─── Fallback fixed stops (used if ADR data unavailable) ─────────────────────

STOP_LOSS = -0.07
TAKE_PROFIT = 0.15

# ─── Position Sizing ─────────────────────────────────────────────────────────

POSITION_SIZE = 0.05
MAX_POSITIONS = 5


# ─── ADR Computation ─────────────────────────────────────────────────────────

def compute_adr(df: pd.DataFrame) -> pd.Series:
    """Compute Average Daily Range as a dollar value."""
    daily_range = df["High"] - df["Low"]
    adr = daily_range.rolling(ADR_PERIOD).mean()
    return adr


def compute_adr_pct(df: pd.DataFrame) -> pd.Series:
    """Compute ADR as a percentage of close price."""
    adr = compute_adr(df)
    return adr / df["Close"]


# ─── Signal Generation ───────────────────────────────────────────────────────

def compute_signals(df: pd.DataFrame) -> pd.Series:
    """
    Entry signals based on momentum + ATR filter.
    Exit logic is handled by the backtest engine using ADR stops.
    """
    close = df["Close"].copy()
    high = df["High"].copy()
    low = df["Low"].copy()

    # Momentum
    momentum = close.pct_change(MOMENTUM_PERIOD)

    # ATR (for entry filter)
    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(ATR_PERIOD).mean()
    atr_pct = atr / close

    signals = pd.Series(0, index=df.index)

    # Buy: strong momentum + low volatility
    buy_condition = (momentum > MOMENTUM_THRESHOLD) & (atr_pct < ATR_MAX)
    signals[buy_condition] = 1

    # Sell signal: momentum reversal (backup — ADR stops are primary exit)
    sell_condition = (momentum < 0) & (momentum.shift(1) >= 0)
    signals[sell_condition] = -1

    return signals


# ─── ADR Stop Levels ─────────────────────────────────────────────────────────

def compute_stop_levels(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute per-bar ADR-based stop loss and take profit levels.
    Returns DataFrame with columns: adr, stop_distance, tp_distance
    
    These are DOLLAR distances from entry price:
    - stop_price = entry_price - stop_distance
    - tp_price = entry_price + tp_distance
    - trail_stop = highest_since_entry - trail_distance
    """
    adr = compute_adr(df)
    
    stops = pd.DataFrame(index=df.index)
    stops["adr"] = adr
    stops["stop_distance"] = adr * ADR_STOP_MULTIPLIER
    stops["tp_distance"] = adr * ADR_TP_MULTIPLIER
    stops["trail_distance"] = adr * ADR_TRAIL_MULTIPLIER
    
    return stops


def get_dynamic_stops(df: pd.DataFrame, entry_date, entry_price: float) -> dict:
    """
    Get ADR-based stop levels for a specific entry.
    
    Returns dict with:
    - stop_price: initial stop loss level
    - tp_price: take profit level  
    - trail_distance: ADR * multiplier for trailing stop
    - adr_pct: ADR as % of price (for reporting)
    """
    stops = compute_stop_levels(df)
    
    if entry_date in stops.index and not pd.isna(stops.loc[entry_date, "adr"]):
        adr = float(stops.loc[entry_date, "adr"])
        stop_dist = float(stops.loc[entry_date, "stop_distance"])
        tp_dist = float(stops.loc[entry_date, "tp_distance"])
        trail_dist = float(stops.loc[entry_date, "trail_distance"])
        
        return {
            "stop_price": entry_price - stop_dist,
            "tp_price": entry_price + tp_dist,
            "trail_distance": trail_dist,
            "adr": adr,
            "adr_pct": round(adr / entry_price * 100, 2),
            "use_adr": True,
        }
    else:
        # Fallback to fixed %
        return {
            "stop_price": entry_price * (1 + STOP_LOSS),
            "tp_price": entry_price * (1 + TAKE_PROFIT),
            "trail_distance": None,
            "adr": None,
            "adr_pct": None,
            "use_adr": False,
        }


# ─── Standard interface (backward compatible) ────────────────────────────────

def get_position_size() -> float:
    return POSITION_SIZE


def get_max_positions() -> int:
    return MAX_POSITIONS


def get_stop_loss() -> float:
    """Fallback fixed stop loss."""
    return STOP_LOSS


def get_take_profit() -> float:
    """Fallback fixed take profit."""
    return TAKE_PROFIT


def uses_adr_stops() -> bool:
    """Flag for backtest engine to use ADR-based stops."""
    return True


def uses_trailing_stop() -> bool:
    """Flag for backtest engine to use trailing stops."""
    return ADR_TRAILING
