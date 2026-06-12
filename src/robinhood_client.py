"""Robinhood API wrapper using robin_stocks."""

import logging
import os
import time
from datetime import datetime, timezone
from typing import Optional

import pyotp
import robin_stocks.robinhood as rh

logger = logging.getLogger(__name__)


def _retry(fn, *args, attempts: int = 3, backoff: float = 1.0, **kwargs):
    """Retry transient failures on READ calls only — never wrap order placement
    (replays of non-idempotent writes can double-trade)."""
    last_exc = None
    for attempt in range(attempts):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            last_exc = exc
            if attempt < attempts - 1:
                sleep_s = backoff * (2 ** attempt)
                logger.warning("Transient API failure in %s (attempt %d/%d): %s — retrying in %.1fs",
                               getattr(fn, "__name__", fn), attempt + 1, attempts, exc, sleep_s)
                time.sleep(sleep_s)
    raise last_exc


def login() -> None:
    username = os.environ["ROBINHOOD_USERNAME"]
    password = os.environ["ROBINHOOD_PASSWORD"]
    totp_secret = os.environ.get("ROBINHOOD_TOTP_SECRET")

    mfa_code = pyotp.TOTP(totp_secret).now() if totp_secret else None
    rh.login(username, password, mfa_code=mfa_code, store_session=True)


def logout() -> None:
    rh.logout()


# ── Market session ────────────────────────────────────────────────────────────

def get_market_session(market: str = "XNYS") -> dict:
    """Live market session from the exchange calendar (holidays included).

    Returns session = 'pre' | 'regular' | 'after' | 'closed', plus
    minutes_since_open / minutes_to_close while the regular session is running.
    """
    hours = rh.get_market_today_hours(market) or {}
    now = datetime.now(timezone.utc)
    result = {
        "now": now.isoformat(),
        "is_trading_day": bool(hours.get("is_open")),
        "opens_at": hours.get("opens_at"),
        "closes_at": hours.get("closes_at"),
        "session": "closed",
    }
    if not result["is_trading_day"] or not result["opens_at"] or not result["closes_at"]:
        return result

    opens = datetime.fromisoformat(result["opens_at"].replace("Z", "+00:00"))
    closes = datetime.fromisoformat(result["closes_at"].replace("Z", "+00:00"))
    if now < opens:
        result["session"] = "pre"
    elif now <= closes:
        result["session"] = "regular"
        result["minutes_since_open"] = (now - opens).total_seconds() / 60
        result["minutes_to_close"] = (closes - now).total_seconds() / 60
    else:
        result["session"] = "after"
    return result


# ── Portfolio ─────────────────────────────────────────────────────────────────

def get_portfolio_summary() -> dict:
    profile = rh.load_portfolio_profile()
    account = rh.load_account_profile()
    equity = float(profile.get("equity") or 0)
    prev_close = float(profile.get("equity_previous_close") or 0)
    return {
        "equity": equity,
        "cash": float(account.get("cash") or 0),
        "buying_power": float(account.get("buying_power") or 0),
        "unsettled_funds": float(account.get("unsettled_funds") or 0),
        "day_return_pct": ((equity - prev_close) / prev_close * 100) if prev_close else 0.0,
    }


def get_stock_positions() -> list[dict]:
    positions = _retry(rh.get_open_stock_positions)
    enriched = []
    for p in positions:
        instrument_url = p.get("instrument")
        symbol = rh.get_symbol_by_url(instrument_url) if instrument_url else "UNKNOWN"
        enriched.append((symbol, p))

    # One batched quote call instead of N round-trips
    prices: dict[str, float] = {}
    symbols = [s for s, _ in enriched if s != "UNKNOWN"]
    if symbols:
        try:
            quotes = _retry(rh.get_quotes, symbols) or []
            for q in quotes:
                if q and q.get("symbol"):
                    prices[q["symbol"]] = float(q.get("last_trade_price") or 0)
        except Exception as exc:
            logger.warning("Batch quote lookup failed (%s); falling back to cost basis", exc)

    result = []
    for symbol, p in enriched:
        qty = float(p.get("quantity") or 0)
        avg_buy = float(p.get("average_buy_price") or 0)
        current_price = prices.get(symbol) or avg_buy
        result.append({
            "symbol": symbol,
            "quantity": qty,
            "average_buy_price": avg_buy,
            "current_price": current_price,
            "market_value": qty * current_price,
            "unrealized_pnl": (current_price - avg_buy) * qty,
            "unrealized_pnl_pct": ((current_price - avg_buy) / avg_buy * 100) if avg_buy else 0,
        })
    return result


