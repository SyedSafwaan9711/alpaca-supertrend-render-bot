from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd

from config import BotConfig


class AlpacaClientError(RuntimeError):
    pass


class AlpacaMarketClient:
    def __init__(self, config: BotConfig) -> None:
        self.config = config
        try:
            from alpaca.data.historical import CryptoHistoricalDataClient
            from alpaca.trading.client import TradingClient
        except ImportError as exc:
            raise AlpacaClientError("alpaca-py is not installed") from exc

        self.trading = TradingClient(
            config.alpaca_api_key,
            config.alpaca_secret_key,
            paper=config.trading_mode == "paper",
            url_override=config.alpaca_base_url,
        )
        self.crypto_data = CryptoHistoricalDataClient(config.alpaca_api_key, config.alpaca_secret_key)

    async def authenticate(self) -> dict[str, Any]:
        account = await self.get_account()
        return {
            "account_number": account.get("account_number"),
            "status": account.get("status"),
            "trading_blocked": account.get("trading_blocked"),
        }

    async def get_account(self) -> dict[str, Any]:
        return await asyncio.to_thread(self._get_account_sync)

    async def get_positions(self) -> dict[str, float]:
        positions = await asyncio.to_thread(self.trading.get_all_positions)
        result: dict[str, float] = {}
        for position in positions:
            qty = float(getattr(position, "qty", 0) or 0)
            if qty:
                result[_normalize_symbol(getattr(position, "symbol"))] = qty
        return result

    async def get_bars(self, symbol: str, timeframe: str, limit: int = 100) -> pd.DataFrame:
        return await asyncio.to_thread(self._get_bars_sync, symbol, timeframe, limit)

    async def get_latest_price(self, symbol: str) -> float:
        return await asyncio.to_thread(self._get_latest_price_sync, symbol)

    async def submit_market_order(self, *, symbol: str, side: str, qty: float) -> dict[str, Any]:
        return await asyncio.to_thread(self._submit_market_order_sync, symbol, side, qty)

    async def close_position(self, symbol: str) -> dict[str, Any]:
        return await asyncio.to_thread(self._close_position_sync, symbol)

    def _get_account_sync(self) -> dict[str, Any]:
        account = self.trading.get_account()
        return {
            "account_number": getattr(account, "account_number", None),
            "status": getattr(account, "status", None),
            "equity": float(getattr(account, "equity", 0) or 0),
            "buying_power": float(getattr(account, "buying_power", 0) or 0),
            "trading_blocked": bool(getattr(account, "trading_blocked", False)),
        }

    def _get_bars_sync(self, symbol: str, timeframe: str, limit: int) -> pd.DataFrame:
        from alpaca.data.requests import CryptoBarsRequest

        request = CryptoBarsRequest(
            symbol_or_symbols=[symbol],
            timeframe=_to_timeframe(timeframe),
            start=_lookback_start(timeframe, limit),
            limit=limit,
        )
        bars = self.crypto_data.get_crypto_bars(request)
        frame = bars.df
        if frame.empty:
            return frame
        if isinstance(frame.index, pd.MultiIndex) and "symbol" in frame.index.names:
            symbols = frame.index.get_level_values("symbol")
            if symbol in symbols:
                frame = frame.loc[[symbol]]
        return frame.tail(limit)

    def _get_latest_price_sync(self, symbol: str) -> float:
        from alpaca.data.requests import CryptoLatestTradeRequest

        request = CryptoLatestTradeRequest(symbol_or_symbols=[symbol])
        latest = self.crypto_data.get_crypto_latest_trade(request)
        trade = latest[symbol] if isinstance(latest, dict) else latest
        return float(getattr(trade, "price"))

    def _submit_market_order_sync(self, symbol: str, side: str, qty: float) -> dict[str, Any]:
        from alpaca.trading.enums import OrderSide, TimeInForce
        from alpaca.trading.requests import MarketOrderRequest

        request = MarketOrderRequest(
            symbol=symbol,
            qty=qty,
            side=OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL,
            time_in_force=TimeInForce.GTC,
        )
        order = self.trading.submit_order(order_data=request)
        return _object_to_dict(order)

    def _close_position_sync(self, symbol: str) -> dict[str, Any]:
        response = self.trading.close_position(symbol)
        return _object_to_dict(response)


def _to_timeframe(value: str):
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

    normalized = value.strip().lower()
    if normalized in {"1min", "1m", "minute"}:
        return TimeFrame(1, TimeFrameUnit.Minute)
    if normalized in {"5min", "5m"}:
        return TimeFrame(5, TimeFrameUnit.Minute)
    if normalized in {"15min", "15m"}:
        return TimeFrame(15, TimeFrameUnit.Minute)
    if normalized in {"1h", "1hour", "hour"}:
        return TimeFrame(1, TimeFrameUnit.Hour)
    if normalized in {"1d", "1day", "day"}:
        return TimeFrame(1, TimeFrameUnit.Day)
    raise AlpacaClientError(f"Unsupported TIMEFRAME: {value}")


def _lookback_start(timeframe: str, limit: int) -> datetime:
    normalized = timeframe.strip().lower()
    if normalized.endswith(("h", "hour")):
        return datetime.now(timezone.utc) - timedelta(hours=limit + 24)
    if normalized.endswith(("d", "day")):
        return datetime.now(timezone.utc) - timedelta(days=limit + 7)
    return datetime.now(timezone.utc) - timedelta(minutes=max(limit * 3, 120))


def _object_to_dict(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if hasattr(value, "dict"):
        return value.dict()
    if isinstance(value, dict):
        return value
    return {"value": str(value)}


def _normalize_symbol(symbol: str) -> str:
    value = symbol.upper()
    if "/" not in value and value.endswith("USD"):
        return f"{value[:-3]}/USD"
    return value
