# autoresearch-invest 📈

Autonomous investment strategy optimizer — inspired by [karpathy/autoresearch](https://github.com/karpathy/autoresearch).

## Concept

Same loop as autoresearch but for trading strategies:

1. Agent modifies `strategy.py` (entry/exit rules, indicators, params)
2. Backtests on historical data (~5 min budget)
3. Measures Sharpe ratio, max drawdown, total return
4. Keeps improvement or discards
5. Repeats

Wake up to an optimized strategy.

## Files

| File | Purpose | Who edits |
|------|---------|-----------|
| `prepare.py` | Downloads historical data, prepares splits | Fixed |
| `strategy.py` | Trading strategy — the agent's playground | Agent |
| `backtest.py` | Backtesting engine + metrics | Fixed |
| `program.md` | Agent instructions | Human |

## Quick Start

```bash
# Install deps
uv sync

# Download historical data (one-time)
uv run prepare.py

# Run a single backtest
uv run backtest.py

# Launch autonomous mode — point your coding agent at program.md
```

## Metrics

- **Sharpe Ratio** (primary) — risk-adjusted return, higher is better
- **Max Drawdown** — worst peak-to-trough, lower is better
- **Total Return %** — absolute performance
- **Win Rate** — % of profitable trades
- **Profit Factor** — gross profit / gross loss

## Default Universe

Configured for Michal's watchlist: NVDA, AVGO, AAPL, TSLA, META, GOOG, MSFT, PANW, ISRG, MNDY, GRMN, PTON, DOCU, QCOM, BABA

## License

MIT
