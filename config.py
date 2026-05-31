from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping


PAPER_BASE_URL = "https://paper-api.alpaca.markets"
LIVE_BASE_URL = "https://api.alpaca.markets"


class ConfigError(ValueError):
    pass


@dataclass
class BotConfig:
    alpaca_api_key: str
    alpaca_secret_key: str
    alpaca_base_url: str
    trading_mode: str
    bot_mode: str
    admin_token: str
    symbols: list[str]
    timeframe: str
    position_size_pct: float
    max_daily_loss_pct: float
    cooldown_minutes: int
    max_open_positions: int
    order_interval_seconds: int
    log_level: str
    dry_run: bool
    port: int
    host: str = "0.0.0.0"
    allow_live_trading: bool = False


def load_config(env: Mapping[str, str] | None = None) -> BotConfig:
    if env is None:
        _load_dotenv_if_available()
        env = os.environ

    trading_mode = _choice(env, "TRADING_MODE", "paper", {"paper", "live"}).lower()
    bot_mode = _choice(env, "BOT_MODE", "ASSIST", {"ASSIST", "AUTO"}).upper()
    base_url = _normalize_base_url(_string(env, "ALPACA_BASE_URL", PAPER_BASE_URL))
    allow_live_trading = _bool(env, "ALLOW_LIVE_TRADING", False)

    _validate_base_url(trading_mode, base_url, allow_live_trading)

    return BotConfig(
        alpaca_api_key=_required(env, "ALPACA_API_KEY"),
        alpaca_secret_key=_required(env, "ALPACA_SECRET_KEY"),
        alpaca_base_url=base_url,
        trading_mode=trading_mode,
        bot_mode=bot_mode,
        admin_token=_required(env, "ADMIN_TOKEN"),
        symbols=_symbols(env.get("SYMBOLS", "BTC/USD")),
        timeframe=_string(env, "TIMEFRAME", "1Min"),
        position_size_pct=_float_range(env, "POSITION_SIZE_PCT", 1.0, minimum=0.01, maximum=10.0),
        max_daily_loss_pct=_float_range(env, "MAX_DAILY_LOSS_PCT", 5.0, minimum=0.01, maximum=25.0),
        cooldown_minutes=_int_range(env, "COOLDOWN_MINUTES", 10, minimum=0, maximum=1440),
        max_open_positions=_int_range(env, "MAX_OPEN_POSITIONS", 1, minimum=1, maximum=20),
        order_interval_seconds=_int_range(env, "ORDER_INTERVAL_SECONDS", 60, minimum=1, maximum=86400),
        log_level=_string(env, "LOG_LEVEL", "INFO").upper(),
        dry_run=_bool(env, "DRY_RUN", True),
        host=_string(env, "HOST", "0.0.0.0"),
        port=_int_range(env, "PORT", 8000, minimum=1, maximum=65535),
        allow_live_trading=allow_live_trading,
    )


def config_as_env(config: BotConfig, *, trading_mode: str | None = None) -> dict[str, str]:
    mode = trading_mode or config.trading_mode
    return {
        "ALPACA_API_KEY": config.alpaca_api_key,
        "ALPACA_SECRET_KEY": config.alpaca_secret_key,
        "ALPACA_BASE_URL": config.alpaca_base_url,
        "TRADING_MODE": mode,
        "BOT_MODE": config.bot_mode,
        "ADMIN_TOKEN": config.admin_token,
        "SYMBOLS": ",".join(config.symbols),
        "TIMEFRAME": config.timeframe,
        "POSITION_SIZE_PCT": str(config.position_size_pct),
        "MAX_DAILY_LOSS_PCT": str(config.max_daily_loss_pct),
        "COOLDOWN_MINUTES": str(config.cooldown_minutes),
        "MAX_OPEN_POSITIONS": str(config.max_open_positions),
        "ORDER_INTERVAL_SECONDS": str(config.order_interval_seconds),
        "LOG_LEVEL": config.log_level,
        "DRY_RUN": str(config.dry_run).lower(),
        "HOST": config.host,
        "PORT": str(config.port),
        "ALLOW_LIVE_TRADING": str(config.allow_live_trading).lower(),
    }


def _load_dotenv_if_available() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv()


def _required(env: Mapping[str, str], key: str) -> str:
    value = env.get(key, "").strip()
    if not value:
        raise ConfigError(f"{key} is required")
    return value


def _string(env: Mapping[str, str], key: str, default: str) -> str:
    return env.get(key, default).strip() or default


def _choice(env: Mapping[str, str], key: str, default: str, allowed: set[str]) -> str:
    value = _string(env, key, default)
    normalized = value.upper() if default.isupper() else value.lower()
    normalized_allowed = {item.upper() if default.isupper() else item.lower() for item in allowed}
    if normalized not in normalized_allowed:
        allowed_text = ", ".join(sorted(allowed))
        raise ConfigError(f"{key} must be one of: {allowed_text}")
    return normalized


def _bool(env: Mapping[str, str], key: str, default: bool) -> bool:
    raw = env.get(key)
    if raw is None or raw == "":
        return default
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "y", "on"}:
        return True
    if value in {"0", "false", "no", "n", "off"}:
        return False
    raise ConfigError(f"{key} must be a boolean")


def _float_range(
    env: Mapping[str, str], key: str, default: float, *, minimum: float, maximum: float
) -> float:
    raw = env.get(key, str(default)).strip()
    try:
        value = float(raw)
    except ValueError as exc:
        raise ConfigError(f"{key} must be a number") from exc
    if value < minimum or value > maximum:
        raise ConfigError(f"{key} must be between {minimum} and {maximum}")
    return value


def _int_range(
    env: Mapping[str, str], key: str, default: int, *, minimum: int, maximum: int
) -> int:
    raw = env.get(key, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{key} must be an integer") from exc
    if value < minimum or value > maximum:
        raise ConfigError(f"{key} must be between {minimum} and {maximum}")
    return value


def _symbols(raw: str) -> list[str]:
    symbols = [_normalize_symbol(part.strip()) for part in raw.split(",") if part.strip()]
    if not symbols:
        raise ConfigError("SYMBOLS must contain at least one symbol")
    return symbols


def _normalize_symbol(symbol: str) -> str:
    value = symbol.upper().replace("-", "/")
    if "/" not in value and value.endswith("USD"):
        return f"{value[:-3]}/USD"
    return value


def _normalize_base_url(base_url: str) -> str:
    value = base_url.rstrip("/")
    if value.endswith("/v2"):
        return value.removesuffix("/v2")
    return value


def _validate_base_url(trading_mode: str, base_url: str, allow_live_trading: bool) -> None:
    if trading_mode == "paper":
        if "paper-api.alpaca.markets" not in base_url:
            raise ConfigError("paper trading mode requires the paper Alpaca endpoint")
        return

    if "paper-api.alpaca.markets" in base_url:
        raise ConfigError("live trading mode cannot use the paper Alpaca endpoint")
    if "api.alpaca.markets" not in base_url:
        raise ConfigError("live trading mode requires the live Alpaca endpoint")
    if not allow_live_trading:
        raise ConfigError("live trading requires ALLOW_LIVE_TRADING=true")
