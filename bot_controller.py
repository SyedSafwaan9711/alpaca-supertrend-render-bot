from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from config import BotConfig, ConfigError, config_as_env, load_config
from risk_manager import RiskManager
from strategy import StrategyDecision


logger = logging.getLogger(__name__)


class BotController:
    def __init__(self, config: BotConfig, *, market, strategy, executor, risk: RiskManager | None = None) -> None:
        self.config = config
        self.market = market
        self.strategy = strategy
        self.executor = executor
        self.risk = risk or getattr(executor, "risk", RiskManager())
        self.auto_paused = config.bot_mode != "AUTO"
        self.latest_signals: dict[str, StrategyDecision] = {}
        self.last_action: dict[str, Any] | None = None
        self.started_at = datetime.now(timezone.utc)
        self.last_tick_at: datetime | None = None
        self.authenticated = False
        self.auth_status: dict[str, Any] = {}
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    async def authenticate(self) -> None:
        self.auth_status = await self.market.authenticate()
        self.authenticated = True
        logger.info("Authenticated with Alpaca account=%s", self.auth_status.get("account_number"))

    async def start(self) -> None:
        if not self.authenticated:
            await self.authenticate()
        self._stop_event.clear()
        self._task = asyncio.create_task(self.run_forever())

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task:
            await self._task

    async def run_forever(self) -> None:
        while not self._stop_event.is_set():
            await self.tick()
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self.config.order_interval_seconds,
                )
            except asyncio.TimeoutError:
                pass

    async def tick(self) -> None:
        self.last_tick_at = datetime.now(timezone.utc)
        try:
            account = await self.market.get_account()
            equity = float(account.get("equity", 0) or 0)
            if equity:
                self.risk.update_equity(equity, now=self.last_tick_at)

            positions = await self.market.get_positions()
            for symbol in self.config.symbols:
                bars = await self.market.get_bars(symbol, self.config.timeframe, 100)
                position_qty = positions.get(symbol, 0)
                decision = self.strategy.evaluate(bars, position_qty, symbol=symbol)
                self.latest_signals[symbol] = decision
                logger.info(
                    "Signal symbol=%s action=%s price=%s supertrend=%s reason=%s",
                    symbol,
                    decision.action,
                    decision.price,
                    decision.supertrend,
                    decision.reason,
                )
                if self._can_auto_trade() and decision.action == "buy":
                    self.last_action = await self.executor.buy(symbol, price=decision.price)
                elif self._can_auto_trade() and decision.action == "sell":
                    self.last_action = await self.executor.sell(symbol, price=decision.price)
            self.risk.record_api_success()
        except Exception:
            self.risk.record_api_failure()
            logger.exception("Bot tick failed")

    def pause_auto(self) -> dict:
        self.auto_paused = True
        logger.warning("AUTO mode paused")
        return self.status()

    def resume_auto(self) -> dict:
        if self.config.bot_mode == "AUTO" and not self.risk.emergency_stop_enabled:
            self.auto_paused = False
            logger.warning("AUTO mode resumed")
        return self.status()

    def set_bot_mode(self, mode: str) -> dict:
        normalized = mode.upper()
        if normalized not in {"AUTO", "ASSIST"}:
            raise ValueError("mode must be AUTO or ASSIST")
        self.config.bot_mode = normalized
        self.auto_paused = normalized != "AUTO" or self.risk.emergency_stop_enabled
        logger.warning("Bot mode set to %s", normalized)
        return self.status()

    def set_trading_mode(self, mode: str) -> dict:
        normalized = mode.lower()
        if normalized not in {"paper", "live"}:
            raise ValueError("mode must be paper or live")
        try:
            load_config(config_as_env(self.config, trading_mode=normalized))
        except ConfigError as exc:
            raise ValueError(str(exc)) from exc
        if normalized != self.config.trading_mode:
            raise ValueError("changing trading mode requires restarting with matching Alpaca credentials")
        return self.status()

    def set_symbols(self, symbols: list[str]) -> dict:
        if not symbols:
            raise ValueError("symbols must not be empty")
        self.config.symbols = symbols
        logger.warning("Symbols set to %s", ",".join(symbols))
        return self.status()

    def emergency_stop(self, reason: str) -> dict:
        self.risk.activate_emergency_stop(reason)
        self.auto_paused = True
        logger.critical("Emergency stop activated: %s", reason)
        return self.status()

    async def buy(self, symbol: str, qty: float | None = None) -> dict:
        return await self.executor.buy(symbol, qty=qty)

    async def sell(self, symbol: str, qty: float | None = None) -> dict:
        return await self.executor.sell(symbol, qty=qty)

    async def close_position(self, symbol: str) -> dict:
        return await self.executor.close_position(symbol)

    def health(self) -> dict:
        return {
            "ok": self.risk.consecutive_failures < self.risk.max_consecutive_failures,
            "bot_mode": self.config.bot_mode,
            "trading_mode": self.config.trading_mode,
            "dry_run": self.config.dry_run,
            "auto_paused": self.auto_paused,
            "authenticated": self.authenticated,
            "last_tick_at": self.last_tick_at.isoformat() if self.last_tick_at else None,
            "risk_lock": self.risk.daily_loss_locked or self.risk.emergency_stop_enabled,
        }

    def status(self) -> dict:
        return {
            "bot_mode": self.config.bot_mode,
            "trading_mode": self.config.trading_mode,
            "dry_run": self.config.dry_run,
            "symbols": self.config.symbols,
            "timeframe": self.config.timeframe,
            "auto_paused": self.auto_paused,
            "authenticated": self.authenticated,
            "auth_status": self.auth_status,
            "started_at": self.started_at.isoformat(),
            "last_tick_at": self.last_tick_at.isoformat() if self.last_tick_at else None,
            "latest_signals": {
                symbol: {
                    "action": decision.action,
                    "price": decision.price,
                    "supertrend": decision.supertrend,
                    "reason": decision.reason,
                    "timestamp": decision.timestamp.isoformat(),
                }
                for symbol, decision in self.latest_signals.items()
            },
            "last_action": self.last_action,
            "risk": self.risk.status(),
        }

    def _can_auto_trade(self) -> bool:
        return self.config.bot_mode == "AUTO" and not self.auto_paused
