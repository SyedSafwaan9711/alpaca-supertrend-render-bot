import pandas as pd

from strategy import SupertrendStrategy, decide_from_values


def test_decide_from_values_preserves_original_buy_sell_rules():
    buy = decide_from_values(close=101, supertrend=100, position_qty=0)
    sell = decide_from_values(close=99, supertrend=100, position_qty=0.5)
    hold_existing = decide_from_values(close=101, supertrend=100, position_qty=0.5)
    hold_flat = decide_from_values(close=99, supertrend=100, position_qty=0)

    assert buy.action == "buy"
    assert sell.action == "sell"
    assert hold_existing.action == "hold"
    assert hold_flat.action == "hold"


def test_supertrend_strategy_returns_latest_decision_with_indicator_value():
    bars = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01", periods=20, freq="min", tz="UTC"),
            "high": [
                100,
                101,
                102,
                103,
                104,
                105,
                106,
                107,
                108,
                109,
                110,
                111,
                112,
                113,
                114,
                115,
                116,
                117,
                118,
                119,
            ],
            "low": [
                98,
                99,
                100,
                101,
                102,
                103,
                104,
                105,
                106,
                107,
                108,
                109,
                110,
                111,
                112,
                113,
                114,
                115,
                116,
                117,
            ],
            "close": [
                99,
                100,
                101,
                102,
                103,
                104,
                105,
                106,
                107,
                108,
                109,
                110,
                111,
                112,
                113,
                114,
                115,
                116,
                117,
                120,
            ],
        }
    )

    decision = SupertrendStrategy(length=7, multiplier=3).evaluate(bars, position_qty=0)

    assert decision.action in {"buy", "sell", "hold"}
    assert decision.price == 120
    assert decision.supertrend is not None
    assert "close" in decision.reason
