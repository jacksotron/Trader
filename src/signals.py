"""Quantitative signal engine — pure-python indicators computed from OHLCV bars.

Everything here is deterministic and dependency-free so it can be unit-tested
without market access. Bars are dicts with open/high/low/close/volume keys,
oldest first (the shape returned by robinhood_client historicals helpers).
"""

import math
from typing import Optional


# ── Primitives ────────────────────────────────────────────────────────────────

def sma(values: list[float], period: int) -> Optional[float]:
    if len(values) < period or period <= 0:
        return None
    return sum(values[-period:]) / period


def ema(values: list[float], period: int) -> Optional[float]:
    if len(values) < period or period <= 0:
        return None
    k = 2 / (period + 1)
    e = sum(values[:period]) / period
    for v in values[period:]:
        e = v * k + e * (1 - k)
    return e


def rsi(closes: list[float], period: int = 14) -> Optional[float]:
    """Wilder's RSI."""
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for prev, cur in zip(closes, closes[1:]):
        change = cur - prev
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for g, l in zip(gains[period:], losses[period:]):
        avg_gain = (avg_gain * (period - 1) + g) / period
        avg_loss = (avg_loss * (period - 1) + l) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - 100 / (1 + rs)


def atr(bars: list[dict], period: int = 14) -> Optional[float]:
    """Wilder's Average True Range."""
    if len(bars) < period + 1:
        return None
    trs = []
    for prev, cur in zip(bars, bars[1:]):
        trs.append(max(
            cur["high"] - cur["low"],
            abs(cur["high"] - prev["close"]),
            abs(cur["low"] - prev["close"]),
        ))
    a = sum(trs[:period]) / period
    for tr in trs[period:]:
        a = (a * (period - 1) + tr) / period
    return a


def realized_vol_pct(closes: list[float], period: int = 20) -> Optional[float]:
    """Std-dev of simple per-bar returns over the window, in percent."""
    if len(closes) < period + 1:
        return None
    rets = [(c / p - 1) for p, c in zip(closes[-period - 1:-1], closes[-period:])]
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / len(rets)
    return math.sqrt(var) * 100


def vwap(bars: list[dict]) -> Optional[float]:
    """Volume-weighted average price across the provided bars (use intraday bars)."""
    num = den = 0.0
    for b in bars:
        typical = (b["high"] + b["low"] + b["close"]) / 3
        num += typical * b["volume"]
        den += b["volume"]
    return (num / den) if den else None


def volume_zscore(bars: list[dict], period: int = 20) -> Optional[float]:
    """How unusual is the latest bar's volume vs the trailing window."""
    if len(bars) < period + 1:
        return None
    vols = [b["volume"] for b in bars[-period - 1:-1]]
    mean = sum(vols) / len(vols)
    var = sum((v - mean) ** 2 for v in vols) / len(vols)
    sd = math.sqrt(var)
    if sd == 0:
        return 0.0
    return (bars[-1]["volume"] - mean) / sd


def pct_return(closes: list[float], lookback: int) -> Optional[float]:
    if len(closes) < lookback + 1 or closes[-lookback - 1] == 0:
        return None
    return (closes[-1] / closes[-lookback - 1] - 1) * 100


# ── Composites ────────────────────────────────────────────────────────────────

def trend_state(closes: list[float]) -> str:
    """'up' / 'down' / 'chop' from the 20/50 MA stack and 20MA slope."""
    s20, s50 = sma(closes, 20), sma(closes, 50)
    if s20 is None:
        return "unknown"
    last = closes[-1]
    prev_s20 = sma(closes[:-5], 20) if len(closes) >= 25 else None
    slope_up = prev_s20 is not None and s20 > prev_s20
    slope_down = prev_s20 is not None and s20 < prev_s20
    if s50 is not None:
        if last > s20 > s50 and slope_up:
            return "up"
        if last < s20 < s50 and slope_down:
            return "down"
    else:
        if last > s20 and slope_up:
            return "up"
        if last < s20 and slope_down:
            return "down"
    return "chop"


