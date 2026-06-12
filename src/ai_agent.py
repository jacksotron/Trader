"""Claude-powered trading agent with full tool use loop.

Architecture, in the order a cycle runs:
  1. Journal enforcement — open plans (entry/stop/target) are injected into the
     cycle context and stops/targets are honored mechanically before discretion.
  2. Signal engine (signals.py) — ATR, RSI, trend state, relative strength, VWAP,
     volume z-scores computed in code; the model reasons over the table.
  3. Regime score — SPY+QQQ composite with defined exposure thresholds.
  4. Risk-budget sizing — every entry is sized off its stop distance so a stop-out
     costs a fixed % of equity (RiskManager.validate_trade_risk).
  5. Execution guards — regular-session only, auction-window avoidance, spread
     caps, marketable limits, cooldowns, entry/day and loss-streak throttles.
  6. Journal write-back — entries record thesis/stop/target; exits record reason
     and realized P&L; stats feed the next cycle.
"""

import json
import logging
from typing import Any, Optional

import anthropic

from . import robinhood_client as rh
from . import signals
from .journal import TradeJournal
from .risk_manager import RiskManager

logger = logging.getLogger(__name__)

_PLAYBOOK_TEMPLATE = """\
You are a disciplined, systematic trader operating a live Robinhood account. Your edge is
process, not prediction: quantified signals, fixed risk budgets, ruthless exits, and a
journal that holds every trade accountable. You never chase, never average down a loser,
and never trade just to trade.

PLAYBOOK — work through these phases in order, every cycle:

1. ENFORCE PLANS (mechanical — before any new analysis)
   - The cycle context contains every open plan: entry, stop, target, thesis.
   - Price at/below stop -> sell_stock with exit_reason='stop'. No exceptions, no
     "give it one more cycle". The stop was set by a calmer version of you.
   - Price at/above target -> scale out at least half (exit_reason='target').
   - Up >= 1R (one risk unit = entry minus stop) -> move the stop to breakeven via
     update_exit_plan. Trail winners; stops only ever move UP (enforced).
   - A position without a plan is a bug: set one immediately via update_exit_plan.

2. REGIME (get_regime — defined thresholds, not vibes)
   - score >= 70 (risk_on): full sizing_multiplier 1.0
   - 40-69 (mixed): half sizing
   - < 40 (risk_off): NO new longs; manage exits only.

3. SELECT (get_signals on candidates — only if regime allows)
   - Favor: trend='up', positive 5d relative strength vs index, RSI 45-70 (momentum
     without chase), above VWAP, volume_z > 0 on up moves.
   - Avoid: RSI > 75 chases, trend='down' knife-catches, spread > {max_spread_pct}%,
     cooldown symbols (stopped out today), anything without a clear invalidation.
   - Leveraged ETFs ({leveraged_symbols}): tighter exits — stop {leveraged_stop}%,
     scale at +{leveraged_target}% — daily-reset decay punishes drift.

4. SIZE & EXECUTE
   - Stop first, size second: use the suggested_stop (2xATR, clamped) or your own
     tighter level, then size so a stop-out costs {risk_per_trade_pct}% of equity x
     the regime sizing_multiplier. get_signals returns qty_for_risk_budget.
   - buy_stock REQUIRES stop, target, and rationale — they are journaled and the
     next cycle enforces them. Target must be >= 2R away or skip the trade.
   - Marketable limits only (auto-priced ask*(1+{slippage_pct}%)); regular session
     only; no entries in the first {avoid_open_minutes} or final
     {avoid_close_minutes} minutes; exits allowed all session.
   - Throttles (enforced): max {max_new_entries_per_day} new entries/day; after
     {loss_streak_halt} consecutive losing exits today, no more entries today.

5. JOURNAL & REVIEW
   - Your stats (win rate, expectancy, streaks) are in the cycle context. If
     expectancy is negative over the last 10+ trades, tighten selection rather
     than sizing up. Recent losing patterns are information — name them.

HARD LIMITS (enforced in code — a rejection is final, do not retry around it):
- Max {max_position_pct}% of equity per position; max {max_portfolio_risk_pct}%
  deployed; {min_cash_reserve_pct}% cash reserve; daily halt at -{max_daily_loss_pct}%;
  per-trade risk capped at {risk_per_trade_pct}% of equity.

Capital preservation outranks any single opportunity. Flat is a position. The journal
remembers what you promised — keep your word to it.
"""


