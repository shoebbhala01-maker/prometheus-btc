"""
PROMETHEUS BTC TERMINAL: Risk Governor & Position Sizing Engine
Enforces strict quantitative capital protection, daily drawdown caps, and contract sizing for Delta India.
Never places real orders. Purely risk-governed simulation.
"""

from typing import Dict, List, Optional, Any, Tuple
import time

from config.settings import config


class RiskGovernor:
    def __init__(self):
        self.account_equity = config.risk.account_capital
        self.daily_starting_equity = config.risk.account_capital
        self.daily_realized_pnl = 0.0
        self.consecutive_losses = 0
        self.cooldown_until_ts = 0.0
        self.active_positions_count = 0

    def evaluate_order(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        stop_loss: float,
        current_spread_bps: float,
        is_feed_healthy: bool = True
    ) -> Dict[str, Any]:
        """
        Validates risk constraints and computes position size in contracts (0.001 BTC per contract).
        """
        now = time.time()
        rejections = []

        # 1. Stale Feed Check
        if not is_feed_healthy:
            return self._reject(["Trade blocked: Exchange market data feed is stale or corrupted."])

        # 2. Cooldown Check
        if now < self.cooldown_until_ts:
            rem_min = round((self.cooldown_until_ts - now) / 60.0, 1)
            return self._reject([f"Trade blocked: Cooldown active after {config.risk.max_consecutive_losses} consecutive losses ({rem_min} min remaining)."])

        # 3. Max Daily Loss Check
        max_daily_loss = self.daily_starting_equity * (config.risk.max_daily_loss_pct / 100.0)
        if self.daily_realized_pnl <= -max_daily_loss:
            return self._reject([f"Trade blocked: Max daily drawdown limit reached (-${abs(self.daily_realized_pnl):.2f} / -${max_daily_loss:.2f})."])

        # 4. Max Concurrent Positions Check
        if self.active_positions_count >= config.risk.max_concurrent_positions:
            return self._reject([f"Trade blocked: Max concurrent positions limit ({config.risk.max_concurrent_positions}) reached."])

        # 5. Spread Limit Check
        if current_spread_bps > config.risk.max_slippage_bps:
            return self._reject([f"Trade blocked: Spread ({current_spread_bps:.1f} bps) exceeds maximum allowable threshold ({config.risk.max_slippage_bps:.1f} bps)."])

        # 6. Stop Loss Validity Check
        if stop_loss <= 0 or (direction == "BUY" and stop_loss >= entry_price) or (direction == "SELL" and stop_loss <= entry_price):
            return self._reject(["Trade blocked: Proposed stop loss is invalid relative to entry price."])

        # 7. Position Sizing Calculation
        risk_fraction = config.risk.max_risk_per_trade_pct / 100.0
        risk_amount_usd = self.account_equity * risk_fraction
        stop_distance_pts = abs(entry_price - stop_loss)

        # Loss per contract in USD:
        # Contract value = 0.001 BTC
        # Price diff loss = stop_distance_pts * 0.001
        # Round-trip taker fee: 2 * (entry_price * 0.0005 * 0.001)
        # Estimated slippage: 2 * (entry_price * 0.0002 * 0.001)
        contract_mult = config.risk.contract_value_btc
        price_loss_per_contract = stop_distance_pts * contract_mult
        fees_per_contract = (entry_price * config.risk.futures_taker_fee * 2.0) * contract_mult
        slippage_per_contract = (entry_price * 0.0002 * 2.0) * contract_mult

        total_loss_per_contract = price_loss_per_contract + fees_per_contract + slippage_per_contract

        if total_loss_per_contract <= 0:
            return self._reject(["Trade blocked: Calculated loss per contract is zero or negative."])

        contracts = int(risk_amount_usd / total_loss_per_contract)

        # Check minimum order size (1 contract = 0.001 BTC = ~$85)
        if contracts < 1:
            return self._reject([f"Trade blocked: Minimum contract size (1 contract) requires ${total_loss_per_contract:.2f} risk, exceeding max permitted risk (${risk_amount_usd:.2f})."])

        total_actual_risk = round(contracts * total_loss_per_contract, 2)
        btc_position_size = round(contracts * contract_mult, 4)
        notional_usd = round(contracts * contract_mult * entry_price, 2)

        return {
            "status": "APPROVED",
            "contracts": contracts,
            "btc_size": btc_position_size,
            "notional_usd": notional_usd,
            "max_risk_budget_usd": round(risk_amount_usd, 2),
            "estimated_loss_at_stop_usd": total_actual_risk,
            "estimated_fees_usd": round(contracts * fees_per_contract, 2),
            "estimated_slippage_usd": round(contracts * slippage_per_contract, 2),
            "account_equity": round(self.account_equity, 2),
            "daily_pnl": round(self.daily_realized_pnl, 2),
            "rejections": []
        }

    def record_trade_outcome(self, net_pnl: float):
        self.account_equity += net_pnl
        self.daily_realized_pnl += net_pnl

        if net_pnl < 0:
            self.consecutive_losses += 1
            if self.consecutive_losses >= config.risk.max_consecutive_losses:
                self.cooldown_until_ts = time.time() + (config.risk.cooldown_period_minutes * 60)
        else:
            self.consecutive_losses = 0

    def _reject(self, reasons: List[str]) -> Dict[str, Any]:
        return {
            "status": "REJECTED",
            "contracts": 0,
            "btc_size": 0.0,
            "notional_usd": 0.0,
            "rejections": reasons
        }


risk_governor = RiskGovernor()
