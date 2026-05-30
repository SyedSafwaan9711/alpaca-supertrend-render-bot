from __future__ import annotations

import logging
from datetime import datetime, timezone

from config import BotConfig
from risk_manager import RiskManager


logger = logging.getLogger(__name__)


class ExecutionService:
    def __init__(self, config: BotConfig, market, risk: RiskManager) -> None:
        self.config = config
        self.market = market
        self.risk = risk

    async def buy(self, symbol: str, price: float | None = None, qty: float | None = None) -> dict:
        price = price or await self.market.get_latest_price(symbol)
        qty = qty or await self._qty_from_buying_power(price)
        return await self._submit(symbol=symbol, side="buy", qty=qty)

    async def sell(self, symbol: str, price: float | None = None, qty: float | None = None) -> dict:
        positions = await self.market.get_positions()
        qty = qty or positions.get(symbol, 0)
        if qty <= 0:
            return {"status": "rejected", "reason": f"no open position for {symbol}"}
        return await self._submit(symbol=symbol, side="sell", qty=qty)

    async def close_position(self, symbol: str) -> dict:
        if self.config.dry_run:
            logger.info("DRY_RUN close-position symbol=%s", symbol)
            return {"status": "dry_run", "symbol": symbol, "side": "close"}
        result = await self.market.close_position(symbol)
        self.risk.record_order(symbol)
        logger.info("Closed position symbol=%s result=%s", symbol, result)
        return result

    async def _submit(self, *, symbol: str, side: str, qty: float) -> dict:
        now = datetime.now(timezone.utc)
        positions = await self.market.get_positions()
        decision = self.risk.check_order_allowed(
            symbol=symbol,
            side=side,
            open_positions=positions,
            now=now,
        )
        if not decision.allowed:
            logger.warning("Risk blocked %s %s: %s", side, symbol, decision.reason)
            return {"status": "blocked", "symbol": symbol, "side": side, "reason": decision.reason}

        if qty <= 0:
            return {"status": "rejected", "symbol": symbol, "side": side, "reason": "qty must be positive"}

        if self.config.dry_run:
            self.risk.record_order(symbol, now=now)
            logger.info("DRY_RUN order side=%s symbol=%s qty=%s", side, symbol, qty)
            return {"status": "dry_run", "symbol": symbol, "side": side, "qty": qty}

        result = await self.market.submit_market_order(symbol=symbol, side=side, qty=qty)
        self.risk.record_order(symbol, now=now)
        logger.info("Submitted order side=%s symbol=%s qty=%s result=%s", side, symbol, qty, result)
        return result

    async def _qty_from_buying_power(self, price: float) -> float:
        account = await self.market.get_account()
        buying_power = float(account.get("buying_power", 0) or 0)
        notional = buying_power * (self.config.position_size_pct / 100)
        return round(notional / price, 8)