def _make_tools(risk: RiskManager, cfg: dict) -> list[dict]:
    options_cfg = cfg.get("options", {})
    assets_cfg = cfg.get("assets", {})

    tools = [
        {
            "name": "get_market_session",
            "description": (
                "Returns the live market session ('pre', 'regular', 'after', 'closed') from the "
                "exchange calendar, with minutes since open / to close during the regular session."
            ),
            "input_schema": {"type": "object", "properties": {}, "required": []},
        },
        {
            "name": "get_portfolio_summary",
            "description": "Returns overall portfolio equity, cash, buying power, and day return %.",
            "input_schema": {"type": "object", "properties": {}, "required": []},
        },
        {
            "name": "get_stock_positions",
            "description": "Returns all open stock positions with quantities, avg buy price, current price, and P&L.",
            "input_schema": {"type": "object", "properties": {}, "required": []},
        },
        {
            "name": "get_crypto_positions",
            "description": "Returns all open crypto positions with quantities, avg buy price, current price, and P&L.",
            "input_schema": {"type": "object", "properties": {}, "required": []},
        },
        {
            "name": "get_options_positions",
            "description": "Returns all open options positions with contract details and P&L.",
            "input_schema": {"type": "object", "properties": {}, "required": []},
        },
        {
            "name": "get_regime",
            "description": (
                "Computes the market regime score (0-100) from SPY+QQQ trend, RSI, momentum, VWAP "
                "position, and realized vol. Returns score, label (risk_on/mixed/risk_off), and the "
                "sizing_multiplier to apply to all new entries. Call once per cycle before entries."
            ),
            "input_schema": {"type": "object", "properties": {}, "required": []},
        },
        {
            "name": "get_signals",
            "description": (
                "Quantitative signal table for up to 6 symbols: trend state (20/50 MA), RSI14, "
                "ATR14 (+%), 1/5/20-day returns, 5d relative strength vs SPY, realized vol, volume "
                "z-score, VWAP position, 20d high/low, plus suggested_stop (2xATR clamped) and "
                "qty_for_risk_budget sized to the per-trade risk limit. Use this instead of eyeballing "
                "raw bars."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "symbols": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Stock tickers (max 6 per call).",
                    },
                },
                "required": ["symbols"],
            },
        },
        {
            "name": "get_trade_journal",
            "description": (
                "Returns open plans (entry/stop/target/thesis per position), performance stats "
                "(win rate, expectancy, streaks, entries today), recent closed trades, and cooldown "
                "symbols. The cycle context already includes a snapshot; call this only if you need "
                "more history."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "recent_n": {"type": "integer", "description": "How many recent closed trades (default 10)."},
                },
                "required": [],
            },
        },
        {
            "name": "update_exit_plan",
            "description": (
                "Adjust the journaled stop and/or target for an open position — used for trailing "
                "stops and breakeven moves. Stops can only move UP (rejections are final). Always "
                "give the reason."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "stop": {"type": "number", "description": "New stop price (must be >= current stop)."},
                    "target": {"type": "number", "description": "New target price."},
                    "reason": {"type": "string", "description": "Why this adjustment (e.g. '+1R, moving to breakeven')."},
                },
                "required": ["symbol", "reason"],
            },
        },
        {
            "name": "get_stock_quote",
            "description": (
                "Returns current bid/ask/last, spread %, daily change %, and halt status for a stock. "
                "Always check the quote immediately before any order."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Stock ticker, e.g. AAPL"},
                },
                "required": ["symbol"],
            },
        },
        {
            "name": "get_crypto_quote",
            "description": "Returns the current mark price, bid/ask, high/low, and daily change % for a crypto.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Crypto code, e.g. BTC, ETH"},
                },
                "required": ["symbol"],
            },
        },
        {
            "name": "get_stock_historicals",
            "description": "Raw OHLCV bars for a stock. Prefer get_signals; use this only for bespoke analysis.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "interval": {
                        "type": "string",
                        "enum": ["5minute", "10minute", "hour", "day", "week"],
                        "description": "Bar interval. Default: 5minute",
                    },
                    "span": {
                        "type": "string",
                        "enum": ["day", "week", "month", "3month", "year", "5year"],
                        "description": "Time span. Default: day",
                    },
                },
                "required": ["symbol"],
            },
        },
        {
            "name": "get_crypto_historicals",
            "description": "Returns OHLCV bars for a crypto asset.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "interval": {
                        "type": "string",
                        "enum": ["5minute", "10minute", "hour", "day", "week"],
                    },
                    "span": {
                        "type": "string",
                        "enum": ["day", "week", "month", "3month", "year", "5year"],
                    },
                },
                "required": ["symbol"],
            },
        },
        {
            "name": "get_options_chain",
            "description": (
                "Returns available options contracts for a symbol with greeks (delta, gamma, theta), "
                "bid/ask, IV, volume, and open interest. Filter by expiration_date and option_type."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "expiration_date": {
                        "type": "string",
                        "description": "YYYY-MM-DD format. If omitted returns nearest expiration.",
                    },
                    "option_type": {
                        "type": "string",
                        "enum": ["call", "put"],
                        "description": "Filter by option type.",
                    },
                },
                "required": ["symbol"],
            },
        },
        {
            "name": "get_open_orders",
            "description": "Returns all currently open (pending) stock orders.",
            "input_schema": {"type": "object", "properties": {}, "required": []},
        },
    ]

    if assets_cfg.get("stocks", True):
        tools += [
            {
                "name": "buy_stock",
                "description": (
                    "Buy shares with a marketable limit order and journal the trade plan. stop, "
                    "target, and rationale are REQUIRED — the next cycle enforces them. Size with "
                    "qty_for_risk_budget from get_signals (x regime sizing_multiplier). Blocked: "
                    "outside regular session, open/close windows, wide spreads, cooldown symbols, "
                    "entry/day and loss-streak throttles, risk-budget and portfolio-cap violations."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "symbol": {"type": "string"},
                        "quantity": {"type": "number", "description": "Shares to buy (risk-budget sized)."},
                        "stop": {"type": "number", "description": "Stop price — exit if reached. Journaled."},
                        "target": {"type": "number", "description": "Target price (>= 2R from entry). Journaled."},
                        "limit_price": {
                            "type": "number",
                            "description": "Optional explicit limit. Omit for auto marketable limit.",
                        },
                        "rationale": {
                            "type": "string",
                            "description": "Thesis + invalidation, one line each. Journaled.",
                        },
                    },
                    "required": ["symbol", "quantity", "stop", "target", "rationale"],
                },
            },
            {
                "name": "sell_stock",
                "description": (
                    "Sell shares with a marketable limit order (auto-priced off the bid) and record "
                    "the exit in the journal with realized P&L. Allowed any time in the regular "
                    "session — exits are never window-blocked."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "symbol": {"type": "string"},
                        "quantity": {"type": "number"},
                        "exit_reason": {
                            "type": "string",
                            "enum": ["stop", "target", "trail", "thesis_invalidated", "rebalance", "discretionary"],
                            "description": "Why this exit. 'stop' triggers a same-day re-entry cooldown.",
                        },
                        "limit_price": {"type": "number"},
                        "rationale": {"type": "string", "description": "One line vs the original plan."},
                    },
                    "required": ["symbol", "quantity", "exit_reason", "rationale"],
                },
            },
        ]

    if assets_cfg.get("crypto", True):
        tools += [
            {
                "name": "buy_crypto",
                "description": (
                    "Buy a cryptocurrency by dollar amount. Crypto trades 24/7 and is exempt from "
                    "equity session guards. Risk limits are enforced."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "symbol": {"type": "string", "description": "e.g. BTC, ETH, SOL"},
                        "amount_dollars": {"type": "number", "description": "Dollar amount to spend"},
                        "rationale": {"type": "string"},
                    },
                    "required": ["symbol", "amount_dollars", "rationale"],
                },
            },
            {
                "name": "sell_crypto",
                "description": "Sell a cryptocurrency position by dollar amount.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "symbol": {"type": "string"},
                        "amount_dollars": {"type": "number"},
                        "rationale": {"type": "string"},
                    },
                    "required": ["symbol", "amount_dollars", "rationale"],
                },
            },
        ]

    if assets_cfg.get("options", True):
        tools += [
            {
                "name": "buy_option",
                "description": (
                    "Buy option contracts with a REQUIRED per-contract limit price — at or inside "
                    "the ask, never market. Look up option_id via get_options_chain. "
                    f"DTE {options_cfg.get('min_dte', 1)}-{options_cfg.get('max_dte', 45)}, "
                    f"|delta| {options_cfg.get('min_delta', 0.10)}-{options_cfg.get('max_delta', 0.90)}, "
                    f"max {options_cfg.get('max_contracts', 10)} contracts."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "option_id": {"type": "string", "description": "From get_options_chain"},
                        "contracts": {"type": "integer"},
                        "limit_price": {"type": "number", "description": "Per-contract limit (required)."},
                        "rationale": {"type": "string"},
                    },
                    "required": ["option_id", "contracts", "limit_price", "rationale"],
                },
            },
            {
                "name": "sell_option",
                "description": "Sell/close option contracts with a REQUIRED per-contract limit price.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "option_id": {"type": "string"},
                        "contracts": {"type": "integer"},
                        "limit_price": {"type": "number"},
                        "rationale": {"type": "string"},
                    },
                    "required": ["option_id", "contracts", "limit_price", "rationale"],
                },
            },
        ]

    tools.append({
        "name": "cancel_order",
        "description": "Cancel a pending open order by order ID.",
        "input_schema": {
            "type": "object",
            "properties": {"order_id": {"type": "string"}},
            "required": ["order_id"],
        },
    })

    return tools


