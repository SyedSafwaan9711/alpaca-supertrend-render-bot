from __future__ import annotations

import uvicorn

from alpaca_client import AlpacaMarketClient
from bot_controller import BotController
from config import load_config
from execution import ExecutionService
from logging_utils import configure_logging
from risk_manager import RiskManager
from strategy import SupertrendStrategy
from web_server import create_app


def build_controller(config):
    market = AlpacaMarketClient(config)
    risk = RiskManager(
        max_open_positions=config.max_open_positions,
        max_daily_loss_pct=config.max_daily_loss_pct,
        cooldown_minutes=config.cooldown_minutes,
        order_interval_seconds=config.order_interval_seconds,
    )
    executor = ExecutionService(config, market, risk)
    strategy = SupertrendStrategy(length=7, multiplier=3)
    return BotController(config, market=market, strategy=strategy, executor=executor, risk=risk)


def main() -> None:
    config = load_config()
    configure_logging(config.log_level)
    controller = build_controller(config)
    app = create_app(config, controller, manage_lifecycle=True)
    uvicorn.run(app, host=config.host, port=config.port)


if __name__ == "__main__":
    main()
