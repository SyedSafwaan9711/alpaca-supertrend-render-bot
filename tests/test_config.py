import pytest

from config import ConfigError, load_config


def base_env(**overrides):
    env = {
        "ALPACA_API_KEY": "paper-key",
        "ALPACA_SECRET_KEY": "paper-secret",
        "ALPACA_BASE_URL": "https://paper-api.alpaca.markets",
        "ADMIN_TOKEN": "admin-token",
    }
    env.update(overrides)
    return env


def test_load_config_uses_safe_defaults():
    config = load_config(base_env())

    assert config.trading_mode == "paper"
    assert config.bot_mode == "ASSIST"
    assert config.symbols == ["BTC/USD"]
    assert config.timeframe == "1Min"
    assert config.position_size_pct == 1.0
    assert config.max_open_positions == 1
    assert config.dry_run is True
    assert config.host == "0.0.0.0"


def test_load_config_rejects_missing_secrets():
    with pytest.raises(ConfigError, match="ALPACA_API_KEY"):
        load_config(base_env(ALPACA_API_KEY=""))

    with pytest.raises(ConfigError, match="ADMIN_TOKEN"):
        load_config(base_env(ADMIN_TOKEN=""))


def test_load_config_rejects_paper_live_endpoint_mismatch():
    with pytest.raises(ConfigError, match="paper"):
        load_config(base_env(TRADING_MODE="paper", ALPACA_BASE_URL="https://api.alpaca.markets"))

    with pytest.raises(ConfigError, match="live"):
        load_config(base_env(TRADING_MODE="live", ALPACA_BASE_URL="https://paper-api.alpaca.markets"))


def test_load_config_rejects_unsafe_numeric_values():
    with pytest.raises(ConfigError, match="POSITION_SIZE_PCT"):
        load_config(base_env(POSITION_SIZE_PCT="30"))

    with pytest.raises(ConfigError, match="MAX_DAILY_LOSS_PCT"):
        load_config(base_env(MAX_DAILY_LOSS_PCT="0"))

    with pytest.raises(ConfigError, match="ORDER_INTERVAL_SECONDS"):
        load_config(base_env(ORDER_INTERVAL_SECONDS="0"))
