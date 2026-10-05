"""
PROMETHEUS BTC TERMINAL: 100-Point Setup Score & Decision Engine
Transparent, explainable multi-component scoring matrix with normalized inputs and strict penalty rules.
"""

from typing import Dict, List, Optional, Any
from config.constants import DecisionState, MarketRegime, BreakoutStage, SpikeState


class SetupScoringEngine:
    def __init__(self):
        # Configurable weights summing to 100
        self.weights = {
            "market_structure": 20.0,
            "momentum_alignment": 15.0,
            "vwap_confirmation": 10.0,
            "trade_flow_volume": 15.0,
            "oi_funding_basis": 15.0,
            "liquidity_execution": 10.0,
            "volatility_exhaustion": 15.0
        }
        self.current_decision = DecisionState.NO_TRADE.value
        self.current_direction = "NONE"


    def evaluate_score(
        self,
        regime_output: Dict[str, Any],
        breakout_output: Dict[str, Any],
        spike_output: Dict[str, Any],
        orderflow_output: Dict[str, Any],
        oi_data: Dict[str, Any],
        liquidity_output: Dict[str, Any],
        indicator_output: Dict[str, Any],
        is_feed_healthy: bool = True
    ) -> Dict[str, Any]:
        """Evaluates complete 100-point multi-factor decision matrix."""
        if not is_feed_healthy:
            return {
                "decision": DecisionState.DATA_INVALID.value,
                "final_score": 0.0,
                "confidence_pct": 0.0,
                "direction": "NONE",
                "components": {},
                "penalties": [-50.0],
                "explanation": "Critical data feed is stale or corrupted. Trading engine halted.",
                "invalidation_rules": ["Restore healthy exchange connectivity"]
            }

        components = {}
        direction_bias = 0.0  # +1.0 for Bullish, -1.0 for Bearish
        conflicts = []
        evidence = []

        # ----------------------------------------------------
        # 1. Market Structure & Key Levels (Weight: 20)
        # ----------------------------------------------------
        # Raw: Breakout stage, regime confidence, distance to key level
        b_stage = breakout_output.get("stage")
        regime = regime_output.get("regime")
        c1_score = 0.0
        if b_stage in (BreakoutStage.CONFIRMED.value, BreakoutStage.RETEST_OR_ACCEPTANCE.value):
            c1_score = 20.0
            evidence.append(f"Breakout confirmed at {breakout_output.get('level_name')}")
            direction_bias += 1.0 if breakout_output.get("direction") == "BUY" else -1.0
        elif b_stage in (BreakoutStage.BREAKOUT_CANDLE_CLOSED.value, BreakoutStage.CONFIRMATION_PENDING.value):
            c1_score = 14.0
            evidence.append("Breakout candle closed; awaiting full order flow confirmation")
            direction_bias += 0.5 if breakout_output.get("direction") == "BUY" else -0.5
        elif regime in (MarketRegime.TREND_UP.value, MarketRegime.TREND_DOWN.value):
            c1_score = 12.0
            direction_bias += 0.5 if regime == MarketRegime.TREND_UP.value else -0.5
        else:
            c1_score = 5.0
            conflicts.append("Market in Range / Compression structure")

        components["market_structure"] = {
            "weight": self.weights["market_structure"],
            "score": round(c1_score, 1),
            "raw": f"Stage: {b_stage}, Regime: {regime}",
            "normalization": "0-20 based on structural breakout stage and regime alignment"
        }

        # ----------------------------------------------------
        # 2. Momentum & Timeframe Alignment (Weight: 15)
        # ----------------------------------------------------
        # Raw: ADX 14, RSI 14, EMA stack
        adx = indicator_output.get("adx14") or 20.0
        rsi = indicator_output.get("rsi14") or 50.0
        c2_score = 0.0
        if adx >= 25.0:
            c2_score += 8.0
            evidence.append(f"Strong trend momentum (ADX {adx:.1f} >= 25)")
        else:
            c2_score += 3.0

        if (direction_bias >= 0 and 50.0 <= rsi <= 68.0) or (direction_bias < 0 and 32.0 <= rsi <= 50.0):
            c2_score += 7.0
            evidence.append(f"RSI ({rsi:.1f}) in prime momentum expansion zone")
        elif rsi > 75.0 or rsi < 25.0:
            c2_score += 1.0
            conflicts.append(f"RSI ({rsi:.1f}) in extreme overbought/oversold territory")
        else:
            c2_score += 4.0

        components["momentum_alignment"] = {
            "weight": self.weights["momentum_alignment"],
            "score": round(c2_score, 1),
            "raw": f"ADX: {adx:.1f}, RSI: {rsi:.1f}",
            "normalization": "ADX > 25 (8 pts) + Non-overextended RSI (7 pts)"
        }

        # ----------------------------------------------------
        # 3. VWAP & Trend Confirmation (Weight: 10)
        # ----------------------------------------------------
        # Raw: Price vs VWAP, Distance in ATRs
        dist_vwap_atr = indicator_output.get("dist_vwap_atr", 0.0)
        c3_score = 0.0
        if (direction_bias >= 0 and 0.2 <= dist_vwap_atr <= 1.8) or (direction_bias < 0 and -1.8 <= dist_vwap_atr <= -0.2):
            c3_score = 10.0
            evidence.append(f"Healthy VWAP alignment ({dist_vwap_atr:+.1f} ATRs)")
        elif abs(dist_vwap_atr) > 2.5:
            c3_score = 2.0
            conflicts.append(f"Severely stretched from VWAP ({dist_vwap_atr:+.1f} ATRs)")
        else:
            c3_score = 6.0

        components["vwap_confirmation"] = {
            "weight": self.weights["vwap_confirmation"],
            "score": round(c3_score, 1),
            "raw": f"VWAP dist: {dist_vwap_atr:+.2f} ATRs",
            "normalization": "Healthy 0.2-1.8 ATR distance earns 10 pts, >2.5 penalized"
        }

        # ----------------------------------------------------
        # 4. Trade Flow & Volume (Weight: 15)
        # ----------------------------------------------------
        # Raw: Normalized Volume Delta, RVOL, 5m Delta
        norm_delta = orderflow_output.get("normalized_delta", 0.0)
        rvol = indicator_output.get("rvol", 1.0)
        c4_score = 0.0
        if rvol >= 1.5:
            c4_score += 7.0
            evidence.append(f"Volume surge (RVOL {rvol:.1f}x)")
        elif rvol >= 1.1:
            c4_score += 4.0
        else:
            c4_score += 2.0

        if (direction_bias >= 0 and norm_delta > 0.15) or (direction_bias < 0 and norm_delta < -0.15):
            c4_score += 8.0
            evidence.append(f"Aggressive taker flow aligned with direction ({norm_delta:+.2f})")
        elif abs(norm_delta) <= 0.08:
            c4_score += 4.0
        else:
            c4_score += 1.0
            conflicts.append("Taker volume delta opposes setup direction")

        components["trade_flow_volume"] = {
            "weight": self.weights["trade_flow_volume"],
            "score": round(c4_score, 1),
            "raw": f"RVOL: {rvol:.2f}, NormDelta: {norm_delta:+.2f}",
            "normalization": "RVOL > 1.5 (7 pts) + Delta alignment (8 pts)"
        }

        # ----------------------------------------------------
        # 5. Open Interest, Funding & Basis (Weight: 15)
        # ----------------------------------------------------
        # Raw: 5m OI change, Funding rate, Perpetual Basis %
        oi_chg_5m = oi_data.get("oi_change_5m_pct", 0.0)
        funding = oi_data.get("funding_rate", 0.0)
        basis_pct = oi_data.get("basis_pct", 0.0)
        c5_score = 0.0

        # Fresh positioning if OI rising with move
        if oi_chg_5m > 0.2:
            c5_score += 8.0
            evidence.append(f"Fresh positioning: Open Interest expanding (+{oi_chg_5m:.2f}%)")
        elif oi_chg_5m < -0.5:
            c5_score += 3.0
            conflicts.append(f"Open Interest contracting ({oi_chg_5m:.2f}%) — Possible short covering / long liquidation")
        else:
            c5_score += 5.0

        # Neutral funding (< 0.01% per 8h) is healthy
        if abs(funding) < 0.0003:
            c5_score += 7.0
        elif (direction_bias > 0 and funding > 0.001) or (direction_bias < 0 and funding < -0.001):
            c5_score += 2.0
            conflicts.append(f"Elevated funding rate ({funding * 100:.3f}%) indicates crowded positioning")
        else:
            c5_score += 5.0

        components["oi_funding_basis"] = {
            "weight": self.weights["oi_funding_basis"],
            "score": round(c5_score, 1),
            "raw": f"OI 5m: {oi_chg_5m:+.2f}%, Funding: {funding:.5f}, Basis: {basis_pct:+.2f}%",
            "normalization": "OI expansion (8 pts) + Uncrowded funding (7 pts)"
        }

        # ----------------------------------------------------
        # 6. Liquidity & Execution Quality (Weight: 10)
        # ----------------------------------------------------
        # Raw: Spread, Depth imbalance at 25 bps
        spread = orderflow_output.get("spread", 0.5)
        spread_bps = orderflow_output.get("spread_bps", 1.0)
        imbalance = orderflow_output.get("imbalance_25bps", 0.0)
        c6_score = 0.0
        if spread_bps <= 2.5:
            c6_score += 6.0
        else:
            c6_score += 2.0
            conflicts.append(f"Wide spread ({spread_bps:.1f} bps / ${spread:.1f})")

        if (direction_bias >= 0 and imbalance > 0.10) or (direction_bias < 0 and imbalance < -0.10):
            c6_score += 4.0
        else:
            c6_score += 2.0

        components["liquidity_execution"] = {
            "weight": self.weights["liquidity_execution"],
            "score": round(c6_score, 1),
            "raw": f"Spread: ${spread:.1f} ({spread_bps:.1f} bps), Imbalance: {imbalance:+.2f}",
            "normalization": "Tight spread <= 2.5 bps (6 pts) + Favorable book depth (4 pts)"
        }

        # ----------------------------------------------------
        # 7. Volatility & Exhaustion Risk (Weight: 15)
        # ----------------------------------------------------
        # Raw: Spike Radar state
        spike_state = spike_output.get("state")
        c7_score = 0.0
        if spike_state == SpikeState.NORMAL.value:
            c7_score = 15.0
        elif spike_state == SpikeState.MOVE_ACCELERATING.value:
            c7_score = 10.0
        elif spike_state in (SpikeState.SPIKE_DETECTED.value, SpikeState.EXHAUSTION_RISK.value):
            c7_score = 2.0
            conflicts.append(f"Spike radar in {spike_state} — high risk of exhaustion wick")
        elif spike_state == SpikeState.REVERSAL_CONFIRMED.value:
            c7_score = 12.0  # Favorable for reversal trade
            evidence.append("Reversal confirmed by price velocity rejection")
        else:
            c7_score = 8.0

        components["volatility_exhaustion"] = {
            "weight": self.weights["volatility_exhaustion"],
            "score": round(c7_score, 1),
            "raw": f"Spike State: {spike_state}",
            "normalization": "Normal volatility (15 pts), Exhaustion heavily penalized"
        }

        # Calculate Total Score & Penalties
        raw_total = sum(c["score"] for c in components.values())
        penalties = 0.0

        # Counter-trend penalty (-20 points)
        if regime_output.get("is_counter_trend", False):
            penalties += 20.0
            conflicts.append("Penalty: Setup operating against Higher-Timeframe Market Structure (-20 pts)")

        final_score = max(0.0, round(raw_total - penalties, 1))

        # Decision State Logic with Hysteresis Stability (Schmitt Trigger)
        # Entry threshold: 75.0 | Holding exit threshold: 58.0
        decision = DecisionState.NO_TRADE.value
        trade_dir = "NONE"

        if regime_output.get("is_counter_trend", False) and final_score >= 65.0:
            decision = DecisionState.COUNTER_TREND_WARNING.value
            trade_dir = "BUY" if direction_bias > 0 else "SELL"
            self.current_decision = decision
            self.current_direction = trade_dir
        elif final_score >= 75.0 and (direction_bias >= 0.3 or regime == MarketRegime.TREND_UP.value):
            decision = DecisionState.LONG_SETUP.value
            trade_dir = "BUY"
            self.current_decision = decision
            self.current_direction = trade_dir
        elif final_score >= 75.0 and (direction_bias <= -0.3 or regime == MarketRegime.TREND_DOWN.value):
            decision = DecisionState.SHORT_SETUP.value
            trade_dir = "SELL"
            self.current_decision = decision
            self.current_direction = trade_dir
        elif self.current_decision == DecisionState.LONG_SETUP.value and final_score >= 58.0 and direction_bias >= -0.2:
            # Hold active LONG setup during minor 5m compression pullbacks
            decision = DecisionState.LONG_SETUP.value
            trade_dir = "BUY"
        elif self.current_decision == DecisionState.SHORT_SETUP.value and final_score >= 58.0 and direction_bias <= 0.2:
            # Hold active SHORT setup during minor 5m compression bounces
            decision = DecisionState.SHORT_SETUP.value
            trade_dir = "SELL"
        elif final_score >= 55.0:
            decision = DecisionState.WAIT.value
            trade_dir = "NONE"
            self.current_decision = decision
            self.current_direction = trade_dir
        else:
            decision = DecisionState.NO_TRADE.value
            trade_dir = "NONE"
            self.current_decision = decision
            self.current_direction = trade_dir


        invalidation_rules = [
            "Candle close returning inside prior range",
            "Normalized volume delta flipping negative for longs or positive for shorts",
            "Spike radar entering EXHAUSTION_RISK"
        ]

        return {
            "decision": decision,
            "final_score": final_score,
            "raw_score": round(raw_total, 1),
            "penalties_applied": penalties,
            "direction": trade_dir,
            "components": components,
            "evidence": evidence,
            "conflicts": conflicts,
            "invalidation_rules": invalidation_rules
        }


setup_scoring_engine = SetupScoringEngine()
