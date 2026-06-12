"""Claude-powered trading agent with full tool use loop.

The agent follows a strict playbook (review -> regime -> select -> execute ->
journal) and every order passes through hard execution guards: regular-session
only, opening/closing auction avoidance, spread caps, and marketable-limit
pricing. The RiskManager separately enforces sizing and the daily-loss halt.
"""

import json
import logging
from typing import Any, Optional

import anthropic

from . import robinhood_client as rh
from .risk_manager import RiskManager

logger = logging.getLogger(__name__)

_PLAYBOOK_TEMPLATE = """\
You are a disciplined, systematic trader operating a live Robinhood account. Your edge is
process, not prediction: superior execution, ruthless risk control, and emotionless exits.
You never chase, never average down, and never trade just to trade.

PLAYBOOK — work through these phases in order, every cycle:

1. REVIEW (always first)
   - get_portfolio_summary, then every open position and open order.
   - For each position: is the thesis intact? If price is at or below its stop
     (entry minus {stop_loss_pct}%) or the setup is invalidated, EXIT NOW.
   - Leveraged ETFs ({leveraged_symbols}) run tighter: stop {leveraged_stop}%,
     scale out at +{leveraged_target}% — daily-reset decay punishes letting them drift.
   - At or beyond +{take_profit_pct}%: take at least half off, exit fully, or set a
     tighter mental trail — decide and act, don't drift.
   - Cancel any stale open order you no longer want.

2. REGIME (before adding any new risk)
   - Pull SPY and QQQ historicals (5minute/day and hour/week) to read the tape.
   - Strong, broad tape: full sizing. Mixed: half sizing. Risk-off (indices down
     sharply or breaking lower): no new longs — manage exits instead.

3. SELECT (only if regime allows)
   - Scan watchlist quotes; rank by momentum, volume, and strength relative to the index.
   - Skip anything quoted wider than {max_spread_pct}% bid/ask spread — bad fills
     compound forever.
   - Options (when enabled): {min_dte}-{max_dte} DTE, |delta| {min_delta}-{max_delta},
     liquid chains only (real volume and open interest), always limit-priced.

4. EXECUTE
   - Marketable limit orders only: buys priced at ask*(1+{slippage_pct}%), sells at
     bid*(1-{slippage_pct}%). Omit limit_price and the system computes it for you.
   - Regular session only — orders are blocked while the market is closed and are
     NEVER queued for the next open; opening-auction fills are uncontrolled.
   - No new entries in the first {avoid_open_minutes} minutes or final
     {avoid_close_minutes} minutes of the session. Exits are allowed all session.
   - Concentrate sizing in your best one or two ideas up to the per-position cap
     rather than spraying minimum-size positions everywhere.

5. JOURNAL
   - Every order's rationale must state thesis, entry, stop, target, and what would
     prove it wrong — one line each. The next cycle's REVIEW depends on it.

HARD LIMITS (enforced in code — a rejection is final, do not retry around it):
- Max {max_position_pct}% of equity in one position; max {max_portfolio_risk_pct}%
  deployed; keep {min_cash_reserve_pct}% cash; all trading halts at
  -{max_daily_loss_pct}% on the day.

Capital preservation outranks any single opportunity. Flat is a position. A good trade
not taken costs nothing; a bad fill is paid for forever.
"""


