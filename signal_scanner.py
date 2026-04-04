#!/usr/bin/env python3
"""
signal_scanner.py — Daily signal scanner for live trading alerts.

Fetches recent price data, computes momentum + ATR signals,
and outputs actionable buy/sell/hold for each ticker.

Includes MACRO REGIME FILTER (added Apr 4, 2026):
- SPY must be above 50-day MA (uptrend)
- VIX must be below 28 (no elevated fear)
- If either fails → BUY signals suppressed (risk-off mode)

Designed to run pre-market via cron → Telegram alert.
"""

import json
import sys
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import yfinance as yf

# ─── Strategy Parameters (must match strategy.py) ────────────────────────────

MOMENTUM_PERIOD = 20
MOMENTUM_THRESHOLD = 0.08  # 8%
ATR_PERIOD = 14
ATR_MAX = 0.06  # 6%
STOP_LOSS = -0.07
TAKE_PROFIT = 0.15

# ─── Macro Regime Filter ─────────────────────────────────────────────────────
# Suppress BUY signals when broad market is in downtrend

REGIME_ENABLED = True
REGIME_BENCHMARK = "SPY"
REGIME_MA_PERIOD = 50        # SPY must be above 50-day MA
REGIME_VIX_TICKER = "^VIX"
REGIME_VIX_MAX = 28.0        # Suppress buys when VIX > 28

UNIVERSE = [
    "NVDA", "AVGO", "AAPL", "TSLA", "META", "GOOG", "MSFT",
    "PANW", "ISRG", "MNDY", "GRMN", "PTON", "DOCU", "QCOM", "BABA",
]

# How many days of history to fetch (need enough for indicator warmup)
LOOKBACK_DAYS = 90

# State file — tracks open positions for sell signals
STATE_FILE = "scanner_state.json"


# ─── Macro Regime Check ─────────────────────────────────────────────────────

def check_macro_regime() -> dict:
    """
    Check if the broad market is in a favorable regime for buying.
    Returns dict with regime_ok (bool), details (str), spy_ok, vix_ok.
    """
    if not REGIME_ENABLED:
        return {"regime_ok": True, "details": "Regime filter disabled",
                "spy_ok": True, "vix_ok": True, "spy_price": None,
                "spy_ma50": None, "vix_level": None}

    regime = {"regime_ok": True, "spy_ok": True, "vix_ok": True,
              "spy_price": None, "spy_ma50": None, "vix_level": None}
    details = []

    # Check SPY vs 50-day MA
    try:
        spy = yf.download(REGIME_BENCHMARK, period="120d", interval="1d",
                          auto_adjust=True, progress=False)
        if isinstance(spy.columns, pd.MultiIndex):
            spy.columns = spy.columns.get_level_values(0)
        if not spy.empty and len(spy) >= REGIME_MA_PERIOD:
            spy_close = float(spy["Close"].iloc[-1])
            spy_ma50 = float(spy["Close"].rolling(REGIME_MA_PERIOD).mean().iloc[-1])
            spy_vs_ma = ((spy_close / spy_ma50) - 1) * 100
            regime["spy_price"] = round(spy_close, 2)
            regime["spy_ma50"] = round(spy_ma50, 2)
            if spy_close < spy_ma50:
                regime["spy_ok"] = False
                details.append(f"SPY ${spy_close:.0f} BELOW 50-MA ${spy_ma50:.0f} ({spy_vs_ma:+.1f}%)")
            else:
                details.append(f"SPY ${spy_close:.0f} above 50-MA ${spy_ma50:.0f} ({spy_vs_ma:+.1f}%)")
    except Exception as e:
        details.append(f"SPY check failed: {e}")

    # Check VIX
    try:
        vix = yf.download(REGIME_VIX_TICKER, period="5d", interval="1d",
                          auto_adjust=True, progress=False)
        if isinstance(vix.columns, pd.MultiIndex):
            vix.columns = vix.columns.get_level_values(0)
        if not vix.empty:
            vix_level = float(vix["Close"].iloc[-1])
            regime["vix_level"] = round(vix_level, 1)
            if vix_level > REGIME_VIX_MAX:
                regime["vix_ok"] = False
                details.append(f"VIX {vix_level:.1f} ABOVE threshold {REGIME_VIX_MAX}")
            else:
                details.append(f"VIX {vix_level:.1f} (threshold {REGIME_VIX_MAX})")
    except Exception as e:
        details.append(f"VIX check failed: {e}")

    regime["regime_ok"] = regime["spy_ok"] and regime["vix_ok"]
    regime["details"] = " | ".join(details)
    return regime


