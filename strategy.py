from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

import pandas as pd


Action = Literal["buy", "sell", "hold"]


class StrategyError(RuntimeError):
    pass


@dataclass
class StrategyDecision:
    symbol: str
    action: Action
    price: float
    supertrend: float | None
    reason: str
    timestamp: datetime


def decide_from_values(
    *,
    close: float,
    supertrend: float,
    position_qty: float,
    symbol: str = "BTC/USD",
    timestamp: datetime | None = None,
) -> StrategyDecision:
    timestamp = timestamp or datetime.now(timezone.utc)
    if close > supertrend and position_qty <= 0:
        action: Action = "buy"
        reason = f"close {close:.8f} above supertrend {supertrend:.8f}"
    elif close < supertrend and position_qty > 0:
        action = "sell"
        reason = f"close {close:.8f} below supertrend {supertrend:.8f}"
    else:
        action = "hold"
        reason = f"close {close:.8f} did not require a position change vs supertrend {supertrend:.8f}"
    return StrategyDecision(symbol, action, float(close), float(supertrend), reason, timestamp)


class SupertrendStrategy:
    def __init__(self, *, length: int = 7, multiplier: float = 3.0) -> None:
        self.length = length
        self.multiplier = multiplier

    def evaluate(self, bars: pd.DataFrame, position_qty: float, symbol: str = "BTC/USD") -> StrategyDecision:
        frame = normalize_bars_frame(bars)
        if len(frame) < self.length + 2:
            raise StrategyError(f"Need at least {self.length + 2} bars to compute supertrend")

        frame["supertrend"] = compute_supertrend(frame, self.length, self.multiplier)
        valid = frame.dropna(subset=["supertrend"])
        if valid.empty:
            raise StrategyError("Supertrend produced no valid indicator values")

        latest = valid.iloc[-1]
        timestamp = _extract_timestamp(latest)
        return decide_from_values(
            close=float(latest["close"]),
            supertrend=float(latest["supertrend"]),
            position_qty=position_qty,
            symbol=symbol,
            timestamp=timestamp,
        )


def normalize_bars_frame(bars: pd.DataFrame) -> pd.DataFrame:
    frame = bars.copy()
    if isinstance(frame.index, pd.MultiIndex):
        frame = frame.reset_index()
    elif frame.index.name:
        frame = frame.reset_index()

    rename = {
        "open": "open",
        "high": "high",
        "low": "low",
        "close": "close",
        "o": "open",
        "h": "high",
        "l": "low",
        "c": "close",
        "t": "timestamp",
    }
    frame = frame.rename(columns={key: value for key, value in rename.items() if key in frame.columns})
    required = {"high", "low", "close"}
    missing = required.difference(frame.columns)
    if missing:
        raise StrategyError(f"Bars are missing required columns: {', '.join(sorted(missing))}")
    return frame.sort_values("timestamp") if "timestamp" in frame.columns else frame


def compute_supertrend(frame: pd.DataFrame, length: int, multiplier: float) -> pd.Series:
    high = frame["high"].astype(float)
    low = frame["low"].astype(float)
    close = frame["close"].astype(float)

    previous_close = close.shift(1)
    true_range = pd.concat(
        [
            high - low,
            (high - previous_close).abs(),
            (low - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr = true_range.rolling(window=length, min_periods=length).mean()
    hl2 = (high + low) / 2
    basic_upper = hl2 + multiplier * atr
    basic_lower = hl2 - multiplier * atr

    final_upper = basic_upper.copy()
    final_lower = basic_lower.copy()
    supertrend = pd.Series(index=frame.index, dtype="float64")
    direction = pd.Series(index=frame.index, dtype="int64")

    for i in range(len(frame)):
        if pd.isna(atr.iloc[i]):
            continue
        if i == 0 or pd.isna(supertrend.iloc[i - 1]):
            direction.iloc[i] = 1
            supertrend.iloc[i] = final_lower.iloc[i]
            continue

        if basic_upper.iloc[i] < final_upper.iloc[i - 1] or close.iloc[i - 1] > final_upper.iloc[i - 1]:
            final_upper.iloc[i] = basic_upper.iloc[i]
        else:
            final_upper.iloc[i] = final_upper.iloc[i - 1]

        if basic_lower.iloc[i] > final_lower.iloc[i - 1] or close.iloc[i - 1] < final_lower.iloc[i - 1]:
            final_lower.iloc[i] = basic_lower.iloc[i]
        else:
            final_lower.iloc[i] = final_lower.iloc[i - 1]

        if supertrend.iloc[i - 1] == final_upper.iloc[i - 1]:
            direction.iloc[i] = 1 if close.iloc[i] > final_upper.iloc[i] else -1
        else:
            direction.iloc[i] = -1 if close.iloc[i] < final_lower.iloc[i] else 1

        supertrend.iloc[i] = final_lower.iloc[i] if direction.iloc[i] == 1 else final_upper.iloc[i]

    return supertrend


def _extract_timestamp(row: pd.Series) -> datetime:
    value = row.get("timestamp")
    if value is None or pd.isna(value):
        return datetime.now(timezone.utc)
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("UTC")
    return timestamp.to_pydatetime()
