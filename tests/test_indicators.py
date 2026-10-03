"""
Test Suite 1: Indicators & Candle Aggregation
Tests EMA, VWAP, ATR, ADX, RSI, Swings, and Candle Resampler.
"""

import pytest
import math
from quant.indicator_engine import indicator_engine
from quant.candle_builder import CandleBuilder


def test_ema_calculation():
    prices = [10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0, 19.0]
    ema9 = indicator_engine.calculate_ema(prices, period=9)
    assert len(ema9) == 10
    assert math.isnan(ema9[0])
    assert not math.isnan(ema9[8])
    # The 9th value (index 8) is the SMA of first 9 items: sum(10..18)/9 = 14.0
    assert abs(ema9[8] - 14.0) < 1e-4
    # 10th value: 19 * (2/10) + 14 * 0.8 = 3.8 + 11.2 = 15.0
    assert abs(ema9[9] - 15.0) < 1e-4


def test_atr_calculation():
    highs = [100 + i * 2 for i in range(20)]
    lows = [90 + i * 2 for i in range(20)]
    closes = [95 + i * 2 for i in range(20)]
    atr = indicator_engine.calculate_atr(highs, lows, closes, period=14)
    assert len(atr) == 20
    assert not math.isnan(atr[-1])
    assert atr[-1] > 0.0


def test_rsi_calculation():
    # Continual upward price series should yield RSI > 70
    closes = [100.0 + (i * 2.0) for i in range(30)]
    rsi = indicator_engine.calculate_rsi(closes, period=14)
    assert not math.isnan(rsi[-1])
    assert rsi[-1] > 70.0


def test_adx_calculation():
    # Strong upward trend
    highs = [100.0 + (i * 3.0) for i in range(40)]
    lows = [90.0 + (i * 3.0) for i in range(40)]
    closes = [95.0 + (i * 3.0) for i in range(40)]
    adx, plus_di, minus_di = indicator_engine.calculate_adx(highs, lows, closes, period=14)
    assert not math.isnan(adx[-1])
    assert plus_di[-1] > minus_di[-1]


def test_vwap_and_atr_distance():
    candles = [
        {"time": 1700000000 + (i * 300), "open": 80000.0 + i, "high": 80010.0 + i, "low": 79990.0 + i, "close": 80005.0 + i, "volume": 10.0}
        for i in range(30)
    ]
    vwap_data = indicator_engine.calculate_vwap(candles, anchor_utc_midnight=False)
    assert vwap_data["vwap"] > 0
    assert vwap_data["upper_1"] > vwap_data["vwap"]
    assert vwap_data["lower_1"] < vwap_data["vwap"]


def test_candle_builder_aggregation():
    cb = CandleBuilder()
    # Feed five 1-minute bars belonging to the same 5-minute bucket (e.g. 0 to 240 sec)
    base_t = 1700000000 // 300 * 300
    for i in range(5):
        cb.on_1m_candle({
            "time": base_t + (i * 60),
            "open": 84000.0 if i == 0 else 84000.0 + i,
            "high": 84010.0 + i,
            "low": 83990.0,
            "close": 84005.0 + i,
            "volume": 10.0
        })

    # The 5m candle should now be closed
    confirmed_5m = cb.get_confirmed_candles("5m")
    assert len(confirmed_5m) == 1
    assert confirmed_5m[0]["open"] == 84000.0
    assert confirmed_5m[0]["volume"] == 50.0
    assert confirmed_5m[0]["is_closed"] is True
