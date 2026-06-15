"""Core-policy backtest: how should the leveraged index core be managed?

Tests, on real TQQQ/UPRO daily bars with the regime gate computed from SPY+QQQ
history (no lookahead):

  P0  buy-hold 50/50 (no gate, no stops) — the benchmark to beat
  P1  regime-gated hold (cash when risk_off), no stops
  P2  P1 + 5% stop, full size       (current live policy)
  P3  P1 + 8% stop, 5/8 size        (same dollar risk per stop-out)
  P4  P2 + weekend flatten (sell Fri close, re-enter Mon open)
  P5  P3 + weekend flatten

Decision rule (pre-committed): adopt a change only if it improves the
return/max-drawdown trade-off over P2 on the full period AND in both halves.
Run from repo root: python3 scripts/backtest_core.py <data_dir>
"""

import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src import signals  # noqa: E402

SLIP = 0.0005  # 5 bps per side
COOLDOWN_DAYS = 1


def load(data_dir, sym):
    with open(os.path.join(data_dir, f"yf_{sym}.json")) as f:
        j = json.load(f)
    r = j["chart"]["result"][0]
    ts, q = r["timestamp"], r["indicators"]["quote"][0]
    bars = []
    for i, t in enumerate(ts):
        o, h, l, c, v = (q["open"][i], q["high"][i], q["low"][i], q["close"][i], q["volume"][i])
        if None in (o, h, l, c) or not v:
            continue
        d = datetime.fromtimestamp(t, tz=timezone.utc)
        bars.append({"date": d.strftime("%Y-%m-%d"), "weekday": d.weekday(),
                     "open": o, "high": h, "low": l, "close": c, "volume": v,
                     "begins_at": d.strftime("%Y-%m-%dT00:00:00Z")})
    return bars


def align(symdata):
    common = sorted(set.intersection(*(set(b["date"] for b in bars) for bars in symdata.values())))
    return common, {s: {b["date"]: b for b in bars} for s, bars in symdata.items()}


def regime_series(dates, by_date, warmup=60):
    """sizing multiplier per date, computed from SPY+QQQ history strictly before t."""
    out = {}
    spy_hist, qqq_hist = [], []
    for i, d in enumerate(dates):
        if i >= warmup:
            spy_ind = signals.compute_indicators(spy_hist[:])
            qqq_ind = signals.compute_indicators(qqq_hist[:])
            out[d] = signals.regime_score(spy_ind, qqq_ind)["sizing_multiplier"]
        spy_hist.append(by_date["SPY"][d])
        qqq_hist.append(by_date["QQQ"][d])
    return out


def simulate(dates, by_date, regime, legs=("TQQQ", "UPRO"), use_gate=True,
             stop_pct=None, size_frac=1.0, weekend_flatten=False, start=100.0):
    cash = start
    pos = {}      # sym -> {qty, entry, stop}
    cooldown = {}  # sym -> days remaining
    curve = []
    trades = 0

    for i, d in enumerate(dates):
        if d not in regime:
            continue
        gate_ok = (regime[d] > 0) if use_gate else True

        for sym in legs:
            bar = by_date[sym][d]
            p = pos.get(sym)
            # exits
            if p:
                stop_hit = stop_pct is not None and bar["low"] <= p["stop"]
                gate_exit = use_gate and not gate_ok
                friday_exit = weekend_flatten and bar["weekday"] == 4
                if stop_hit:
                    fill = min(bar["open"], p["stop"]) * (1 - SLIP)
                    cash += p["qty"] * fill
                    del pos[sym]
                    cooldown[sym] = COOLDOWN_DAYS
                    trades += 1
                elif gate_exit or friday_exit:
                    fill = bar["close"] * (1 - SLIP)
                    cash += p["qty"] * fill
                    del pos[sym]
                    trades += 1
            # entries (at open; weekend_flatten re-enters Monday open)
            p = pos.get(sym)
            if not p and gate_ok and cooldown.get(sym, 0) == 0:
                if weekend_flatten and bar["weekday"] == 4:
                    pass  # don't enter on a Friday just to flatten at the close
                else:
                    eq = cash + sum(pp["qty"] * by_date[s2][d]["open"] for s2, pp in pos.items())
                    alloc = eq / len(legs) * size_frac
                    if alloc > 1 and cash >= alloc:
                        entry = bar["open"] * (1 + SLIP)
                        qty = alloc / entry
                        cash -= qty * entry
                        pos[sym] = {"qty": qty, "entry": entry,
                                    "stop": entry * (1 - (stop_pct or 0) / 100)}
                        trades += 1
            if cooldown.get(sym, 0) > 0:
                cooldown[sym] -= 1

        eq = cash + sum(p["qty"] * by_date[s]["" + d]["close"] for s, p in pos.items())
        curve.append(eq)

    peak, max_dd = -1e9, 0.0
    for e in curve:
        peak = max(peak, e)
        max_dd = max(max_dd, (peak - e) / peak * 100 if peak > 0 else 0)
    ret = (curve[-1] / start - 1) * 100 if curve else 0.0
    return {"return_pct": round(ret, 2), "max_dd_pct": round(max_dd, 2),
            "mar": round(ret / max_dd, 2) if max_dd > 0 else None, "trades": trades}


def run(data_dir):
    data = {s: load(data_dir, s) for s in ("TQQQ", "UPRO", "SPY", "QQQ")}
    dates, by_date = align(data)
    regime = regime_series(dates, by_date)

    policies = {
        "P0 buy-hold 50/50":           dict(use_gate=False),
        "P1 regime-gated hold":        dict(),
        "P2 gate + 5% stop (LIVE)":    dict(stop_pct=5.0),
        "P3 gate + 8% stop, 5/8 size": dict(stop_pct=8.0, size_frac=0.625),
        "P4 = P2 + weekend flatten":   dict(stop_pct=5.0, weekend_flatten=True),
        "P5 = P3 + weekend flatten":   dict(stop_pct=8.0, size_frac=0.625, weekend_flatten=True),
    }

    half = len(dates) // 2
    splits = {"FULL": dates, "H1": dates[:half], "H2": dates[half:]}
    print(f"{'policy':<28} | " + " | ".join(f"{k}: ret%/DD%/MAR/trd" for k in splits))
    print("-" * 110)
    for name, kw in policies.items():
        cells = []
        for split_dates in splits.values():
            # regime needs warmup history: recompute per split window
            reg = regime_series(split_dates, by_date)
            r = simulate(split_dates, by_date, reg, **kw)
            cells.append(f"{r['return_pct']:>6.2f}/{r['max_dd_pct']:>5.2f}/"
                         f"{(r['mar'] if r['mar'] is not None else float('nan')):>5.2f}/{r['trades']:>3}")
        print(f"{name:<28} | " + " | ".join(cells))


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "data")
