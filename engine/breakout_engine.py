"""
PROMETHEUS BTC TERMINAL: 8-Stage Breakout & Breakdown Engine
Multi-factor state machine with ATR buffers, confirmed candle closes, retest acceptance, and fakeout trap detection.
"""

from typing import Dict, List, Optional, Any, Tuple
import time

from config.constants import BreakoutStage, TradeDirection


class BreakoutEngine:
    def __init__(self):
        self.stage = BreakoutStage.RANGE_IDENTIFIED
        self.direction = TradeDirection.NONE
        self.reference_level = 0.0
        self.level_name = "NONE"
        self.trigger_time = 0.0
        self.retest_price = 0.0
        self.failed_reason = ""
        self.history: List[Dict[str, Any]] = []

    def evaluate(
        self,
        spot: float,
        last_closed_candle: Dict[str, Any],
        key_resistance: float,
        key_support: float,
        res_name: str,
        sup_name: str,
        atr14: float,
        rvol: float,
        norm_delta: float,
        oi_change_pct: float
    ) -> Dict[str, Any]:
        """
        Evaluates potential breakout or breakdown against resistance/support levels.
        """
        if spot <= 0 or key_resistance <= 0 or key_support <= 0:
            return self._build_output(reasons=["Key levels not yet identified"])

        buffer = max(5.0, 0.20 * atr14)  # Dynamic ATR buffer
        c_close = float(last_closed_candle.get("close", spot))
        c_high = float(last_closed_candle.get("high", spot))
        c_low = float(last_closed_candle.get("low", spot))
        reasons = []

        # 1. State: RANGE_IDENTIFIED
        if self.stage == BreakoutStage.RANGE_IDENTIFIED:
            # Check approaching
            if (key_resistance - spot) <= (0.5 * atr14) and spot < key_resistance:
                self.stage = BreakoutStage.LEVEL_APPROACHING
                self.direction = TradeDirection.BUY
                self.reference_level = key_resistance
                self.level_name = res_name
                reasons.append(f"Price approaching resistance {res_name} (${key_resistance:.1f})")
            elif (spot - key_support) <= (0.5 * atr14) and spot > key_support:
                self.stage = BreakoutStage.LEVEL_APPROACHING
                self.direction = TradeDirection.SELL
                self.reference_level = key_support
                self.level_name = sup_name
                reasons.append(f"Price approaching support {sup_name} (${key_support:.1f})")
            else:
                reasons.append(f"Price consolidating between ${key_support:.1f} and ${key_resistance:.1f}")

        # 2. State: LEVEL_APPROACHING
        elif self.stage == BreakoutStage.LEVEL_APPROACHING:
            if self.direction == TradeDirection.BUY:
                if spot > self.reference_level:
                    self.stage = BreakoutStage.BREAKOUT_ATTEMPT
                    self.trigger_time = time.time()
                    reasons.append(f"Live price attempting breakout above {self.level_name}")
                elif spot < (self.reference_level - 1.5 * atr14):
                    self.stage = BreakoutStage.RANGE_IDENTIFIED
                    reasons.append("Price pulled back from resistance")
            elif self.direction == TradeDirection.SELL:
                if spot < self.reference_level:
                    self.stage = BreakoutStage.BREAKOUT_ATTEMPT
                    self.trigger_time = time.time()
                    reasons.append(f"Live price attempting breakdown below {self.level_name}")
                elif spot > (self.reference_level + 1.5 * atr14):
                    self.stage = BreakoutStage.RANGE_IDENTIFIED
                    reasons.append("Price bounced back from support")

        # 3. State: BREAKOUT_ATTEMPT
        elif self.stage == BreakoutStage.BREAKOUT_ATTEMPT:
            if self.direction == TradeDirection.BUY:
                if c_close > (self.reference_level + buffer):
                    self.stage = BreakoutStage.BREAKOUT_CANDLE_CLOSED
                    reasons.append(f"Confirmed candle closed above {self.level_name} (${c_close:.1f} > ${self.reference_level + buffer:.1f})")
                elif spot < (self.reference_level - buffer):
                    self.stage = BreakoutStage.FAILED_BREAKOUT
                    self.failed_reason = "Price rejected at resistance; wick rejection"
                    reasons.append(self.failed_reason)
            elif self.direction == TradeDirection.SELL:
                if c_close < (self.reference_level - buffer):
                    self.stage = BreakoutStage.BREAKOUT_CANDLE_CLOSED
                    reasons.append(f"Confirmed candle closed below {self.level_name} (${c_close:.1f} < ${self.reference_level - buffer:.1f})")
                elif spot > (self.reference_level + buffer):
                    self.stage = BreakoutStage.FAILED_BREAKOUT
                    self.failed_reason = "Price rejected at support; lower wick bounce"
                    reasons.append(self.failed_reason)

        # 4. State: BREAKOUT_CANDLE_CLOSED
        elif self.stage == BreakoutStage.BREAKOUT_CANDLE_CLOSED:
            # Check volume & delta confirmation
            is_vol_confirmed = rvol >= 1.4
            is_delta_confirmed = (norm_delta > 0.15) if self.direction == TradeDirection.BUY else (norm_delta < -0.15)

            if is_vol_confirmed and is_delta_confirmed:
                self.stage = BreakoutStage.RETEST_OR_ACCEPTANCE
                reasons.append("Volume expansion (RVOL > 1.4) and aggressive taker delta confirm move")
            elif is_vol_confirmed or is_delta_confirmed:
                self.stage = BreakoutStage.CONFIRMATION_PENDING
                reasons.append("Partial confirmation; awaiting secondary order flow or retest")
            else:
                self.stage = BreakoutStage.CONFIRMATION_PENDING
                reasons.append("Candle closed beyond level but volume/delta expansion is weak")

        # 5. State: CONFIRMATION_PENDING
        elif self.stage == BreakoutStage.CONFIRMATION_PENDING:
            if self.direction == TradeDirection.BUY:
                if spot < self.reference_level - buffer:
                    self.stage = BreakoutStage.FAILED_BREAKOUT
                    self.failed_reason = "Bull trap detected: Price collapsed back inside range"
                    reasons.append(self.failed_reason)
                elif c_close > self.reference_level + (0.5 * atr14):
                    self.stage = BreakoutStage.CONFIRMED
                    reasons.append("Sustained acceptance above broken resistance")
            elif self.direction == TradeDirection.SELL:
                if spot > self.reference_level + buffer:
                    self.stage = BreakoutStage.FAILED_BREAKOUT
                    self.failed_reason = "Bear trap detected: Price reclaimed prior support"
                    reasons.append(self.failed_reason)
                elif c_close < self.reference_level - (0.5 * atr14):
                    self.stage = BreakoutStage.CONFIRMED
                    reasons.append("Sustained acceptance below broken support")

        # 6. State: RETEST_OR_ACCEPTANCE
        elif self.stage == BreakoutStage.RETEST_OR_ACCEPTANCE:
            if self.direction == TradeDirection.BUY:
                # Retest is healthy if price tests broken level and holds above it
                if self.reference_level - buffer <= spot <= self.reference_level + buffer:
                    reasons.append(f"Testing broken level ${self.reference_level:.1f} for support")
                elif spot > self.reference_level + buffer:
                    self.stage = BreakoutStage.CONFIRMED
                    reasons.append("Retest held successfully; continuation departs level")
                elif spot < self.reference_level - (1.0 * atr14):
                    self.stage = BreakoutStage.FAILED_BREAKOUT
                    self.failed_reason = "Retest failed: Price fell deeply back into prior range"
                    reasons.append(self.failed_reason)
            elif self.direction == TradeDirection.SELL:
                if self.reference_level - buffer <= spot <= self.reference_level + buffer:
                    reasons.append(f"Testing broken level ${self.reference_level:.1f} for resistance")
                elif spot < self.reference_level - buffer:
                    self.stage = BreakoutStage.CONFIRMED
                    reasons.append("Retest held successfully; breakdown continuation confirmed")
                elif spot > self.reference_level + (1.0 * atr14):
                    self.stage = BreakoutStage.FAILED_BREAKOUT
                    self.failed_reason = "Retest failed: Price spiked deeply back into prior range"
                    reasons.append(self.failed_reason)

        # 7. State: CONFIRMED or FAILED_BREAKOUT
        elif self.stage in (BreakoutStage.CONFIRMED, BreakoutStage.FAILED_BREAKOUT, BreakoutStage.INVALIDATED):
            # Check for reset after 15 minutes or significant displacement
            if abs(spot - self.reference_level) > (3.0 * atr14):
                self.stage = BreakoutStage.RANGE_IDENTIFIED
                self.direction = TradeDirection.NONE
                reasons.append("Resetting breakout engine after move completed")

        return self._build_output(reasons, spot, atr14)

    def _build_output(self, reasons: List[str], spot: float = 0.0, atr: float = 0.0) -> Dict[str, Any]:
        is_confirmed = (self.stage == BreakoutStage.CONFIRMED)
        is_trap = (self.stage == BreakoutStage.FAILED_BREAKOUT)

        stop_loss = 0.0
        target = 0.0
        rr_ratio = 0.0

        if self.direction == TradeDirection.BUY and self.reference_level > 0 and atr > 0:
            stop_loss = round(self.reference_level - (1.2 * atr), 1)
            target = round(spot + (2.5 * atr), 1)
            risk = max(1.0, spot - stop_loss)
            reward = max(1.0, target - spot)
            rr_ratio = round(reward / risk, 2)
        elif self.direction == TradeDirection.SELL and self.reference_level > 0 and atr > 0:
            stop_loss = round(self.reference_level + (1.2 * atr), 1)
            target = round(spot - (2.5 * atr), 1)
            risk = max(1.0, stop_loss - spot)
            reward = max(1.0, spot - target)
            rr_ratio = round(reward / risk, 2)

        return {
            "stage": self.stage.value,
            "direction": self.direction.value,
            "reference_level": round(self.reference_level, 1),
            "level_name": self.level_name,
            "is_confirmed": is_confirmed,
            "is_failed_trap": is_trap,
            "stop_loss_proposal": stop_loss,
            "target_proposal": target,
            "risk_reward_ratio": rr_ratio,
            "invalidation_level": stop_loss,
            "failed_reason": self.failed_reason if is_trap else "",
            "reasons": reasons
        }


breakout_engine = BreakoutEngine()