_EQUITY_OPTION_ORDER_TOOLS = {"buy_stock", "sell_stock", "buy_option", "sell_option"}
_BUY_TOOLS = {"buy_stock", "buy_option", "buy_crypto"}


def _session_guard(name: str, exec_cfg: dict) -> Optional[str]:
    """Reject equity/option orders outside the regular session, and new entries
    inside the open/close avoidance windows. Returns a rejection reason or None."""
    if name not in _EQUITY_OPTION_ORDER_TOOLS:
        return None  # crypto trades 24/7

    is_buy = name in _BUY_TOOLS
    try:
        session = rh.get_market_session()
    except Exception as exc:
        logger.warning("Market session lookup failed: %s", exc)
        return f"Cannot verify the market session ({exc}); refusing new entry." if is_buy else None

    if session["session"] != "regular":
        return (
            f"Market session is '{session['session']}' — orders go out only during the regular "
            "session and are never queued for the next open (opening-auction fills are uncontrolled)."
        )

    if is_buy:
        avoid_open = exec_cfg.get("avoid_open_minutes", 15)
        avoid_close = exec_cfg.get("avoid_close_minutes", 5)
        if session.get("minutes_since_open", avoid_open) < avoid_open:
            return (
                f"Inside the first {avoid_open} minutes after the open — no new entries until "
                "price discovery settles. Exits are still allowed."
            )
        if session.get("minutes_to_close", avoid_close) < avoid_close:
            return f"Inside the final {avoid_close} minutes — no new entries into the closing auction."
    return None


