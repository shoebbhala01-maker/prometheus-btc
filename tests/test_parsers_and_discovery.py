"""
Test Suite 2: Parsers, Orderflow, Discovery, and Derivatives Analytics
"""

import pytest
from quant.orderflow_engine import OrderflowEngine
from quant.options_analytics import options_analytics


def test_trade_aggressor_classification():
    of = OrderflowEngine()
    trades = [
        {"price": "84500.0", "size": 10.0, "buyer_role": "taker", "seller_role": "maker"}, # Buy
        {"price": "84501.0", "size": 5.0, "buyer_role": "taker", "seller_role": "maker"},  # Buy
        {"price": "84499.0", "size": 20.0, "buyer_role": "maker", "seller_role": "taker"}  # Sell
    ]
    res = of.process_trades(trades)
    assert res["buy_volume"] == 15.0
    assert res["sell_volume"] == 20.0
    assert res["volume_delta"] == -5.0
    # Normalized delta = -5 / 35 = -0.143
    assert abs(res["normalized_delta"] - (-0.143)) < 0.01
    assert res["cvd"] == -5.0


def test_orderbook_depth_and_imbalance():
    of = OrderflowEngine()
    mock_book = {
        "buy": [
            {"limit_price": "84500.0", "size": 1000},
            {"limit_price": "84490.0", "size": 2000},
        ],
        "sell": [
            {"limit_price": "84501.0", "size": 500},
            {"limit_price": "84510.0", "size": 1000},
        ]
    }
    res = of.update_orderbook(mock_book)
    assert res["best_bid"] == 84500.0
    assert res["best_ask"] == 84501.0
    assert res["spread"] == 1.0
    # More bids than asks => positive imbalance
    assert res["imbalance_25bps"] > 0.0


def test_perpetual_basis_formula():
    perp_price = 84600.0
    index_price = 84500.0
    basis_pts = perp_price - index_price
    basis_pct = 100.0 * (perp_price - index_price) / index_price
    assert basis_pts == 100.0
    assert round(basis_pct, 4) == round((100.0 / 84500.0) * 100.0, 4)


def test_max_pain_calculation():
    # Simple 3-strike ladder
    ladder = [
        {"strike": 80000.0, "call": {"oi": 10.0}, "put": {"oi": 50.0}},
        {"strike": 85000.0, "call": {"oi": 30.0}, "put": {"oi": 30.0}},
        {"strike": 90000.0, "call": {"oi": 60.0}, "put": {"oi": 5.0}},
    ]
    max_pain = options_analytics._calculate_max_pain(ladder)
    assert max_pain == 85000.0


def test_option_pnl_with_multiplier():
    # 1 contract of BTC option, multiplier = 0.001 BTC
    # Entry premium = $1,000, Exit premium = $1,500
    res = options_analytics.calculate_option_pnl(
        entry_price=1000.0,
        exit_price=1500.0,
        contracts=10,
        is_call=True,
        is_long=True
    )
    # Gross PnL = (1500 - 1000) * 10 * 0.001 = $5.00
    assert res["gross_pnl_usd"] == 5.00
    assert res["net_pnl_usd"] < 5.00  # Fees deducted
    assert res["btc_exposure"] == 0.010
