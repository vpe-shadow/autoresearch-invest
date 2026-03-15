#!/usr/bin/env python3
"""
backtest.py — Backtesting engine with ADR-based dynamic stops.

Supports both fixed % stops and ADR-based stops (when strategy signals it).
"""

import json
import sys
import time
import traceback
import pandas as pd
import numpy as np
from datetime import datetime

from prepare import load_universe
from strategy import (
    compute_signals,
    get_position_size,
    get_max_positions,
    get_stop_loss,
    get_take_profit,
)

# Import ADR functions if available
try:
    from strategy import uses_adr_stops, uses_trailing_stop, get_dynamic_stops
    HAS_ADR = True
except ImportError:
    HAS_ADR = False

INITIAL_CAPITAL = 100_000.0
COMMISSION = 0.001
RESULTS_FILE = "results.json"
TIME_BUDGET_SEC = 300


class Portfolio:
    def __init__(self, capital: float):
        self.initial_capital = capital
        self.cash = capital
        self.positions: dict[str, dict] = {}
        self.trades: list[dict] = []
        self.equity_curve: list[float] = []

    def buy(self, ticker: str, price: float, date, position_size: float,
            stop_info: dict = None):
        if ticker in self.positions or len(self.positions) >= get_max_positions():
            return
        allocation = self.cash * position_size
        shares = int(allocation / price)
        if shares <= 0:
            return
        cost = shares * price * (1 + COMMISSION)
        if cost > self.cash:
            return
        self.cash -= cost
        pos = {
            "shares": shares,
            "entry_price": price,
            "entry_date": str(date),
            "highest_price": price,  # for trailing stop
        }
        if stop_info:
            pos["stop_price"] = stop_info["stop_price"]
            pos["tp_price"] = stop_info["tp_price"]
            pos["trail_distance"] = stop_info.get("trail_distance")
            pos["use_adr"] = stop_info.get("use_adr", False)
        else:
            pos["stop_price"] = price * (1 + get_stop_loss())
            pos["tp_price"] = price * (1 + get_take_profit())
            pos["trail_distance"] = None
            pos["use_adr"] = False
        self.positions[ticker] = pos

    def sell(self, ticker: str, price: float, date, reason: str = "signal"):
        if ticker not in self.positions:
            return
        pos = self.positions.pop(ticker)
        revenue = pos["shares"] * price * (1 - COMMISSION)
        self.cash += revenue
        pnl = revenue - (pos["shares"] * pos["entry_price"] * (1 + COMMISSION))
        pnl_pct = (price / pos["entry_price"]) - 1
        self.trades.append({
            "ticker": ticker, "entry_date": pos["entry_date"],
            "exit_date": str(date),
            "entry_price": round(pos["entry_price"], 2),
            "exit_price": round(price, 2),
            "shares": pos["shares"], "pnl": round(pnl, 2),
            "pnl_pct": round(pnl_pct * 100, 2), "reason": reason,
            "adr_stops": pos.get("use_adr", False),
        })

    def check_stops(self, prices: dict[str, float], date):
        """Check ADR-based and fixed stops for all positions."""
        use_trailing = HAS_ADR and uses_trailing_stop()

        for ticker in list(self.positions.keys()):
            if ticker not in prices:
                continue
            pos = self.positions[ticker]
            price = prices[ticker]

            # Update highest price for trailing stop
            if price > pos.get("highest_price", 0):
                pos["highest_price"] = price

            # Trailing stop: adjust stop_price upward
            if use_trailing and pos.get("trail_distance") and pos.get("use_adr"):
                trail_stop = pos["highest_price"] - pos["trail_distance"]
                if trail_stop > pos["stop_price"]:
                    pos["stop_price"] = trail_stop

            # Check stop loss
            if price <= pos["stop_price"]:
                self.sell(ticker, price, date, reason="stop_loss")
                continue

            # Check take profit
            if price >= pos["tp_price"]:
                self.sell(ticker, price, date, reason="take_profit")

    def mark_to_market(self, prices: dict[str, float]) -> float:
        positions_value = sum(
            pos["shares"] * prices.get(ticker, pos["entry_price"])
            for ticker, pos in self.positions.items()
        )
        return self.cash + positions_value


