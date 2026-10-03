"""
PROMETHEUS BTC TERMINAL: Multi-Factor Market Regime Engine
Classifies the market into 6 robust quantitative regimes with hysteresis and counter-trend detection.
"""

from typing import Dict, List, Optional, Any, Tuple
from config.constants import MarketRegime


class MarketRegimeEngine:
    def __init__(self):
        self.current_regime = MarketRegime.INSUFFICIENT_DATA
        self.regime_candidate = MarketRegime.INSUFFICIENT_DATA
        self.candidate_count = 0
        self.hysteresis_threshold = 2  # Requires 2 consecutive evaluations to transition

    def evaluate_regime(
        self,
        spot: float,
        vwap: float,
        dist_vwap_atr: float,
        ema21: Optional[float],
        ema50: Optional[float],
        ema200: Optional[float],
        adx14: Optional[float],
        plus_di: Optional[float],
        minus_di: Optional[float],
        realized_vol: float,
        htf_bias: str = "NEUTRAL"
    ) -> Dict[str, Any]:
        """
        Synthesizes multi-factor conditions into an explainable regime.
        """
        if spot <= 0 or ema21 is None or ema50 is None:
            return {
                "regime": MarketRegime.INSUFFICIENT_DATA.value,
                "confidence_score": 0.0,
                "is_counter_trend": False,
                "reasons": ["Insufficient candle history for EMA/ADX calculations"]
            }

        reasons = []
        trend_score = 0.0  # -100 (Extremely Bearish) to +100 (Extremely Bullish)

        # 1. EMA Alignment (30 pts)
        if spot > ema21 > ema50:
            trend_score += 30.0
            reasons.append("Bullish moving average alignment (Spot > EMA21 > EMA50)")
        elif spot < ema21 < ema50:
            trend_score -= 30.0
            reasons.append("Bearish moving average alignment (Spot < EMA21 < EMA50)")
        else:
            reasons.append("Moving averages converging or choppy")

        # 2. VWAP Location & Normalized ATR Distance (25 pts)
        if spot > vwap:
            if dist_vwap_atr >= 0.5:
                trend_score += 25.0
                reasons.append(f"Price sustaining above Session VWAP (+{dist_vwap_atr} ATRs)")
            else:
                trend_score += 15.0
                reasons.append("Price hovering just above Session VWAP")
        else:
            if dist_vwap_atr <= -0.5:
                trend_score -= 25.0
                reasons.append(f"Price sustaining below Session VWAP ({dist_vwap_atr} ATRs)")
            else:
                trend_score -= 15.0
                reasons.append("Price hovering just below Session VWAP")

        # 3. ADX & Directional Movement (25 pts)
        is_trending_strength = False
        if adx14 is not None and plus_di is not None and minus_di is not None:
            if adx14 >= 25.0:
                is_trending_strength = True
                if plus_di > minus_di:
                    trend_score += 25.0
                    reasons.append(f"Strong bullish trend momentum (ADX {adx14:.1f}, +DI > -DI)")
                else:
                    trend_score -= 25.0
                    reasons.append(f"Strong bearish trend momentum (ADX {adx14:.1f}, -DI > +DI)")
            else:
                reasons.append(f"Low trend strength / compression (ADX {adx14:.1f} < 25)")

        # 4. Volatility Check
        is_high_vol = realized_vol > 65.0  # Annualized volatility > 65% for BTC
        if is_high_vol:
            reasons.append(f"Elevated realized volatility ({realized_vol:.1f}%)")

        # Regime Determination
        raw_regime = MarketRegime.RANGE
        if is_high_vol and abs(trend_score) < 35.0:
            raw_regime = MarketRegime.HIGH_VOLATILITY
        elif trend_score >= 45.0:
            raw_regime = MarketRegime.TREND_UP
        elif trend_score <= -45.0:
            raw_regime = MarketRegime.TREND_DOWN
        elif abs(trend_score) >= 20.0:
            raw_regime = MarketRegime.TRANSITION
        else:
            raw_regime = MarketRegime.RANGE

        # Apply Hysteresis
        if raw_regime == self.current_regime:
            self.candidate_count = 0
        else:
            if raw_regime == self.regime_candidate:
                self.candidate_count += 1
                if self.candidate_count >= self.hysteresis_threshold:
                    self.current_regime = raw_regime
                    self.candidate_count = 0
            else:
                self.regime_candidate = raw_regime
                self.candidate_count = 1

        # Check for Counter-Trend Warning
        is_counter_trend = False
        if self.current_regime == MarketRegime.TREND_UP and htf_bias == "BEARISH":
            is_counter_trend = True
            reasons.append("⚠️ COUNTER-TREND: Intraday uptrend operating against Bearish Higher Timeframe Structure!")
        elif self.current_regime == MarketRegime.TREND_DOWN and htf_bias == "BULLISH":
            is_counter_trend = True
            reasons.append("⚠️ COUNTER-TREND: Intraday downtrend operating against Bullish Higher Timeframe Structure!")

        confidence = min(100.0, max(20.0, abs(trend_score) + (15.0 if is_trending_strength else 0.0)))

        return {
            "regime": self.current_regime.value,
            "raw_candidate": raw_regime.value,
            "trend_score": round(trend_score, 1),
            "confidence_score": round(confidence, 1),
            "is_counter_trend": is_counter_trend,
            "reasons": reasons
        }


regime_engine = MarketRegimeEngine()
