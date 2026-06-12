"""Persistent trade journal — the agent's memory across cycles.

Every entry records its thesis, stop, and target; every exit records the reason
and realized P&L. The next cycle's REVIEW phase enforces these plans instead of
re-deriving them, and the running stats (win rate, expectancy, streaks) feed
back into sizing decisions. JSON-file backed; stdlib only.
"""

import json
import logging
import os
from datetime import date, datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_PATH = "trader_journal.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class TradeJournal:
    def __init__(self, path: str = DEFAULT_PATH):
        self.path = path
        self._data = {
            "open_plans": {},      # symbol -> plan dict
            "closed_trades": [],   # list of completed round-trips
            "stop_outs": {},       # symbol -> ISO date of last stop-out (cooldown)
            "equity_curve": [],    # [{ts, equity}] one point per cycle
        }
        self._load()

    # ── Persistence ──────────────────────────────────────────────────────────

    def _load(self) -> None:
        if os.path.exists(self.path):
            try:
                with open(self.path) as f:
                    stored = json.load(f)
                self._data.update({k: stored[k] for k in self._data if k in stored})
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Journal %s unreadable (%s); starting fresh", self.path, exc)

    def _save(self) -> None:
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self._data, f, indent=2)
        os.replace(tmp, self.path)

    # ── Plans (open positions) ───────────────────────────────────────────────

    def record_entry(self, symbol: str, quantity: float, entry_price: float,
                     stop: float, target: float, thesis: str) -> dict:
        plan = self._data["open_plans"].get(symbol)
        if plan:
            # Scale-in: blend cost basis, keep tightest stop, latest thesis.
            total_qty = plan["quantity"] + quantity
            plan["entry_price"] = round(
                (plan["entry_price"] * plan["quantity"] + entry_price * quantity) / total_qty, 4)
            plan["quantity"] = round(total_qty, 6)
            plan["stop"] = max(plan["stop"], stop)
            plan["target"] = target
            plan["thesis"] = thesis
            plan["updated_at"] = _now()
        else:
            plan = {
                "symbol": symbol,
                "quantity": round(quantity, 6),
                "entry_price": round(entry_price, 4),
                "stop": round(stop, 4),
                "target": round(target, 4),
                "thesis": thesis,
                "opened_at": _now(),
                "updated_at": _now(),
                "breakeven_moved": False,
            }
            self._data["open_plans"][symbol] = plan
        self._save()
        return plan

    def update_plan(self, symbol: str, stop: Optional[float] = None,
                    target: Optional[float] = None,
                    reason: str = "") -> tuple[bool, str]:
        plan = self._data["open_plans"].get(symbol)
        if not plan:
            return False, f"No open plan for {symbol}"
        if stop is not None:
            if stop < plan["stop"]:
                return False, (
                    f"Refused: stop for {symbol} can only move UP (current ${plan['stop']:.2f}, "
                    f"requested ${stop:.2f}). Widening a stop is how losses grow."
                )
            plan["stop"] = round(stop, 4)
            if stop >= plan["entry_price"]:
                plan["breakeven_moved"] = True
        if target is not None:
            plan["target"] = round(target, 4)
        plan["updated_at"] = _now()
        if reason:
            plan["last_adjust_reason"] = reason
        self._save()
        return True, "Plan updated"

    def record_exit(self, symbol: str, quantity: float, exit_price: float,
                    reason: str) -> dict:
        plan = self._data["open_plans"].get(symbol)
        if not plan:
            trade = {"symbol": symbol, "quantity": quantity, "exit_price": exit_price,
                     "reason": reason, "closed_at": _now(), "pnl": None,
                     "note": "exit without recorded plan"}
            self._data["closed_trades"].append(trade)
            self._save()
            return trade

        pnl = (exit_price - plan["entry_price"]) * quantity
        pnl_pct = (exit_price / plan["entry_price"] - 1) * 100 if plan["entry_price"] else 0.0
        trade = {
            "symbol": symbol,
            "quantity": round(quantity, 6),
            "entry_price": plan["entry_price"],
            "exit_price": round(exit_price, 4),
            "pnl": round(pnl, 4),
            "pnl_pct": round(pnl_pct, 3),
            "reason": reason,
            "thesis": plan.get("thesis", ""),
            "opened_at": plan.get("opened_at"),
            "closed_at": _now(),
        }
        self._data["closed_trades"].append(trade)

        remaining = round(plan["quantity"] - quantity, 6)
        if remaining > 1e-9:
            plan["quantity"] = remaining
            plan["updated_at"] = _now()
        else:
            del self._data["open_plans"][symbol]

        if reason == "stop" and pnl < 0:
            self._data["stop_outs"][symbol] = date.today().isoformat()
        self._save()
        return trade

    def get_open_plans(self) -> dict:
        return dict(self._data["open_plans"])

    # ── Discipline helpers ───────────────────────────────────────────────────

    def in_cooldown(self, symbol: str) -> bool:
        """True if the symbol was stopped out today — no same-day re-entry."""
        return self._data["stop_outs"].get(symbol) == date.today().isoformat()

    def entries_today(self) -> int:
        today = date.today().isoformat()
        n = sum(1 for p in self._data["open_plans"].values()
                if (p.get("opened_at") or "").startswith(today))
        n += sum(1 for t in self._data["closed_trades"]
                 if (t.get("opened_at") or "").startswith(today))
        return n

    def consecutive_losses_today(self) -> int:
        today = date.today().isoformat()
        streak = 0
        for t in reversed(self._data["closed_trades"]):
            if not (t.get("closed_at") or "").startswith(today):
                break
            pnl = t.get("pnl")
            if pnl is None:
                continue
            if pnl < 0:
                streak += 1
            else:
                break
        return streak

    # ── Analytics ────────────────────────────────────────────────────────────

    def record_equity(self, equity: float) -> None:
        self._data["equity_curve"].append({"ts": _now(), "equity": round(equity, 4)})
        self._data["equity_curve"] = self._data["equity_curve"][-2000:]
        self._save()

    def stats(self) -> dict:
        trades = [t for t in self._data["closed_trades"] if t.get("pnl") is not None]
        if not trades:
            return {"closed_trades": 0}
        wins = [t for t in trades if t["pnl"] > 0]
        losses = [t for t in trades if t["pnl"] <= 0]
        total = sum(t["pnl"] for t in trades)
        avg_win = sum(t["pnl"] for t in wins) / len(wins) if wins else 0.0
        avg_loss = sum(t["pnl"] for t in losses) / len(losses) if losses else 0.0
        win_rate = len(wins) / len(trades)
        expectancy = win_rate * avg_win + (1 - win_rate) * avg_loss
        return {
            "closed_trades": len(trades),
            "win_rate_pct": round(win_rate * 100, 1),
            "total_realized_pnl": round(total, 4),
            "avg_win": round(avg_win, 4),
            "avg_loss": round(avg_loss, 4),
            "expectancy_per_trade": round(expectancy, 4),
            "consecutive_losses_today": self.consecutive_losses_today(),
            "entries_today": self.entries_today(),
        }

    def recent_trades(self, n: int = 10) -> list[dict]:
        return self._data["closed_trades"][-n:]

    def context_block(self) -> dict:
        """Compact snapshot injected into every agent cycle."""
        return {
            "open_plans": self.get_open_plans(),
            "stats": self.stats(),
            "recent_trades": self.recent_trades(5),
            "cooldown_symbols": [s for s in self._data["stop_outs"]
                                 if self.in_cooldown(s)],
        }
