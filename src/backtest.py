"""Event-driven backtester — replays the live playbook over historical daily bars.

Runs the SAME components used live (signals.compute_indicators, regime_score,
suggest_stop, position_size, RiskManager caps) so a backtest validates the actual
rules, not a lookalike. Stdlib only.

Anti-lookahead discipline: signals are computed on bars strictly BEFORE the
action day; fills happen at the action day's open (entries) or at stop/target
levels gap-adjusted to the open. Slippage is charged on every fill.
"""

import itertools
import math
from dataclasses import dataclass, field
from typing import Optional

from . import signals
from .risk_manager import RiskManager


@dataclass
class BacktestParams:
    risk_per_trade_pct: float = 2.0
    atr_mult: float = 2.0            # stop = entry - atr_mult * ATR (clamped in suggest_stop)
    target_r: float = 3.0            # target = entry + target_r * (entry - stop)
    max_positions: int = 4
    rsi_min: float = 45.0
    rsi_max: float = 70.0
    use_regime: bool = True
    breakeven_at_r: float = 1.0
    slippage_bps: float = 5.0        # per side, models marketable-limit cost
    max_position_pct: float = 25.0
    max_portfolio_risk_pct: float = 90.0
    min_cash_reserve_pct: float = 5.0
    min_history: int = 60            # bars required before a symbol is tradable


@dataclass
class _Position:
    symbol: str
    qty: float
    entry: float
    stop: float
    target: float
    risk_per_share: float
    breakeven_moved: bool = False


@dataclass
class BacktestResult:
    params: dict
    start_equity: float
    end_equity: float
    total_return_pct: float
    benchmark_return_pct: float
    max_drawdown_pct: float
    sharpe: Optional[float]
    trades: int
    win_rate_pct: Optional[float]
    expectancy: Optional[float]
    avg_exposure_pct: float
    equity_curve: list = field(default_factory=list, repr=False)
    trade_log: list = field(default_factory=list, repr=False)

    def summary(self) -> dict:
        return {
            "params": self.params,
            "total_return_pct": round(self.total_return_pct, 2),
            "benchmark_return_pct": round(self.benchmark_return_pct, 2),
            "max_drawdown_pct": round(self.max_drawdown_pct, 2),
            "sharpe": round(self.sharpe, 2) if self.sharpe is not None else None,
            "trades": self.trades,
            "win_rate_pct": round(self.win_rate_pct, 1) if self.win_rate_pct is not None else None,
            "expectancy": round(self.expectancy, 4) if self.expectancy is not None else None,
            "avg_exposure_pct": round(self.avg_exposure_pct, 1),
        }


def _align(bars_by_symbol: dict[str, list[dict]], index_symbol: str) -> tuple[list[str], dict]:
    """Intersect trading dates across all symbols so every day has every bar."""
    date_sets = []
    by_sym_date = {}
    for sym, bars in bars_by_symbol.items():
        d = {b["begins_at"][:10]: b for b in bars if b.get("begins_at")}
        by_sym_date[sym] = d
        date_sets.append(set(d))
    common = sorted(set.intersection(*date_sets)) if date_sets else []
    if index_symbol not in by_sym_date:
        raise ValueError(f"bars_by_symbol must include the index symbol {index_symbol}")
    return common, by_sym_date


