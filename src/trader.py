"""Main trading loop — market-session aware, scheduled, fully autonomous."""

import logging
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import schedule

from . import robinhood_client as rh
from .ai_agent import TradingAgent
from .risk_manager import RiskManager

logger = logging.getLogger(__name__)

ET = ZoneInfo("America/New_York")


class Trader:
    def __init__(self, config: dict):
        trading_cfg = config.get("trading", {})
        self.trading_cfg = trading_cfg
        self.interval_minutes = trading_cfg.get("interval_minutes", 30)
        self.market_hours = trading_cfg.get("market_hours", {"open": "09:30", "close": "16:00"})

        self.risk = RiskManager(
            max_position_pct=trading_cfg.get("max_position_pct", 25.0),
            max_daily_loss_pct=trading_cfg.get("max_daily_loss_pct", 10.0),
            max_portfolio_risk_pct=trading_cfg.get("max_portfolio_risk_pct", 90.0),
            min_cash_reserve_pct=trading_cfg.get("min_cash_reserve_pct", 5.0),
            stop_loss_pct=trading_cfg.get("stop_loss_pct", 8.0),
            take_profit_pct=trading_cfg.get("take_profit_pct", 20.0),
        )
        self.agent = TradingAgent(trading_cfg, self.risk)

        self._running = False

    # ── Market session ───────────────────────────────────────────────────────

    def _clock_session(self) -> dict:
        """Config-clock fallback when the exchange calendar is unreachable.
        Knows weekends but not holidays — the live calendar is authoritative."""
        now = datetime.now(ET)
        if now.weekday() >= 5:  # Saturday=5, Sunday=6
            return {"session": "closed", "source": "clock"}
        o_h, o_m = map(int, self.market_hours.get("open", "09:30").split(":"))
        c_h, c_m = map(int, self.market_hours.get("close", "16:00").split(":"))
        opens = now.replace(hour=o_h, minute=o_m, second=0, microsecond=0)
        closes = now.replace(hour=c_h, minute=c_m, second=0, microsecond=0)
        if now < opens:
            session = "pre"
        elif now <= closes:
            session = "regular"
        else:
            session = "after"
        return {
            "session": session,
            "minutes_since_open": (now - opens).total_seconds() / 60,
            "minutes_to_close": (closes - now).total_seconds() / 60,
            "source": "clock",
        }

    def _current_session(self) -> dict:
        try:
            return rh.get_market_session()
        except Exception as exc:
            logger.warning("Exchange calendar lookup failed (%s); using config clock", exc)
            return self._clock_session()

    def _crypto_only(self) -> bool:
        assets = self.trading_cfg.get("assets", {})
        return (
            assets.get("crypto", True)
            and not assets.get("stocks", True)
            and not assets.get("options", True)
        )

    # ── Cycle ────────────────────────────────────────────────────────────────

    def _run_cycle(self) -> None:
        session = self._current_session()
        if session["session"] != "regular" and not self._crypto_only():
            # Equity orders are only ever sent live during the regular session;
            # nothing is queued overnight for the opening auction.
            logger.info("Session '%s' — skipping cycle", session["session"])
            return

        logger.info("=== Starting trading cycle ===")
        try:
            portfolio = rh.get_portfolio_summary()
            self.risk.initialize(portfolio["equity"])  # idempotent: baseline set once per day

            if self.risk.is_daily_loss_limit_breached(portfolio["equity"]):
                logger.warning("Daily loss limit breached — no trading today")
                return

            stocks_wl = self.trading_cfg.get("stocks_watchlist", [])
            crypto_wl = self.trading_cfg.get("crypto_watchlist", [])
            context = (
                f"Session: {session['session']}"
                + (
                    f" (~{session.get('minutes_since_open', 0):.0f} min since open, "
                    f"~{session.get('minutes_to_close', 0):.0f} min to close)."
                    if session["session"] == "regular" else "."
                )
                + f" Equity ${portfolio['equity']:.2f}, cash ${portfolio['cash']:.2f}, "
                f"day {portfolio['day_return_pct']:+.2f}% "
                f"(halt at -{self.risk.max_daily_loss_pct:.0f}%). "
                f"Stocks watchlist: {', '.join(stocks_wl)}. "
                f"Crypto watchlist: {', '.join(crypto_wl)}."
            )

            summary = self.agent.run_cycle(watchlist_context=context)
            logger.info("Cycle summary: %s", summary)

        except Exception:
            logger.exception("Error during trading cycle")

        logger.info("=== Trading cycle complete ===")

    def run_once(self) -> None:
        rh.login()
        try:
            self._run_cycle()
        finally:
            rh.logout()

    def run_continuous(self) -> None:
        logger.info("Starting continuous trader (interval=%d min)", self.interval_minutes)
        rh.login()
        self._running = True

        schedule.every(self.interval_minutes).minutes.do(self._run_cycle)
        # Run immediately on startup
        self._run_cycle()

        try:
            while self._running:
                schedule.run_pending()
                time.sleep(30)
        except KeyboardInterrupt:
            logger.info("Trader stopped by user")
        finally:
            rh.logout()
            self._running = False

    def stop(self) -> None:
        self._running = False
