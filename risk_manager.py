from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone


@dataclass
class RiskDecision:
    allowed: bool
    reason: str


@dataclass
class RiskManager:
    max_open_positions: int = 1
    max_daily_loss_pct: float = 5.0
    cooldown_minutes: int = 10
    order_interval_seconds: int = 60
    max_consecutive_failures: int = 5
    emergency_stop_enabled: bool = False
    emergency_reason: str | None = None
    daily_start_equity: float | None = None
    daily_date: date | None = None
    daily_loss_locked: bool = False
    last_order_at: dict[str, datetime] = field(default_factory=dict)
    cooldown_until: dict[str, datetime] = field(default_factory=dict)
    consecutive_failures: int = 0

    def activate_emergency_stop(self, reason: str) -> None:
        self.emergency_stop_enabled = True
        self.emergency_reason = reason

    def clear_emergency_stop(self) -> None:
        self.emergency_stop_enabled = False
        self.emergency_reason = None

    def update_equity(self, equity: float, *, now: datetime | None = None) -> None:
        now = now or datetime.now(timezone.utc)
        current_date = now.date()
        if self.daily_date != current_date:
            self.daily_date = current_date
            self.daily_start_equity = equity
            self.daily_loss_locked = False
        if self.daily_start_equity is None:
            self.daily_start_equity = equity
        loss_pct = ((self.daily_start_equity - equity) / self.daily_start_equity) * 100
        if loss_pct >= self.max_daily_loss_pct:
            self.daily_loss_locked = True

    def record_order(self, symbol: str, *, now: datetime | None = None) -> None:
        self.last_order_at[symbol] = now or datetime.now(timezone.utc)

    def record_trade_result(
        self, symbol: str, *, realized_pnl: float, now: datetime | None = None
    ) -> None:
        if realized_pnl < 0:
            self.cooldown_until[symbol] = (now or datetime.now(timezone.utc)) + timedelta(
                minutes=self.cooldown_minutes
            )

    def record_api_failure(self) -> None:
        self.consecutive_failures += 1

    def record_api_success(self) -> None:
        self.consecutive_failures = 0

    def check_order_allowed(
        self,
        *,
        symbol: str,
        side: str,
        open_positions: dict[str, float],
        now: datetime | None = None,
    ) -> RiskDecision:
        now = now or datetime.now(timezone.utc)
        side = side.lower()

        if self.emergency_stop_enabled:
            return RiskDecision(False, f"emergency stop active: {self.emergency_reason or 'manual'}")
        if self.consecutive_failures >= self.max_consecutive_failures:
            return RiskDecision(False, "circuit breaker active after repeated failures")

        last_order = self.last_order_at.get(symbol)
        if last_order and now - last_order < timedelta(seconds=self.order_interval_seconds):
            return RiskDecision(False, "minimum order interval has not elapsed")

        if side == "buy":
            if self.daily_loss_locked:
                return RiskDecision(False, "daily loss lock is active")
            cooldown_until = self.cooldown_until.get(symbol)
            if cooldown_until and now < cooldown_until:
                return RiskDecision(False, "losing trade cooldown is active")
            if symbol not in open_positions and len(open_positions) >= self.max_open_positions:
                return RiskDecision(False, "max open positions limit reached")

        return RiskDecision(True, "allowed")

    def status(self) -> dict:
        return {
            "emergency_stop": self.emergency_stop_enabled,
            "emergency_reason": self.emergency_reason,
            "daily_loss_locked": self.daily_loss_locked,
            "daily_start_equity": self.daily_start_equity,
            "daily_date": self.daily_date.isoformat() if self.daily_date else None,
            "consecutive_failures": self.consecutive_failures,
            "cooldown_symbols": sorted(self.cooldown_until),
            "last_order_symbols": sorted(self.last_order_at),
        }
