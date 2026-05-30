from datetime import datetime, timedelta, timezone

from risk_manager import RiskManager


def test_emergency_stop_blocks_all_new_orders():
    risk = RiskManager(max_open_positions=1)
    risk.activate_emergency_stop("manual")

    decision = risk.check_order_allowed(
        symbol="BTC/USD",
        side="buy",
        open_positions={},
        now=datetime.now(timezone.utc),
    )

    assert decision.allowed is False
    assert "emergency" in decision.reason


def test_max_open_positions_blocks_new_buy_entries():
    risk = RiskManager(max_open_positions=1)

    decision = risk.check_order_allowed(
        symbol="ETH/USD",
        side="buy",
        open_positions={"BTC/USD": 0.1},
        now=datetime.now(timezone.utc),
    )

    assert decision.allowed is False
    assert "max open positions" in decision.reason


def test_order_interval_blocks_duplicate_orders():
    now = datetime.now(timezone.utc)
    risk = RiskManager(max_open_positions=1, order_interval_seconds=60)
    risk.record_order("BTC/USD", now=now)

    decision = risk.check_order_allowed(
        symbol="BTC/USD",
        side="buy",
        open_positions={},
        now=now + timedelta(seconds=30),
    )

    assert decision.allowed is False
    assert "interval" in decision.reason


def test_daily_loss_lock_blocks_new_entries():
    risk = RiskManager(max_open_positions=1, max_daily_loss_pct=2)
    risk.update_equity(10_000, now=datetime(2026, 1, 1, tzinfo=timezone.utc))
    risk.update_equity(9_700, now=datetime(2026, 1, 1, 1, tzinfo=timezone.utc))

    decision = risk.check_order_allowed(
        symbol="BTC/USD",
        side="buy",
        open_positions={},
        now=datetime(2026, 1, 1, 1, 1, tzinfo=timezone.utc),
    )

    assert decision.allowed is False
    assert "daily loss" in decision.reason


def test_losing_trade_cooldown_blocks_entries_until_elapsed():
    now = datetime.now(timezone.utc)
    risk = RiskManager(max_open_positions=1, cooldown_minutes=10)
    risk.record_trade_result("BTC/USD", realized_pnl=-5, now=now)

    blocked = risk.check_order_allowed(
        symbol="BTC/USD",
        side="buy",
        open_positions={},
        now=now + timedelta(minutes=5),
    )
    allowed = risk.check_order_allowed(
        symbol="BTC/USD",
        side="buy",
        open_positions={},
        now=now + timedelta(minutes=11),
    )

    assert blocked.allowed is False
    assert "cooldown" in blocked.reason
    assert allowed.allowed is True
