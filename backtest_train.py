#!/usr/bin/env python3
"""
backtest_train.py — Runs backtest on TRAIN split only.
Wrapper around backtest.py's run_backtest with split="train".
"""

from backtest import run_backtest

if __name__ == "__main__":
    import json, sys, traceback
    from datetime import datetime
    try:
        sharpe = run_backtest(split="train", results_file="results_train.json")
        print(f"\n>>> PRIMARY METRIC (sharpe_ratio): {sharpe:.4f}")
    except Exception as e:
        print(f"\nBACKTEST FAILED: {e}")
        traceback.print_exc()
        with open("results_train.json", "w") as f:
            json.dump({"timestamp": datetime.now().isoformat(), "error": str(e),
                        "metrics": {"sharpe_ratio": -999.0}}, f, indent=2)
        sys.exit(1)