# ─── Core Logic ──────────────────────────────────────────────────────────────

def fetch_data(ticker: str) -> pd.DataFrame | None:
    """Fetch recent daily data for a ticker."""
    try:
        df = yf.download(
            ticker, period=f"{LOOKBACK_DAYS}d", interval="1d",
            auto_adjust=True, progress=False
        )
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        if df.empty or len(df) < MOMENTUM_PERIOD + 5:
            return None
        return df
    except Exception:
        return None


def compute_signal(df: pd.DataFrame) -> dict:
    """Compute momentum + ATR signal for latest bar."""
    close = df["Close"]
    high = df["High"]
    low = df["Low"]

    # Momentum
    momentum = close.pct_change(MOMENTUM_PERIOD)

    # ATR
    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(ATR_PERIOD).mean()
    atr_pct = atr / close

    latest_mom = float(momentum.iloc[-1])
    latest_atr = float(atr_pct.iloc[-1])
    latest_price = float(close.iloc[-1])
    prev_mom = float(momentum.iloc[-2]) if len(momentum) > 1 else 0

    # Signal logic (matches strategy.py)
    # BUY may be suppressed by regime filter in main()
    signal = "HOLD"
    if latest_mom > MOMENTUM_THRESHOLD and latest_atr < ATR_MAX:
        signal = "BUY"
    elif latest_mom < 0 and prev_mom >= 0:
        signal = "SELL"

    return {
        "signal": signal,
        "price": round(latest_price, 2),
        "momentum_pct": round(latest_mom * 100, 1),
        "atr_pct": round(latest_atr * 100, 1),
        "date": str(df.index[-1].date()),
    }


def load_state() -> dict:
    """Load position tracking state."""
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"positions": {}, "history": []}


def save_state(state: dict):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def format_report(results: list[dict], state: dict, regime: dict = None) -> str:
    """Format results as a Telegram-friendly report."""
    now = datetime.now()
    lines = [f"📊 **Signal Scanner** — {now.strftime('%a %b %d, %Y')}"]
    lines.append("")

    # Macro regime status
    if regime:
        if regime["regime_ok"]:
            lines.append(f"🟢 **Macro: RISK-ON** — {regime['details']}")
        else:
            lines.append(f"🔴 **Macro: RISK-OFF** — {regime['details']}")
            lines.append("_⚠️ BUY signals suppressed until macro improves_")
        lines.append("")

    buys = [r for r in results if r["signal"] == "BUY"]
    sells = [r for r in results if r["signal"] == "SELL"]
    holds = [r for r in results if r["signal"] == "HOLD"]
    errors = [r for r in results if r["signal"] == "ERROR"]

    # Active positions
    if state.get("positions"):
        lines.append("📌 **Tracking positions:**")
        for ticker, pos in state["positions"].items():
            entry = pos["entry_price"]
            current = next((r["price"] for r in results if r["ticker"] == ticker), entry)
            pnl = ((current / entry) - 1) * 100
            emoji = "🟢" if pnl > 0 else "🔴"
            sl_price = round(entry * (1 + STOP_LOSS), 2)
            tp_price = round(entry * (1 + TAKE_PROFIT), 2)
            lines.append(f"  {emoji} {ticker}: ${current} ({pnl:+.1f}%) | SL ${sl_price} | TP ${tp_price}")
        lines.append("")

    if buys:
        lines.append("🟢 **BUY signals:**")
        for r in sorted(buys, key=lambda x: x["momentum_pct"], reverse=True):
            lines.append(f"  • **{r['ticker']}** ${r['price']} — momentum +{r['momentum_pct']}%, ATR {r['atr_pct']}%")
        lines.append("")

    # Show suppressed signals (would-be buys blocked by regime)
    suppressed = [r for r in results if r.get("_suppressed")]
    if suppressed:
        lines.append("🟡 **Suppressed by macro filter (would-be BUY):**")
        for r in suppressed:
            lines.append(f"  • {r['ticker']} ${r['price']} — momentum +{r['momentum_pct']}%, ATR {r['atr_pct']}%")
        lines.append("")

    if sells:
        lines.append("🔴 **SELL signals:**")
        for r in sells:
            lines.append(f"  • **{r['ticker']}** ${r['price']} — momentum {r['momentum_pct']}%")
        lines.append("")

    if holds:
        hold_tickers = [r["ticker"] for r in holds]
        lines.append(f"⚪ **No signal:** {', '.join(hold_tickers)}")
        lines.append("")

    if errors:
        err_tickers = [r["ticker"] for r in errors]
        lines.append(f"⚠️ **Data errors:** {', '.join(err_tickers)}")
        lines.append("")

    # Strategy reminder
    lines.append("_Strategy: 20d momentum >8% + ATR <6% | SL -7% | TP +15%_")
    lines.append("_Macro filter: SPY > 50-MA + VIX < 28 | 5% sizing | Max 5 positions_")

    return "\n".join(lines)