def _marketable_limit(quote: dict, side: str, slippage_pct: float) -> Optional[float]:
    """Limit price pegged just through the touch: pay up at most slippage_pct."""
    if side == "buy":
        ref = quote.get("ask_price") or quote.get("last_trade_price") or 0
        return round(ref * (1 + slippage_pct / 100), 2) if ref else None
    ref = quote.get("bid_price") or quote.get("last_trade_price") or 0
    return round(ref * (1 - slippage_pct / 100), 2) if ref else None


def _fetch_indicators(symbol: str) -> dict:
    daily = rh.get_stock_historicals(symbol, interval="day", span="year")
    intraday = rh.get_stock_historicals(symbol, interval="5minute", span="day")
    return signals.compute_indicators(daily, intraday)


def _execute_tool(
    name: str,
    inputs: dict,
    risk: RiskManager,
    cfg: dict,
    journal: TradeJournal,
) -> Any:
    options_cfg = cfg.get("options", {})
    exec_cfg = cfg.get("execution", {})
    slippage_pct = cfg.get("limit_order_slippage_pct", 0.3)
    max_spread_pct = exec_cfg.get("max_spread_pct", 1.0)

    # ── Read-only tools ──────────────────────────────────────────────────────
    if name == "get_market_session":
        return rh.get_market_session()
    if name == "get_portfolio_summary":
        return rh.get_portfolio_summary()
    if name == "get_stock_positions":
        return rh.get_stock_positions()
    if name == "get_crypto_positions":
        return rh.get_crypto_positions()
    if name == "get_options_positions":
        return rh.get_options_positions()
    if name == "get_stock_quote":
        return rh.get_stock_quote(inputs["symbol"])
    if name == "get_crypto_quote":
        return rh.get_crypto_quote(inputs["symbol"])
    if name == "get_stock_historicals":
        return rh.get_stock_historicals(
            inputs["symbol"],
            interval=inputs.get("interval", "5minute"),
            span=inputs.get("span", "day"),
        )
    if name == "get_crypto_historicals":
        return rh.get_crypto_historicals(
            inputs["symbol"],
            interval=inputs.get("interval", "5minute"),
            span=inputs.get("span", "day"),
        )
    if name == "get_options_chain":
        return rh.get_options_chain(
            inputs["symbol"],
            expiration_date=inputs.get("expiration_date"),
            option_type=inputs.get("option_type"),
        )
    if name == "get_open_orders":
        return rh.get_open_orders()
    if name == "cancel_order":
        return rh.cancel_order(inputs["order_id"])
    if name == "get_trade_journal":
        block = journal.context_block()
        block["recent_trades"] = journal.recent_trades(int(inputs.get("recent_n", 10)))
        return block

    if name == "get_regime":
        spy_ind = _fetch_indicators("SPY")
        qqq_ind = _fetch_indicators("QQQ")
        out = signals.regime_score(spy_ind, qqq_ind)
        out["spy"] = {k: spy_ind.get(k) for k in ("trend", "rsi14", "ret_5d_pct", "above_vwap", "realized_vol20_pct")}
        out["qqq"] = {k: qqq_ind.get(k) for k in ("trend", "rsi14", "ret_5d_pct", "above_vwap", "realized_vol20_pct")}
        return out

    if name == "get_signals":
        symbols = [s.upper() for s in inputs.get("symbols", [])][:6]
        if not symbols:
            return {"error": "Provide 1-6 symbols."}
        portfolio = rh.get_portfolio_summary()
        equity = portfolio["equity"]
        spy_daily = rh.get_stock_historicals("SPY", interval="day", span="year")
        spy_closes = [b["close"] for b in spy_daily]
        table = {}
        for sym in symbols:
            try:
                ind = _fetch_indicators(sym)
                closes = None  # relative strength needs the symbol's own closes
                daily = rh.get_stock_historicals(sym, interval="day", span="year")
                closes = [b["close"] for b in daily]
                ind["rel_strength_5d_vs_spy"] = signals.relative_strength(closes, spy_closes, 5)
                quote = rh.get_stock_quote(sym)
                ind["spread_pct"] = quote.get("spread_pct")
                ind["trading_halted"] = quote.get("trading_halted")
                ref_price = quote.get("ask_price") or ind.get("last_close") or 0
                stop = signals.suggest_stop(ref_price, ind.get("atr14")) if ref_price else None
                ind["suggested_stop"] = stop
                if stop and ref_price:
                    ind["qty_for_risk_budget"] = signals.position_size(
                        equity, risk.risk_per_trade_pct, ref_price, stop)
                ind["in_cooldown"] = journal.in_cooldown(sym)
                table[sym] = ind
            except Exception as exc:
                table[sym] = {"error": str(exc)}
        return {"equity": equity, "risk_per_trade_pct": risk.risk_per_trade_pct, "signals": table}

    if name == "update_exit_plan":
        ok, msg = journal.update_plan(
            inputs["symbol"].upper(),
            stop=inputs.get("stop"),
            target=inputs.get("target"),
            reason=inputs.get("reason", ""),
        )
        return {"ok": ok, "message": msg} if ok else {"error": msg}

    # ── Trading tools: session guard, then risk checks ───────────────────────
    reason = _session_guard(name, exec_cfg)
    if reason:
        return {"error": f"Execution guard: {reason}"}

    portfolio = rh.get_portfolio_summary()
    equity = portfolio["equity"]
    cash = portfolio["cash"]

    if risk.is_daily_loss_limit_breached(equity):
        return {"error": "Daily loss limit breached — trading halted for today."}

    stock_positions = rh.get_stock_positions()
    crypto_positions = rh.get_crypto_positions()
    options_positions = rh.get_options_positions()
    deployed = sum(p["market_value"] for p in stock_positions + crypto_positions + options_positions)

    if name == "buy_stock":
        symbol = inputs["symbol"].upper()
        quantity = float(inputs["quantity"])
        stop = float(inputs["stop"])
        target = float(inputs["target"])

        if journal.in_cooldown(symbol):
            return {"error": f"{symbol} was stopped out today — no same-day re-entry (cooldown)."}
        if journal.entries_today() >= risk.max_new_entries_per_day:
            return {"error": f"Entry throttle: already {journal.entries_today()} new entries today "
                             f"(max {risk.max_new_entries_per_day})."}
        if journal.consecutive_losses_today() >= risk.loss_streak_halt:
            return {"error": f"Loss-streak halt: {journal.consecutive_losses_today()} consecutive "
                             "losing exits today — no new entries until tomorrow."}

        quote = rh.get_stock_quote(symbol)
        if not quote or not (quote.get("ask_price") or quote.get("last_trade_price")):
            return {"error": f"Could not get a live quote for {symbol}"}
        if quote.get("trading_halted"):
            return {"error": f"{symbol} is halted — no order sent."}
        spread = quote.get("spread_pct")
        if spread is not None and spread > max_spread_pct:
            return {"error": (
                f"Execution guard: {symbol} spread {spread:.2f}% exceeds the {max_spread_pct}% cap — "
                "entry skipped to avoid a bad fill."
            )}

        limit_price = inputs.get("limit_price") or _marketable_limit(quote, "buy", slippage_pct)
        if not limit_price:
            return {"error": f"Could not derive a limit price for {symbol}"}
        if not (stop < limit_price < target):
            return {"error": (
                f"Bracket sanity failed: need stop (${stop:.2f}) < entry (${limit_price:.2f}) < "
                f"target (${target:.2f})."
            )}

        ok, msg = risk.validate_trade_risk(quantity, limit_price, stop, equity)
        if not ok:
            return {"error": f"Risk-budget check failed: {msg}"}

        current_pos = next((p["market_value"] for p in stock_positions if p["symbol"] == symbol), 0.0)
        ok, msg = risk.validate_stock_buy(symbol, quantity, limit_price, equity, cash, deployed, current_pos)
        if not ok:
            return {"error": f"Risk check failed: {msg}"}

        logger.info("BUY %s x%.4f @ limit $%.2f (stop $%.2f / target $%.2f) | %s",
                    symbol, quantity, limit_price, stop, target, inputs.get("rationale", ""))
        result = rh.buy_stock(symbol, quantity, order_type="limit", limit_price=limit_price)
        if not result.get("error"):
            plan = journal.record_entry(symbol, quantity, limit_price, stop, target,
                                        inputs.get("rationale", ""))
            result["journaled_plan"] = plan
        return result

    if name == "sell_stock":
        symbol = inputs["symbol"].upper()
        quantity = float(inputs["quantity"])
        exit_reason = inputs.get("exit_reason", "discretionary")

        pos = next((p for p in stock_positions if p["symbol"] == symbol), None)
        if not pos:
            return {"error": f"No open position in {symbol}"}
        if quantity > pos["quantity"]:
            return {"error": f"Requested to sell {quantity} but only hold {pos['quantity']} shares of {symbol}"}

        quote = rh.get_stock_quote(symbol)
        limit_price = inputs.get("limit_price") or _marketable_limit(quote, "sell", slippage_pct)
        if not limit_price:
            return {"error": f"Could not derive a limit price for {symbol}"}

        logger.info("SELL %s x%.4f @ limit $%.2f (%s) | %s", symbol, quantity, limit_price,
                    exit_reason, inputs.get("rationale", ""))
        result = rh.sell_stock(symbol, quantity, order_type="limit", limit_price=limit_price)
        if not result.get("error"):
            trade = journal.record_exit(symbol, quantity, limit_price, exit_reason)
            result["journaled_trade"] = trade
        return result

    if name == "buy_crypto":
        symbol = inputs["symbol"].upper()
        amount = float(inputs["amount_dollars"])

        current_pos = next((p["market_value"] for p in crypto_positions if p["symbol"] == symbol), 0.0)
        ok, msg = risk.validate_crypto_buy(symbol, amount, equity, cash, deployed, current_pos)
        if not ok:
            return {"error": f"Risk check failed: {msg}"}

        logger.info("BUY CRYPTO %s $%.2f | %s", symbol, amount, inputs.get("rationale", ""))
        return rh.buy_crypto(symbol, amount)

    if name == "sell_crypto":
        symbol = inputs["symbol"].upper()
        amount = float(inputs["amount_dollars"])

        pos = next((p for p in crypto_positions if p["symbol"] == symbol), None)
        if not pos:
            return {"error": f"No open crypto position in {symbol}"}
        if amount > pos["market_value"] * 1.01:
            return {"error": f"Requested to sell ${amount:.2f} but position worth ${pos['market_value']:.2f}"}

        logger.info("SELL CRYPTO %s $%.2f | %s", symbol, amount, inputs.get("rationale", ""))
        return rh.sell_crypto(symbol, amount)

    if name == "buy_option":
        option_id = inputs["option_id"]
        contracts = int(inputs["contracts"])
        limit_price = float(inputs["limit_price"])

        max_contracts = options_cfg.get("max_contracts", 10)
        ok, msg = risk.validate_option_buy(
            "option", contracts, limit_price, equity, cash, deployed, max_contracts
        )
        if not ok:
            return {"error": f"Risk check failed: {msg}"}

        logger.info("BUY OPTION id=%s x%d @ $%.2f | %s",
                    option_id, contracts, limit_price, inputs.get("rationale", ""))
        return rh.buy_option(option_id, contracts, limit_price=limit_price)

    if name == "sell_option":
        option_id = inputs["option_id"]
        contracts = int(inputs["contracts"])
        limit_price = float(inputs["limit_price"])

        pos = next((p for p in options_positions if p["option_id"] == option_id), None)
        if not pos:
            return {"error": f"No open position for option_id={option_id}"}
        if contracts > pos["quantity"]:
            return {"error": f"Requested to sell {contracts} contracts but only hold {pos['quantity']}"}

        logger.info("SELL OPTION id=%s x%d @ $%.2f | %s", option_id, contracts, limit_price,
                    inputs.get("rationale", ""))
        return rh.sell_option(option_id, contracts, limit_price=limit_price)

    return {"error": f"Unknown tool: {name}"}


