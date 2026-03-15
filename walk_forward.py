#!/usr/bin/env python3
"""
walk_forward.py — Walk-forward validation engine.

Tests strategy.py across multiple rolling time windows to detect overfitting.
Instead of one fixed train/val split, we slide a window forward through time.

Each fold:
  - Train period: 12 months (strategy could use this for indicator warmup)
  - Test period: 3 months (out-of-sample evaluation)
  - Step: 3 months forward

This gives ~12-14 non-overlapping test folds across 5 years of data.
"""

import json
import os
import sys
import numpy as np
import pandas as pd
from datetime import datetime

from strategy import (
    compute_signals,
    get_position_size,
    get_max_positions,
    get_stop_loss,
    get_take_profit,
)

try:
    from strategy import uses_adr_stops, uses_trailing_stop, get_dynamic_stops
    HAS_ADR = True
except ImportError:
    HAS_ADR = False

# ─── Constants ───────────────────────────────────────────────────────────────

DATA_DIR = "data"
INITIAL_CAPITAL = 100_000.0
COMMISSION = 0.001
WARMUP_MONTHS = 12    # months of data before test window (indicator warmup)
TEST_MONTHS = 3       # out-of-sample test window
STEP_MONTHS = 3       # how far to slide forward each fold
RESULTS_FILE = "walk_forward_results.json"

UNIVERSE = [
    "NVDA", "AVGO", "AAPL", "TSLA", "META", "GOOG", "MSFT",
    "PANW", "ISRG", "MNDY", "GRMN", "PTON", "DOCU", "QCOM", "BABA",
    "SPY", "QQQ",
]


# ─── Portfolio (same as backtest.py) ─────────────────────────────────────────

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
            "shares": shares, "entry_price": price, "entry_date": str(date),
            "highest_price": price,
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
            "ticker": ticker, "pnl": round(pnl, 2),
            "pnl_pct": round(pnl_pct * 100, 2), "reason": reason,
        })

    def check_stops(self, prices: dict[str, float], date):
        use_trailing = HAS_ADR and uses_trailing_stop()
        for ticker in list(self.positions.keys()):
            if ticker not in prices:
                continue
            pos = self.positions[ticker]
            price = prices[ticker]

            if price > pos.get("highest_price", 0):
                pos["highest_price"] = price

            if use_trailing and pos.get("trail_distance") and pos.get("use_adr"):
                trail_stop = pos["highest_price"] - pos["trail_distance"]
                if trail_stop > pos["stop_price"]:
                    pos["stop_price"] = trail_stop

            if price <= pos["stop_price"]:
                self.sell(ticker, price, date, reason="stop_loss")
                continue
            if price >= pos["tp_price"]:
                self.sell(ticker, price, date, reason="take_profit")

    def mark_to_market(self, prices: dict[str, float]) -> float:
        positions_value = sum(
            pos["shares"] * prices.get(ticker, pos["entry_price"])
            for ticker, pos in self.positions.items()
        )
        return self.cash + positions_value


# ─── Load full dataset ───────────────────────────────────────────────────────

def load_full_data() -> dict[str, pd.DataFrame]:
    """Load raw (unsplit) CSVs."""
    result = {}
    for ticker in UNIVERSE:
        path = os.path.join(DATA_DIR, f"{ticker}.csv")
        if os.path.exists(path):
            df = pd.read_csv(path, index_col=0, parse_dates=True)
            result[ticker] = df
    return result


# ─── Run one fold ────────────────────────────────────────────────────────────