def _make_tools(risk: RiskManager, cfg: dict) -> list[dict]:
    options_cfg = cfg.get("options", {})
    assets_cfg = cfg.get("assets", {})

    tools = [
        {
            "name": "get_market_session",
            "description": (
                "Returns the live market session ('pre', 'regular', 'after', 'closed') from the "
                "exchange calendar, with minutes since open / to close during the regular session. "
                "Check before planning entries."
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
            "name": "get_stock_quote",
            "description": (
                "Returns current bid/ask/last, spread %, daily change %, and halt status for a stock. "
                "Always check the quote (and its spread) immediately before any order."
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
            "description": "Returns OHLCV bars for a stock. Use for trend and regime analysis.",
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
            "description": "Returns OHLCV bars for a crypto asset. Use for trend analysis.",
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
                    "Buy shares with a marketable limit order. Omit limit_price to have the system "
                    "price it at ask*(1+slippage cap) from the live quote — preferred. Blocked outside "
                    "the regular session, inside the open/close avoidance windows, on wide spreads, "
                    "and on risk-limit violations."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "symbol": {"type": "string"},
                        "quantity": {"type": "number", "description": "Number of shares to buy"},
                        "limit_price": {
                            "type": "number",
                            "description": "Optional explicit limit. Omit for an auto marketable limit.",
                        },
                        "rationale": {
                            "type": "string",
                            "description": "Thesis, entry, stop, target, invalidation — one line each.",
                        },
                    },
                    "required": ["symbol", "quantity", "rationale"],
                },
            },
            {
                "name": "sell_stock",
                "description": (
                    "Sell shares you hold with a marketable limit order (auto-priced at "
                    "bid*(1-slippage cap) when limit_price is omitted). Allowed any time during the "
                    "regular session — exits are never window-blocked."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "symbol": {"type": "string"},
                        "quantity": {"type": "number"},
                        "limit_price": {"type": "number"},
                        "rationale": {"type": "string", "description": "Why this exit, vs the original plan."},
                    },
                    "required": ["symbol", "quantity", "rationale"],
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
                        "amount_dollars": {
                            "type": "number",
                            "description": "Dollar amount to spend",
                        },
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
                    "Buy option contracts (calls or puts) with a REQUIRED per-contract limit price — "
                    "price at or inside the ask, never market. Look up option_id and the quote via "
                    "get_options_chain first. Each contract covers 100 shares. "
                    f"DTE {options_cfg.get('min_dte', 1)}-{options_cfg.get('max_dte', 45)}, "
                    f"|delta| {options_cfg.get('min_delta', 0.10)}-{options_cfg.get('max_delta', 0.90)}, "
                    f"max {options_cfg.get('max_contracts', 10)} contracts."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "option_id": {
                            "type": "string",
                            "description": "The option instrument ID from get_options_chain",
                        },
                        "contracts": {
                            "type": "integer",
                            "description": f"Number of contracts (max {options_cfg.get('max_contracts', 10)})",
                        },
                        "limit_price": {
                            "type": "number",
                            "description": "Per-contract limit price (required).",
                        },
                        "rationale": {"type": "string"},
                    },
                    "required": ["option_id", "contracts", "limit_price", "rationale"],
                },
            },
            {
                "name": "sell_option",
                "description": (
                    "Sell/close option contracts you hold, with a REQUIRED per-contract limit price "
                    "(at or inside the bid)."
                ),
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
            "properties": {
                "order_id": {"type": "string"},
            },
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
        # Fail closed for new risk, open for risk-reducing exits.
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


def _execute_tool(
    name: str,
    inputs: dict,
    risk: RiskManager,
    cfg: dict,
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

        current_pos = next((p["market_value"] for p in stock_positions if p["symbol"] == symbol), 0.0)
        ok, msg = risk.validate_stock_buy(symbol, quantity, limit_price, equity, cash, deployed, current_pos)
        if not ok:
            return {"error": f"Risk check failed: {msg}"}

        exits = risk.exit_levels(limit_price)
        logger.info("BUY %s x%.4f @ limit $%.2f (stop $%.2f / target $%.2f) | %s",
                    symbol, quantity, limit_price, exits["stop"], exits["target"],
                    inputs.get("rationale", ""))
        result = rh.buy_stock(symbol, quantity, order_type="limit", limit_price=limit_price)
        result["suggested_exits"] = exits
        return result

    if name == "sell_stock":
        symbol = inputs["symbol"].upper()
        quantity = float(inputs["quantity"])

        pos = next((p for p in stock_positions if p["symbol"] == symbol), None)
        if not pos:
            return {"error": f"No open position in {symbol}"}
        if quantity > pos["quantity"]:
            return {"error": f"Requested to sell {quantity} but only hold {pos['quantity']} shares of {symbol}"}

        quote = rh.get_stock_quote(symbol)
        limit_price = inputs.get("limit_price") or _marketable_limit(quote, "sell", slippage_pct)
        if not limit_price:
            return {"error": f"Could not derive a limit price for {symbol}"}

        logger.info("SELL %s x%.4f @ limit $%.2f | %s", symbol, quantity, limit_price,
                    inputs.get("rationale", ""))
        return rh.sell_stock(symbol, quantity, order_type="limit", limit_price=limit_price)

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
    def __init__(self, config: dict, risk: RiskManager):
        self.cfg = config
        self.risk = risk
        agent_cfg = config.get("agent", {})
        exec_cfg = config.get("execution", {})
        options_cfg = config.get("options", {})
        leveraged_cfg = config.get("leveraged", {})
        self.model = agent_cfg.get("model", "claude-opus-4-8")
        self.effort = agent_cfg.get("effort", "high")

        playbook = _PLAYBOOK_TEMPLATE.format(
            stop_loss_pct=risk.stop_loss_pct,
            take_profit_pct=risk.take_profit_pct,
            leveraged_symbols=", ".join(leveraged_cfg.get("symbols", [])) or "none held",
            leveraged_stop=leveraged_cfg.get("stop_loss_pct", 5.0),
            leveraged_target=leveraged_cfg.get("take_profit_pct", 10.0),
            max_spread_pct=exec_cfg.get("max_spread_pct", 1.0),
            slippage_pct=config.get("limit_order_slippage_pct", 0.3),
            avoid_open_minutes=exec_cfg.get("avoid_open_minutes", 15),
            avoid_close_minutes=exec_cfg.get("avoid_close_minutes", 5),
            min_dte=options_cfg.get("min_dte", 1),
            max_dte=options_cfg.get("max_dte", 45),
            min_delta=options_cfg.get("min_delta", 0.10),
            max_delta=options_cfg.get("max_delta", 0.90),
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
        messages: list[dict] = [
            {
                "role": "user",
                "content": (
                    "Run one full trading cycle now. Follow the playbook phases in order: review "
                    "positions and exits first, then regime, then new entries only where justified, "
                    "then journal. Gather data with tools before deciding; finish with a concise "
                    "summary of every action taken and why, plus the watch points for next cycle."
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
                    result = _execute_tool(block.name, block.input, self.risk, self.cfg)
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