class TradingAgent:
    def __init__(self, config: dict, risk: RiskManager, journal: Optional[TradeJournal] = None):
        self.cfg = config
        self.risk = risk
        self.journal = journal or TradeJournal(config.get("journal_path", "trader_journal.json"))
        agent_cfg = config.get("agent", {})
        exec_cfg = config.get("execution", {})
        options_cfg = config.get("options", {})
        leveraged_cfg = config.get("leveraged", {})
        self.model = agent_cfg.get("model", "claude-opus-4-8")
        self.effort = agent_cfg.get("effort", "high")

        playbook = _PLAYBOOK_TEMPLATE.format(
            max_spread_pct=exec_cfg.get("max_spread_pct", 1.0),
            slippage_pct=config.get("limit_order_slippage_pct", 0.3),
            avoid_open_minutes=exec_cfg.get("avoid_open_minutes", 15),
            avoid_close_minutes=exec_cfg.get("avoid_close_minutes", 5),
            leveraged_symbols=", ".join(leveraged_cfg.get("symbols", [])) or "none held",
            leveraged_stop=leveraged_cfg.get("stop_loss_pct", 5.0),
            leveraged_target=leveraged_cfg.get("take_profit_pct", 10.0),
            risk_per_trade_pct=risk.risk_per_trade_pct,
            max_new_entries_per_day=risk.max_new_entries_per_day,
            loss_streak_halt=risk.loss_streak_halt,
            max_position_pct=risk.max_position_pct,
            max_portfolio_risk_pct=risk.max_portfolio_risk_pct,
            min_cash_reserve_pct=risk.min_cash_reserve_pct,
            max_daily_loss_pct=risk.max_daily_loss_pct,
        )
        extra = (agent_cfg.get("system_context") or "").strip()
        self.system = playbook + (f"\nOWNER'S ADDITIONAL GUIDANCE:\n{extra}\n" if extra else "")
        self.client = anthropic.Anthropic()

    def run_cycle(self, watchlist_context: str = "") -> str:
        tools = _make_tools(self.risk, self.cfg)
        journal_snapshot = json.dumps(self.journal.context_block(), default=str)
        messages: list[dict] = [
            {
                "role": "user",
                "content": (
                    "Run one full trading cycle now. Phase order is mandatory: enforce journaled "
                    "plans first (stops/targets/trails), then regime, then signal-driven entries "
                    "only where the regime and throttles allow, then journal. Finish with a concise "
                    "summary of every action and the watch points for next cycle.\n\n"
                    f"JOURNAL SNAPSHOT: {journal_snapshot}"
                    + (f"\n\nCycle context: {watchlist_context}" if watchlist_context else "")
                ),
            }
        ]

        logger.info("Starting agent cycle (model=%s, effort=%s)", self.model, self.effort)

        while True:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=16000,
                thinking={"type": "adaptive"},
                output_config={"effort": self.effort},
                system=self.system,
                tools=tools,
                messages=messages,
            )

            logger.debug("Agent response: stop_reason=%s, content_blocks=%d",
                         response.stop_reason, len(response.content))

            if response.stop_reason == "end_turn":
                summary = " ".join(
                    block.text for block in response.content
                    if hasattr(block, "text") and block.type == "text"
                )
                logger.info("Agent cycle complete: %s", summary[:200])
                return summary

            if response.stop_reason != "tool_use":
                logger.warning("Unexpected stop_reason: %s", response.stop_reason)
                break

            messages.append({"role": "assistant", "content": response.content})

            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                logger.info("Tool call: %s(%s)", block.name,
                            json.dumps(block.input, separators=(",", ":")))
                try:
                    result = _execute_tool(block.name, block.input, self.risk, self.cfg, self.journal)
                except Exception as exc:
                    logger.exception("Tool %s raised exception", block.name)
                    result = {"error": str(exc)}

                logger.info("Tool result: %s", json.dumps(result, default=str)[:300])
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result, default=str),
                })

            messages.append({"role": "user", "content": tool_results})

        return "Agent cycle ended unexpectedly."
