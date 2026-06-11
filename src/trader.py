"""Main trading loop — market hours aware, scheduled, fully autonomous."""

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


def _market_open(open_time: str, close_time: str) -> bool:
    now = datetime.now(ET)
    if now.weekday() >= 5:  # Saturday=5, Sunday=6
        return False
    o_h, o_m = map(int, open_time.split(":"))
    c_h, c_m = map(int, close_time.split(":"))
    market_open = now.replace(hour=o_h, minute=o_m, second=0, microsecond=0)
    market_close = now.replace(hour=c_h, minute=c_m, second=0, microsecond=0)
    return market_open <= now <= market_close


class Trader:
    def __init__(self, config: dict):
        trading_cfg = config.get("trading", {})
        self.trading_cfg = trading_cfg
        self.interval_minutes = trading_cfg.get("interval_minutes", 30)
        self.market_hours = trading_cfg.get("market_hours", {"open": "09:30", "close": "16:00"})
        self.extended_hours = self.market_hours.get("extended_hours", False)

        self.risk = RiskManager(
            max_position_pct=trading_cfg.get("max_position_pct", 10.0),
            max_daily_loss_pct=trading_cfg.get("max_daily_loss_pct", 3.0),
            max_portfolio_risk_pct=trading_cfg.get("max_portfolio_risk_pct", 50.0),
            min_cash_reserve_pct=trading_cfg.get("min_cash_reserve_pct", 10.0),
        )
        self.agent = TradingAgent(trading_cfg, self.risk)

        self._running = False

    def _should_trade(self) -> bool:
        assets = self.trading_cfg.get("assets", {})
        crypto_only = assets.get("crypto", True) and not assets.get("stocks", True) and not assets.get("options", True)
        if crypto_only:
            return True  # Crypto trades 24/7

        in_market = _market_open(
            self.market_hours.get("open", "09:30"),
            self.market_hours.get("close", "16:00"),
        )
        return in_market

    def _run_cycle(self) -> None:
        if not self._should_trade():
            logger.info("Market closed — skipping cycle")
            return

        logger.info("=== Starting trading cycle ===")
        try:
            portfolio = rh.get_portfolio_summary()
            self.risk.initialize(portfolio["equity"])

            if self.risk.is_daily_loss_limit_breached(portfolio["equity"]):
                logger.warning("Daily loss limit breached — no trading today")
                return

            stocks_wl = self.trading_cfg.get("stocks_watchlist", [])
            crypto_wl = self.trading_cfg.get("crypto_watchlist", [])
            context = (
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
