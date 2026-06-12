"""Risk management: enforces position limits, daily loss caps, and order sizing."""

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class RiskManager:
    max_position_pct: float = 25.0
    max_daily_loss_pct: float = 10.0
    max_portfolio_risk_pct: float = 90.0
    min_cash_reserve_pct: float = 5.0
    stop_loss_pct: float = 8.0
    take_profit_pct: float = 20.0

    _baseline_date: Optional[date] = field(default=None, init=False, repr=False)
    _session_start_equity: float = field(default=0.0, init=False, repr=False)
    _realized_pnl_today: float = field(default=0.0, init=False, repr=False)

    def initialize(self, current_equity: float) -> None:
        """Set the daily-loss baseline.

        Idempotent within a calendar day: repeated calls only reset the baseline
        when the day rolls over, so intraday drawdown accumulates against a fixed
        morning baseline instead of being wiped out every cycle.
        """
        today = date.today()
        if self._baseline_date == today:
            return
        self._baseline_date = today
        self._session_start_equity = current_equity
        self._realized_pnl_today = 0.0
        logger.info("Daily risk baseline set: equity=$%.2f", current_equity)

    def record_trade_pnl(self, pnl: float) -> None:
        self._realized_pnl_today += pnl

    @property
    def daily_pnl(self) -> float:
        return self._realized_pnl_today

    def is_daily_loss_limit_breached(self, current_equity: float) -> bool:
        if self._session_start_equity <= 0:
            return False
        loss_pct = (self._session_start_equity - current_equity) / self._session_start_equity * 100
        if loss_pct >= self.max_daily_loss_pct:
            logger.warning(
                "Daily loss limit breached: %.2f%% loss (limit %.2f%%)",
                loss_pct, self.max_daily_loss_pct
            )
            return True
        return False

    def exit_levels(self, entry_price: float) -> dict:
        """Default stop and target prices for a long entry."""
        return {
            "stop": round(entry_price * (1 - self.stop_loss_pct / 100), 2),
            "target": round(entry_price * (1 + self.take_profit_pct / 100), 2),
        }

    def max_position_value(self, portfolio_equity: float) -> float:
        return portfolio_equity * (self.max_position_pct / 100)

    def max_order_value(self, portfolio_equity: float, cash: float,
                        current_deployed: float) -> float:
        max_deploy = portfolio_equity * (self.max_portfolio_risk_pct / 100)
        remaining_deploy = max(0.0, max_deploy - current_deployed)
        cash_reserve = portfolio_equity * (self.min_cash_reserve_pct / 100)
        available_cash = max(0.0, cash - cash_reserve)
        return min(remaining_deploy, available_cash, self.max_position_value(portfolio_equity))

    def validate_stock_buy(
        self,
        symbol: str,
        quantity: float,
        price: float,
        portfolio_equity: float,
        cash: float,
        current_deployed: float,
        current_position_value: float = 0.0,
    ) -> tuple[bool, str]:
        order_value = quantity * price
        max_order = self.max_order_value(portfolio_equity, cash, current_deployed)
        max_pos = self.max_position_value(portfolio_equity)

        if order_value > max_order:
            return False, (
                f"Order value ${order_value:.2f} exceeds max allowed ${max_order:.2f}. "
                f"Consider reducing quantity to {int(max_order / price)} shares."
            )
        if current_position_value + order_value > max_pos:
            return False, (
                f"Adding ${order_value:.2f} to existing ${current_position_value:.2f} position "
                f"in {symbol} would exceed max position size ${max_pos:.2f}."
            )
        if order_value > cash:
            return False, f"Insufficient cash: need ${order_value:.2f}, have ${cash:.2f}."
        return True, "OK"

    def validate_crypto_buy(
        self,
        symbol: str,
        amount_dollars: float,
        portfolio_equity: float,
        cash: float,
        current_deployed: float,
        current_position_value: float = 0.0,
    ) -> tuple[bool, str]:
        max_order = self.max_order_value(portfolio_equity, cash, current_deployed)
        max_pos = self.max_position_value(portfolio_equity)

        if amount_dollars > max_order:
            return False, (
                f"Crypto buy ${amount_dollars:.2f} exceeds max allowed ${max_order:.2f}."
            )
        if current_position_value + amount_dollars > max_pos:
            return False, (
                f"Adding ${amount_dollars:.2f} to existing ${current_position_value:.2f} "
                f"position in {symbol} would exceed max position ${max_pos:.2f}."
            )
        if amount_dollars > cash:
            return False, f"Insufficient cash: need ${amount_dollars:.2f}, have ${cash:.2f}."
        return True, "OK"

    def validate_option_buy(
        self,
        symbol: str,
        contracts: int,
        premium_per_contract: float,
        portfolio_equity: float,
        cash: float,
        current_deployed: float,
        max_contracts: int = 10,
    ) -> tuple[bool, str]:
        if premium_per_contract <= 0:
            return False, "Options orders require a real limit price; refusing to validate against a guess."
        order_value = contracts * premium_per_contract * 100
        max_order = self.max_order_value(portfolio_equity, cash, current_deployed)

        if contracts > max_contracts:
            return False, f"Requested {contracts} contracts exceeds max {max_contracts}."
        if order_value > max_order:
            return False, (
                f"Options order ${order_value:.2f} exceeds max allowed ${max_order:.2f}."
            )
        if order_value > cash:
            return False, f"Insufficient cash: need ${order_value:.2f}, have ${cash:.2f}."
        return True, "OK"

    def suggest_quantity(self, price: float, portfolio_equity: float,
                         cash: float, current_deployed: float) -> float:
        max_val = self.max_order_value(portfolio_equity, cash, current_deployed)
        if price <= 0:
            return 0
        qty = max_val / price
        return max(0.0, qty)
