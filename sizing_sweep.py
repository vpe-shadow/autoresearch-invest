#!/usr/bin/env python3
"""
Quick sweep of position sizing to find walk-forward optimal.
Temporarily patches strategy params and runs walk-forward for each.
"""

import json
import subprocess
import re

SIZES_TO_TEST = [0.05, 0.08, 0.10, 0.12, 0.15, 0.18, 0.20, 0.25]

def read_strategy():
    with open("strategy.py") as f:
        return f.read()

def write_strategy(content):
    with open("strategy.py", "w") as f:
        f.write(content)

def set_position_size(original: str, size: float) -> str:
    return re.sub(r'POSITION_SIZE\s*=\s*[\d.]+', f'POSITION_SIZE = {size}', original)

def run_walk_forward():
    result = subprocess.run(["python3", "walk_forward.py"], capture_output=True, text=True, timeout=300)
    output = result.stdout
    # Parse key metrics from output
    metrics = {}
    for line in output.split("\n"):
        if "Sharpe (mean±std):" in line:
            parts = line.split(":")[-1].strip().split("±")
            metrics["mean_sharpe"] = float(parts[0].strip())
            metrics["std_sharpe"] = float(parts[1].strip())
        elif "Sharpe (median):" in line:
            metrics["median_sharpe"] = float(line.split(":")[-1].strip())
        elif "Compounded return:" in line:
            metrics["compounded_return"] = float(line.split(":")[-1].strip().replace("%", "").replace("+", ""))
        elif "Worst drawdown:" in line:
            metrics["worst_dd"] = float(line.split(":")[-1].strip().replace("%", ""))
        elif "Profitable folds:" in line:
            m = re.search(r'(\d+)/(\d+)', line)
            if m:
                metrics["profitable_folds"] = f"{m.group(1)}/{m.group(2)}"
        elif "Positive Sharpe folds:" in line:
            m = re.search(r'(\d+)/(\d+)', line)
            if m:
                metrics["positive_sharpe_folds"] = f"{m.group(1)}/{m.group(2)}"
        elif "Avg max drawdown:" in line:
            metrics["avg_dd"] = float(line.split(":")[-1].strip().replace("%", ""))
    return metrics

original = read_strategy()

print("=" * 80)
print("POSITION SIZING SWEEP — Walk-Forward Validation")
print("=" * 80)
print(f"{'Size':>6s} | {'Mean Sharpe':>12s} | {'Median':>8s} | {'Compounded':>12s} | {'Worst DD':>10s} | {'Avg DD':>8s} | {'Prof Folds':>11s}")
print("-" * 80)

results = []
for size in SIZES_TO_TEST:
    modified = set_position_size(original, size)
    write_strategy(modified)
    
    try:
        metrics = run_walk_forward()
        ms = metrics.get("mean_sharpe", 0)
        md = metrics.get("median_sharpe", 0)
        cr = metrics.get("compounded_return", 0)
        wd = metrics.get("worst_dd", 0)
        ad = metrics.get("avg_dd", 0)
        pf = metrics.get("profitable_folds", "?/?")
        
        print(f"{size*100:5.0f}% | {ms:+12.3f} | {md:+8.3f} | {cr:+11.1f}% | {wd:9.1f}% | {ad:7.1f}% | {pf:>11s}")
        results.append({"size": size, **metrics})
    except Exception as e:
        print(f"{size*100:5.0f}% | ERROR: {e}")

# Find best by mean Sharpe
best = max(results, key=lambda r: r.get("mean_sharpe", -999))
print("=" * 80)
print(f"BEST: {best['size']*100:.0f}% → Mean Sharpe {best['mean_sharpe']:.3f}, Compounded {best.get('compounded_return', 0):.1f}%")
print("=" * 80)

# Restore best
modified = set_position_size(original, best["size"])
write_strategy(modified)
print(f"\nstrategy.py updated to {best['size']*100:.0f}% position size")

# Save results
with open("sizing_sweep_results.json", "w") as f:
    json.dump(results, f, indent=2)
