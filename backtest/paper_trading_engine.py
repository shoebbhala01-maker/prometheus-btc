"""
PROMETHEUS BTC TERMINAL: Real-Time Paper Trading Engine
Simulates real-time execution against live bid/ask spreads.
Tracks stops, targets, MFE/MAE, frictions, and persists trade audit trail in SQLite.
"""

from typing import Dict, List, Optional, Any
import time
import uuid

from config.settings import config
from database.db_manager import db


class PaperTradingEngine:
    def __init__(self):
        self.active_position: Optional[Dict[str, Any]] = None
        self.closed_trades: List[Dict[str, Any]] = []
        self.equity = config.risk.account_capital
        self.realized_pnl = 0.0

    def evaluate_live_market(
        self,
        best_bid: float,
        best_ask: float,
        setup_decision: Dict[str, Any],
        regime: str,
        atr: float
    ) -> Dict[str, Any]:
        """
        Manages active paper position lifecycle and evaluates new entry triggers.
        """
        now = time.time()
        mid_price = (best_bid + best_ask) / 2.0 if (best_bid + best_ask) > 0 else 0.0
        contract_mult = config.risk.contract_value_btc

        # 1. Update Active Position
        if self.active_position is not None:
            pos = self.active_position
            direction = pos["direction"]
            entry_p = pos["entry_price"]
            contracts = pos["size_contracts"]

            # Current price for valuation: Bid if Long, Ask if Short
            cur_p = best_bid if direction == "BUY" else best_ask
            gross_unrealized = ((cur_p - entry_p) if direction == "BUY" else (entry_p - cur_p)) * contracts * contract_mult
            pos["unrealized_pnl"] = round(gross_unrealized, 2)
            pos["current_price"] = cur_p

            # Update MFE / MAE
            if direction == "BUY":
                pos["mfe"] = max(pos["mfe"], best_bid - entry_p)
                pos["mae"] = min(pos["mae"], best_bid - entry_p)
            else:
                pos["mfe"] = max(pos["mfe"], entry_p - best_ask)
                pos["mae"] = min(pos["mae"], entry_p - best_ask)

            # Check Stop Loss Trigger
            is_stop_hit = (best_bid <= pos["stop_loss"]) if direction == "BUY" else (best_ask >= pos["stop_loss"])
            # Check Target Trigger
            is_target_hit = (best_bid >= pos["target1"]) if direction == "BUY" else (best_ask <= pos["target1"])

            if is_stop_hit or is_target_hit:
                exit_price = best_bid if direction == "BUY" else best_ask
                exit_reason = "STOP_LOSS" if is_stop_hit else "TARGET"
                self._close_position(exit_price, exit_reason)

        # 2. Check for New Entry if flat
        elif setup_decision.get("decision") in ("LONG SETUP", "SHORT SETUP"):
            direction = setup_decision.get("direction")
            fill_price = best_ask if direction == "BUY" else best_bid  # Realistic crossing of the spread

            stop_loss = fill_price - (1.5 * atr) if direction == "BUY" else fill_price + (1.5 * atr)
            target1 = fill_price + (2.5 * atr) if direction == "BUY" else fill_price - (2.5 * atr)
            target2 = fill_price + (4.0 * atr) if direction == "BUY" else fill_price - (4.0 * atr)

            risk_budget = self.equity * (config.risk.max_risk_per_trade_pct / 100.0)
            stop_dist = abs(fill_price - stop_loss)
            loss_per_contract = (stop_dist + (fill_price * config.risk.futures_taker_fee * 2.0)) * contract_mult
            contracts = max(1, int(risk_budget / loss_per_contract)) if loss_per_contract > 0 else 1

            trade_id = f"PT-{int(now)}-{uuid.uuid4().hex[:6]}"
            entry_fee = fill_price * config.risk.futures_taker_fee * contracts * contract_mult

            self.active_position = {
                "trade_id": trade_id,
                "symbol": config.default_perp_symbol,
                "direction": direction,
                "entry_time": int(now),
                "entry_price": round(fill_price, 1),
                "current_price": round(fill_price, 1),
                "size_contracts": contracts,
                "btc_size": round(contracts * contract_mult, 4),
                "stop_loss": round(stop_loss, 1),
                "target1": round(target1, 1),
                "target2": round(target2, 1),
                "status": "OPEN",
                "setup_score": setup_decision.get("final_score", 0.0),
                "regime_at_entry": regime,
                "entry_fee": round(entry_fee, 2),
                "unrealized_pnl": 0.0,
                "mfe": 0.0,
                "mae": 0.0
            }

            db.log_audit_event("PAPER_ENTRY", "PaperTrader", f"Opened {direction} {contracts} contracts @ ${fill_price:.1f}")

        return self.get_summary()

    def _close_position(self, exit_price: float, reason: str):
        if not self.active_position:
            return

        pos = self.active_position
        contracts = pos["size_contracts"]
        contract_mult = config.risk.contract_value_btc
        direction = pos["direction"]

        price_diff = (exit_price - pos["entry_price"]) if direction == "BUY" else (pos["entry_price"] - exit_price)
        gross_pnl = price_diff * contracts * contract_mult
        exit_fee = exit_price * config.risk.futures_taker_fee * contracts * contract_mult
        total_fees = pos["entry_fee"] + exit_fee
        net_pnl = gross_pnl - total_fees

        pos["exit_time"] = int(time.time())
        pos["exit_price"] = round(exit_price, 1)
        pos["status"] = "CLOSED"
        pos["exit_reason"] = reason
        pos["gross_pnl"] = round(gross_pnl, 2)
        pos["total_fees"] = round(total_fees, 2)
        pos["slippage_cost"] = 0.0
        pos["net_pnl"] = round(net_pnl, 2)

        self.equity += net_pnl
        self.realized_pnl += net_pnl
        self.closed_trades.insert(0, pos)
        if len(self.closed_trades) > 50:
            self.closed_trades.pop()

        # Persist to database
        db.insert_paper_trade(pos)
        db.log_audit_event("PAPER_EXIT", "PaperTrader", f"Closed {direction} @ ${exit_price:.1f} ({reason}), Net PnL: ${net_pnl:+.2f}")

        self.active_position = None

    def get_summary(self) -> Dict[str, Any]:
        return {
            "account_equity": round(self.equity, 2),
            "realized_pnl": round(self.realized_pnl, 2),
            "active_position": self.active_position,
            "closed_trades_count": len(self.closed_trades),
            "closed_trades": self.closed_trades[:15]
        }


paper_trader = PaperTradingEngine()
