"""Unit tests for the dependency-free core: signals, journal, risk sizing."""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import signals
from src.journal import TradeJournal
from src.risk_manager import RiskManager


def _bars(closes, spread=1.0, volume=1000):
    out = []
    for c in closes:
        out.append({"open": c, "high": c + spread / 2, "low": c - spread / 2,
                    "close": c, "volume": volume})
    return out


class TestSignals(unittest.TestCase):
    def test_sma_ema_basic(self):
        vals = [1, 2, 3, 4, 5]
        self.assertEqual(signals.sma(vals, 5), 3)
        self.assertIsNone(signals.sma(vals, 6))
        self.assertAlmostEqual(signals.ema([2] * 30, 9), 2.0)

    def test_rsi_extremes(self):
        up = list(range(1, 40))
        down = list(range(40, 1, -1))
        self.assertEqual(signals.rsi([float(x) for x in up]), 100.0)
        self.assertEqual(signals.rsi([float(x) for x in down]), 0.0)
        self.assertIsNone(signals.rsi([1.0, 2.0], 14))

    def test_atr_constant_range(self):
        bars = _bars([100.0] * 30, spread=2.0)
        self.assertAlmostEqual(signals.atr(bars, 14), 2.0)

    def test_trend_state(self):
        rising = [float(100 + i) for i in range(60)]
        falling = [float(200 - i) for i in range(60)]
        self.assertEqual(signals.trend_state(rising), "up")
        self.assertEqual(signals.trend_state(falling), "down")

    def test_vwap_and_range_pos(self):
        bars = _bars([10.0, 10.0, 10.0])
        self.assertAlmostEqual(signals.vwap(bars), 10.0)
        self.assertAlmostEqual(signals._range_position(bars), 0.5)

    def test_relative_strength(self):
        sym = [100.0, 100, 100, 100, 100, 110]   # +10% over 5
        idx = [100.0, 100, 100, 100, 100, 105]   # +5% over 5
        self.assertAlmostEqual(signals.relative_strength(sym, idx, 5), 5.0)

    def test_regime_score_directionality(self):
        strong = {"trend": "up", "rsi14": 62, "ret_5d_pct": 2.0,
                  "above_vwap": True, "realized_vol20_pct": 1.0}
        weak = {"trend": "down", "rsi14": 35, "ret_5d_pct": -3.0,
                "above_vwap": False, "realized_vol20_pct": 4.0}
        r_on = signals.regime_score(strong, dict(strong))
        r_off = signals.regime_score(weak, dict(weak))
        self.assertEqual(r_on["label"], "risk_on")
        self.assertEqual(r_on["sizing_multiplier"], 1.0)
        self.assertEqual(r_off["label"], "risk_off")
        self.assertEqual(r_off["sizing_multiplier"], 0.0)
        self.assertGreater(r_on["score"], r_off["score"])

    def test_suggest_stop_clamped(self):
        # Huge ATR clamps to max 8% below entry
        self.assertAlmostEqual(signals.suggest_stop(100.0, 50.0), 92.0)
        # Tiny ATR clamps to min 1.5% below entry
        self.assertAlmostEqual(signals.suggest_stop(100.0, 0.01), 98.5)
        # No ATR -> conservative max stop
        self.assertAlmostEqual(signals.suggest_stop(100.0, None), 92.0)

    def test_position_size_risk_budget(self):
        # $100 equity, 2% risk = $2 budget; $1 per-share risk -> 2 shares
        self.assertAlmostEqual(signals.position_size(100.0, 2.0, 10.0, 9.0), 2.0)
        self.assertEqual(signals.position_size(100.0, 2.0, 10.0, 11.0), 0.0)


class TestJournal(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "journal.json")
        self.j = TradeJournal(self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_entry_exit_roundtrip_and_stats(self):
        self.j.record_entry("NVDA", 2.0, 100.0, stop=95.0, target=120.0, thesis="test")
        self.assertIn("NVDA", self.j.get_open_plans())
        self.assertEqual(self.j.entries_today(), 1)

        trade = self.j.record_exit("NVDA", 2.0, 96.0, reason="discretionary")
        self.assertAlmostEqual(trade["pnl"], -8.0)
        self.assertNotIn("NVDA", self.j.get_open_plans())
        stats = self.j.stats()
        self.assertEqual(stats["closed_trades"], 1)
        self.assertEqual(stats["win_rate_pct"], 0.0)
        self.assertEqual(stats["consecutive_losses_today"], 1)

    def test_stop_only_moves_up(self):
        self.j.record_entry("TQQQ", 1.0, 80.0, stop=76.0, target=88.0, thesis="t")
        ok, msg = self.j.update_plan("TQQQ", stop=74.0)
        self.assertFalse(ok)
        ok, _ = self.j.update_plan("TQQQ", stop=80.0, reason="+1R breakeven")
        self.assertTrue(ok)
        self.assertTrue(self.j.get_open_plans()["TQQQ"]["breakeven_moved"])

    def test_stop_out_cooldown(self):
        self.j.record_entry("META", 1.0, 100.0, stop=95.0, target=115.0, thesis="t")
        self.j.record_exit("META", 1.0, 94.5, reason="stop")
        self.assertTrue(self.j.in_cooldown("META"))
        self.assertFalse(self.j.in_cooldown("GOOGL"))

    def test_partial_exit_keeps_plan(self):
        self.j.record_entry("SPY", 2.0, 100.0, stop=95.0, target=120.0, thesis="t")
        self.j.record_exit("SPY", 1.0, 121.0, reason="target")
        plans = self.j.get_open_plans()
        self.assertIn("SPY", plans)
        self.assertAlmostEqual(plans["SPY"]["quantity"], 1.0)

    def test_scale_in_blends_and_persists(self):
        self.j.record_entry("UPRO", 1.0, 100.0, stop=95.0, target=120.0, thesis="a")
        self.j.record_entry("UPRO", 1.0, 110.0, stop=98.0, target=130.0, thesis="b")
        plan = self.j.get_open_plans()["UPRO"]
        self.assertAlmostEqual(plan["entry_price"], 105.0)
        self.assertAlmostEqual(plan["stop"], 98.0)
        # Reload from disk
        j2 = TradeJournal(self.path)
        self.assertAlmostEqual(j2.get_open_plans()["UPRO"]["entry_price"], 105.0)


class TestRiskSizing(unittest.TestCase):
    def test_validate_trade_risk(self):
        r = RiskManager(risk_per_trade_pct=2.0)
        ok, _ = r.validate_trade_risk(quantity=2.0, entry_price=10.0, stop_price=9.0,
                                      portfolio_equity=100.0)
        self.assertTrue(ok)  # risks exactly the $2 budget
        ok, msg = r.validate_trade_risk(quantity=5.0, entry_price=10.0, stop_price=9.0,
                                        portfolio_equity=100.0)
        self.assertFalse(ok)
        self.assertIn("Reduce to", msg)
        ok, _ = r.validate_trade_risk(quantity=1.0, entry_price=10.0, stop_price=11.0,
                                      portfolio_equity=100.0)
        self.assertFalse(ok)  # stop above entry

    def test_daily_baseline_idempotent(self):
        r = RiskManager(max_daily_loss_pct=10.0)
        r.initialize(100.0)
        r.initialize(95.0)  # same day: must NOT reset the baseline
        self.assertFalse(r.is_daily_loss_limit_breached(91.0))   # -9% from 100
        self.assertTrue(r.is_daily_loss_limit_breached(89.9))    # -10.1% from 100


if __name__ == "__main__":
    unittest.main()
