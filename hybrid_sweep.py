#!/usr/bin/env python3
"""Sweep stop-loss / take-profit combinations for hybrid strategy."""

import json, re, subprocess

STOPS = [0.02, 0.03, 0.04, 0.05, 0.07]
TPS = [0.08, 0.10, 0.12, 0.15, 0.20]

def read_strategy():
    with open("strategy.py") as f:
        return f.read()

def write_strategy(content):
    with open("strategy.py", "w") as f:
        f.write(content)

def set_params(original, sl, tp):
    s = re.sub(r'STOP_LOSS\s*=\s*-?[\d.]+', f'STOP_LOSS = -{sl}', original)
    s = re.sub(r'TAKE_PROFIT\s*=\s*[\d.]+', f'TAKE_PROFIT = {tp}', s)
    return s

def run_walk_forward():
    result = subprocess.run(["python3", "walk_forward.py"], capture_output=True, text=True, timeout=300)
    metrics = {}
    for line in result.stdout.split("\n"):
        if "Sharpe (mean±std):" in line:
            parts = line.split(":")[-1].strip().split("±")
            metrics["mean_sharpe"] = float(parts[0].strip())
            metrics["std_sharpe"] = float(parts[1].strip())
        elif "Sharpe (median):" in line:
            metrics["median_sharpe"] = float(line.split(":")[-1].strip())
        elif "Compounded return:" in line:
            metrics["compounded"] = float(line.split(":")[-1].strip().replace("%","").replace("+",""))
        elif "Worst drawdown:" in line:
            metrics["worst_dd"] = float(line.split(":")[-1].strip().replace("%",""))
        elif "Profitable folds:" in line:
            m = re.search(r'(\d+)/(\d+)', line)
            if m: metrics["prof_folds"] = f"{m.group(1)}/{m.group(2)}"
        elif "Avg max drawdown:" in line:
            metrics["avg_dd"] = float(line.split(":")[-1].strip().replace("%",""))
    return metrics

original = read_strategy()

print("=" * 95)
print("HYBRID STOP/TP SWEEP — Walk-Forward Validation")
print("=" * 95)
print(f"{'SL':>5s} {'TP':>5s} | {'Ratio':>5s} | {'MeanSh':>8s} {'MedSh':>8s} | {'Compound':>10s} | {'WorstDD':>8s} {'AvgDD':>7s} | {'Folds':>7s}")
print("-" * 95)

results = []
for sl in STOPS:
    for tp in TPS:
        ratio = tp / sl
        modified = set_params(original, sl, tp)
        write_strategy(modified)
        try:
            m = run_walk_forward()
            ms = m.get("mean_sharpe", 0)
            md = m.get("median_sharpe", 0)
            cr = m.get("compounded", 0)
            wd = m.get("worst_dd", 0)
            ad = m.get("avg_dd", 0)
            pf = m.get("prof_folds", "?")
            print(f"{sl*100:4.0f}% {tp*100:4.0f}% | {ratio:5.1f} | {ms:+8.3f} {md:+8.3f} | {cr:+9.1f}% | {wd:7.1f}% {ad:6.1f}% | {pf:>7s}")
            results.append({"sl": sl, "tp": tp, "ratio": round(ratio,1), **m})
        except Exception as e:
            print(f"{sl*100:4.0f}% {tp*100:4.0f}% | ERROR: {e}")

best = max(results, key=lambda r: r.get("mean_sharpe", -999))
print("=" * 95)
print(f"BEST: SL=-{best['sl']*100:.0f}% TP=+{best['tp']*100:.0f}% (ratio {best['ratio']}) → Mean Sharpe {best['mean_sharpe']:.3f}, Compounded {best.get('compounded',0):.1f}%")
print("=" * 95)

# Set best
modified = set_params(original, best["sl"], best["tp"])
write_strategy(modified)

with open("hybrid_sweep_results.json", "w") as f:
    json.dump(results, f, indent=2)