def compute_indicators(daily_bars: list[dict], intraday_bars: Optional[list[dict]] = None) -> dict:
    """Full indicator block for one symbol. daily_bars drive trend/vol;
    intraday_bars (today's session) drive VWAP positioning."""
    closes = [b["close"] for b in daily_bars]
    out = {
        "last_close": closes[-1] if closes else None,
        "sma20": sma(closes, 20),
        "sma50": sma(closes, 50),
        "ema9": ema(closes, 9),
        "rsi14": rsi(closes, 14),
        "atr14": atr(daily_bars, 14),
        "ret_1d_pct": pct_return(closes, 1),
        "ret_5d_pct": pct_return(closes, 5),
        "ret_20d_pct": pct_return(closes, 20),
        "realized_vol20_pct": realized_vol_pct(closes, 20),
        "volume_z": volume_zscore(daily_bars, 20),
        "trend": trend_state(closes),
        "high_20": max(b["high"] for b in daily_bars[-20:]) if len(daily_bars) >= 20 else None,
        "low_20": min(b["low"] for b in daily_bars[-20:]) if len(daily_bars) >= 20 else None,
    }
    if out["atr14"] and out["last_close"]:
        out["atr_pct"] = out["atr14"] / out["last_close"] * 100
    else:
        out["atr_pct"] = None
    if intraday_bars:
        v = vwap(intraday_bars)
        out["vwap"] = v
        last = intraday_bars[-1]["close"]
        out["above_vwap"] = (last > v) if (v and last) else None
        out["day_range_pos"] = _range_position(intraday_bars)
    return out


def _range_position(bars: list[dict]) -> Optional[float]:
    """Where the last price sits in today's range: 0 = at low, 1 = at high."""
    hi = max(b["high"] for b in bars)
    lo = min(b["low"] for b in bars)
    if hi == lo:
        return 0.5
    return (bars[-1]["close"] - lo) / (hi - lo)


def relative_strength(symbol_closes: list[float], index_closes: list[float],
                      lookback: int = 5) -> Optional[float]:
    """Symbol return minus index return over the lookback, in percentage points."""
    a = pct_return(symbol_closes, lookback)
    b = pct_return(index_closes, lookback)
    if a is None or b is None:
        return None
    return a - b


def regime_score(spy_ind: dict, qqq_ind: dict) -> dict:
    """0-100 risk-appetite score from index indicators, with defined thresholds.

    >= 70: risk-on (full sizing) · 40-69: mixed (half sizing) · < 40: risk-off
    (no new longs). The components are intentionally simple and auditable.
    """
    score = 50.0
    for ind, weight in ((spy_ind, 1.0), (qqq_ind, 1.0)):
        trend = ind.get("trend")
        if trend == "up":
            score += 12 * weight
        elif trend == "down":
            score -= 15 * weight
        r = ind.get("rsi14")
        if r is not None:
            if r >= 60:
                score += 5 * weight
            elif r <= 40:
                score -= 7 * weight
            if r >= 75:
                score -= 4 * weight  # overbought chase penalty
        ret5 = ind.get("ret_5d_pct")
        if ret5 is not None:
            score += max(min(ret5, 3.0), -3.0) * 2 * weight
        above = ind.get("above_vwap")
        if above is True:
            score += 4 * weight
        elif above is False:
            score -= 4 * weight
        rv = ind.get("realized_vol20_pct")
        if rv is not None and rv > 2.5:
            score -= (rv - 2.5) * 4 * weight  # vol spike penalty
    score = max(0.0, min(100.0, score))
    label = "risk_on" if score >= 70 else ("mixed" if score >= 40 else "risk_off")
    sizing = {"risk_on": 1.0, "mixed": 0.5, "risk_off": 0.0}[label]
    return {"score": round(score, 1), "label": label, "sizing_multiplier": sizing}


# ── Trade construction ────────────────────────────────────────────────────────

def suggest_stop(entry_price: float, atr_value: Optional[float],
                 atr_mult: float = 2.0, max_stop_pct: float = 8.0,
                 min_stop_pct: float = 1.5) -> float:
    """Volatility-adjusted stop: atr_mult x ATR below entry, clamped to sane bounds."""
    if atr_value and entry_price > 0:
        stop_pct = min(max(atr_value * atr_mult / entry_price * 100, min_stop_pct), max_stop_pct)
    else:
        stop_pct = max_stop_pct
    return round(entry_price * (1 - stop_pct / 100), 4)


def position_size(equity: float, risk_per_trade_pct: float,
                  entry_price: float, stop_price: float) -> float:
    """Shares such that a fill at entry stopped at stop loses risk_per_trade_pct of equity."""
    risk_budget = equity * risk_per_trade_pct / 100
    per_share_risk = entry_price - stop_price
    if per_share_risk <= 0 or entry_price <= 0:
        return 0.0
    return max(round(risk_budget / per_share_risk, 6), 0.0)
