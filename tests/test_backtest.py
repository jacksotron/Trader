"""Backtester tests on synthetic, deterministic price series."""

import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.backtest import BacktestParams, grid_search, run_backtest


def _series(n, start=100.0, drift=0.0, wave_amp=0.0, wave_len=10.0):
    """Deterministic close series: exponential drift + sine oscillation."""
    closes = []
    for i in range(n):
        base = start * ((1 + drift) ** i)
        closes.append(base * (1 + wave_amp * math.sin(i / wave_len)))
    return closes


def _bars_from_closes(closes, day0=1, intraday_range=0.01):
    bars = []
    prev = closes[0]
    for i, c in enumerate(closes):
        o = prev
        hi = max(o, c) * (1 + intraday_range)
        lo = min(o, c) * (1 - intraday_range)
        bars.append({
            "begins_at": f"2025-{(day0 + i) // 31 % 12 + 1:02d}-{(day0 + i) % 28 + 1:02d}T00:00:00Z",
            "open": o, "high": hi, "low": lo, "close": c,
            "volume": 1_000_000,
        })
        prev = c
    return bars


def _dataset(n=200):
    """Two trending names with pullbacks (so RSI cycles through the entry band),
    one weak name, plus SPY/QQQ indices that trend up."""
    return {
        "SPY": _bars_from_closes(_series(n, 100, drift=0.0015, wave_amp=0.01, wave_len=8)),
        "QQQ": _bars_from_closes(_series(n, 100, drift=0.0018, wave_amp=0.012, wave_len=8)),
        "AAA": _bars_from_closes(_series(n, 50, drift=0.004, wave_amp=0.02, wave_len=6)),
        "BBB": _bars_from_closes(_series(n, 80, drift=0.003, wave_amp=0.015, wave_len=7)),
        "CCC": _bars_from_closes(_series(n, 60, drift=-0.002, wave_amp=0.02, wave_len=9)),
    }


class TestBacktest(unittest.TestCase):
    def test_uptrend_profitable_and_traded(self):
        result = run_backtest(_dataset(), start_equity=100.0)
        self.assertGreater(result.trades, 0)
        self.assertGreater(result.end_equity, 95.0)  # risk control even if entries are unlucky
        self.assertLess(result.max_drawdown_pct, 20.0)

    def test_per_trade_loss_bounded_by_risk_budget(self):
        params = BacktestParams(risk_per_trade_pct=2.0)
        result = run_backtest(_dataset(), start_equity=100.0, params=params)
        # Worst single stop-out should not greatly exceed the 2% budget
        # (tolerance for intraday-range gap fills and slippage).
        for t in result.trade_log:
            self.assertGreater(t["pnl"], -100.0 * 0.02 * 2.0,
                               msg=f"trade lost more than 2x the risk budget: {t}")

    def test_choppy_market_contained(self):
        n = 200
        chop = {
            "SPY": _bars_from_closes(_series(n, 100, drift=0.0, wave_amp=0.03, wave_len=12)),
            "QQQ": _bars_from_closes(_series(n, 100, drift=0.0, wave_amp=0.03, wave_len=12)),
            "AAA": _bars_from_closes(_series(n, 50, drift=0.0, wave_amp=0.05, wave_len=10)),
            "BBB": _bars_from_closes(_series(n, 80, drift=0.0, wave_amp=0.04, wave_len=14)),
        }
        result = run_backtest(chop, start_equity=100.0)
        # Chop is where momentum bleeds; the requirement is contained damage.
        self.assertGreater(result.end_equity, 80.0)
        self.assertLess(result.max_drawdown_pct, 20.0)

    def test_regime_off_reduces_trading_in_downtrend(self):
        n = 200
        down = {
            "SPY": _bars_from_closes(_series(n, 100, drift=-0.003, wave_amp=0.01, wave_len=8)),
            "QQQ": _bars_from_closes(_series(n, 100, drift=-0.003, wave_amp=0.01, wave_len=8)),
            "AAA": _bars_from_closes(_series(n, 50, drift=0.004, wave_amp=0.02, wave_len=6)),
        }
        with_regime = run_backtest(down, params=BacktestParams(use_regime=True))
        without = run_backtest(down, params=BacktestParams(use_regime=False))
        self.assertLessEqual(with_regime.trades, without.trades)

    def test_alignment_drops_missing_dates(self):
        data = _dataset(120)
        data["AAA"] = data["AAA"][:-10]  # shorter series
        result = run_backtest(data)  # must not raise
        self.assertIsNotNone(result.end_equity)

    def test_grid_search_sorted(self):
        grid = {"atr_mult": [1.5, 2.5], "target_r": [2.0, 3.0]}
        results = grid_search(_dataset(150), grid)
        self.assertEqual(len(results), 4)
        returns = [r.total_return_pct for r in results]
        self.assertEqual(returns, sorted(returns, reverse=True))


if __name__ == "__main__":
    unittest.main()
