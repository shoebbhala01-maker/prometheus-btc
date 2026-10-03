"""
Test Suite 4: Risk Governor & Position Sizing
"""

import pytest
from engine.risk_governor import RiskGovernor


def test_position_sizing_calculation():
    rg = RiskGovernor()
    rg.account_equity = 10000.0  # $10k equity
    # 1% risk = $100
    # Entry: $85,000, Stop Loss: $84,500 ($500 stop distance)
    # Loss per contract = 500 * 0.001 BTC = $0.50 + fees & slippage ≈ $0.59
    # Expected contracts = int(100 / 0.59) ≈ 169 contracts (0.169 BTC)
    res = rg.evaluate_order(
        symbol="BTCUSD",
        direction="BUY",
        entry_price=85000.0,
        stop_loss=84500.0,
        current_spread_bps=1.0,
        is_feed_healthy=True
    )
    assert res["status"] == "APPROVED"
    assert res["contracts"] > 100
    assert res["estimated_loss_at_stop_usd"] <= 100.0
    assert res["btc_size"] == round(res["contracts"] * 0.001, 4)


def test_stale_feed_blocking():
    rg = RiskGovernor()
    res = rg.evaluate_order(
        symbol="BTCUSD",
        direction="BUY",
        entry_price=85000.0,
        stop_loss=84500.0,
        current_spread_bps=1.0,
        is_feed_healthy=False  # Stale feed
    )
    assert res["status"] == "REJECTED"
    assert any("stale" in r.lower() for r in res["rejections"])


def test_wide_spread_blocking():
    rg = RiskGovernor()
    res = rg.evaluate_order(
        symbol="BTCUSD",
        direction="BUY",
        entry_price=85000.0,
        stop_loss=84500.0,
        current_spread_bps=12.0,  # 12 bps > 5 bps limit
        is_feed_healthy=True
    )
    assert res["status"] == "REJECTED"
    assert any("spread" in r.lower() for r in res["rejections"])


def test_daily_drawdown_limit():
    rg = RiskGovernor()
    rg.daily_realized_pnl = -350.0  # > 3% on $10k
    res = rg.evaluate_order(
        symbol="BTCUSD",
        direction="BUY",
        entry_price=85000.0,
        stop_loss=84500.0,
        current_spread_bps=1.0,
        is_feed_healthy=True
    )
    assert res["status"] == "REJECTED"
    assert any("daily drawdown" in r.lower() for r in res["rejections"])
