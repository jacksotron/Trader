"""Convert Yahoo chart JSON -> bars format, run baseline + parameter grid."""
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.backtest import BacktestParams, grid_search, run_backtest

SYMS = ["SPY", "QQQ", "NVDA", "TSLA", "META", "GOOGL", "AAPL", "MSFT", "AMZN"]

def load(sym):
    with open(f"data/yf_{sym}.json") as f:
        j = json.load(f)
    r = j["chart"]["result"][0]
    ts = r["timestamp"]
    q = r["indicators"]["quote"][0]
    bars = []
    for i, t in enumerate(ts):
        o, h, l, c, v = (q["open"][i], q["high"][i], q["low"][i], q["close"][i], q["volume"][i])
        if None in (o, h, l, c) or not v:
            continue
        d = datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%dT00:00:00Z")
        bars.append({"begins_at": d, "open": o, "high": h, "low": l, "close": c, "volume": v})
    return bars

data = {s: load(s) for s in SYMS}
print("bars per symbol:", {s: len(b) for s, b in data.items()})
print("date range:", data["SPY"][0]["begins_at"][:10], "->", data["SPY"][-1]["begins_at"][:10])

print("\n=== BASELINE (live config: atr_mult=2.0, target_r=3.0, regime on, 2% risk) ===")
base = run_backtest(data, start_equity=100.0)
print(json.dumps(base.summary(), indent=2))

print("\n=== GRID (12 cells) sorted by return ===")
grid = {"atr_mult": [1.5, 2.0, 2.5], "target_r": [2.0, 3.0], "use_regime": [True, False]}
results = grid_search(data, grid, start_equity=100.0)
hdr = f"{'atr':>4} {'tgtR':>4} {'regime':>6} | {'ret%':>7} {'bench%':>7} {'maxDD%':>6} {'shrp':>5} {'trds':>4} {'win%':>5} {'expct':>7} {'expo%':>5}"
print(hdr); print("-" * len(hdr))
for r in results:
    s = r.summary(); p = s["params"]
    print(f"{p['atr_mult']:>4} {p['target_r']:>4} {str(p['use_regime']):>6} | "
          f"{s['total_return_pct']:>7.2f} {s['benchmark_return_pct']:>7.2f} {s['max_drawdown_pct']:>6.2f} "
          f"{(s['sharpe'] if s['sharpe'] is not None else float('nan')):>5.2f} {s['trades']:>4} "
          f"{(s['win_rate_pct'] if s['win_rate_pct'] is not None else float('nan')):>5.1f} "
          f"{(s['expectancy'] if s['expectancy'] is not None else float('nan')):>7.4f} {s['avg_exposure_pct']:>5.1f}")

# Walk-forward sanity: split the year in half, check the grid winner holds up out-of-sample
print("\n=== WALK-FORWARD: best in-sample params from H1, tested on H2 ===")
half = len(data["SPY"]) // 2
h1 = {s: b[:half] for s, b in data.items()}
h2 = {s: b[half - 60:] for s, b in data.items()}  # keep warmup history
res_h1 = grid_search(h1, grid, start_equity=100.0)
best = res_h1[0].params
print("best H1 params:", best)
params_obj = BacktestParams(**{k: v for k, v in best.items()
                               if k in ("atr_mult", "target_r", "use_regime")})
oos = run_backtest(h2, start_equity=100.0, params=params_obj)
base_h2 = run_backtest(h2, start_equity=100.0)
print("H2 out-of-sample with H1-best params:", json.dumps(oos.summary()))
print("H2 with default params:             ", json.dumps(base_h2.summary()))
