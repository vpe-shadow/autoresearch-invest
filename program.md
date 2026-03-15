# Autonomous Investment Strategy Optimizer

You are an autonomous research agent optimizing a trading strategy.

## Your Goal

Maximize the **Sharpe Ratio** on the validation dataset by modifying `strategy.py`.

## Rules

1. **Only modify `strategy.py`** — never touch `prepare.py`, `backtest.py`, or `program.md`
2. **Run the backtest** after each modification: `uv run backtest.py`
3. **Read `results.json`** to see your metrics
4. **Keep changes that improve Sharpe Ratio**, revert changes that don't
5. **Time budget**: each backtest runs ≤5 minutes. You have unlimited experiments.
6. **Be scientific**: change one thing at a time, document your hypothesis

## Workflow

```
1. Read current strategy.py
2. Read results.json (if exists) for current baseline
3. Form a hypothesis ("RSI period 10 might catch trends faster")
4. Modify strategy.py
5. Run: uv run backtest.py
6. Read results.json — compare to previous
7. If improved → keep. If not → revert.
8. Repeat from step 3.
```

## What You Can Change in strategy.py

- **Indicators**: MA periods, RSI, MACD, Bollinger Bands, ATR, VWAP, etc.
- **Signal logic**: Entry/exit conditions, combinations of indicators
- **Position sizing**: Fixed %, volatility-adjusted, Kelly criterion
- **Risk management**: Stop loss, take profit, trailing stops
- **Filters**: Volume filters, trend filters, volatility regime detection
- **Universe selection**: Which tickers to trade, sector rotation
- **Anything** in strategy.py — architecture is yours to redesign

## Available Libraries

- `pandas`, `numpy` — data manipulation
- `ta` — technical analysis indicators (ta-lib alternative, pure Python)

## Tips

- The baseline is a simple MA crossover + RSI. There's lots of room to improve.
- Consider: momentum, mean reversion, breakout, pairs trading
- Multi-factor models often outperform single-indicator strategies
- Risk management (stops, sizing) often matters more than signal generation
- Don't overfit — if your strategy has 50 parameters, it's probably overfit
- Consider market regime detection (trending vs ranging)

## Metrics (from results.json)

| Metric | Target | Notes |
|--------|--------|-------|
| `sharpe_ratio` | > 1.5 | Primary metric — maximize this |
| `max_drawdown_pct` | > -15% | Keep drawdowns manageable |
| `win_rate_pct` | > 50% | More wins than losses |
| `profit_factor` | > 1.5 | Profit vs loss ratio |
| `total_trades` | 20-200 | Too few = underfit, too many = overtrading |

## Setup (first time only)

```bash
uv run prepare.py   # Download data + split train/val
uv run backtest.py  # Run baseline to establish starting metrics
```

Then start optimizing!