def get_crypto_positions() -> list[dict]:
    positions = rh.get_crypto_positions()
    result = []
    for p in positions:
        currency = p.get("currency", {})
        code = currency.get("code", "UNKNOWN")
        qty = float(p.get("quantity") or 0)
        cost_basis = float(p.get("cost_bases", [{}])[0].get("direct_cost_basis") or 0)
        avg_buy = cost_basis / qty if qty else 0
        quote = rh.get_crypto_quote(code)
        current_price = float(quote.get("mark_price") or avg_buy) if quote else avg_buy
        result.append({
            "symbol": code,
            "quantity": qty,
            "average_buy_price": avg_buy,
            "current_price": current_price,
            "market_value": qty * current_price,
            "unrealized_pnl": (current_price - avg_buy) * qty,
            "unrealized_pnl_pct": ((current_price - avg_buy) / avg_buy * 100) if avg_buy else 0,
        })
    return [p for p in result if p["quantity"] > 0]


def get_options_positions() -> list[dict]:
    positions = rh.get_open_option_positions()
    result = []
    for p in positions:
        option_id = p.get("option_id") or (p.get("option") or "").rstrip("/").split("/")[-1]
        details = rh.get_option_instrument_data_by_id(option_id) if option_id else {}
        qty = float(p.get("quantity") or 0)
        avg_buy = float(p.get("average_price") or 0) / 100  # API reports per-contract notional
        market = rh.get_option_market_data_by_id(option_id) if option_id else None
        if isinstance(market, list):
            market = market[0] if market else {}
        current_price = float((market or {}).get("adjusted_mark_price") or 0) or avg_buy
        result.append({
            "symbol": (details or {}).get("chain_symbol", "UNKNOWN"),
            "option_id": option_id,
            "option_type": (details or {}).get("type", "unknown"),
            "strike_price": float((details or {}).get("strike_price") or 0),
            "expiration_date": (details or {}).get("expiration_date", ""),
            "quantity": qty,
            "average_buy_price": avg_buy,
            "current_price": current_price,
            "market_value": qty * current_price * 100,
            "unrealized_pnl": (current_price - avg_buy) * qty * 100,
        })
    return result


# ── Quotes ────────────────────────────────────────────────────────────────────

def get_stock_quote(symbol: str) -> dict:
    quote = rh.get_quotes(symbol)[0]
    if not quote:
        return {}
    bid = float(quote.get("bid_price") or 0)
    ask = float(quote.get("ask_price") or 0)
    mid = (bid + ask) / 2 if bid and ask else 0
    return {
        "symbol": symbol,
        "ask_price": ask,
        "bid_price": bid,
        "spread_pct": ((ask - bid) / mid * 100) if mid else None,
        "last_trade_price": float(quote.get("last_trade_price") or 0),
        "last_extended_hours_trade_price": float(quote.get("last_extended_hours_trade_price") or 0) or None,
        "previous_close": float(quote.get("previous_close") or 0),
        "change_pct": (
            (float(quote.get("last_trade_price") or 0) - float(quote.get("previous_close") or 0))
            / float(quote.get("previous_close") or 1) * 100
        ),
        "trading_halted": quote.get("trading_halted", False),
    }


def get_crypto_quote(symbol: str) -> dict:
    quote = rh.get_crypto_quote(symbol)
    if not quote:
        return {}
    mark = float(quote.get("mark_price") or 0)
    ask = float(quote.get("ask_price") or mark)
    bid = float(quote.get("bid_price") or mark)
    return {
        "symbol": symbol,
        "mark_price": mark,
        "ask_price": ask,
        "bid_price": bid,
        "high_price": float(quote.get("high_price") or 0),
        "low_price": float(quote.get("low_price") or 0),
        "open_price": float(quote.get("open_price") or 0),
        "change_pct": ((mark - float(quote.get("open_price") or mark)) / float(quote.get("open_price") or 1) * 100),
    }


def get_options_chain(symbol: str, expiration_date: Optional[str] = None,
                      option_type: Optional[str] = None) -> list[dict]:
    chains = rh.find_options_by_expiration(
        symbol,
        expirationDate=expiration_date,
        optionType=option_type,
    )
    result = []
    for opt in (chains or []):
        result.append({
            "symbol": symbol,
            "option_id": opt.get("id"),
            "option_type": opt.get("type"),
            "strike_price": float(opt.get("strike_price") or 0),
            "expiration_date": opt.get("expiration_date"),
            "ask_price": float(opt.get("ask_price") or 0),
            "bid_price": float(opt.get("bid_price") or 0),
            "mark_price": float(opt.get("adjusted_mark_price") or 0),
            "delta": float(opt.get("delta") or 0),
            "gamma": float(opt.get("gamma") or 0),
            "theta": float(opt.get("theta") or 0),
            "implied_volatility": float(opt.get("implied_volatility") or 0),
            "volume": int(opt.get("volume") or 0),
            "open_interest": int(opt.get("open_interest") or 0),
        })
    return result


def get_stock_historicals(symbol: str, interval: str = "5minute",
                           span: str = "day") -> list[dict]:
    data = rh.get_stock_historicals(symbol, interval=interval, span=span)
    result = []
    for bar in (data or []):
        result.append({
            "begins_at": bar.get("begins_at"),
            "open": float(bar.get("open_price") or 0),
            "high": float(bar.get("high_price") or 0),
            "low": float(bar.get("low_price") or 0),
            "close": float(bar.get("close_price") or 0),
            "volume": int(bar.get("volume") or 0),
        })
    return result