def run_backtest(bars_by_symbol: dict[str, list[dict]], start_equity: float = 100.0,
                 index_symbol: str = "SPY", regime_symbol2: str = "QQQ",
                 params: Optional[BacktestParams] = None) -> BacktestResult:
    p = params or BacktestParams()
    risk = RiskManager(
        max_position_pct=p.max_position_pct,
        max_portfolio_risk_pct=p.max_portfolio_risk_pct,
        min_cash_reserve_pct=p.min_cash_reserve_pct,
        risk_per_trade_pct=p.risk_per_trade_pct,
    )
    dates, by_sym = _align(bars_by_symbol, index_symbol)
    tradable = [s for s in bars_by_symbol if s not in (index_symbol, regime_symbol2)]
    slip = p.slippage_bps / 10_000

    cash = start_equity
    positions: dict[str, _Position] = {}
    equity_curve: list[dict] = []
    trade_log: list[dict] = []
    exposure_samples: list[float] = []

    def history(sym: str, upto: int) -> list[dict]:
        return [by_sym[sym][d] for d in dates[:upto] if d in by_sym[sym]]

    def mark_equity(day_idx: int) -> float:
        eq = cash
        for sym, pos in positions.items():
            bar = by_sym[sym].get(dates[day_idx])
            px = bar["close"] if bar else pos.entry
            eq += pos.qty * px
        return eq

    for i in range(p.min_history, len(dates)):
        date = dates[i]
        equity_before = mark_equity(i - 1)

        # ── Exits first (gap-aware) ──────────────────────────────────────────
        for sym in list(positions):
            pos = positions[sym]
            bar = by_sym[sym].get(date)
            if not bar:
                continue
            # Stop: if the day trades at/below the stop, fill at min(open, stop)
            if bar["low"] <= pos.stop:
                fill = min(bar["open"], pos.stop) * (1 - slip)
                pnl = (fill - pos.entry) * pos.qty
                cash += pos.qty * fill
                trade_log.append({"symbol": sym, "side": "stop", "entry": pos.entry,
                                  "exit": round(fill, 4), "qty": pos.qty,
                                  "pnl": round(pnl, 4), "date": date})
                del positions[sym]
                continue
            # Target: scale out half at max(open, target)
            if bar["high"] >= pos.target and pos.qty > 0:
                fill = max(bar["open"], pos.target) * (1 - slip)
                half = pos.qty / 2
                pnl = (fill - pos.entry) * half
                cash += half * fill
                trade_log.append({"symbol": sym, "side": "target_half", "entry": pos.entry,
                                  "exit": round(fill, 4), "qty": half,
                                  "pnl": round(pnl, 4), "date": date})
                pos.qty -= half
                # Remainder trails: stop ratchets to entry at worst
                pos.stop = max(pos.stop, pos.entry)
                pos.breakeven_moved = True
            # Breakeven move at +breakeven_at_r R (on close)
            if not pos.breakeven_moved and bar["close"] >= pos.entry + p.breakeven_at_r * pos.risk_per_share:
                pos.stop = max(pos.stop, pos.entry)
                pos.breakeven_moved = True

        # ── Regime (computed on history BEFORE today) ────────────────────────
        sizing_mult = 1.0
        if p.use_regime:
            idx1 = signals.compute_indicators(history(index_symbol, i))
            idx2_hist = history(regime_symbol2, i) if regime_symbol2 in by_sym else []
            idx2 = signals.compute_indicators(idx2_hist) if idx2_hist else idx1
            sizing_mult = signals.regime_score(idx1, idx2)["sizing_multiplier"]

        # ── Entries at today's open ──────────────────────────────────────────
        if sizing_mult > 0:
            idx_closes = [b["close"] for b in history(index_symbol, i)]
            candidates = []
            for sym in tradable:
                if sym in positions:
                    continue
                hist = history(sym, i)
                if len(hist) < p.min_history or dates[i] not in by_sym[sym]:
                    continue
                ind = signals.compute_indicators(hist)
                r = ind.get("rsi14")
                if ind.get("trend") != "up" or r is None or not (p.rsi_min <= r <= p.rsi_max):
                    continue
                closes = [b["close"] for b in hist]
                rs = signals.relative_strength(closes, idx_closes, 5)
                if rs is None or rs <= 0:
                    continue
                candidates.append((rs, sym, ind))
            candidates.sort(reverse=True)

            for rs, sym, ind in candidates:
                if len(positions) >= p.max_positions:
                    break
                bar = by_sym[sym][dates[i]]
                entry = bar["open"] * (1 + slip)
                stop = signals.suggest_stop(entry, ind.get("atr14"), atr_mult=p.atr_mult)
                rps = entry - stop
                if rps <= 0:
                    continue
                qty = signals.position_size(equity_before, p.risk_per_trade_pct * sizing_mult,
                                            entry, stop)
                if qty <= 0:
                    continue
                deployed = equity_before - cash
                ok, _ = risk.validate_stock_buy(sym, qty, entry, equity_before, cash, deployed)
                if not ok:
                    max_val = risk.max_order_value(equity_before, cash, deployed)
                    qty = max_val / entry if entry > 0 else 0
                    if qty * rps < equity_before * 0.001:  # not worth the trade
                        continue
                cost = qty * entry
                if cost > cash:
                    qty = cash / entry * 0.999
                    cost = qty * entry
                if qty <= 0:
                    continue
                cash -= cost
                positions[sym] = _Position(sym, qty, entry, stop,
                                           entry + p.target_r * rps, rps)

        eq = mark_equity(i)
        equity_curve.append({"date": date, "equity": round(eq, 4)})
        exposure_samples.append((eq - cash) / eq * 100 if eq > 0 else 0)

    # ── Metrics ──────────────────────────────────────────────────────────────
    end_equity = equity_curve[-1]["equity"] if equity_curve else start_equity
    peak, max_dd = -math.inf, 0.0
    for pt in equity_curve:
        peak = max(peak, pt["equity"])
        if peak > 0:
            max_dd = max(max_dd, (peak - pt["equity"]) / peak * 100)
    rets = []
    for a, b in zip(equity_curve, equity_curve[1:]):
        if a["equity"] > 0:
            rets.append(b["equity"] / a["equity"] - 1)
    sharpe = None
    if len(rets) > 2:
        mean = sum(rets) / len(rets)
        var = sum((r - mean) ** 2 for r in rets) / len(rets)
        sd = math.sqrt(var)
        sharpe = (mean / sd * math.sqrt(252)) if sd > 0 else None

    closed = [t for t in trade_log]
    wins = [t for t in closed if t["pnl"] > 0]
    win_rate = len(wins) / len(closed) * 100 if closed else None
    expectancy = sum(t["pnl"] for t in closed) / len(closed) if closed else None

    idx_bars = [by_sym[index_symbol][d] for d in dates[p.min_history:] if d in by_sym[index_symbol]]
    bench = ((idx_bars[-1]["close"] / idx_bars[0]["open"] - 1) * 100) if len(idx_bars) > 1 else 0.0

    return BacktestResult(
        params={k: getattr(p, k) for k in ("risk_per_trade_pct", "atr_mult", "target_r",
                                           "max_positions", "rsi_min", "rsi_max", "use_regime")},
        start_equity=start_equity,
        end_equity=end_equity,
        total_return_pct=(end_equity / start_equity - 1) * 100,
        benchmark_return_pct=bench,
        max_drawdown_pct=max_dd,
        sharpe=sharpe,
        trades=len(closed),
        win_rate_pct=win_rate,
        expectancy=expectancy,
        avg_exposure_pct=sum(exposure_samples) / len(exposure_samples) if exposure_samples else 0.0,
        equity_curve=equity_curve,
        trade_log=trade_log,
    )


def grid_search(bars_by_symbol: dict[str, list[dict]], grid: dict[str, list],
                start_equity: float = 100.0, **kwargs) -> list[BacktestResult]:
    """Run a small parameter grid; returns results sorted by total return.
    Keep grids small — every cell you test is a chance to overfit."""
    keys = sorted(grid)
    results = []
    for combo in itertools.product(*(grid[k] for k in keys)):
        params = BacktestParams(**dict(zip(keys, combo)))
        results.append(run_backtest(bars_by_symbol, start_equity=start_equity,
                                    params=params, **kwargs))
    results.sort(key=lambda r: r.total_return_pct, reverse=True)
    return results
