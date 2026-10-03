"""
Test Suite 3: State Machines
Tests 8-stage Breakout/Breakdown, 7-stage Spike Radar, and Regime Engine with Hysteresis.
"""

import pytest
from config.constants import BreakoutStage, SpikeState, MarketRegime
from engine.breakout_engine import BreakoutEngine
from engine.spike_radar import SpikeRadar
from engine.market_regime_engine import MarketRegimeEngine


def test_breakout_state_machine_lifecycle():
    bo = BreakoutEngine()
    assert bo.stage == BreakoutStage.RANGE_IDENTIFIED

    # 1. Price approaches resistance
    res = bo.evaluate(
        spot=84950.0,
        last_closed_candle={"close": 84900.0, "high": 84960.0, "low": 84850.0},
        key_resistance=85000.0,
        key_support=84000.0,
        res_name="Day High",
        sup_name="Day Low",
        atr14=200.0,
        rvol=1.5,
        norm_delta=0.25,
        oi_change_pct=1.0
    )
    assert bo.stage == BreakoutStage.LEVEL_APPROACHING

    # 2. Live price penetrates level
    res = bo.evaluate(
        spot=85050.0,
        last_closed_candle={"close": 84980.0, "high": 85060.0, "low": 84900.0},
        key_resistance=85000.0,
        key_support=84000.0,
        res_name="Day High",
        sup_name="Day Low",
        atr14=200.0,
        rvol=1.5,
        norm_delta=0.25,
        oi_change_pct=1.0
    )
    assert bo.stage == BreakoutStage.BREAKOUT_ATTEMPT

    # 3. Candle confirmed closed above level + buffer
    res = bo.evaluate(
        spot=85100.0,
        last_closed_candle={"close": 85100.0, "high": 85150.0, "low": 85010.0},
        key_resistance=85000.0,
        key_support=84000.0,
        res_name="Day High",
        sup_name="Day Low",
        atr14=200.0,
        rvol=1.8,
        norm_delta=0.30,
        oi_change_pct=1.0
    )
    assert bo.stage in (BreakoutStage.BREAKOUT_CANDLE_CLOSED, BreakoutStage.RETEST_OR_ACCEPTANCE)


def test_spike_radar_lifecycle():
    sr = SpikeRadar()
    assert sr.state == SpikeState.NORMAL

    # Seed baseline prices
    for i in range(10):
        sr.update_tick(84000.0 + i)

    # Sudden vertical surge of $1500 (1.8%) within 5 min
    res = sr.evaluate(
        spot=85500.0,
        vwap=84200.0,
        dist_vwap_atr=3.2,
        atr14=250.0,
        rvol=2.5,
        norm_delta=0.40,
        delta_5m=150.0,
        oi_change_5m_pct=-1.5
    )
    assert res["is_spike"] is True
    # VWAP distance > 2.5 ATRs and negative OI should trigger exhaustion risk
    assert res["state"] in (SpikeState.SPIKE_DETECTED, SpikeState.EXHAUSTION_RISK)


def test_regime_engine_hysteresis():
    re = MarketRegimeEngine()
    re.hysteresis_threshold = 2

    # Initial state
    out = re.evaluate_regime(
        spot=85000.0,
        vwap=84500.0,
        dist_vwap_atr=1.5,
        ema21=84800.0,
        ema50=84500.0,
        ema200=83000.0,
        adx14=30.0,
        plus_di=28.0,
        minus_di=12.0,
        realized_vol=40.0
    )
    # 1st evaluation sets candidate
    assert re.candidate_count == 1
    # 2nd evaluation confirms state transition
    out = re.evaluate_regime(
        spot=85000.0,
        vwap=84500.0,
        dist_vwap_atr=1.5,
        ema21=84800.0,
        ema50=84500.0,
        ema200=83000.0,
        adx14=30.0,
        plus_di=28.0,
        minus_di=12.0,
        realized_vol=40.0
    )
    assert out["regime"] == MarketRegime.TREND_UP.value