def get_crypto_historicals(symbol: str, interval: str = "5minute",
                            span: str = "day") -> list[dict]:
    data = rh.get_crypto_historicals(symbol, interval=interval, span=span)
    result = []
    for bar in (data or []):
        result.append({
            "begins_at": bar.get("begins_at"),
            "open": float(bar.get("open_price") or 0),
            "high": float(bar.get("high_price") or 0),
            "low": float(bar.get("low_price") or 0),
            "close": float(bar.get("close_price") or 0),
            "volume": int(bar.get("volume") or 0),
        })
    return result


# ── Orders ────────────────────────────────────────────────────────────────────

def buy_stock(symbol: str, quantity: float, order_type: str = "limit",
              limit_price: Optional[float] = None) -> dict:
    if order_type == "limit" and limit_price:
        order = rh.order_buy_limit(symbol, quantity, limit_price)
    else:
        order = rh.order_buy_market(symbol, quantity)
    return _parse_order(order)


def sell_stock(symbol: str, quantity: float, order_type: str = "limit",
               limit_price: Optional[float] = None) -> dict:
    if order_type == "limit" and limit_price:
        order = rh.order_sell_limit(symbol, quantity, limit_price)
    else:
        order = rh.order_sell_market(symbol, quantity)
    return _parse_order(order)


def buy_crypto(symbol: str, amount_in_dollars: float) -> dict:
    order = rh.order_buy_crypto_by_price(symbol, amount_in_dollars)
    return _parse_order(order)


def sell_crypto(symbol: str, amount_in_dollars: float) -> dict:
    order = rh.order_sell_crypto_by_price(symbol, amount_in_dollars)
    return _parse_order(order)


def buy_option(option_id: str, quantity: int, limit_price: float) -> dict:
    """Options orders are always limit-priced; market orders on options are never sent."""
    order = rh.order_buy_option_limit("open", "debit", limit_price, option_id, quantity)
    return _parse_order(order)


def sell_option(option_id: str, quantity: int, limit_price: float) -> dict:
    order = rh.order_sell_option_limit("close", "credit", limit_price, option_id, quantity)
    return _parse_order(order)


def cancel_order(order_id: str) -> dict:
    result = rh.cancel_stock_order(order_id)
    return result or {"status": "cancelled", "order_id": order_id}


def get_order_status(order_id: str) -> dict:
    """Current state of a single order (state, filled qty, average fill price)."""
    order = _retry(rh.get_stock_order_info, order_id)
    parsed = _parse_order(order)
    if order:
        parsed["average_price"] = float(order.get("average_price") or 0) or None
        parsed["cumulative_quantity"] = float(order.get("cumulative_quantity") or 0)
    return parsed


def wait_for_fill(order_id: str, timeout_s: float = 10.0, poll_s: float = 1.5) -> dict:
    """Poll an order until it reaches a terminal state or the timeout lapses.
    Returns the last status; caller decides whether to cancel a non-filled order."""
    deadline = time.monotonic() + timeout_s
    status = get_order_status(order_id)
    while time.monotonic() < deadline:
        if status.get("state") in ("filled", "cancelled", "rejected", "failed"):
            return status
        time.sleep(poll_s)
        status = get_order_status(order_id)
    return status


def cancel_stale_orders(max_age_minutes: float = 15.0) -> list[dict]:
    """Cancel open stock orders older than max_age_minutes. A resting marketable
    limit that hasn't filled is stale information — reprice it, don't let it lurk."""
    cancelled = []
    now = datetime.now(timezone.utc)
    for o in _retry(rh.get_all_open_stock_orders) or []:
        created = o.get("created_at")
        try:
            age_min = (now - datetime.fromisoformat(created.replace("Z", "+00:00"))).total_seconds() / 60
        except (ValueError, AttributeError):
            continue
        if age_min >= max_age_minutes:
            order_id = o.get("id")
            logger.info("Cancelling stale order %s (age %.0f min)", order_id, age_min)
            rh.cancel_stock_order(order_id)
            cancelled.append({"order_id": order_id, "age_minutes": round(age_min, 1)})
    return cancelled


def get_open_orders() -> list[dict]:
    orders = _retry(rh.get_all_open_stock_orders)
    return [_parse_order(o) for o in (orders or [])]


def _parse_order(order: Optional[dict]) -> dict:
    if not order:
        return {"error": "Order placement returned no response"}
    return {
        "order_id": order.get("id"),
        "state": order.get("state"),
        "symbol": order.get("symbol") or order.get("chain_symbol"),
        "side": order.get("side"),
        "order_type": order.get("type"),
        "quantity": order.get("quantity"),
        "price": order.get("price") or order.get("average_price"),
        "created_at": order.get("created_at"),
    }