def main():
    state = load_state()
    results = []

    # Check macro regime FIRST
    print("Checking macro regime...")
    regime = check_macro_regime()
    if regime["regime_ok"]:
        print(f"  ✅ RISK-ON: {regime['details']}")
    else:
        print(f"  ⚠️ RISK-OFF: {regime['details']}")
        print("  BUY signals will be suppressed.")
    print()

    print(f"Scanning {len(UNIVERSE)} tickers...")
    for ticker in UNIVERSE:
        print(f"  {ticker}...", end=" ")
        df = fetch_data(ticker)
        if df is None:
            print("ERROR")
            results.append({"ticker": ticker, "signal": "ERROR", "price": 0,
                            "momentum_pct": 0, "atr_pct": 0})
            continue

        info = compute_signal(df)
        info["ticker"] = ticker
        results.append(info)
        print(f"{info['signal']} (mom={info['momentum_pct']}%, atr={info['atr_pct']}%)")

        # Suppress BUY if macro regime is risk-off
        if info["signal"] == "BUY" and not regime["regime_ok"]:
            info["_suppressed"] = True
            info["signal"] = "HOLD"  # Downgrade to HOLD
            print(f"    → BUY suppressed (risk-off regime)")

        # Track positions
        if info["signal"] == "BUY" and ticker not in state["positions"]:
            state["positions"][ticker] = {
                "entry_price": info["price"],
                "entry_date": info["date"],
            }
            state["history"].append({
                "action": "BUY", "ticker": ticker, "price": info["price"],
                "date": info["date"],
            })
        elif info["signal"] == "SELL" and ticker in state["positions"]:
            entry = state["positions"].pop(ticker)
            pnl_pct = ((info["price"] / entry["entry_price"]) - 1) * 100
            state["history"].append({
                "action": "SELL", "ticker": ticker, "price": info["price"],
                "date": info["date"], "pnl_pct": round(pnl_pct, 1),
            })

        # Check stop loss / take profit on tracked positions
        if ticker in state["positions"]:
            entry_price = state["positions"][ticker]["entry_price"]
            change = (info["price"] / entry_price) - 1
            if change <= STOP_LOSS:
                state["positions"].pop(ticker)
                state["history"].append({
                    "action": "STOP_LOSS", "ticker": ticker, "price": info["price"],
                    "date": info["date"], "pnl_pct": round(change * 100, 1),
                })
                info["signal"] = "SELL"
                info["_reason"] = "stop_loss"
            elif change >= TAKE_PROFIT:
                state["positions"].pop(ticker)
                state["history"].append({
                    "action": "TAKE_PROFIT", "ticker": ticker, "price": info["price"],
                    "date": info["date"], "pnl_pct": round(change * 100, 1),
                })
                info["signal"] = "SELL"
                info["_reason"] = "take_profit"

    save_state(state)

    report = format_report(results, state, regime)
    print("\n" + "=" * 60)
    print(report)
    print("=" * 60)

    # Save report for cron delivery
    with open("latest_signal_report.txt", "w") as f:
        f.write(report)

    # Also save as JSON — include regime data
    with open("latest_signals.json", "w") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "regime": {
                "ok": regime["regime_ok"],
                "spy_price": regime.get("spy_price"),
                "spy_ma50": regime.get("spy_ma50"),
                "vix_level": regime.get("vix_level"),
            },
            "results": results,
            "positions": state["positions"],
        }, f, indent=2)

    print(f"\nReport saved. {len(state['positions'])} tracked positions.")
    return report


if __name__ == "__main__":
    report = main()
