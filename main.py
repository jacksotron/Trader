#!/usr/bin/env python3
"""Entry point for the autonomous Robinhood trading agent."""

import argparse
import logging
import os
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv


def setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("trader.log"),
        ],
    )


def load_config(path: str) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def main() -> None:
    parser = argparse.ArgumentParser(description="Autonomous Robinhood AI Trader")
    parser.add_argument(
        "--config", default=os.environ.get("CONFIG_PATH", "config.yaml"),
        help="Path to config YAML (default: config.yaml)",
    )
    parser.add_argument(
        "--once", action="store_true",
        help="Run a single trading cycle then exit",
    )
    parser.add_argument(
        "--log-level", default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    args = parser.parse_args()

    setup_logging(args.log_level)
    logger = logging.getLogger(__name__)

    load_dotenv()

    # Validate required env vars
    missing = [v for v in ("ROBINHOOD_USERNAME", "ROBINHOOD_PASSWORD", "ANTHROPIC_API_KEY") if not os.environ.get(v)]
    if missing:
        logger.error("Missing required environment variables: %s", ", ".join(missing))
        logger.error("Copy .env.example to .env and fill in your credentials.")
        sys.exit(1)

    config_path = Path(args.config)
    if not config_path.exists():
        logger.error("Config file not found: %s", config_path)
        sys.exit(1)

    config = load_config(str(config_path))
    logger.info("Loaded config from %s", config_path)

    from src.trader import Trader
    trader = Trader(config)

    if args.once:
        logger.info("Running single cycle")
        trader.run_once()
    else:
        trader.run_continuous()


if __name__ == "__main__":
    main()
