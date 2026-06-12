# Trader

Autonomous Claude-powered trading agent for Robinhood. The agent runs a strict
playbook on a schedule; every rule that matters is enforced in code, not prose.

## Architecture

| Module | Job |
|---|---|
| `src/trader.py` | Market-session-aware cycle loop; stale-order cleanup; daily risk baseline |
| `src/ai_agent.py` | Claude tool-use loop + execution guards (session/windows/spreads/throttles) |
| `src/signals.py` | Indicators: ATR, RSI, MA trend state, VWAP, relative strength, regime score |
| `src/journal.py` | Persistent memory: entry thesis/stop/target per position, realized P&L, stats, cooldowns |
| `src/risk_manager.py` | Caps: per-position %, deployment %, cash reserve, daily-loss halt, per-trade risk budget |
| `src/backtest.py` | Replays the live rules over historical bars; grid search for parameters |
| `src/robinhood_client.py` | robin_stocks wrapper: batched quotes, read retries, fill polling |

## The playbook (each cycle)

1. **Enforce plans** — journaled stops/targets are executed mechanically; stops only move up;
   +1R moves stops to breakeven.
2. **Regime** — SPY+QQQ composite score: ≥70 full sizing, 40–69 half, <40 no new longs.
3. **Select** — trend up + RSI 45–70 + positive relative strength; spread ≤1%; no re-entry
   the day after a stop-out.
4. **Size & execute** — stop first (2×ATR clamped), size so a stop-out costs ≤2% of equity;
   marketable limits only; regular session only; never queued overnight; unfilled orders
   cancelled after 10s (the journal records fill truth only).
5. **Journal** — every trade carries thesis/stop/target/invalidation; stats feed back into
   the next cycle.

## Running

```bash
cp .env.example .env   # Robinhood credentials + Anthropic API key
pip install -r requirements.txt
python main.py --once  # single cycle
python main.py         # continuous (interval from config.yaml)
python -m unittest discover -s tests
```

Strategy and risk settings live in `config.yaml`.

> **Warning:** trading involves substantial risk of loss. Backtest results are
> in-sample, historical, and not predictive. Nothing here guarantees profit.