def run_fold(universe: dict[str, pd.DataFrame],
             warmup_start: pd.Timestamp,
             test_start: pd.Timestamp,
             test_end: pd.Timestamp) -> dict:
    """Run strategy on one walk-forward fold."""

    # Slice data: warmup + test window for signal computation, but only
    # evaluate trades in the test window
    fold_data = {}
    test_data = {}
    for ticker, df in universe.items():
        fold = df[(df.index >= warmup_start) & (df.index < test_end)]
        test = df[(df.index >= test_start) & (df.index < test_end)]
        if len(fold) > 0 and len(test) > 0:
            fold_data[ticker] = fold
            test_data[ticker] = test

    if not fold_data:
        return None

    # Compute signals on full fold (warmup + test) for indicator warmup
    all_signals = {}
    for ticker, df in fold_data.items():
        try:
            signals = compute_signals(df)
            # Only keep signals in test window
            test_signals = signals[signals.index >= test_start]
            all_signals[ticker] = test_signals
        except Exception:
            all_signals[ticker] = pd.Series(0, index=test_data.get(ticker, pd.DataFrame()).index)

    # Get test dates
    test_dates = sorted(set().union(*[df.index for df in test_data.values()]))
    if not test_dates:
        return None

    # Simulate
    portfolio = Portfolio(INITIAL_CAPITAL)
    position_size = get_position_size()

    for date in test_dates:
        prices = {}
        for ticker, df in test_data.items():
            if date in df.index:
                prices[ticker] = float(df.loc[date, "Close"])

        portfolio.check_stops(prices, date)

        use_adr = HAS_ADR and uses_adr_stops()
        for ticker in test_data:
            if ticker not in all_signals or date not in all_signals[ticker].index:
                continue
            signal = all_signals[ticker].loc[date]
            if ticker not in prices:
                continue
            if signal == 1:
                stop_info = None
                if use_adr:
                    stop_info = get_dynamic_stops(fold_data[ticker], date, prices[ticker])
                portfolio.buy(ticker, prices[ticker], date, position_size, stop_info)
            elif signal == -1:
                portfolio.sell(ticker, prices[ticker], date, reason="signal")

        portfolio.equity_curve.append(portfolio.mark_to_market(prices))

    # Close remaining
    last_prices = {}
    for ticker, df in test_data.items():
        if not df.empty:
            last_prices[ticker] = float(df.iloc[-1]["Close"])
    for ticker in list(portfolio.positions.keys()):
        if ticker in last_prices:
            portfolio.sell(ticker, last_prices[ticker], test_dates[-1], "end_of_fold")

    # Metrics
    equity = np.array(portfolio.equity_curve)
    if len(equity) < 2:
        return None

    total_return = (equity[-1] / INITIAL_CAPITAL) - 1
    daily_returns = np.diff(equity) / equity[:-1]

    if daily_returns.std() > 0:
        sharpe = (daily_returns.mean() / daily_returns.std()) * np.sqrt(252)
    else:
        sharpe = 0.0

    peak = np.maximum.accumulate(equity)
    drawdown = (equity - peak) / peak
    max_drawdown = float(drawdown.min())

    trades = portfolio.trades
    winning = [t for t in trades if t["pnl"] > 0]
    losing = [t for t in trades if t["pnl"] <= 0]
    win_rate = len(winning) / len(trades) if trades else 0

    return {
        "test_start": str(test_start.date()),
        "test_end": str(test_end.date()),
        "trading_days": len(test_dates),
        "sharpe_ratio": round(sharpe, 4),
        "total_return_pct": round(total_return * 100, 2),
        "max_drawdown_pct": round(max_drawdown * 100, 2),
        "win_rate_pct": round(win_rate * 100, 1),
        "total_trades": len(trades),
        "final_equity": round(equity[-1], 2),
    }


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    print("=" * 70)
    print("WALK-FORWARD VALIDATION")
    print("=" * 70)
    print(f"Warmup: {WARMUP_MONTHS}mo | Test: {TEST_MONTHS}mo | Step: {STEP_MONTHS}mo")
    print()

    universe = load_full_data()
    if not universe:
        print("ERROR: No data. Run prepare.py first.")
        sys.exit(1)

    # Find date range
    all_dates = sorted(set().union(*[df.index for df in universe.values()]))
    data_start = all_dates[0]
    data_end = all_dates[-1]
    print(f"Data range: {data_start.date()} → {data_end.date()}")

    # Generate folds
    folds = []
    warmup_start = data_start
    while True:
        test_start = warmup_start + pd.DateOffset(months=WARMUP_MONTHS)
        test_end = test_start + pd.DateOffset(months=TEST_MONTHS)
        if test_end > data_end + pd.DateOffset(days=1):
            break
        folds.append((warmup_start, test_start, test_end))
        warmup_start += pd.DateOffset(months=STEP_MONTHS)

    print(f"Generated {len(folds)} folds\n")

    # Run each fold
    results = []
    for i, (ws, ts, te) in enumerate(folds):
        print(f"Fold {i+1}/{len(folds)}: test {ts.date()} → {te.date()}", end=" ... ")
        fold_result = run_fold(universe, ws, ts, te)
        if fold_result:
            results.append(fold_result)
            print(f"Sharpe={fold_result['sharpe_ratio']:+.3f}  Return={fold_result['total_return_pct']:+.1f}%  Trades={fold_result['total_trades']}")
        else:
            print("SKIPPED (insufficient data)")

    if not results:
        print("\nERROR: No valid folds")
        sys.exit(1)

    # ─── Aggregate stats ─────────────────────────────────────────────────

    sharpes = [r["sharpe_ratio"] for r in results]
    returns = [r["total_return_pct"] for r in results]
    drawdowns = [r["max_drawdown_pct"] for r in results]
    trades = [r["total_trades"] for r in results]

    positive_sharpe = sum(1 for s in sharpes if s > 0)
    profitable_folds = sum(1 for r in returns if r > 0)

    summary = {
        "folds": len(results),
        "sharpe": {
            "mean": round(np.mean(sharpes), 4),
            "median": round(np.median(sharpes), 4),
            "std": round(np.std(sharpes), 4),
            "min": round(min(sharpes), 4),
            "max": round(max(sharpes), 4),
            "positive_folds": positive_sharpe,
            "positive_pct": round(positive_sharpe / len(results) * 100, 1),
        },
        "returns": {
            "mean_pct": round(np.mean(returns), 2),
            "median_pct": round(np.median(returns), 2),
            "std_pct": round(np.std(returns), 2),
            "min_pct": round(min(returns), 2),
            "max_pct": round(max(returns), 2),
            "profitable_folds": profitable_folds,
            "profitable_pct": round(profitable_folds / len(results) * 100, 1),
        },
        "drawdown": {
            "mean_pct": round(np.mean(drawdowns), 2),
            "worst_pct": round(min(drawdowns), 2),
        },
        "trades_per_fold": {
            "mean": round(np.mean(trades), 1),
            "total": sum(trades),
        },
    }

    # Compounded return across all folds
    compounded = 1.0
    for r in returns:
        compounded *= (1 + r / 100)
    summary["compounded_return_pct"] = round((compounded - 1) * 100, 2)

    print("\n" + "=" * 70)
    print("WALK-FORWARD SUMMARY")
    print("=" * 70)
    print(f"  Folds tested:          {summary['folds']}")
    print(f"  Sharpe (mean±std):     {summary['sharpe']['mean']:.3f} ± {summary['sharpe']['std']:.3f}")
    print(f"  Sharpe (median):       {summary['sharpe']['median']:.3f}")
    print(f"  Sharpe range:          [{summary['sharpe']['min']:.3f}, {summary['sharpe']['max']:.3f}]")
    print(f"  Positive Sharpe folds: {summary['sharpe']['positive_folds']}/{summary['folds']} ({summary['sharpe']['positive_pct']}%)")
    print(f"  ---")
    print(f"  Return/fold (mean):    {summary['returns']['mean_pct']:+.2f}%")
    print(f"  Return/fold (median):  {summary['returns']['median_pct']:+.2f}%")
    print(f"  Return range:          [{summary['returns']['min_pct']:+.1f}%, {summary['returns']['max_pct']:+.1f}%]")
    print(f"  Profitable folds:      {summary['returns']['profitable_folds']}/{summary['folds']} ({summary['returns']['profitable_pct']}%)")
    print(f"  Compounded return:     {summary['compounded_return_pct']:+.2f}%")
    print(f"  ---")
    print(f"  Avg max drawdown:      {summary['drawdown']['mean_pct']:.2f}%")
    print(f"  Worst drawdown:        {summary['drawdown']['worst_pct']:.2f}%")
    print(f"  ---")
    print(f"  Avg trades/fold:       {summary['trades_per_fold']['mean']:.0f}")
    print(f"  Total trades:          {summary['trades_per_fold']['total']}")
    print("=" * 70)

    # Robustness assessment
    print("\n📊 ROBUSTNESS ASSESSMENT:")
    mean_sharpe = summary["sharpe"]["mean"]
    pos_pct = summary["sharpe"]["positive_pct"]
    if mean_sharpe > 1.0 and pos_pct >= 70:
        print("  ✅ ROBUST — Strategy holds up across time periods")
    elif mean_sharpe > 0.5 and pos_pct >= 50:
        print("  ⚠️  MODERATE — Strategy works but inconsistently")
    elif mean_sharpe > 0 and pos_pct >= 40:
        print("  ⚠️  WEAK — Strategy has some edge but unreliable")
    else:
        print("  ❌ OVERFIT — Strategy likely overfit to validation period")

    # Save
    output = {
        "timestamp": datetime.now().isoformat(),
        "config": {
            "warmup_months": WARMUP_MONTHS,
            "test_months": TEST_MONTHS,
            "step_months": STEP_MONTHS,
        },
        "folds": results,
        "summary": summary,
    }

    with open(RESULTS_FILE, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nFull results saved to {RESULTS_FILE}")


if __name__ == "__main__":
    main()
