from fastapi.testclient import TestClient

from config import BotConfig
from web_server import create_app


class FakeController:
    def __init__(self):
        self.pause_called = False
        self.mode = "ASSIST"

    def health(self):
        return {"ok": True, "bot_mode": self.mode, "trading_mode": "paper"}

    def status(self):
        return {"bot_mode": self.mode, "trading_mode": "paper"}

    def pause_auto(self):
        self.pause_called = True
        return self.status()

    def resume_auto(self):
        return self.status()

    def set_bot_mode(self, mode):
        self.mode = mode
        return self.status()

    def set_trading_mode(self, mode):
        return self.status() | {"requested_trading_mode": mode}

    def set_symbols(self, symbols):
        return self.status() | {"symbols": symbols}

    async def buy(self, symbol, qty=None):
        return {"symbol": symbol, "side": "buy", "qty": qty}

    async def sell(self, symbol, qty=None):
        return {"symbol": symbol, "side": "sell", "qty": qty}

    async def close_position(self, symbol):
        return {"symbol": symbol, "side": "close"}

    def emergency_stop(self, reason):
        return self.status() | {"emergency_stop": True, "reason": reason}


def config():
    return BotConfig(
        alpaca_api_key="paper-key",
        alpaca_secret_key="paper-secret",
        alpaca_base_url="https://paper-api.alpaca.markets",
        trading_mode="paper",
        bot_mode="ASSIST",
        admin_token="admin-token",
        symbols=["BTC/USD"],
        timeframe="1Min",
        position_size_pct=1.0,
        max_daily_loss_pct=5.0,
        cooldown_minutes=10,
        max_open_positions=1,
        order_interval_seconds=60,
        log_level="INFO",
        dry_run=True,
        port=8000,
    )


def test_health_and_status_are_public():
    client = TestClient(create_app(config(), FakeController()))

    assert client.get("/health").status_code == 200
    assert client.get("/status").status_code == 200


def test_post_endpoints_require_admin_token():
    fake = FakeController()
    client = TestClient(create_app(config(), fake))

    assert client.post("/pause-auto").status_code == 401

    response = client.post("/pause-auto", headers={"X-Admin-Token": "admin-token"})
    assert response.status_code == 200
    assert fake.pause_called is True


def test_manual_buy_endpoint_accepts_authorized_symbol():
    client = TestClient(create_app(config(), FakeController()))

    response = client.post(
        "/buy",
        headers={"Authorization": "Bearer admin-token"},
        json={"symbol": "BTC/USD", "qty": 0.01},
    )

    assert response.status_code == 200
    assert response.json()["side"] == "buy"
