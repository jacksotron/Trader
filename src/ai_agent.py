"""Claude-powered trading agent with full tool use loop."""

import json
import logging
from typing import Any

import anthropic

from . import robinhood_client as rh
from .risk_manager import RiskManager

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are an autonomous AI trading agent operating a live Robinhood account. Your job is to
analyze the current portfolio, market data, and opportunities, then execute trades that will
grow the portfolio. You have access to real-time quotes, price history, options chains, and
the current portfolio state.

Trading philosophy:
- Preserve capital first. Never risk more than you can afford to lose on any single trade.
- Seek asymmetric risk/reward. Options can provide leveraged upside with defined risk.
- Be patient. A good trade not taken is better than a bad trade executed.
- React to momentum and news. Short-term price action matters for near-term trades.
- Always check your portfolio state before trading to avoid over-concentration.

You MUST obey risk limits enforced by the system. The risk manager will reject trades that
violate position sizing or daily loss rules — so check available capital before deciding.

Workflow:
1. Call get_portfolio_summary to understand current equity, cash, and buying power.
2. Call get_stock_positions, get_crypto_positions, and get_options_positions to see holdings.
3. For assets on the watchlist, call get_stock_quote / get_crypto_quote to check prices.
4. Pull recent price history with get_stock_historicals / get_crypto_historicals for trends.
5. For options opportunities, call get_options_chain to find the right contracts.
6. Make your trading decisions and call the appropriate buy/sell/option functions.
7. After all trades, call get_portfolio_summary again to confirm the new state.
"""


def _make_tools(risk: RiskManager, cfg: dict) -> list[dict]:
    options_cfg = cfg.get("options", {})
    assets_cfg = cfg.get("assets", {})

    tools = [
        {
            "name": "get_portfolio_summary",
            "description": "Returns overall portfolio equity, cash, buying power, and day return.",
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
            "description": "Returns the current bid/ask/last price and daily change % for a stock symbol.",
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
            "description": "Returns OHLCV bars for a stock. Use for trend analysis.",
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
                    "Buy shares of a stock. Specify quantity (number of shares). "
                    "Risk limits are enforced — the system will reject the order if limits are breached."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "symbol": {"type": "string"},
                        "quantity": {"type": "number", "description": "Number of shares to buy"},
                        "order_type": {
                            "type": "string",
                            "enum": ["market", "limit"],
                            "description": "Order type. Default: market",
                        },
                        "limit_price": {
                            "type": "number",
                            "description": "Limit price (only used if order_type is limit)",
                        },
                        "rationale": {
                            "type": "string",
                            "description": "Brief reason for this trade (for logging)",
                        },
                    },
                    "required": ["symbol", "quantity"],
                },
            },
            {
                "name": "sell_stock",
                "description": "Sell shares of a stock you currently hold.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "symbol": {"type": "string"},
                        "quantity": {"type": "number"},
                        "order_type": {"type": "string", "enum": ["market", "limit"]},
                        "limit_price": {"type": "number"},
                        "rationale": {"type": "string"},
                    },
                    "required": ["symbol", "quantity"],
                },
            },
        ]

    if assets_cfg.get("crypto", True):
        tools += [
            {
                "name": "buy_crypto",
                "description": (
                    "Buy a cryptocurrency by dollar amount. Crypto trades 24/7. "
                    "Risk limits are enforced."
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
                    "required": ["symbol", "amount_dollars"],
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
                    "required": ["symbol", "amount_dollars"],
                },
            },
        ]

    if assets_cfg.get("options", True):
        tools += [
            {
                "name": "buy_option",
                "description": (
                    "Buy option contracts (calls or puts). You must first look up the option_id "
                    "from get_options_chain. Each contract covers 100 shares. "
                    f"Max delta allowed: {options_cfg.get('max_delta', 0.70)}, "
                    f"DTE range: {options_cfg.get('min_dte', 7)}-{options_cfg.get('max_dte', 45)} days."
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
                            "description": f"Number of contracts (max {options_cfg.get('max_contracts', 5)})",
                        },
                        "limit_price": {
                            "type": "number",
                            "description": "Per-contract limit price. Recommended to avoid bad fills.",
                        },
                        "rationale": {"type": "string"},
                    },
                    "required": ["option_id", "contracts"],
                },
            },
            {
                "name": "sell_option",
                "description": "Sell/close option contracts you currently hold.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "option_id": {"type": "string"},
                        "contracts": {"type": "integer"},
                        "limit_price": {"type": "number"},
                        "rationale": {"type": "string"},
                    },
                    "required": ["option_id", "contracts"],
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


def _execute_tool(
    name: str,
    inputs: dict,
    risk: RiskManager,
    cfg: dict,
) -> Any:
    options_cfg = cfg.get("options", {})

    # ── Read-only tools ──────────────────────────────────────────────────────
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

    # ── Trading tools (risk-checked) ─────────────────────────────────────────
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
        order_type = inputs.get("order_type", "market")
        limit_price = inputs.get("limit_price")

        quote = rh.get_stock_quote(symbol)
        price = limit_price or quote.get("last_trade_price", 0)
        if not price:
            return {"error": f"Could not get price for {symbol}"}

        current_pos = next((p["market_value"] for p in stock_positions if p["symbol"] == symbol), 0.0)
        ok, msg = risk.validate_stock_buy(symbol, quantity, price, equity, cash, deployed, current_pos)
        if not ok:
            return {"error": f"Risk check failed: {msg}"}

        logger.info("BUY %s x%.2f @ $%.2f | %s", symbol, quantity, price, inputs.get("rationale", ""))
        return rh.buy_stock(symbol, quantity, order_type=order_type, limit_price=limit_price)

    if name == "sell_stock":
        symbol = inputs["symbol"].upper()
        quantity = float(inputs["quantity"])
        order_type = inputs.get("order_type", "market")
        limit_price = inputs.get("limit_price")

        pos = next((p for p in stock_positions if p["symbol"] == symbol), None)
        if not pos:
            return {"error": f"No open position in {symbol}"}
        if quantity > pos["quantity"]:
            return {"error": f"Requested to sell {quantity} but only hold {pos['quantity']} shares of {symbol}"}

        logger.info("SELL %s x%.2f | %s", symbol, quantity, inputs.get("rationale", ""))
        return rh.sell_stock(symbol, quantity, order_type=order_type, limit_price=limit_price)

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
        limit_price = inputs.get("limit_price")

        max_contracts = options_cfg.get("max_contracts", 5)
        premium = limit_price or 1.0  # fallback — validate_option_buy will catch overspend
        ok, msg = risk.validate_option_buy(
            "option", contracts, premium, equity, cash, deployed, max_contracts
        )
        if not ok:
            return {"error": f"Risk check failed: {msg}"}

        logger.info("BUY OPTION id=%s x%d @ $%.2f | %s",
                    option_id, contracts, limit_price or 0, inputs.get("rationale", ""))
        return rh.buy_option(option_id, contracts, limit_price=limit_price)

    if name == "sell_option":
        option_id = inputs["option_id"]
        contracts = int(inputs["contracts"])
        limit_price = inputs.get("limit_price")

        pos = next((p for p in options_positions if p["option_id"] == option_id), None)
        if not pos:
            return {"error": f"No open position for option_id={option_id}"}
        if contracts > pos["quantity"]:
            return {"error": f"Requested to sell {contracts} contracts but only hold {pos['quantity']}"}

        logger.info("SELL OPTION id=%s x%d | %s", option_id, contracts, inputs.get("rationale", ""))
        return rh.sell_option(option_id, contracts, limit_price=limit_price)

    if name == "cancel_order":
        return rh.cancel_order(inputs["order_id"])

    return {"error": f"Unknown tool: {name}"}


class TradingAgent:
    def __init__(self, config: dict, risk: RiskManager):
        self.cfg = config
        self.risk = risk
        agent_cfg = config.get("agent", {})
        self.model = agent_cfg.get("model", "claude-opus-4-8")
        self.effort = agent_cfg.get("effort", "high")
        self.system = agent_cfg.get("system_context", "") or _SYSTEM_PROMPT
        self.client = anthropic.Anthropic()

    def run_cycle(self, watchlist_context: str = "") -> str:
        tools = _make_tools(self.risk, self.cfg)
        messages: list[dict] = [
            {
                "role": "user",
                "content": (
                    "Please analyze the portfolio and current market conditions, then execute any "
                    "trades you deem appropriate based on the available data. Use your tools to "
                    "gather information before trading. After trading, summarize what you did and why."
                    + (f"\n\nAdditional context: {watchlist_context}" if watchlist_context else "")
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
                # Extract the final text summary
                summary = " ".join(
                    block.text for block in response.content
                    if hasattr(block, "text") and block.type == "text"
                )
                logger.info("Agent cycle complete: %s", summary[:200])
                return summary

            if response.stop_reason != "tool_use":
                logger.warning("Unexpected stop_reason: %s", response.stop_reason)
                break

            # Append assistant message to conversation
            messages.append({"role": "assistant", "content": response.content})

            # Execute all tool calls and collect results
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
