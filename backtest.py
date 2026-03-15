#!/usr/bin/env python3
"""
backtest.py — Backtesting engine + metrics. Do NOT modify.

Runs strategy.py against validation data, computes performance metrics,
and outputs a JSON result file for the autonomous loop to evaluate.
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

# ─── Constants ───────────────────────────────────────────────────────────────

INITIAL_CAPITAL = 100_000.0
COMMISSION = 0.001  # 0.1% per trade (round trip)
RESULTS_FILE = "results.json"
TIME_BUDGET_SEC = 300  # 5 minutes max

# ─── Portfolio Simulator ─────────────────────────────────────────────────────

class Portfolio:
    def __init__(self, capital: float):
        self.initial_capital = capital
        self.cash = capital
        self.positions: dict[str, dict] = {}  # ticker -> {shares, entry_price, entry_date}
        self.trades: list[dict] = []
        self.equity_curve: list[float] = []

    def buy(self, ticker: str, price: float, date, position_size: float):
        if ticker in self.positions:
            return  # already holding
        if len(self.positions) >= get_max_positions():
            return  # max positions reached

        allocation = self.cash * position_size
        shares = int(allocation / price)
        if shares <= 0:
            return

        cost = shares * price * (1 + COMMISSION)
        if cost > self.cash:
            return

        self.cash -= cost
        self.positions[ticker] = {
            "shares": shares,
            "entry_price": price,
            "entry_date": str(date),
        }

    def sell(self, ticker: str, price: float, date, reason: str = "signal"):
        if ticker not in self.positions:
            return

        pos = self.positions.pop(ticker)
        revenue = pos["shares"] * price * (1 - COMMISSION)
        self.cash += revenue

        pnl = revenue - (pos["shares"] * pos["entry_price"] * (1 + COMMISSION))
        pnl_pct = (price / pos["entry_price"]) - 1

        self.trades.append({
            "ticker": ticker,
            "entry_date": pos["entry_date"],
            "exit_date": str(date),
            "entry_price": round(pos["entry_price"], 2),
            "exit_price": round(price, 2),
            "shares": pos["shares"],
            "pnl": round(pnl, 2),
            "pnl_pct": round(pnl_pct * 100, 2),
            "reason": reason,
        })

    def check_stops(self, prices: dict[str, float], date):
        """Check stop loss and take profit for all positions."""
        stop_loss = get_stop_loss()
        take_profit = get_take_profit()

        for ticker in list(self.positions.keys()):
            if ticker not in prices:
                continue
            price = prices[ticker]
            entry = self.positions[ticker]["entry_price"]
            change = (price / entry) - 1

            if change <= stop_loss:
                self.sell(ticker, price, date, reason="stop_loss")
            elif change >= take_profit:
                self.sell(ticker, price, date, reason="take_profit")

    def mark_to_market(self, prices: dict[str, float]) -> float:
        """Return total portfolio value."""
        positions_value = sum(
            pos["shares"] * prices.get(ticker, pos["entry_price"])
            for ticker, pos in self.positions.items()
        )
        return self.cash + positions_value


# ─── Backtest Runner ─────────────────────────────────────────────────────────

def run_backtest():
    start_time = time.time()

    print("Loading validation data...")
    universe = load_universe("val")
    if not universe:
        print("ERROR: No data found. Run prepare.py first.")
        sys.exit(1)

    print(f"Universe: {list(universe.keys())}")

    # Compute signals for each ticker
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

    # Get all unique dates across the universe
    all_dates = sorted(set().union(*[df.index for df in universe.values()]))

    # Simulate
    print("Running simulation...")
    portfolio = Portfolio(INITIAL_CAPITAL)
    position_size = get_position_size()

    for date in all_dates:
        # Check time budget
        if time.time() - start_time > TIME_BUDGET_SEC:
            print("TIME BUDGET EXCEEDED — stopping early")
            break

        # Get current prices
        prices = {}
        for ticker, df in universe.items():
            if date in df.index:
                prices[ticker] = float(df.loc[date, "Close"])

        # Check stops first
        portfolio.check_stops(prices, date)

        # Process signals
        for ticker in universe:
            if date not in all_signals[ticker].index:
                continue
            signal = all_signals[ticker].loc[date]
            if ticker not in prices:
                continue

            if signal == 1:
                portfolio.buy(ticker, prices[ticker], date, position_size)
            elif signal == -1:
                portfolio.sell(ticker, prices[ticker], date, reason="signal")

        # Record equity
        portfolio.equity_curve.append(portfolio.mark_to_market(prices))

    # Close remaining positions at last known prices
    last_prices = {}
    for ticker, df in universe.items():
        if not df.empty:
            last_prices[ticker] = float(df.iloc[-1]["Close"])
    for ticker in list(portfolio.positions.keys()):
        if ticker in last_prices:
            portfolio.sell(ticker, last_prices[ticker], all_dates[-1], reason="end_of_backtest")

    # ─── Compute Metrics ─────────────────────────────────────────────────

    equity = np.array(portfolio.equity_curve)
    if len(equity) < 2:
        print("ERROR: Not enough data points for metrics")
        sys.exit(1)

    total_return = (equity[-1] / INITIAL_CAPITAL) - 1
    daily_returns = np.diff(equity) / equity[:-1]

    # Sharpe Ratio (annualized, 252 trading days)
    if daily_returns.std() > 0:
        sharpe = (daily_returns.mean() / daily_returns.std()) * np.sqrt(252)
    else:
        sharpe = 0.0

    # Max Drawdown
    peak = np.maximum.accumulate(equity)
    drawdown = (equity - peak) / peak
    max_drawdown = float(drawdown.min())

    # Trade stats
    trades = portfolio.trades
    winning = [t for t in trades if t["pnl"] > 0]
    losing = [t for t in trades if t["pnl"] <= 0]
    win_rate = len(winning) / len(trades) if trades else 0

    gross_profit = sum(t["pnl"] for t in winning) if winning else 0
    gross_loss = abs(sum(t["pnl"] for t in losing)) if losing else 1
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    elapsed = time.time() - start_time

    results = {
        "timestamp": datetime.now().isoformat(),
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
        "summary": f"Sharpe={sharpe:.3f} | Return={total_return*100:.1f}% | MaxDD={max_drawdown*100:.1f}% | Trades={len(trades)} | WinRate={win_rate*100:.0f}%",
    }

    # Print results
    print("\n" + "=" * 60)
    print("BACKTEST RESULTS")
    print("=" * 60)
    for k, v in results["metrics"].items():
        print(f"  {k:>20s}: {v}")
    print(f"\n  {results['summary']}")
    print(f"  Elapsed: {elapsed:.1f}s")
    print("=" * 60)

    # Save results
    with open(RESULTS_FILE, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to {RESULTS_FILE}")

    # Save trade log
    if trades:
        trades_df = pd.DataFrame(trades)
        trades_df.to_csv("trades.csv", index=False)
        print(f"Trade log saved to trades.csv ({len(trades)} trades)")

    # Return the primary metric for the autonomous loop
    return sharpe


if __name__ == "__main__":
    try:
        sharpe = run_backtest()
        print(f"\n>>> PRIMARY METRIC (sharpe_ratio): {sharpe:.4f}")
    except Exception as e:
        print(f"\nBACKTEST FAILED: {e}")
        traceback.print_exc()
        # Write failure result so the agent knows
        with open(RESULTS_FILE, "w") as f:
            json.dump({
                "timestamp": datetime.now().isoformat(),
                "error": str(e),
                "metrics": {"sharpe_ratio": -999.0},
            }, f, indent=2)
        sys.exit(1)
