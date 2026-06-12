# Backtest findings — 2025-06-12 → 2026-06-12 (252 daily bars)

Universe: AAPL, MSFT, NVDA, AMZN, GOOGL, META, TSLA (entries) with SPY+QQQ as
regime inputs and SPY as benchmark. Engine: `src/backtest.py` replaying the live
rules (signals → regime gate → ATR stops → 2% risk-budget sizing → breakeven at
+1R → half off at target). Slippage 5 bps/side. Data: Yahoo daily bars
(`scripts/run_backtest.py`).

## Headline

| Config | Return | Benchmark (SPY) | Max DD | Trades | Win rate |
|---|---|---|---|---|---|
| Live defaults (ATR 2.0, 3R, regime on) | **−1.4%** | **+14.3%** | 7.9% | 295 | 20% |
| Best grid cell (ATR 2.0, 2R, regime on) | +0.9% | +14.3% | 5.8% | 418 | 16% |
| Worst grid cell (ATR 1.5, 3R, regime off) | −9.3% | +14.3% | 13.6% | 468 | 10% |

Walk-forward: parameters optimized on H1 returned **−11.1%** on H2 vs −7.9% for
defaults — in-sample optimization did not transfer (overfitting confirmed by
design of the test).

## What validated

1. **Regime gate** — every regime-on cell beat its regime-off twin. Keep it.
2. **Risk containment** — with win rates of 10–20% across hundreds of trades, the
   worst full-year loss was −9.3% and max drawdown 15.8%. Stops + per-trade risk
   budgets did their job: being wrong was survivable.

## What failed

3. **Daily-bar momentum churn on mega-caps is negative-edge after costs.**
   295–500 trades/year with 3R targets rarely reached. The strategy's losses scale
   with its trade count.
4. **Parameter optimization** — the grid winner flipped between halves of the year.
   Tuning harder makes this worse, not better.

## Decisions taken from the evidence

- `max_new_entries_per_day` cut 4 → 2; selection bar unchanged but the playbook
  now treats single-name entries as the exception, not the routine.
- Core exposure = regime-gated index holding (leveraged tier per config); the
  regime score is the validated component, so it manages exposure rather than
  per-name churn.
- No further parameter tuning without out-of-sample confirmation
  (`scripts/run_backtest.py` runs the walk-forward automatically).

## Caveats

One year, one market regime (a +14% SPY tape), 7 large-cap names, daily bars,
no intraday simulation. This is evidence, not proof; treat all results as
in-sample until tested forward.
