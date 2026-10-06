import pytest
import time
from datetime import datetime, timezone

from config.constants import MarketBattleState
from engine.market_battle_engine import (
    BtcMarketBattleEngine,
    BtcTargetStep,
    BtcConditionalScenarioItem,
    btc_market_battle_engine
)


@pytest.fixture
def engine():
    return BtcMarketBattleEngine()


def test_basic_evaluation_output_structure(engine):
    """Verifies that evaluate_battle returns all required intelligence layers."""
    res = engine.evaluate_battle(
        spot=85000.0,
        vwap=84800.0,
        mark_price=85010.0,
        funding_rate=0.0001,
        cvd=15.0,
        orderbook_imbalance=0.25,
        rvol=1.4,
        day_high=85500.0,
        day_low=84200.0,
        range_high=85400.0,
        range_low=84400.0,
        closest_support=84500.0,
        closest_resistance=85300.0,
        top_traders_ls_ratio=1.35,
        is_live=True
    )

    required_keys = [
        "battle_state", "battle_state_desc", "clock_phase",
        "participant_layers", "buyer_pressure", "seller_pressure",
        "buyer_breakdown", "seller_breakdown", "pressure_change",
        "battle_score", "absorption", "divergence", "target_ladder",
        "scenarios", "who_is_winning", "buyers_route", "sellers_route",
        "next_decisive_event", "thirty_second_read", "desi_answers"
    ]
    for key in required_keys:
        assert key in res, f"Missing key '{key}' in battle evaluation output"

    # Buyer and Seller pressure must be within 0-100 range
    assert 0.0 <= res["buyer_pressure"] <= 100.0
    assert 0.0 <= res["seller_pressure"] <= 100.0


def test_battle_score_and_classifications(engine):
    """Verifies classification logic for net buyer/seller advantage."""
    # Strong buyer advantage: net >= 25
    c1 = engine._calculate_battle_score(75.0, 35.0)
    assert c1["net_pressure"] == 40.0
    assert c1["classification"] == "STRONG BUYER ADVANTAGE"

    # Buyer advantage: net between 10 and 24
    c2 = engine._calculate_battle_score(60.0, 45.0)
    assert c2["net_pressure"] == 15.0
    assert c2["classification"] == "BUYER ADVANTAGE"

    # Balanced: net between -9 and +9
    c3 = engine._calculate_battle_score(50.0, 52.0)
    assert c3["net_pressure"] == -2.0
    assert c3["classification"] == "BALANCED"

    # Seller advantage: net between -10 and -24
    c4 = engine._calculate_battle_score(35.0, 50.0)
    assert c4["net_pressure"] == -15.0
    assert c4["classification"] == "SELLER ADVANTAGE"

    # Strong seller advantage: net <= -25
    c5 = engine._calculate_battle_score(25.0, 65.0)
    assert c5["net_pressure"] == -40.0
    assert c5["classification"] == "STRONG SELLER ADVANTAGE"


def test_pressure_deltas_over_time(engine):
    """Tests multi-timeframe rolling pressure history deltas."""
    base_t = 1700000000.0

    # 1. Feed initial baseline
    engine.evaluate_battle(
        spot=85000.0, vwap=85000.0, mark_price=85000.0, funding_rate=0.0001,
        cvd=0.0, orderbook_imbalance=0.0, rvol=1.0,
        day_high=85500.0, day_low=84500.0, range_high=85400.0, range_low=84600.0,
        closest_support=84500.0, closest_resistance=85500.0,
        now_ts=base_t
    )

    # 2. Feed surging buyer pressure 30 seconds later
    res_30s = engine.evaluate_battle(
        spot=85350.0, vwap=85020.0, mark_price=85360.0, funding_rate=0.0002,
        cvd=35.0, orderbook_imbalance=0.45, rvol=2.2,
        day_high=85500.0, day_low=84500.0, range_high=85400.0, range_low=84600.0,
        closest_support=84500.0, closest_resistance=85500.0,
        now_ts=base_t + 30.0
    )

    deltas = res_30s["pressure_change"]["deltas"]
    assert "30s" in deltas
    assert "60s" in deltas
    assert deltas["30s"]["buy"] > 0
    assert "MOMENTUM" in res_30s["pressure_change"]["momentum_label"] or "BUYERS" in res_30s["pressure_change"]["momentum_label"]


def test_wyckoff_absorption_support_and_resistance(engine):
    """Tests Wyckoff absorption detection on support floor defense."""
    # Near support ($84,000), spot=$84,020, heavy seller pressure, high rvol
    abs_res = engine._detect_absorption(
        spot=84020.0,
        day_high=85500.0,
        day_low=84000.0,
        closest_resistance=85000.0,
        closest_support=84000.0,
        rvol=1.6,
        buyer_pressure=40.0,
        seller_pressure=65.0,
        cvd=-15.0
    )
    assert abs_res["is_detected"] is True
    assert abs_res["side"] == "BUYER"
    assert abs_res["level"] == 84000.0