def run_backtest(split: str = "val", results_file: str = None):
    if results_file is None:
        results_file = RESULTS_FILE
    start_time = time.time()

    print(f"Loading {split.upper()} data...")
    universe = load_universe(split)
    if not universe:
        print("ERROR: No data. Run prepare.py first.")
        sys.exit(1)

    print(f"Universe: {list(universe.keys())}")
    use_adr = HAS_ADR and uses_adr_stops()
    print(f"Stop mode: {'ADR-based dynamic' if use_adr else 'Fixed %'}")

    print("Computing signals...")
    all_signals = {}
    for ticker, df in universe.items():
        try:
            signals = compute_signals(df)
            all_signals[ticker] = signals
        except Exception as e:
            print(f"  {ticker}: signal error — {e}")
            traceback.print_exc()
            all_signals[ticker] = pd.Series(0, index=df.index)

    all_dates = sorted(set().union(*[df.index for df in universe.values()]))

    print("Running simulation...")
    portfolio = Portfolio(INITIAL_CAPITAL)
    position_size = get_position_size()

    for date in all_dates:
        if time.time() - start_time > TIME_BUDGET_SEC:
            print("TIME BUDGET EXCEEDED")
            break

        prices = {}
        for ticker, df in universe.items():
            if date in df.index:
                prices[ticker] = float(df.loc[date, "Close"])

        portfolio.check_stops(prices, date)

        for ticker in universe:
            if date not in all_signals[ticker].index:
                continue
            signal = all_signals[ticker].loc[date]
            if ticker not in prices:
                continue

            if signal == 1:
                stop_info = None
                if use_adr:
                    stop_info = get_dynamic_stops(universe[ticker], date, prices[ticker])
                portfolio.buy(ticker, prices[ticker], date, position_size, stop_info)
            elif signal == -1:
                portfolio.sell(ticker, prices[ticker], date, reason="signal")

        portfolio.equity_curve.append(portfolio.mark_to_market(prices))

    # Close remaining
    last_prices = {}
    for ticker, df in universe.items():
        if not df.empty:
            last_prices[ticker] = float(df.iloc[-1]["Close"])
    for ticker in list(portfolio.positions.keys()):
        if ticker in last_prices:
            portfolio.sell(ticker, last_prices[ticker], all_dates[-1], "end_of_backtest")

    # Metrics
    equity = np.array(portfolio.equity_curve)
    if len(equity) < 2:
        print("ERROR: Not enough data")
        sys.exit(1)

    total_return = (equity[-1] / INITIAL_CAPITAL) - 1
    daily_returns = np.diff(equity) / equity[:-1]
    sharpe = (daily_returns.mean() / daily_returns.std()) * np.sqrt(252) if daily_returns.std() > 0 else 0.0
    peak = np.maximum.accumulate(equity)
    drawdown = (equity - peak) / peak
    max_drawdown = float(drawdown.min())

    trades = portfolio.trades
    winning = [t for t in trades if t["pnl"] > 0]
    losing = [t for t in trades if t["pnl"] <= 0]
    win_rate = len(winning) / len(trades) if trades else 0
    gross_profit = sum(t["pnl"] for t in winning) if winning else 0
    gross_loss = abs(sum(t["pnl"] for t in losing)) if losing else 1
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    # Stop type breakdown
    stop_exits = [t for t in trades if t["reason"] == "stop_loss"]
    tp_exits = [t for t in trades if t["reason"] == "take_profit"]
    signal_exits = [t for t in trades if t["reason"] == "signal"]

    elapsed = time.time() - start_time

    results = {
        "timestamp": datetime.now().isoformat(),
        "split": split.upper(),
        "stop_mode": "ADR" if use_adr else "fixed",
        "elapsed_sec": round(elapsed, 1),
        "metrics": {
            "sharpe_ratio": round(sharpe, 4),
            "total_return_pct": round(total_return * 100, 2),
            "max_drawdown_pct": round(max_drawdown * 100, 2),
            "win_rate_pct": round(win_rate * 100, 1),
            "profit_factor": round(profit_factor, 2),
            "total_trades": len(trades),
            "winning_trades": len(winning),
            "losing_trades": len(losing),
            "final_equity": round(equity[-1], 2),
        },
        "exit_breakdown": {
            "stop_loss": len(stop_exits),
            "take_profit": len(tp_exits),
            "signal": len(signal_exits),
            "end_of_backtest": len([t for t in trades if t["reason"] == "end_of_backtest"]),
        },
        "summary": f"Sharpe={sharpe:.3f} | Return={total_return*100:.1f}% | MaxDD={max_drawdown*100:.1f}% | Trades={len(trades)} | WinRate={win_rate*100:.0f}%",
    }

    print("\n" + "=" * 60)
    print(f"BACKTEST RESULTS ({split.upper()}) — {'ADR Stops' if use_adr else 'Fixed Stops'}")
    print("=" * 60)
    for k, v in results["metrics"].items():
        print(f"  {k:>20s}: {v}")
    print(f"\n  Exit breakdown: SL={len(stop_exits)} TP={len(tp_exits)} Signal={len(signal_exits)}")
    print(f"\n  {results['summary']}")
    print(f"  Elapsed: {elapsed:.1f}s")
    print("=" * 60)

    with open(results_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to {results_file}")

    if trades:
        trades_df = pd.DataFrame(trades)
        trades_df.to_csv("trades.csv", index=False)

    return sharpe


if __name__ == "__main__":
    try:
        sharpe = run_backtest()
        print(f"\n>>> PRIMARY METRIC (sharpe_ratio): {sharpe:.4f}")
    except Exception as e:
        print(f"\nBACKTEST FAILED: {e}")
        traceback.print_exc()
        with open(RESULTS_FILE, "w") as f:
            json.dump({"timestamp": datetime.now().isoformat(), "error": str(e),
                        "metrics": {"sharpe_ratio": -999.0}}, f, indent=2)
        sys.exit(1)
