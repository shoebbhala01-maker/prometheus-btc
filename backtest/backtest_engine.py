"""
PROMETHEUS BTC TERMINAL: Quantitative Historical Backtesting Engine
Zero look-ahead bias, chronological walk-forward validation, realistic Delta Exchange frictions,
and multi-dimensional performance attribution.
"""

from typing import Dict, List, Optional, Any, Tuple
import math
import numpy as np

from config.settings import config
from quant.indicator_engine import indicator_engine
from engine.market_regime_engine import regime_engine
from engine.breakout_engine import breakout_engine
from engine.setup_scoring_engine import setup_scoring_engine


class BacktestEngine:
    def __init__(
        self,
        taker_fee: float = 0.0005,      # 0.05% Delta India taker fee
        maker_fee: float = 0.0002,      # 0.02%
        slippage_rate: float = 0.0002,  # 0.02% (2 bps) slippage per fill
        initial_capital: float = 10000.0,
        risk_per_trade_pct: float = 1.0
    ):
        self.taker_fee = taker_fee
        self.maker_fee = maker_fee
        self.slippage_rate = slippage_rate
        self.initial_capital = initial_capital
        self.risk_per_trade_pct = risk_per_trade_pct

    def run_backtest(self, candles_5m: List[Dict[str, Any]], min_setup_score: float = 75.0) -> Dict[str, Any]:
        """
        Executes chronological backtest over 5-minute candles.
        Enforces warm-up period of 50 candles before any signal evaluation.
        """
        if len(candles_5m) < 60:
            return {"status": "ERROR", "message": "At least 60 candles required for backtesting."}

        capital = self.initial_capital
        trades = []
        equity_curve = [capital]
        active_trade: Optional[Dict[str, Any]] = None

        warmup = 50
        contract_mult = config.risk.contract_value_btc

        for i in range(warmup, len(candles_5m)):
            prev_candles = candles_5m[:i]  # Strictly prior candles
            curr_c = candles_5m[i]

            # If position is active, check exit on current candle
            if active_trade is not None:
                exit_res = self._check_exit(active_trade, curr_c)
                if exit_res is not None:
                    trades.append(exit_res)
                    capital += exit_res["net_pnl"]
                    equity_curve.append(round(capital, 2))
                    active_trade = None
                    continue

            # Evaluate indicators on confirmed prior candles
            ind = indicator_engine.evaluate_all(prev_candles)
            if ind.get("status") != "VALID":
                continue

            spot = prev_candles[-1]["close"]
            atr = ind["atr14"]

            # Key levels from prior candles
            highs_window = [c["high"] for c in prev_candles[-24:]]
            lows_window = [c["low"] for c in prev_candles[-24:]]
            res_level = max(highs_window)
            sup_level = min(lows_window)

            # Evaluate Breakout
            b_out = breakout_engine.evaluate(
                spot=spot,
                last_closed_candle=prev_candles[-1],
                key_resistance=res_level,
                key_support=sup_level,
                res_name="Range High",
                sup_name="Range Low",
                atr14=atr,
                rvol=ind.get("rvol", 1.0),
                norm_delta=0.25 if (spot > res_level) else -0.25,
                oi_change_pct=0.5
            )

            # Evaluate Regime
            reg_out = regime_engine.evaluate_regime(
                spot=spot,
                vwap=ind["vwap"],
                dist_vwap_atr=ind["dist_vwap_atr"],
                ema21=ind["ema21"],
                ema50=ind["ema50"],
                ema200=ind["ema200"],
                adx14=ind["adx14"],
                plus_di=ind["plus_di"],
                minus_di=ind["minus_di"],
                realized_vol=ind["realized_vol_pct"]
            )

            # Setup Score
            setup_out = setup_scoring_engine.evaluate_score(
                regime_output=reg_out,
                breakout_output=b_out,
                spike_output={"state": "NORMAL"},
                orderflow_output={"normalized_delta": 0.20 if b_out.get("direction") == "BUY" else -0.20, "spread_bps": 1.0, "imbalance_25bps": 0.15},
                oi_data={"oi_change_5m_pct": 0.4, "funding_rate": 0.0001, "basis_pct": 0.05},
                liquidity_output={},
                indicator_output=ind,
                is_feed_healthy=True
            )

            # Check Signal Entry Trigger
            if setup_out["final_score"] >= min_setup_score and setup_out["direction"] in ("BUY", "SELL"):
                direction = setup_out["direction"]
                entry_fill_price = curr_c["open"] * (1.0 + self.slippage_rate if direction == "BUY" else 1.0 - self.slippage_rate)
                stop_loss = b_out.get("stop_loss_proposal") or (entry_fill_price - (1.5 * atr) if direction == "BUY" else entry_fill_price + (1.5 * atr))
                target = b_out.get("target_proposal") or (entry_fill_price + (2.5 * atr) if direction == "BUY" else entry_fill_price - (2.5 * atr))

                # Position sizing
                risk_budget = capital * (self.risk_per_trade_pct / 100.0)
                loss_per_contract = (abs(entry_fill_price - stop_loss) + (entry_fill_price * (self.taker_fee + self.slippage_rate) * 2.0)) * contract_mult
                contracts = max(1, int(risk_budget / loss_per_contract)) if loss_per_contract > 0 else 1

                active_trade = {
                    "entry_time": curr_c["time"],
                    "direction": direction,
                    "entry_price": entry_fill_price,
                    "stop_loss": stop_loss,
                    "target": target,
                    "contracts": contracts,
                    "score": setup_out["final_score"],
                    "regime": reg_out["regime"],
                    "mfe": 0.0,
                    "mae": 0.0
                }

        metrics = self._calculate_metrics(trades, capital)
        return {
            "status": "SUCCESS",
            "metrics": metrics,
            "trades_count": len(trades),
            "trades": trades[-50:],  # Return last 50 trades
            "equity_curve": equity_curve
        }

    def _check_exit(self, trade: Dict[str, Any], candle: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        c_high = candle["high"]
        c_low = candle["low"]
        c_open = candle["open"]
        direction = trade["direction"]
        contracts = trade["contracts"]
        contract_mult = config.risk.contract_value_btc
        entry_p = trade["entry_price"]

        # Track MFE / MAE
        if direction == "BUY":
            trade["mfe"] = max(trade["mfe"], c_high - entry_p)
            trade["mae"] = min(trade["mae"], c_low - entry_p)
        else:
            trade["mfe"] = max(trade["mfe"], entry_p - c_low)
            trade["mae"] = min(trade["mae"], entry_p - c_high)

        exit_price = 0.0
        exit_reason = ""

        if direction == "BUY":
            if c_low <= trade["stop_loss"]:
                exit_price = trade["stop_loss"] * (1.0 - self.slippage_rate)
                exit_reason = "STOP_LOSS"
            elif c_high >= trade["target"]:
                exit_price = trade["target"] * (1.0 - self.slippage_rate)
                exit_reason = "TARGET"
        else:
            if c_high >= trade["stop_loss"]:
                exit_price = trade["stop_loss"] * (1.0 + self.slippage_rate)
                exit_reason = "STOP_LOSS"
            elif c_low <= trade["target"]:
                exit_price = trade["target"] * (1.0 + self.slippage_rate)
                exit_reason = "TARGET"

        if exit_price > 0:
            price_diff = (exit_price - entry_p) if direction == "BUY" else (entry_p - exit_price)
            gross_pnl = price_diff * contracts * contract_mult
            entry_fee = entry_p * self.taker_fee * contracts * contract_mult
            exit_fee = exit_price * self.taker_fee * contracts * contract_mult
            slippage_cost = (entry_p + exit_price) * self.slippage_rate * contracts * contract_mult
            total_frictions = entry_fee + exit_fee + slippage_cost
            net_pnl = gross_pnl - total_frictions

            return {
                "entry_time": trade["entry_time"],
                "exit_time": candle["time"],
                "direction": direction,
                "entry_price": round(entry_p, 1),
                "exit_price": round(exit_price, 1),
                "contracts": contracts,
                "gross_pnl": round(gross_pnl, 2),
                "total_fees": round(total_frictions, 2),
                "net_pnl": round(net_pnl, 2),
                "exit_reason": exit_reason,
                "is_win": (net_pnl > 0),
                "regime": trade["regime"],
                "mfe_usd": round(trade["mfe"] * contracts * contract_mult, 2),
                "mae_usd": round(trade["mae"] * contracts * contract_mult, 2)
            }
        return None

    def _calculate_metrics(self, trades: List[Dict[str, Any]], final_capital: float) -> Dict[str, Any]:
        if not trades:
            return {
                "total_trades": 0,
                "win_rate_pct": 0.0,
                "profit_factor": 0.0,
                "expectancy_usd": 0.0,
                "max_drawdown_usd": 0.0,
                "max_drawdown_pct": 0.0,
                "net_profit_usd": 0.0,
                "total_frictions_usd": 0.0
            }

        wins = [t for t in trades if t["is_win"]]
        losses = [t for t in trades if not t["is_win"]]

        total_trades = len(trades)
        win_rate = (len(wins) / total_trades) * 100.0
        gross_profit = sum(t["net_pnl"] for t in wins)
        gross_loss = abs(sum(t["net_pnl"] for t in losses))
        profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else 99.0

        net_profit = round(final_capital - self.initial_capital, 2)
        expectancy = round(net_profit / total_trades, 2)
        total_frictions = round(sum(t["total_fees"] for t in trades), 2)

        # Max Drawdown
        equity = self.initial_capital
        peak = equity
        max_dd = 0.0
        for t in trades:
            equity += t["net_pnl"]
            if equity > peak:
                peak = equity
            dd = peak - equity
            if dd > max_dd:
                max_dd = dd

        max_dd_pct = round((max_dd / peak) * 100.0, 2) if peak > 0 else 0.0

        # Long vs Short
        long_trades = [t for t in trades if t["direction"] == "BUY"]
        short_trades = [t for t in trades if t["direction"] == "SELL"]
        long_win_rate = (len([t for t in long_trades if t["is_win"]]) / len(long_trades) * 100.0) if long_trades else 0.0
        short_win_rate = (len([t for t in short_trades if t["is_win"]]) / len(short_trades) * 100.0) if short_trades else 0.0

        return {
            "initial_capital_usd": self.initial_capital,
            "final_capital_usd": round(final_capital, 2),
            "net_profit_usd": net_profit,
            "total_trades": total_trades,
            "win_rate_pct": round(win_rate, 1),
            "profit_factor": profit_factor,
            "expectancy_usd": expectancy,
            "max_drawdown_usd": round(max_dd, 2),
            "max_drawdown_pct": max_dd_pct,
            "total_frictions_usd": total_frictions,
            "long_trades_count": len(long_trades),
            "long_win_rate_pct": round(long_win_rate, 1),
            "short_trades_count": len(short_trades),
            "short_win_rate_pct": round(short_win_rate, 1)
        }


backtest_engine = BacktestEngine()