def test_positioning_divergence(engine):
    """Tests Whale vs Retail positioning divergence detection."""
    # Scenario: Price & buyers surging above VWAP, but Top traders heavily shorting + negative funding (Short Squeeze setup)
    div = engine._detect_positioning_divergence(
        funding_rate=-0.0002,
        top_traders_ls_ratio=0.65,
        spot=85200.0,
        vwap=85000.0,
        cvd=25.0,
        buyer_pressure=68.0,
        seller_pressure=32.0
    )
    assert div["is_divergent"] is True
    assert "SHORT SQUEEZE" in div["headline"]
    assert len(div["explanations"]) > 0


def test_target_ladder_structure(engine):
    """Verifies that upside and downside target ladders are constructed properly."""
    res = engine.evaluate_battle(
        spot=85000.0,
        vwap=84800.0,
        mark_price=85000.0,
        funding_rate=0.0001,
        cvd=10.0,
        orderbook_imbalance=0.1,
        rvol=1.2,
        day_high=86000.0,
        day_low=84000.0,
        range_high=85800.0,
        range_low=84200.0,
        closest_support=84600.0,
        closest_resistance=85400.0
    )

    ladder = res["target_ladder"]
    assert "upside_path" in ladder
    assert "downside_path" in ladder
    assert len(ladder["upside_path"]) >= 2
    assert len(ladder["downside_path"]) >= 2

    # Check upside target fields
    step0 = ladder["upside_path"][0]
    for prop in ["level", "type", "strength", "distance_pts", "confidence_label", "confidence_score"]:
        assert prop in step0


def test_conditional_scenarios(engine):
    """Verifies that 3 conditional scenarios exist and enforce 'No Prediction Without Condition'."""
    res = engine.evaluate_battle(
        spot=85000.0,
        vwap=84850.0,
        mark_price=85000.0,
        funding_rate=0.0001,
        cvd=5.0,
        orderbook_imbalance=0.1,
        rvol=1.0,
        day_high=85500.0,
        day_low=84500.0,
        range_high=85400.0,
        range_low=84600.0,
        closest_support=84600.0,
        closest_resistance=85400.0
    )

    scenarios = res["scenarios"]
    assert len(scenarios) == 3
    for sc in scenarios:
        assert "name" in sc
        assert "confidence_label" in sc
        assert "confidence_score" in sc
        assert "trigger" in sc
        assert "invalidation" in sc
        assert "evidence_required" in sc


def test_desi_qa_and_30s_read(engine):
    """Verifies Desi Q&A and 30-Second Cockpit Read formats."""
    res = engine.evaluate_battle(
        spot=85000.0,
        vwap=84900.0,
        mark_price=85000.0,
        funding_rate=0.0001,
        cvd=8.0,
        orderbook_imbalance=0.2,
        rvol=1.1,
        day_high=85600.0,
        day_low=84400.0,
        range_high=85500.0,
        range_low=84500.0,
        closest_support=84500.0,
        closest_resistance=85500.0
    )

    desi = res["desi_answers"]
    assert "abhi_kya_ho_raha_hai" in desi
    assert "kaun_jeet_raha_hai" in desi
    assert "kya_invalidation_hai" in desi
    assert "abhi_trade_ya_wait" in desi

    cockpit = res["thirty_second_read"]
    assert "price" in cockpit
    assert "buy_pressure" in cockpit
    assert "sell_pressure" in cockpit
    assert "current_winner" in cockpit
    assert "action" in cockpit


def test_crypto_clock_sessions(engine):
    """Verifies 24/7 session detection for Asia, London, NY, and Weekends."""
    # Weekend test (Saturday: weekday 5)
    dt_sat = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)
    sat_clock = engine._evaluate_crypto_clock(dt_sat, is_live=True)
    assert sat_clock["is_weekend"] is True
    assert "WEEKEND" in sat_clock["phase_name"]

    # London session (weekday 0, hour 10 UTC)
    dt_mon_london = datetime(2026, 10, 12, 10, 0, tzinfo=timezone.utc)
    london_clock = engine._evaluate_crypto_clock(dt_mon_london, is_live=True)
    assert london_clock["is_weekend"] is False
    assert "LONDON" in london_clock["phase_name"]

    # US / NY session (weekday 1, hour 16 UTC)
    dt_ny = datetime(2026, 10, 13, 16, 0, tzinfo=timezone.utc)
    ny_clock = engine._evaluate_crypto_clock(dt_ny, is_live=True)
    assert "NEW YORK" in ny_clock["phase_name"]
