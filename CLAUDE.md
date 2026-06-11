# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an autonomous AI-powered stock/crypto/options trading system that uses Claude as its decision-making agent. It connects to a live Robinhood brokerage account and executes real trades. **All operations here use real money.**

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env   # then fill in credentials
```

Required environment variables (`.env`):
- `ROBINHOOD_USERNAME`, `ROBINHOOD_PASSWORD` — Robinhood credentials
- `ROBINHOOD_TOTP_SECRET` — optional MFA secret
- `ANTHROPIC_API_KEY` — Claude API key
- `CONFIG_PATH` — optional override for config file path

## Running

```bash
python main.py                          # continuous trading loop (default 30-min intervals)
python main.py --once                   # single trading cycle then exit
python main.py --config path/config.yaml
python main.py --log-level DEBUG
```

There is no test suite or linter configured in this project.

## Architecture

### Data Flow

```
main.py
  └── Trader (src/trader.py)          # scheduling, market hours, login/logout
        ├── RiskManager (src/risk_manager.py)   # validates all orders before execution
        ├── TradingAgent (src/ai_agent.py)       # Claude-powered agentic loop
        └── RobinhoodClient (src/robinhood_client.py)  # API wrapper
```

### Key Design Points

**Agentic loop (`src/ai_agent.py`)**: The agent runs a multi-turn conversation with Claude where Claude calls ~17 tools to gather market data and execute trades. The loop continues until Claude stops requesting tools or a max-iteration limit is hit. All tool calls are dispatched via a `_execute_tool()` method that routes to the appropriate `RobinhoodClient` or `RiskManager` method.

**Risk-first execution**: Every buy order (stocks, crypto, options) is passed through `RiskManager` before hitting Robinhood. The risk manager enforces:
- Max 10% of portfolio per position
- Max 3% daily loss
- Max 50% portfolio deployment
- Min 10% cash reserve

These limits are configurable in `config.yaml` under the `risk` section.

**Market hours**: The `Trader` class only runs trading cycles during configured hours (default 9:30–16:00 ET). Crypto is treated as 24/7. The scheduler uses the `schedule` library to call `run_cycle()` at the configured interval.

**Configuration**: `config.yaml` controls everything: trading interval, risk limits, which asset classes are enabled (stocks/crypto/options), watchlists, Claude model selection, and agent effort level. The config is loaded once at startup and passed into all components.

**Claude model**: Defaults to `claude-opus-4-8` with `output_config={"effort": "high"}` and `thinking={"type": "adaptive"}` for extended reasoning. The model and effort level can be changed in `config.yaml` under `agent.model` and `agent.effort`.

### Tool Surface

The agent has tools in three categories:
- **Data**: `get_portfolio_summary`, `get_stock_quote`, `get_crypto_quote`, `get_options_chain`, `get_historicals`, and position getters
- **Trading**: `buy_stock`, `sell_stock`, `buy_crypto`, `sell_crypto`, `buy_option`, `sell_option`, `cancel_order`
- All trading tools call through `RiskManager.validate_*()` before executing

Adding a new tool requires: defining it in `ai_agent.py`'s tool list, adding a handler branch in `_execute_tool()`, and implementing the underlying method in `RobinhoodClient` if needed.
