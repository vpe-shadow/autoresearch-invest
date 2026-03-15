#!/usr/bin/env python3
"""
One-time data preparation: download historical price data and split into
train/validation sets. Do NOT modify this file.
"""

import os
import json
import yfinance as yf
import pandas as pd
from datetime import datetime

# ─── Constants ───────────────────────────────────────────────────────────────

DATA_DIR = "data"
UNIVERSE = [
    "NVDA", "AVGO", "AAPL", "TSLA", "META", "GOOG", "MSFT",
    "PANW", "ISRG", "MNDY", "GRMN", "PTON", "DOCU", "QCOM", "BABA",
    # ETFs for sector context
    "SPY", "QQQ",
]

# 5 years of daily data
HISTORY_PERIOD = "5y"

# Train/val split: last 6 months = validation
VAL_MONTHS = 6

# ─── Download ────────────────────────────────────────────────────────────────

def download_data():
    os.makedirs(DATA_DIR, exist_ok=True)

    print(f"Downloading {len(UNIVERSE)} tickers ({HISTORY_PERIOD} history)...")
    for ticker in UNIVERSE:
        path = os.path.join(DATA_DIR, f"{ticker}.csv")
        if os.path.exists(path):
            print(f"  {ticker}: cached")
            continue

        print(f"  {ticker}: downloading...", end=" ")
        try:
            df = yf.download(ticker, period=HISTORY_PERIOD, interval="1d",
                             auto_adjust=True, progress=False)
            if df.empty:
                print("EMPTY — skipped")
                continue
            # Flatten multi-level columns if present
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            df.to_csv(path)
            print(f"OK ({len(df)} rows)")
        except Exception as e:
            print(f"ERROR: {e}")

def split_data():
    """Split each ticker CSV into train and val sets."""
    train_dir = os.path.join(DATA_DIR, "train")
    val_dir = os.path.join(DATA_DIR, "val")
    os.makedirs(train_dir, exist_ok=True)
    os.makedirs(val_dir, exist_ok=True)

    cutoff = pd.Timestamp.now() - pd.DateOffset(months=VAL_MONTHS)

    meta = {}
    for fname in sorted(os.listdir(DATA_DIR)):
        if not fname.endswith(".csv"):
            continue
        ticker = fname.replace(".csv", "")
        df = pd.read_csv(os.path.join(DATA_DIR, fname), index_col=0, parse_dates=True)

        train = df[df.index < cutoff]
        val = df[df.index >= cutoff]

        train.to_csv(os.path.join(train_dir, fname))
        val.to_csv(os.path.join(val_dir, fname))

        meta[ticker] = {
            "total_rows": len(df),
            "train_rows": len(train),
            "val_rows": len(val),
            "start": str(df.index.min().date()),
            "end": str(df.index.max().date()),
            "cutoff": str(cutoff.date()),
        }
        print(f"  {ticker}: {len(train)} train / {len(val)} val")

    with open(os.path.join(DATA_DIR, "meta.json"), "w") as f:
        json.dump(meta, f, indent=2)

    print(f"\nData ready in {DATA_DIR}/")


# ─── Runtime utilities (used by backtest.py) ─────────────────────────────────

def load_ticker(ticker: str, split: str = "val") -> pd.DataFrame:
    """Load a ticker's data for the given split."""
    path = os.path.join(DATA_DIR, split, f"{ticker}.csv")
    if not os.path.exists(path):
        raise FileNotFoundError(f"No data for {ticker} in {split} split. Run prepare.py first.")
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    return df


def load_universe(split: str = "val") -> dict[str, pd.DataFrame]:
    """Load all tickers for a split as {ticker: DataFrame}."""
    split_dir = os.path.join(DATA_DIR, split)
    result = {}
    for fname in sorted(os.listdir(split_dir)):
        if fname.endswith(".csv"):
            ticker = fname.replace(".csv", "")
            result[ticker] = pd.read_csv(
                os.path.join(split_dir, fname), index_col=0, parse_dates=True
            )
    return result


if __name__ == "__main__":
    download_data()
    split_data()
