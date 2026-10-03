"""
PROMETHEUS BTC TERMINAL: Spike & Reversal Radar
Monitors 5-10 minute vertical thrusts, VWAP overextensions, CVD divergence, and exhaustion.
Transitions through 7 distinct risk states. Never front-runs without order-flow confirmation.
"""

from typing import Dict, List, Optional, Any, Tuple
from collections import deque
import time

from config.constants import SpikeState


class SpikeRadar:
    def __init__(self, history_len: int = 30):
        self.state = SpikeState.NORMAL
        self.price_history: deque = deque(maxlen=history_len)  # [(timestamp, price, volume), ...]
        self.spike_start_price = 0.0
        self.spike_direction = "NONE"
        self.spike_peak_price = 0.0
        self.spike_timestamp = 0.0
        self.outcomes_log: List[Dict[str, Any]] = []

    def update_tick(self, price: float, volume: float = 0.0):
        now = time.time()
        if price > 0:
            self.price_history.append((now, price, volume))

    def evaluate(
        self,
        spot: float,
        vwap: float,
        dist_vwap_atr: float,
        atr14: float,
        rvol: float,
        norm_delta: float,
        delta_5m: float,
        oi_change_5m_pct: float
    ) -> Dict[str, Any]:
        now = time.time()
        self.update_tick(spot)

        if len(self.price_history) < 6 or atr14 <= 0:
            return self._build_output(reasons=["Gathering price velocity history"])

        # Calculate 1m and 5m returns & velocities
        p_now = spot
        p_1m = self._get_price_seconds_ago(60)
        p_5m = self._get_price_seconds_ago(300)
        p_10m = self._get_price_seconds_ago(600)

        ret_1m_pct = ((p_now - p_1m) / p_1m) * 100.0 if p_1m > 0 else 0.0
        ret_5m_pct = ((p_now - p_5m) / p_5m) * 100.0 if p_5m > 0 else 0.0
        vel_5m_pct_min = ret_5m_pct / 5.0
        displacement_atr = abs(p_now - p_5m) / atr14 if atr14 > 0 else 0.0

        reasons = []

        # 1. State: NORMAL
        if self.state in (SpikeState.NORMAL, SpikeState.RESET):
            if displacement_atr >= 2.2 or abs(ret_5m_pct) >= 1.5:
                self.state = SpikeState.SPIKE_DETECTED
                self.spike_start_price = p_5m
                self.spike_direction = "UP" if ret_5m_pct > 0 else "DOWN"
                self.spike_timestamp = now
                self.spike_peak_price = p_now
                reasons.append(f"🚨 SPIKE DETECTED: Explosive displacement of {ret_5m_pct:+.2f}% ({displacement_atr:.1f} ATRs)")
            elif abs(vel_5m_pct_min) >= 0.25 and displacement_atr >= 1.5 and rvol >= 1.8:
                self.state = SpikeState.MOVE_ACCELERATING
                self.spike_start_price = p_5m
                self.spike_direction = "UP" if ret_5m_pct > 0 else "DOWN"
                self.spike_timestamp = now
                self.spike_peak_price = p_now
                reasons.append(f"Move accelerating rapidly: {ret_5m_pct:+.2f}% in 5m ({displacement_atr:.1f} ATRs), RVOL {rvol:.1f}x")
            else:
                self.state = SpikeState.NORMAL
                reasons.append(f"Price velocity normal ({vel_5m_pct_min:+.2f}%/min)")

        # 2. State: MOVE_ACCELERATING
        elif self.state == SpikeState.MOVE_ACCELERATING:
            if displacement_atr >= 2.2 or abs(ret_5m_pct) >= 1.5:
                self.state = SpikeState.SPIKE_DETECTED
                self.spike_peak_price = max(self.spike_peak_price, p_now) if self.spike_direction == "UP" else min(self.spike_peak_price, p_now)
                reasons.append(f"🚨 SPIKE DETECTED: Explosive displacement of {ret_5m_pct:+.2f}% ({displacement_atr:.1f} ATRs)")
            elif abs(vel_5m_pct_min) < 0.10:
                self.state = SpikeState.RESET
                reasons.append("Acceleration dissipated without reaching full spike thresholds")

        # 3. State: SPIKE_DETECTED
        elif self.state == SpikeState.SPIKE_DETECTED:
            # Update extreme peak
            if self.spike_direction == "UP":
                self.spike_peak_price = max(self.spike_peak_price, p_now)
            else:
                self.spike_peak_price = min(self.spike_peak_price, p_now)

            # Check Exhaustion Conditions
            # Extreme VWAP stretch (> 2.5 ATRs) or Order Flow Divergence
            is_vwap_stretched = abs(dist_vwap_atr) >= 2.5
            is_delta_diverging = (self.spike_direction == "UP" and norm_delta < -0.10) or (self.spike_direction == "DOWN" and norm_delta > 0.10)
            is_oi_collapsing = oi_change_5m_pct < -0.75  # Liquidation/short squeeze exhaustion

            if is_vwap_stretched or (is_delta_diverging and is_oi_collapsing):
                self.state = SpikeState.EXHAUSTION_RISK
                reasons.append(f"⚠️ EXHAUSTION RISK: VWAP distance {dist_vwap_atr:+.1f} ATRs, OI change {oi_change_5m_pct:+.1f}%")
                if is_delta_diverging:
                    reasons.append("Taker flow is already diverging from the price move!")
            elif (now - self.spike_timestamp) > 900:
                self.state = SpikeState.RESET
                reasons.append("Spike absorbed without exhaustion trigger; resetting")

        # 4. State: EXHAUSTION_RISK
        elif self.state == SpikeState.EXHAUSTION_RISK:
            # Check Reversal Risk: Price fails to hold extreme and begins retracing by > 0.4 ATR
            if self.spike_direction == "UP":
                pullback = self.spike_peak_price - p_now
                if pullback >= (0.4 * atr14) and norm_delta < 0:
                    self.state = SpikeState.REVERSAL_RISK
                    reasons.append(f"REVERSAL RISK: Price pulling back from peak ${self.spike_peak_price:.1f} with active seller taker delta")
            elif self.spike_direction == "DOWN":
                bounce = p_now - self.spike_peak_price
                if bounce >= (0.4 * atr14) and norm_delta > 0:
                    self.state = SpikeState.REVERSAL_RISK
                    reasons.append(f"REVERSAL RISK: Price bouncing from trough ${self.spike_peak_price:.1f} with active buyer taker delta")

        # 5. State: REVERSAL_RISK
        elif self.state == SpikeState.REVERSAL_RISK:
            # Reversal Confirmed when price retraces > 1.0 ATR from peak and delta is strongly opposite
            if self.spike_direction == "UP":
                pullback = self.spike_peak_price - p_now
                if pullback >= (1.0 * atr14) and delta_5m < 0:
                    self.state = SpikeState.REVERSAL_CONFIRMED
                    reasons.append("⚡ REVERSAL CONFIRMED: Deep rejection from high with sustained aggressive selling flow")
                elif p_now > self.spike_peak_price:
                    # New high invalidated exhaustion
                    self.state = SpikeState.SPIKE_DETECTED
                    self.spike_peak_price = p_now
                    reasons.append("Price pushed to new high, invalidating exhaustion premise")
            elif self.spike_direction == "DOWN":
                bounce = p_now - self.spike_peak_price
                if bounce >= (1.0 * atr14) and delta_5m > 0:
                    self.state = SpikeState.REVERSAL_CONFIRMED
                    reasons.append("⚡ REVERSAL CONFIRMED: Deep rejection from low with sustained aggressive buying flow")
                elif p_now < self.spike_peak_price:
                    self.state = SpikeState.SPIKE_DETECTED
                    self.spike_peak_price = p_now
                    reasons.append("Price flushed to new low, invalidating reversal premise")

        # 6. State: REVERSAL_CONFIRMED
        elif self.state == SpikeState.REVERSAL_CONFIRMED:
            if (now - self.spike_timestamp) > 1800:
                self.state = SpikeState.RESET
                reasons.append("Reversal cycle complete; resetting radar")

        return self._build_output(reasons, ret_1m_pct, ret_5m_pct, vel_5m_pct_min, displacement_atr)

    def _get_price_seconds_ago(self, seconds: float) -> float:
        now = time.time()
        target_t = now - seconds
        closest_p = self.price_history[0][1] if self.price_history else 0.0
        min_diff = float("inf")
        for t, p, _ in self.price_history:
            diff = abs(t - target_t)
            if diff < min_diff:
                min_diff = diff
                closest_p = p
        return closest_p

    def _build_output(
        self,
        reasons: List[str],
        ret_1m: float = 0.0,
        ret_5m: float = 0.0,
        vel_5m: float = 0.0,
        displacement_atr: float = 0.0
    ) -> Dict[str, Any]:
        return {
            "state": self.state.value,
            "spike_direction": self.spike_direction,
            "return_1m_pct": round(ret_1m, 2),
            "return_5m_pct": round(ret_5m, 2),
            "velocity_5m_pct_per_min": round(vel_5m, 3),
            "displacement_atr": round(displacement_atr, 2),
            "is_spike": self.state in (SpikeState.SPIKE_DETECTED, SpikeState.EXHAUSTION_RISK, SpikeState.REVERSAL_RISK, SpikeState.REVERSAL_CONFIRMED),
            "is_exhaustion_risk": (self.state == SpikeState.EXHAUSTION_RISK),
            "is_reversal_risk": (self.state == SpikeState.REVERSAL_RISK),
            "is_reversal_confirmed": (self.state == SpikeState.REVERSAL_CONFIRMED),
            "action_guidance": self._get_action_guidance(),
            "reasons": reasons
        }

    def _get_action_guidance(self) -> str:
        if self.state == SpikeState.NORMAL:
            return "Market moving within standard statistical velocity. Normal execution permitted."
        elif self.state == SpikeState.MOVE_ACCELERATING:
            return "Velocity accelerating. Do not enter market orders without limit buffer."
        elif self.state == SpikeState.SPIKE_DETECTED:
            return "Sudden price expansion active! Chasing this move has unfavorable risk/reward."
        elif self.state == SpikeState.EXHAUSTION_RISK:
            return "Rubber-band stretched severely from VWAP. Tighten trailing stops on existing positions."
        elif self.state == SpikeState.REVERSAL_RISK:
            return "Opposing order flow entering. Prepare for potential mean-reversion pullback."
        elif self.state == SpikeState.REVERSAL_CONFIRMED:
            return "Reversal confirmed by price displacement and aggressive taker flow."
        return "Cooldown in effect."


spike_radar = SpikeRadar()
