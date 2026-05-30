import asyncio
from datetime import datetime, timezone

from bot_controller import BotController
from config import BotConfig
from strategy import StrategyDecision


class FakeMarket:
    def __init__(self):
        self.positions = {}
        self.account = {"equity": 10_000, "buying_power": 10_000}
        self.bars_requested = []

    async def authenticate(self):
        return {"account_number": "paper"}

    async def get_account(self):
        return self.account

    async def get_positions(self):
        return self.positions

    async def get_bars(self, symbol, timeframe, limit):
        self.bars_requested.append((symbol, timeframe, limit))
        return []


class FailingAuthMarket(FakeMarket):
    async def authenticate(self):
        raise RuntimeError("invalid credentials")


class FakeStrategy:
    def evaluate(self, bars, position_qty, symbol="BTC/USD"):
        return StrategyDecision(
            symbol=symbol,
            action="buy",
            price=100,
            supertrend=99,
            reason="close above supertrend",
            timestamp=datetime.now(timezone.utc),
        )


class FakeExecutor:
    def __init__(self):
        self.buy_calls = []

    async def buy(self, symbol, price=None, qty=None):
        self.buy_calls.append((symbol, price, qty))
        return {"status": "accepted"}


def config(**overrides):
    values = {
        "alpaca_api_key": "paper-key",
        "alpaca_secret_key": "paper-secret",
        "alpaca_base_url": "https://paper-api.alpaca.markets",
        "trading_mode": "paper",
        "bot_mode": "ASSIST",
        "admin_token": "admin-token",
        "symbols": ["BTC/USD"],
        "timeframe": "1Min",
        "position_size_pct": 1.0,
        "max_daily_loss_pct": 5.0,
        "cooldown_minutes": 10,
        "max_open_positions": 1,
        "order_interval_seconds": 60,
        "log_level": "INFO",
        "dry_run": True,
        "port": 8000,
    }
    values.update(overrides)
    return BotConfig(**values)


def test_assist_mode_analyzes_without_autonomous_order():
    market = FakeMarket()
    executor = FakeExecutor()
    controller = BotController(config(), market=market, strategy=FakeStrategy(), executor=executor)

    asyncio.run(controller.tick())

    assert market.bars_requested == [("BTC/USD", "1Min", 100)]
    assert executor.buy_calls == []
    assert controller.latest_signals["BTC/USD"].action == "buy"


def test_auto_mode_places_order_when_not_paused():
    market = FakeMarket()
    executor = FakeExecutor()
    controller = BotController(
        config(bot_mode="AUTO"), market=market, strategy=FakeStrategy(), executor=executor
    )

    asyncio.run(controller.tick())

    assert executor.buy_calls == [("BTC/USD", 100, None)]


def test_pause_and_emergency_stop_prevent_auto_orders():
    executor = FakeExecutor()
    controller = BotController(
        config(bot_mode="AUTO"), market=FakeMarket(), strategy=FakeStrategy(), executor=executor
    )

    controller.pause_auto()
    asyncio.run(controller.tick())
    controller.resume_auto()
    controller.emergency_stop("test")
    asyncio.run(controller.tick())

    assert executor.buy_calls == []
    assert controller.status()["auto_paused"] is True
    assert controller.status()["risk"]["emergency_stop"] is True


def test_start_keeps_service_alive_when_alpaca_auth_fails():
    controller = BotController(
        config(order_interval_seconds=1),
        market=FailingAuthMarket(),
        strategy=FakeStrategy(),
        executor=FakeExecutor(),
    )

    async def run_start_stop():
        await controller.start()
        await controller.stop()

    asyncio.run(run_start_stop())

    assert controller.health()["authenticated"] is False
    assert "invalid credentials" in controller.status()["auth_status"]["error"]


def test_health_reports_loop_state_without_failing_http_healthcheck():
    controller = BotController(
        config(),
        market=FakeMarket(),
        strategy=FakeStrategy(),
        executor=FakeExecutor(),
    )
    for _ in range(controller.risk.max_consecutive_failures):
        controller.risk.record_api_failure()

    health = controller.health()

    assert health["ok"] is True
    assert health["bot_loop_ok"] is False
