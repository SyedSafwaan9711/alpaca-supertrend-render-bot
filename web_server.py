from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from config import BotConfig


class ModeRequest(BaseModel):
    mode: str


class TradingModeRequest(BaseModel):
    mode: str


class SymbolsRequest(BaseModel):
    symbols: list[str] = Field(min_length=1)


class TradeRequest(BaseModel):
    symbol: str
    qty: float | None = Field(default=None, gt=0)


class CloseRequest(BaseModel):
    symbol: str


class EmergencyStopRequest(BaseModel):
    reason: str = "manual"


def create_app(config: BotConfig, controller, *, manage_lifecycle: bool = False) -> FastAPI:
    lifespan = _lifespan(controller) if manage_lifecycle else None
    app = FastAPI(title="Alpaca Supertrend Bot", version="1.0.0", lifespan=lifespan)

    def require_admin(
        x_admin_token: Annotated[str | None, Header(alias="X-Admin-Token")] = None,
        authorization: Annotated[str | None, Header()] = None,
    ) -> None:
        token = None
        if authorization and authorization.lower().startswith("bearer "):
            token = authorization.split(" ", 1)[1]
        token = token or x_admin_token
        if token != config.admin_token:
            raise HTTPException(status_code=401, detail="admin token required")

    @app.get("/health")
    def health():
        return controller.health()

    @app.get("/status")
    def status():
        return controller.status()

    @app.post("/pause-auto", dependencies=[Depends(require_admin)])
    def pause_auto():
        return controller.pause_auto()

    @app.post("/resume-auto", dependencies=[Depends(require_admin)])
    def resume_auto():
        return controller.resume_auto()

    @app.post("/set-bot-mode", dependencies=[Depends(require_admin)])
    def set_bot_mode(request: ModeRequest):
        return _handle_value_error(lambda: controller.set_bot_mode(request.mode))

    @app.post("/set-trading-mode", dependencies=[Depends(require_admin)])
    def set_trading_mode(request: TradingModeRequest):
        return _handle_value_error(lambda: controller.set_trading_mode(request.mode))

    @app.post("/set-symbols", dependencies=[Depends(require_admin)])
    def set_symbols(request: SymbolsRequest):
        return _handle_value_error(lambda: controller.set_symbols(request.symbols))

    @app.post("/buy", dependencies=[Depends(require_admin)])
    async def buy(request: TradeRequest):
        return await controller.buy(request.symbol, qty=request.qty)

    @app.post("/sell", dependencies=[Depends(require_admin)])
    async def sell(request: TradeRequest):
        return await controller.sell(request.symbol, qty=request.qty)

    @app.post("/close-position", dependencies=[Depends(require_admin)])
    async def close_position(request: CloseRequest):
        return await controller.close_position(request.symbol)

    @app.post("/emergency-stop", dependencies=[Depends(require_admin)])
    def emergency_stop(request: EmergencyStopRequest):
        return controller.emergency_stop(request.reason)

    return app


def _handle_value_error(callback):
    try:
        return callback()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _lifespan(controller):
    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        await controller.start()
        try:
            yield
        finally:
            await controller.stop()

    return lifespan
