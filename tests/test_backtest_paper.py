"""
Test Suite 5: Backtesting Walk-Forward & Paper Trading Accounting
"""

import pytest
from backtest.backtest_engine import BacktestEngine
from backtest.paper_trading_engine import PaperTradingEngine


def test_backtest_walkforward_run():
    be = BacktestEngine(initial_capital=10000.0)
    # Generate 100 synthetic 5m candles
    base_t = 1700000000
    candles = []
    p = 80000.0
    for i in range(100):
        # Trending upward move with occasional pullbacks
        p += 20.0 if i % 4 != 0 else -15.0
        candles.append({
            "time": base_t + (i * 300),
            "open": p - 5.0,
            "high": p + 15.0,
            "low": p - 10.0,
            "close": p,
            "volume": 25.0 + (i % 5)
        })

    res = be.run_backtest(candles, min_setup_score=60.0)
    assert res["status"] == "SUCCESS"
    assert "metrics" in res
    assert "total_trades" in res["metrics"]
    assert "equity_curve" in res


def test_paper_trading_lifecycle():
    pt = PaperTradingEngine()
    pt.equity = 10000.0

    # 1. Trigger Long Setup
    mock_decision = {
        "decision": "LONG SETUP",
        "direction": "BUY",
        "final_score": 82.0
    }
    pt.evaluate_live_market(
        best_bid=85000.0,
        best_ask=85001.0,
        setup_decision=mock_decision,
        regime="TREND_UP",
        atr=200.0
    )
    assert pt.active_position is not None
    pos = pt.active_position
    assert pos["direction"] == "BUY"
    assert pos["entry_price"] == 85001.0  # Crosses the ask
    assert pos["stop_loss"] < 85001.0
    assert pos["target1"] > 85001.0

    # 2. Simulate price advancing to target
    target_p = pos["target1"] + 10.0
    pt.evaluate_live_market(
        best_bid=target_p,
        best_ask=target_p + 1.0,
        setup_decision={"decision": "WAIT"},
        regime="TREND_UP",
        atr=200.0
    )
    # Position should be closed on target
    assert pt.active_position is None
    assert len(pt.closed_trades) == 1
    assert pt.closed_trades[0]["exit_reason"] == "TARGET"
    assert pt.closed_trades[0]["net_pnl"] > 0
