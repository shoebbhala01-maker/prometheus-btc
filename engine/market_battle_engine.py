"""
PROMETHEUS BTC: LIVE MARKET BATTLE ENGINE
An intelligence layer above Bitcoin quantitative signal engines.
Continuously answers:
1. What is happening RIGHT NOW? ("ABHI KYA HO RAHA HAI?")
2. Who currently has the advantage? ("KAUN JEET RAHA HAI?")
3. Are buyers gaining or losing pressure?
4. Are sellers gaining or losing pressure?
5. If buyers continue, how far can price realistically travel? ("BUYERS KA AGALA LEVEL KYA HAI?")
6. Where will sellers likely defend? ("SELLERS KA DEFENCE KAHAN HAI?")
7. If sellers take control, where can price fall? ("AGAR REJECTION HUA TO KAHAN TAK?")
8. What exact event will invalidate the current scenario? ("KYA INVALIDATION HAI?")
9. What evidence would confirm the next move? ("KYA CONFIRMATION CHAHIYE?")
10. What is the current probability/risk of each scenario? ("ABHI TRADE KARNA HAI YA WAIT?")
"""

from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
import time
from datetime import datetime, timezone
from collections import deque
import math

from config.constants import MarketBattleState, MarketRegime, BreakoutStage


@dataclass
class BtcTargetStep:
    level: float
    type: str                  # "VWAP", "DAY_HIGH", "RANGE_HIGH", "PSYCHOLOGICAL_ROUND", "EQUAL_LOWS", "LIQUIDITY_POOL"
    strength: str              # "HIGH", "MEDIUM", "LOW"
    distance_pts: float
    required_confirmation: str
    invalidation: str
    confidence_label: str      # "HIGH", "MEDIUM", "LOW"
    confidence_score: float    # 0 to 100

    def to_dict(self) -> Dict[str, Any]:
        return {
            "level": round(self.level, 1),
            "type": self.type,
            "strength": self.strength,
            "distance_pts": round(self.distance_pts, 1),
            "required_confirmation": self.required_confirmation,
            "invalidation": self.invalidation,
            "confidence_label": self.confidence_label,
            "confidence_score": round(self.confidence_score, 1)
        }


@dataclass
class BtcConditionalScenarioItem:
    name: str                  # "A. Bullish Expansion Path", "B. Bearish Rejection Path", "C. Range Chop"
    confidence_label: str      # "HIGH", "MEDIUM", "LOW"
    confidence_score: float    # 0 to 100
    trigger: str
    target: str
    invalidation: str
    evidence_required: str
    is_active: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "confidence_label": self.confidence_label,
            "confidence_score": round(self.confidence_score, 1),
            "trigger": self.trigger,
            "target": self.target,
            "invalidation": self.invalidation,
            "evidence_required": self.evidence_required,
            "is_active": self.is_active
        }


@dataclass
class HistoricalBtcPressurePoint:
    timestamp: float
    buyer_pressure: float
    seller_pressure: float
    spot: float


class BtcMarketBattleEngine:
    def __init__(self):
        # Rolling historical buffer for multi-timeframe delta calculation (keeps up to 10 mins = 600s)
        self.history: deque = deque(maxlen=600)
        
        # Configurable thresholds
        self.strong_buyer_threshold: float = 25.0
        self.buyer_adv_threshold: float = 10.0
        self.balanced_lower: float = -9.0
        self.balanced_upper: float = 9.0
        self.seller_adv_threshold: float = -10.0
        self.strong_seller_threshold: float = -25.0

    def evaluate_battle(
        self,
        spot: float,
        vwap: float,
        mark_price: float,
        funding_rate: float,
        cvd: float,
        orderbook_imbalance: float,
        rvol: float,
        day_high: float,
        day_low: float,
        range_high: float,
        range_low: float,
        closest_support: float,
        closest_resistance: float,
        top_traders_ls_ratio: float = 1.0,
        is_live: bool = True,
        now_ts: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Executes complete battle evaluation across all 22 required quantitative intelligence layers for BTC.
        """
        now = now_ts or time.time()
        now_dt_utc = datetime.fromtimestamp(now, tz=timezone.utc)

        # 1. 24/7 CRYPTO MARKET CLOCK (Requirement 17)
        clock_phase = self._evaluate_crypto_clock(now_dt_utc, is_live)

        # 2. PARTICIPANT LAYERS (Requirement 2: Whales vs Inferred Crowd Pressure)
        participant_layers = self._evaluate_participants(
            top_traders_ls_ratio, funding_rate, cvd, orderbook_imbalance
        )

        # 3 & 4. BUYER AND SELLER PRESSURE SCORES (Requirements 3 & 4)
        buyer_pressure, buyer_breakdown = self._calculate_buyer_pressure(
            spot=spot, vwap=vwap, mark_price=mark_price, funding_rate=funding_rate,
            cvd=cvd, orderbook_imbalance=orderbook_imbalance, rvol=rvol,
            day_high=day_high, day_low=day_low, range_high=range_high, range_low=range_low,
            closest_resistance=closest_resistance
        )

        seller_pressure, seller_breakdown = self._calculate_seller_pressure(
            spot=spot, vwap=vwap, mark_price=mark_price, funding_rate=funding_rate,
            cvd=cvd, orderbook_imbalance=orderbook_imbalance, rvol=rvol,
            day_high=day_high, day_low=day_low, range_high=range_high, range_low=range_low,
            closest_support=closest_support
        )

        # Record history for rolling deltas
        self.history.append(HistoricalBtcPressurePoint(
            timestamp=now,
            buyer_pressure=buyer_pressure,
            seller_pressure=seller_pressure,
            spot=spot
        ))

        # 5. PRESSURE CHANGE (Requirement 5)
        pressure_change = self._calculate_pressure_changes(now, buyer_pressure, seller_pressure)

        # 6. MARKET BATTLE SCORE (Requirement 6)
        battle_score = self._calculate_battle_score(buyer_pressure, seller_pressure)

        # 11. WYCKOFF ABSORPTION ENGINE (Requirement 11)
        absorption = self._detect_absorption(
            spot=spot, day_high=day_high, day_low=day_low,
            closest_resistance=closest_resistance, closest_support=closest_support,
            rvol=rvol, buyer_pressure=buyer_pressure, seller_pressure=seller_pressure,
            cvd=cvd
        )

        # 7. WHALE POSITIONING VS PRICE ACTION DIVERGENCE (Requirement 7)
        divergence = self._detect_positioning_divergence(
            funding_rate=funding_rate,
            top_traders_ls_ratio=top_traders_ls_ratio,
            spot=spot,
            vwap=vwap,
            cvd=cvd,
            buyer_pressure=buyer_pressure,
            seller_pressure=seller_pressure
        )

        # 1. CLASSIFY OVERALL MARKET BATTLE STATE (Requirement 1)
        battle_state, battle_state_desc = self._classify_battle_state(
            buyer_pressure=buyer_pressure,
            seller_pressure=seller_pressure,
            net_pressure=battle_score["net_pressure"],
            spot=spot,
            vwap=vwap,
            day_high=day_high,
            day_low=day_low,
            range_high=range_high,
            range_low=range_low,
            rvol=rvol,
            absorption=absorption,
            divergence=divergence
        )

        # 8. TARGET LADDER (Requirement 8)
        target_ladder = self._build_target_ladder(
            spot=spot, vwap=vwap, day_high=day_high, day_low=day_low,
            range_high=range_high, range_low=range_low,
            closest_resistance=closest_resistance, closest_support=closest_support,
            buyer_pressure=buyer_pressure, seller_pressure=seller_pressure
        )

        # 9 & 10. CONDITIONAL SCENARIOS & LOGIC (Requirements 9, 10, 19, 20)
        scenarios = self._build_conditional_scenarios(
            spot=spot, vwap=vwap, day_high=day_high, day_low=day_low,
            range_high=range_high, range_low=range_low,
            closest_resistance=closest_resistance, closest_support=closest_support,
            buyer_pressure=buyer_pressure, seller_pressure=seller_pressure,
            net_pressure=battle_score["net_pressure"], rvol=rvol
        )

        # 13. "WHO IS WINNING?" BOX (Requirement 13)
        res_boundary = closest_resistance if closest_resistance > spot else day_high
        sup_boundary = closest_support if closest_support < spot else day_low
        who_is_winning = self._build_who_is_winning_box(
            buyer_pressure=buyer_pressure,
            seller_pressure=seller_pressure,
            net_pressure=battle_score["net_pressure"],
            key_resistance=res_boundary,
            key_support=sup_boundary,
            spot=spot,
            battle_state=battle_state
        )

        # 14 & 15. WHERE CAN THEY TAKE IT? (Requirements 14 & 15)
        buyers_route = self._build_buyers_route(spot, target_ladder["upside_path"])
        sellers_route = self._build_sellers_route(spot, target_ladder["downside_path"])

        # 16. NEXT DECISIVE EVENT (Requirement 16)
        next_decisive_event = self._determine_next_decisive_event(
            spot=spot, vwap=vwap, key_resistance=res_boundary, key_support=sup_boundary
        )

        # 18. 30-SECOND MARKET READ (Requirement 18)
        thirty_sec_read = self._build_30_second_read(
            spot=spot, vwap=vwap, buyer_pressure=buyer_pressure, seller_pressure=seller_pressure,
            pressure_change=pressure_change, funding_rate=funding_rate, cvd=cvd, rvol=rvol,
            who_is_winning=who_is_winning, next_decisive_event=next_decisive_event,
            battle_state=battle_state
        )

        # 22. HUMAN-READABLE / DESI QUESTIONS ANSWERED (Requirement 22)
        desi_answers = self._generate_desi_answers(
            spot=spot, vwap=vwap, who_is_winning=who_is_winning,
            buyer_pressure=buyer_pressure, seller_pressure=seller_pressure,
            pressure_change=pressure_change, target_ladder=target_ladder,
            next_decisive_event=next_decisive_event, battle_state=battle_state,
            absorption=absorption, divergence=divergence
        )

        return {
            "battle_state": battle_state.value,
            "battle_state_desc": battle_state_desc,
            "clock_phase": clock_phase,
            "participant_layers": participant_layers,
            "buyer_pressure": round(buyer_pressure, 1),
            "seller_pressure": round(seller_pressure, 1),
            "buyer_breakdown": buyer_breakdown,
            "seller_breakdown": seller_breakdown,
            "pressure_change": pressure_change,
            "battle_score": battle_score,
            "absorption": absorption,
            "divergence": divergence,
            "target_ladder": target_ladder,
            "scenarios": [s.to_dict() for s in scenarios],
            "who_is_winning": who_is_winning,
            "buyers_route": buyers_route,
            "sellers_route": sellers_route,
            "next_decisive_event": next_decisive_event,
            "thirty_second_read": thirty_sec_read,
            "desi_answers": desi_answers
        }

    # =========================================================================
    # INTERNAL QUANTITATIVE ENGINES
    # =========================================================================

    def _evaluate_crypto_clock(self, dt: datetime, is_live: bool) -> Dict[str, Any]:
        """Requirement 17: 24/7 Global Crypto Session Clock."""
        hr = dt.hour
        is_weekend = dt.weekday() >= 5

        if is_weekend:
            phase = "WEEKEND LOW LIQUIDITY (Caution: Chop & Wicks)"
            risk = "CHOP_RISK"
            desc = "Weekend par CME band rehta hai. Fakeouts aur low-volume wicks ka dhyan rakhein."
        elif 0 <= hr < 8:
            phase = "ASIA SESSION (00:00–08:00 UTC)"
            risk = "RANGE_BOUND"
            desc = "Tokyo & Hong Kong active. Range formation aur liquidity testing phase."
        elif 8 <= hr < 14:
            phase = "LONDON SESSION (08:00–14:00 UTC)"
            risk = "TREND_EXPANSION"
            desc = "European banks active. Genuine institutional directional moves bante hain."
        elif 14 <= hr < 21:
            phase = "NEW YORK SESSION (14:00–21:00 UTC / Prime Volatility)"
            risk = "PEAK_VOLATILITY"
            desc = "Wall Street & US ETF flow active. Sabse highest volume aur big moves yahan aate hain."
        else:
            phase = "US CLOSE & ASIA HANDOVER (21:00–00:00 UTC)"
            risk = "CONSOLIDATION"
            desc = "Post-US session settling phase. Clean setups ka intezaar karein."

        return {
            "phase_name": phase,
            "utc_time": dt.strftime("%H:%M UTC"),
            "risk_profile": risk,
            "guidance": desc,
            "is_weekend": is_weekend
        }

    def _evaluate_participants(
        self, top_traders_ls_ratio: float, funding_rate: float, cvd: float, imbalance: float
    ) -> Dict[str, Any]:
        """Requirement 2: Participant layers separating actual Whales vs Inferred Crowd Pressure."""
        # Whales / Smart Money Layer
        funding_pct = funding_rate * 100.0
        if top_traders_ls_ratio >= 1.3:
            whale_stance = "ACCUMULATING_LONGS"
        elif top_traders_ls_ratio <= 0.75:
            whale_stance = "HEAVY_SHORTING"
        else:
            whale_stance = "BALANCED_HEDGED"

        institutional = {
            "top_traders_ls_ratio": round(top_traders_ls_ratio, 2),
            "whale_stance": whale_stance,
            "funding_rate_8h_pct": round(funding_pct, 4),
            "funding_sentiment": "SHORTS_PAYING (Squeeze Fuel)" if funding_pct < 0 else ("HEALTHY_LONGS" if funding_pct <= 0.02 else "OVERHEATED_LONGS"),
            "cvd_institutional_flow": f"{cvd:+.1f} BTC"
        }

        # Inferred Crowd Pressure (NEVER claim confirmed retail positioning)
        if funding_pct > 0.03 and imbalance < -0.2:
            crowd_bias = "RETAIL_OVERLEVERAGED_LONGS"
            crowd_dir = "LONG_LIQUIDATION_RISK"
        elif funding_pct < -0.01 and imbalance > 0.2:
            crowd_bias = "PANIC_RETAIL_SHORTING"
            crowd_dir = "SHORT_SQUEEZE_FUEL"
        else:
            crowd_bias = "BALANCED_TWO_WAY_FLOW"
            crowd_dir = "NORMAL"

        inferred_crowd = {
            "label": "INFERRED CROWD PRESSURE",
            "disclaimer": "Proxy calculation based on Delta/Binance funding rate skew, taker CVD & liquidation risk — Not individual wallet identity.",
            "crowd_bias": crowd_bias,
            "crowd_direction": crowd_dir,
            "leverage_risk": "HIGH (Overheated)" if abs(funding_pct) > 0.03 else "HEALTHY"
        }

        return {
            "institutional": institutional,
            "inferred_crowd_pressure": inferred_crowd
        }

    def _calculate_buyer_pressure(
        self, spot: float, vwap: float, mark_price: float, funding_rate: float,
        cvd: float, orderbook_imbalance: float, rvol: float,
        day_high: float, day_low: float, range_high: float, range_low: float,
        closest_resistance: float
    ) -> Tuple[float, Dict[str, float]]:
        """Requirement 3: Continuous Buyer Pressure Score 0-100."""
        b = {}
        # 1. Price Momentum vs Range High (0-15)
        rng = max(100.0, range_high - range_low)
        pos = max(0.0, min(1.0, (spot - range_low) / rng))
        b["price_momentum"] = round(pos * 15.0, 1)

        # 2. VWAP Position (0-15)
        if spot > vwap:
            dist = spot - vwap
            if dist <= 300.0:
                b["vwap_position"] = 15.0
            elif dist <= 600.0:
                b["vwap_position"] = 11.0
            else:
                b["vwap_position"] = 7.0  # Overextended
        else:
            b["vwap_position"] = 2.0

        # 3. CVD Volume Aggression (0-15)
        if cvd >= 20.0:
            b["cvd_aggression"] = 15.0
        elif cvd >= 0.0:
            b["cvd_aggression"] = 10.0
        else:
            b["cvd_aggression"] = 3.0

        # 4. Funding Rate Health / Squeeze Potential (0-15)
        # Negative funding is fuel for buyers (shorts will be squeezed)
        if funding_rate <= 0.0:
            b["funding_health"] = 15.0
        elif funding_rate <= 0.015:
            b["funding_health"] = 12.0
        elif funding_rate <= 0.03:
            b["funding_health"] = 6.0
        else:
            b["funding_health"] = 2.0  # Longs overheated

        # 5. Orderbook Bid Imbalance (0-10)
        if orderbook_imbalance >= 0.25:
            b["bid_imbalance"] = 10.0
        elif orderbook_imbalance >= 0.0:
            b["bid_imbalance"] = 7.0
        else:
            b["bid_imbalance"] = 3.0

        # 6. RVOL Volume Expansion (0-10)
        if rvol >= 1.4:
            b["volume_expansion"] = 10.0
        elif rvol >= 1.0:
            b["volume_expansion"] = 7.0
        else:
            b["volume_expansion"] = 3.0

        # 7. Proximity to Breakout of Resistance (0-20)
        dist_res = closest_resistance - spot if closest_resistance > spot else 0.0
        if 0 < dist_res <= 60.0:
            b["breakout_thrust"] = 20.0  # Hammering resistance
        elif dist_res <= 180.0:
            b["breakout_thrust"] = 14.0
        elif spot > range_high:
            b["breakout_thrust"] = 18.0  # Already broken
        else:
            b["breakout_thrust"] = 5.0

        total = sum(b.values())
        return max(0.0, min(100.0, total)), b

    def _calculate_seller_pressure(
        self, spot: float, vwap: float, mark_price: float, funding_rate: float,
        cvd: float, orderbook_imbalance: float, rvol: float,
        day_high: float, day_low: float, range_high: float, range_low: float,
        closest_support: float
    ) -> Tuple[float, Dict[str, float]]:
        """Requirement 4: Continuous Seller Pressure Score 0-100."""
        s = {}
        # 1. Price Rejection vs Range Low (0-15)
        rng = max(100.0, range_high - range_low)
        inv_pos = max(0.0, min(1.0, (range_high - spot) / rng))
        s["price_rejection"] = round(inv_pos * 15.0, 1)

        # 2. VWAP Rejection (0-15)
        if spot < vwap:
            dist = vwap - spot
            if dist <= 300.0:
                s["vwap_rejection"] = 15.0
            elif dist <= 600.0:
                s["vwap_rejection"] = 11.0
            else:
                s["vwap_rejection"] = 7.0
        else:
            s["vwap_rejection"] = 2.0

        # 3. CVD Selling Delta (0-15)
        if cvd <= -20.0:
            s["cvd_dumping"] = 15.0
        elif cvd <= 0.0:
            s["cvd_dumping"] = 10.0
        else:
            s["cvd_dumping"] = 3.0

        # 4. Overheated Funding Long Liquidation Risk (0-15)
        if funding_rate >= 0.035:
            s["liquidation_risk"] = 15.0
        elif funding_rate >= 0.02:
            s["liquidation_risk"] = 11.0
        elif funding_rate >= 0.0:
            s["liquidation_risk"] = 6.0
        else:
            s["liquidation_risk"] = 2.0

        # 5. Orderbook Ask Imbalance (0-10)
        if orderbook_imbalance <= -0.25:
            s["ask_imbalance"] = 10.0
        elif orderbook_imbalance <= 0.0:
            s["ask_imbalance"] = 7.0
        else:
            s["ask_imbalance"] = 3.0

        # 6. RVOL Volume Expansion (0-10)
        if rvol >= 1.4 and spot < vwap:
            s["volume_expansion"] = 10.0
        elif rvol >= 1.0 and spot < vwap:
            s["volume_expansion"] = 7.0
        else:
            s["volume_expansion"] = 3.0

        # 7. Proximity to Breakdown of Support (0-20)
        dist_sup = spot - closest_support if spot > closest_support else 0.0
        if 0 < dist_sup <= 60.0:
            s["breakdown_thrust"] = 20.0  # Pressuring support floor
        elif dist_sup <= 180.0:
            s["breakdown_thrust"] = 14.0
        elif spot < range_low:
            s["breakdown_thrust"] = 18.0
        else:
            s["breakdown_thrust"] = 5.0

        total = sum(s.values())
        return max(0.0, min(100.0, total)), s

    def _calculate_pressure_changes(self, now: float, current_bp: float, current_sp: float) -> Dict[str, Any]:
        """Requirement 5: Multi-window rolling pressure delta (10s, 30s, 60s, 3m, 5m)."""
        deltas = {"10s": {"buy": 0.0, "sell": 0.0},
                  "30s": {"buy": 0.0, "sell": 0.0},
                  "60s": {"buy": 0.0, "sell": 0.0},
                  "3m":  {"buy": 0.0, "sell": 0.0},
                  "5m":  {"buy": 0.0, "sell": 0.0}}

        windows = {"10s": 10.0, "30s": 30.0, "60s": 60.0, "3m": 180.0, "5m": 300.0}

        for w_key, sec in windows.items():
            target_time = now - sec
            closest = None
            min_diff = 9999.0
            for pt in self.history:
                diff = abs(pt.timestamp - target_time)
                if diff < min_diff and diff <= (sec * 0.75):
                    min_diff = diff
                    closest = pt
            if closest:
                deltas[w_key]["buy"] = round(current_bp - closest.buyer_pressure, 1)
                deltas[w_key]["sell"] = round(current_sp - closest.seller_pressure, 1)

        d30_buy = deltas["30s"]["buy"]
        d30_sell = deltas["30s"]["sell"]
        d60_buy = deltas["60s"]["buy"]
        d60_sell = deltas["60s"]["sell"]

        if (d30_buy >= 5.0 or d60_buy >= 10.0) and d30_buy > d30_sell:
            momentum_label = "BUYERS GAINING MOMENTUM 🚀"
        elif (d30_sell >= 5.0 or d60_sell >= 10.0) and d30_sell > d30_buy:
            momentum_label = "SELLERS GAINING MOMENTUM 🔻"
        elif d30_buy <= -6.0:
            momentum_label = "BUYERS LOSING STEAM ⚠️"
        elif d30_sell <= -6.0:
            momentum_label = "SELLERS LOSING STEAM ⚠️"
        else:
            momentum_label = "BALANCED / STEADY ⚖️"

        return {
            "deltas": deltas,
            "momentum_label": momentum_label,
            "summary_30s": f"Buy: {d30_buy:+.1f} | Sell: {d30_sell:+.1f}",
            "summary_1m":  f"Buy: {d60_buy:+.1f} | Sell: {d60_sell:+.1f}"
        }

    def _calculate_battle_score(self, bp: float, sp: float) -> Dict[str, Any]:
        """Requirement 6: Battle Score, Net Pressure, and Advantage classification."""
        net = bp - sp

        if net >= self.strong_buyer_threshold:
            classification = "STRONG BUYER ADVANTAGE"
            badge = "🟢 STRONG BUYER ADVANTAGE"
        elif net >= self.buyer_adv_threshold:
            classification = "BUYER ADVANTAGE"
            badge = "🟢 BUYER ADVANTAGE"
        elif net <= self.strong_seller_threshold:
            classification = "STRONG SELLER ADVANTAGE"
            badge = "🔴 STRONG SELLER ADVANTAGE"
        elif net <= self.seller_adv_threshold:
            classification = "SELLER ADVANTAGE"
            badge = "🔴 SELLER ADVANTAGE"
        else:
            classification = "BALANCED"
            badge = "⚖️ BALANCED BATTLE"

        return {
            "buyer_score": round(bp, 1),
            "seller_score": round(sp, 1),
            "net_pressure": round(net, 1),
            "classification": classification,
            "badge": badge
        }

    def _detect_absorption(
        self, spot: float, day_high: float, day_low: float,
        closest_resistance: float, closest_support: float,
        rvol: float, buyer_pressure: float, seller_pressure: float, cvd: float
    ) -> Dict[str, Any]:
        """Requirement 11: Wyckoff Absorption Engine for BTC."""
        dist_res = abs(closest_resistance - spot)
        dist_sup = abs(spot - closest_support)

        # Buyer absorption near support (heavy selling absorbed)
        if dist_sup <= 80.0 and rvol >= 1.2 and seller_pressure > 50.0 and spot >= closest_support:
            return {
                "is_detected": True,
                "side": "BUYER",
                "level": round(closest_support, 1),
                "strength": "HIGH" if rvol >= 1.5 else "MEDIUM",
                "explanation": f"Heavy selling volume near Support (${closest_support:,.0f}) is being quietly absorbed by buyers. Floor holding firm.",
                "desi_explanation": f"Bhai Support (${closest_support:,.0f}) par sellers ka sara selling pressure buyers absorb kar rahe hain. Floor toot nahi raha (Demand Defense)."
            }

        # Seller absorption near resistance (heavy buying absorbed)
        if dist_res <= 80.0 and rvol >= 1.2 and buyer_pressure > 50.0 and spot <= closest_resistance:
            return {
                "is_detected": True,
                "side": "SELLER",
                "level": round(closest_resistance, 1),
                "strength": "HIGH" if rvol >= 1.5 else "MEDIUM",
                "explanation": f"Heavy buying thrust near Resistance (${closest_resistance:,.0f}) is being met with institutional sell limit orders.",
                "desi_explanation": f"Bhai Resistance (${closest_resistance:,.0f}) par buyers ka sara zor sellers absorb kar rahe hain. Ceiling nahi nikal rahi (Supply Wall)."
            }

        return {
            "is_detected": False,
            "side": "NONE",
            "level": 0.0,
            "strength": "LOW",
            "explanation": "No significant volume absorption detected at key boundaries.",
            "desi_explanation": "Abhi koi hidden absorption active nahi hai."
        }

    def _detect_positioning_divergence(
        self, funding_rate: float, top_traders_ls_ratio: float, spot: float, vwap: float,
        cvd: float, buyer_pressure: float, seller_pressure: float
    ) -> Dict[str, Any]:
        """Requirement 7: Whale Positioning vs Price Action Divergence."""
        funding_pct = funding_rate * 100.0

        # Short Squeeze Divergence: Negative funding / Whales short but Price Rising
        if funding_pct < -0.005 and spot > vwap and buyer_pressure >= 55.0:
            return {
                "is_divergent": True,
                "headline": "⚠️ SHORT SQUEEZE / BEARISH POSITIONING DIVERGENCE",
                "desi_headline": "⚠️ NEGATIVE FUNDING SHORTS TRAPPED IN SQUEEZE",
                "explanations": [
                    "Perpetual funding rate is negative (shorts paying longs) while price pushes higher",
                    "Aggressive spot & perp taker buying forcing leveraged shorts to cover",
                    "Seller absorption active near key resistance",
                    "Cascade risk: If resistance breaks, massive short stop-losses will ignite"
                ],
                "guidance": "Do NOT blindly short. Wait for clean resistance rejection or trade the breakout continuation."
            }

        # Long Squeeze Divergence: Overheated funding (>0.03%) but Price Stalling
        if funding_pct > 0.03 and spot < vwap and seller_pressure >= 55.0:
            return {
                "is_divergent": True,
                "headline": "⚠️ LONG SQUEEZE / OVERHEATED FUNDING DIVERGENCE",
                "desi_headline": "⚠️ OVERHEATED LONGS AT RISK OF LIQUIDATION CASCADE",
                "explanations": [
                    "Funding rate is dangerously elevated (>0.03%) with retail heavily leveraged long",
                    "Price failing to follow through above VWAP — Long fatigue",
                    "Cascade risk: If support breaks, forced long liquidations will accelerate drop"
                ],
                "guidance": "Do NOT chase longs on dips. Protect long capital until funding normalizes."
            }

        return {
            "is_divergent": False,
            "headline": "ALIGNED FLOW",
            "desi_headline": "Funding aur price action me koi bada divergence nahi hai.",
            "explanations": ["Order flow aligned with current market structure."],
            "guidance": "Normal setup execution rules apply."
        }

    def _classify_battle_state(
        self, buyer_pressure: float, seller_pressure: float, net_pressure: float,
        spot: float, vwap: float, day_high: float, day_low: float,
        range_high: float, range_low: float, rvol: float,
        absorption: Dict[str, Any], divergence: Dict[str, Any]
    ) -> Tuple[MarketBattleState, str]:
        """Requirement 1: Classify into the specified 14 MarketBattleStates."""
        dist_high = range_high - spot
        dist_low = spot - range_low

        if absorption["is_detected"]:
            return MarketBattleState.ABSORPTION, f"{absorption['side']} Absorption detected at ${absorption['level']:,.0f}"

        if dist_high <= 40.0 and buyer_pressure > 60.0:
            return MarketBattleState.BREAKOUT_ATTEMPT, f"Testing Range High (${range_high:,.0f}) — Breakout attempt underway"

        if dist_low <= 40.0 and seller_pressure > 60.0:
            return MarketBattleState.BREAKDOWN_ATTEMPT, f"Testing Range Low (${range_low:,.0f}) — Breakdown attempt underway"

        if divergence["is_divergent"] and "SHORT SQUEEZE" in divergence["headline"]:
            return MarketBattleState.SHORT_SQUEEZE, "Negative funding squeeze in progress — Short liquidation pressure"

        if divergence["is_divergent"] and "LONG SQUEEZE" in divergence["headline"]:
            return MarketBattleState.LONG_SQUEEZE, "Overheated longs facing liquidation pressure"

        # Traps
        if spot < range_high and dist_high <= 60.0 and buyer_pressure < 45.0 and rvol >= 1.2:
            return MarketBattleState.BULL_TRAP_RISK, "Failed to sustain above Range High — Bull trap risk elevated"

        if spot > range_low and dist_low <= 60.0 and seller_pressure < 45.0 and rvol >= 1.2:
            return MarketBattleState.BEAR_TRAP_RISK, "Failed to sustain breakdown below Range Low — Bear trap risk elevated"

        if net_pressure >= 25.0:
            return MarketBattleState.BUYERS_DOMINATING, "Buyers in firm control with heavy net delta"
        elif net_pressure >= 10.0:
            return MarketBattleState.BUYERS_ATTACKING, "Buyers pushing upward toward resistance"
        elif net_pressure <= -25.0:
            return MarketBattleState.SELLERS_DOMINATING, "Sellers in firm control with heavy selling pressure"
        elif net_pressure <= -10.0:
            return MarketBattleState.SELLERS_ATTACKING, "Sellers pressing downward toward support"
        elif abs(spot - vwap) <= 120.0 and rvol < 1.0:
            return MarketBattleState.RANGE_CHOP, "Price glued to VWAP with drying volume — Range chop"
        else:
            return MarketBattleState.BALANCED, "Balanced tug-of-war between buyers and sellers"

    def _build_target_ladder(
        self, spot: float, vwap: float, day_high: float, day_low: float,
        range_high: float, range_low: float,
        closest_resistance: float, closest_support: float,
        buyer_pressure: float, seller_pressure: float
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Requirement 8: Upside Path and Downside Path with conditional confirmations & confidence for BTC."""
        upside = []
        downside = []

        # Upside steps:
        if spot < vwap:
            upside.append(BtcTargetStep(
                level=vwap, type="VWAP", strength="HIGH", distance_pts=vwap - spot,
                required_confirmation="1m/5m candle cross above VWAP + expanding taker buy volume",
                invalidation="Rejection wick with slip back below",
                confidence_label="HIGH" if buyer_pressure > 55 else "MEDIUM",
                confidence_score=72.0 if buyer_pressure > 55 else 52.0
            ))

        target1_up = min(range_high, closest_resistance) if min(range_high, closest_resistance) > spot else spot + 200.0
        upside.append(BtcTargetStep(
            level=target1_up, type="RANGE_CEILING", strength="HIGH", distance_pts=target1_up - spot,
            required_confirmation="5m candle close above level + RVOL >= 1.3x",
            invalidation="Upper wick rejection back inside range",
            confidence_label="MEDIUM", confidence_score=64.0
        ))

        target2_up = round((target1_up + 350.0) / 100.0) * 100.0
        upside.append(BtcTargetStep(
            level=target2_up, type="EXPANSION_TARGET_1", strength="MEDIUM", distance_pts=target2_up - spot,
            required_confirmation="Clean retest hold of breakout ceiling + positive CVD",
            invalidation="Loss of breakout anchor level",
            confidence_label="MEDIUM", confidence_score=56.0
        ))

        target3_up = round((target2_up + 500.0) / 500.0) * 500.0
        upside.append(BtcTargetStep(
            level=target3_up, type="PSYCHOLOGICAL_ROUND", strength="VERY_HIGH", distance_pts=target3_up - spot,
            required_confirmation="Heavy short liquidation cascade (> $20M liquidations)",
            invalidation="Aggressive whale sell wall appearance",
            confidence_label="LOW", confidence_score=40.0
        ))

        # Downside steps:
        if spot > vwap:
            downside.append(BtcTargetStep(
                level=vwap, type="VWAP", strength="HIGH", distance_pts=spot - vwap,
                required_confirmation="5m candle close below VWAP + negative CVD",
                invalidation="Reclaim back above VWAP with buyer bounce",
                confidence_label="HIGH" if seller_pressure > 55 else "MEDIUM",
                confidence_score=70.0 if seller_pressure > 55 else 50.0
            ))

        sup1 = max(range_low, closest_support) if max(range_low, closest_support) < spot else spot - 200.0
        downside.append(BtcTargetStep(
            level=sup1, type="RANGE_FLOOR", strength="HIGH", distance_pts=spot - sup1,
            required_confirmation="5m candle close below support + volume surge",
            invalidation="Immediate V-shape bounce back above floor",
            confidence_label="MEDIUM", confidence_score=62.0
        ))

        target2_down = round((sup1 - 350.0) / 100.0) * 100.0
        downside.append(BtcTargetStep(
            level=target2_down, type="LIQUIDITY_POOL", strength="MEDIUM", distance_pts=spot - target2_down,
            required_confirmation="Retest rejection of broken floor + negative funding",
            invalidation="Reclaim back above support",
            confidence_label="LOW", confidence_score=45.0
        ))

        target3_down = round((target2_down - 500.0) / 500.0) * 500.0
        downside.append(BtcTargetStep(
            level=target3_down, type="MAJOR_DEMAND_BASE", strength="VERY_HIGH", distance_pts=spot - target3_down,
            required_confirmation="Long liquidation exhaustion + buyer absorption",
            invalidation="Continued aggressive market sell dumping",
            confidence_label="LOW", confidence_score=35.0
        ))

        return {
            "upside_path": [u.to_dict() for u in upside],
            "downside_path": [d.to_dict() for d in downside]
        }

    def _build_conditional_scenarios(
        self, spot: float, vwap: float, day_high: float, day_low: float,
        range_high: float, range_low: float,
        closest_resistance: float, closest_support: float,
        buyer_pressure: float, seller_pressure: float, net_pressure: float, rvol: float
    ) -> List[BtcConditionalScenarioItem]:
        """Requirements 9, 10, 19, 20: 3 Parallel Conditional Scenarios for BTC."""
        scenarios = []

        # A. Bullish Expansion
        bull_active = net_pressure > 5.0 and spot >= vwap
        bull_conf = 74.0 if net_pressure >= 20.0 else (58.0 if bull_active else 38.0)
        res_trig = closest_resistance if closest_resistance > spot else range_high
        scenarios.append(BtcConditionalScenarioItem(
            name="A. Bullish Expansion Path",
            confidence_label="HIGH" if bull_conf >= 70 else ("MEDIUM" if bull_conf >= 50 else "LOW"),
            confidence_score=bull_conf,
            trigger=f"IF Resistance (${res_trig:,.0f}) breaks WITH 5-minute candle close AND retest holds above ${res_trig - 50:,.0f}",
            target=f"Upside targets toward ${res_trig + 350:,.0f} and ${res_trig + 700:,.0f} become active",
            invalidation=f"Invalidated if price prints an upper rejection wick and falls back below VWAP (${vwap:,.0f})",
            evidence_required="5m close above level + RVOL >= 1.3x + Positive CVD expansion (>+20 BTC)",
            is_active=bull_active
        ))

        # B. Bearish Breakdown / Rejection
        bear_active = net_pressure < -5.0 or spot < vwap
        bear_conf = 72.0 if net_pressure <= -20.0 else (56.0 if bear_active else 36.0)
        sup_trig = closest_support if closest_support < spot else range_low
        scenarios.append(BtcConditionalScenarioItem(
            name="B. Bearish Rejection / Breakdown Path",
            confidence_label="HIGH" if bear_conf >= 70 else ("MEDIUM" if bear_conf >= 50 else "LOW"),
            confidence_score=bear_conf,
            trigger=f"IF price rejects near ${res_trig:,.0f} / VWAP (${vwap:,.0f}) AND breaks below ${sup_trig:,.0f}",
            target=f"Downside path toward ${sup_trig - 350:,.0f} and ${sup_trig - 700:,.0f} becomes active",
            invalidation=f"Invalidated if price decisively reclaims VWAP (${vwap:,.0f}) on high volume",
            evidence_required="5m close below support + Negative CVD dumping + Bid depth collapse",
            is_active=bear_active
        ))

        # C. Range Chop / Consolidation
        range_active = abs(net_pressure) <= 12.0
        range_conf = 78.0 if (abs(spot - vwap) <= 150.0 and rvol < 1.1) else 45.0
        scenarios.append(BtcConditionalScenarioItem(
            name="C. Range-Bound Chop / Consolidation",
            confidence_label="HIGH" if range_conf >= 70 else ("MEDIUM" if range_conf >= 50 else "LOW"),
            confidence_score=range_conf,
            trigger=f"IF price fails to break both ${range_high:,.0f} (Ceiling) and ${range_low:,.0f} (Floor)",
            target=f"Price oscillates between ${range_low + 80:,.0f} and ${range_high - 80:,.0f} around VWAP (${vwap:,.0f})",
            invalidation="Decisive breakout beyond boundaries with volume > 1.4x RVOL",
            evidence_required="Low RVOL (<1.0x), bid-ask balance, flat CVD",
            is_active=range_active
        ))

        return scenarios

    def _build_who_is_winning_box(
        self, buyer_pressure: float, seller_pressure: float, net_pressure: float,
        key_resistance: float, key_support: float, spot: float, battle_state: MarketBattleState
    ) -> Dict[str, Any]:
        """Requirement 13: High-visibility 'WHO IS WINNING?' box for BTC."""
        if net_pressure >= 10.0:
            winner = "BUYERS"
            winner_badge = "🟢 BUYERS WINNING"
            color_class = "c-bull"
        elif net_pressure <= -10.0:
            winner = "SELLERS"
            winner_badge = "🔴 SELLERS WINNING"
            color_class = "c-bear"
        else:
            winner = "BALANCED"
            winner_badge = "⚖️ TIED / BALANCED"
            color_class = "c-neutral"

        if winner == "BUYERS" and spot < key_resistance:
            status_line = f"BUYERS WINNING BUT NOT CONFIRMED BREAKOUT (Ceiling ${key_resistance:,.0f})"
            desi_status = f"Buyers aage hain par Resistance (${key_resistance:,.0f}) ke upar retest hold confirmation baaki hai."
        elif winner == "SELLERS" and spot > key_support:
            status_line = f"SELLERS WINNING BUT NOT CONFIRMED BREAKDOWN (Floor ${key_support:,.0f})"
            desi_status = f"Sellers dabao bana rahe hain par Support (${key_support:,.0f}) ke neeche close confirm hona baaki hai."
        elif winner == "BUYERS":
            status_line = f"BUYERS BREAKOUT IN PROGRESS ABOVE ${key_resistance:,.0f}"
            desi_status = f"Buyers ne Resistance (${key_resistance:,.0f}) tod diya hai — expansion chal raha hai."
        elif winner == "SELLERS":
            status_line = f"SELLERS BREAKDOWN IN PROGRESS BELOW ${key_support:,.0f}"
            desi_status = f"Sellers ne Support (${key_support:,.0f}) tod diya hai — downside expansion chal raha hai."
        else:
            status_line = "NEITHER SIDE IN CONTROL — CONSOLIDATION / CHOP"
            desi_status = "Dono taraf se barabar zor hai — abhi market chop zone mein hai."

        return {
            "buyers_score": round(buyer_pressure, 1),
            "sellers_score": round(seller_pressure, 1),
            "winner": winner,
            "winner_badge": winner_badge,
            "color_class": color_class,
            "key_resistance": round(key_resistance, 1),
            "key_support": round(key_support, 1),
            "status_line": status_line,
            "desi_status": desi_status
        }

    def _build_buyers_route(self, spot: float, upside_steps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Requirement 14: Step-by-step route where buyers can realistically take the price."""
        route = [{"step": 0, "label": "CURRENT SPOT", "price": round(spot, 1), "seller_defense": "Current Battlefield"}]
        for idx, s in enumerate(upside_steps[:4], 1):
            route.append({
                "step": idx,
                "label": s["type"],
                "price": s["level"],
                "distance": f"+${s['distance_pts']:,.0f}",
                "seller_defense_strength": s["strength"],
                "required_action": s["required_confirmation"]
            })
        return route

    def _build_sellers_route(self, spot: float, downside_steps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Requirement 15: Step-by-step route where sellers can push the price."""
        route = [{"step": 0, "label": "CURRENT SPOT", "price": round(spot, 1), "buyer_support": "Current Battlefield"}]
        for idx, s in enumerate(downside_steps[:4], 1):
            route.append({
                "step": idx,
                "label": s["type"],
                "price": s["level"],
                "distance": f"-${s['distance_pts']:,.0f}",
                "buyer_support_strength": s["strength"],
                "required_action": s["required_confirmation"]
            })
        return route

    def _determine_next_decisive_event(
        self, spot: float, vwap: float, key_resistance: float, key_support: float
    ) -> Dict[str, str]:
        """Requirement 16: The single most decisive short-term event to wait for."""
        if spot > vwap:
            if abs(key_resistance - spot) <= 120.0:
                waiting_for = f"${key_resistance:,.0f} BREAK + 5M RETEST HOLD"
                desi = f"Abhi BTC Resistance (${key_resistance:,.0f}) ke paas hai. Wait karein: 5m candle close + retest hold ka."
                invalidation = f"Agar price ${key_resistance:,.0f} se reject hokar VWAP (${vwap:,.0f}) ke neeche slip ho jaye."
            else:
                waiting_for = f"PULLBACK TO VWAP (${vwap:,.0f}) OR HIGHER LOW"
                desi = f"Price VWAP se upar float kar raha hai. Chasing mat karein, VWAP (${vwap:,.0f}) ke paas dip aane ka wait karein."
                invalidation = f"VWAP (${vwap:,.0f}) break hone par bullish idea cancel."
        else:
            if abs(spot - key_support) <= 120.0:
                waiting_for = f"${key_support:,.0f} BREAK + 5M RETEST REJECTION"
                desi = f"BTC Support (${key_support:,.0f}) ke paas hai. Wait karein: 5m candle breakdown + retest rejection ka."
                invalidation = f"Agar price ${key_support:,.0f} se bounce hokar wapas VWAP (${vwap:,.0f}) reclaim kar le."
            else:
                waiting_for = f"PULLBACK TO VWAP (${vwap:,.0f}) REJECTION TO SHORT"
                desi = f"Price VWAP ke neeche hai. VWAP (${vwap:,.0f}) tak pullback aane par rejection dekhkar short plan karein."
                invalidation = f"VWAP (${vwap:,.0f}) ke upar 5m close aane par bearish idea cancel."

        return {
            "title": "NEXT DECISIVE EVENT",
            "waiting_for": waiting_for,
            "desi_explanation": desi,
            "invalidation_rule": invalidation
        }

    def _build_30_second_read(
        self, spot: float, vwap: float, buyer_pressure: float, seller_pressure: float,
        pressure_change: Dict[str, Any], funding_rate: float, cvd: float, rvol: float,
        who_is_winning: Dict[str, Any], next_decisive_event: Dict[str, str], battle_state: MarketBattleState
    ) -> Dict[str, Any]:
        """Requirement 18: Compact 30-Second Market Read Cockpit for BTC."""
        d30_buy = pressure_change["deltas"]["30s"]["buy"]
        d30_sell = pressure_change["deltas"]["30s"]["sell"]

        price_dir = "↑" if spot > vwap else ("↓" if spot < vwap else "FLAT")
        buy_dir = "↑" if d30_buy > 2.0 else ("↓" if d30_buy < -2.0 else "FLAT")
        sell_dir = "↑" if d30_sell > 2.0 else ("↓" if d30_sell < -2.0 else "FLAT")
        funding_str = f"{funding_rate * 100:+.3f}%"
        cvd_dir = "↑" if cvd > 5.0 else ("↓" if cvd < -5.0 else "FLAT")
        vol_dir = "EXPANDING" if rvol >= 1.2 else "DRYING"

        if battle_state in [MarketBattleState.BUYERS_DOMINATING, MarketBattleState.SHORT_SQUEEZE] and rvol >= 1.2:
            action = "LONG (CONFIRMED)"
        elif battle_state in [MarketBattleState.SELLERS_DOMINATING, MarketBattleState.LONG_SQUEEZE] and rvol >= 1.2:
            action = "SHORT (CONFIRMED)"
        elif battle_state in [MarketBattleState.BULL_TRAP_RISK, MarketBattleState.BEAR_TRAP_RISK]:
            action = "EXIT / CAUTION"
        else:
            action = "WAIT (AWAIT TRIGGER)"

        return {
            "price": price_dir,
            "buy_pressure": buy_dir,
            "sell_pressure": sell_dir,
            "funding_rate": funding_str,
            "cvd": cvd_dir,
            "volume": vol_dir,
            "current_winner": who_is_winning["winner"],
            "next_level": f"${who_is_winning['key_resistance']:,.0f}" if who_is_winning["winner"] == "BUYERS" else f"${who_is_winning['key_support']:,.0f}",
            "invalidation": next_decisive_event["invalidation_rule"],
            "action": action
        }

    def _generate_desi_answers(
        self, spot: float, vwap: float, who_is_winning: Dict[str, Any],
        buyer_pressure: float, seller_pressure: float, pressure_change: Dict[str, Any],
        target_ladder: Dict[str, Any], next_decisive_event: Dict[str, str],
        battle_state: MarketBattleState, absorption: Dict[str, Any], divergence: Dict[str, Any]
    ) -> Dict[str, str]:
        """Requirement 22: Answers the 9 critical trader questions in clear, conversational Hinglish for BTC."""
        upside = target_ladder["upside_path"]
        downside = target_ladder["downside_path"]

        t1_up = upside[0]["level"] if upside else spot + 200.0
        t2_up = upside[1]["level"] if len(upside) > 1 else spot + 500.0
        t1_down = downside[0]["level"] if downside else spot - 200.0
        t2_down = downside[1]["level"] if len(downside) > 1 else spot - 500.0

        q1 = f"Bitcoin abhi ${spot:,.1f} par chal raha hai jo VWAP (${vwap:,.1f}) ke {'upar' if spot > vwap else 'neeche'} hai. Battle State: {battle_state.value}."
        if absorption["is_detected"]:
            q1 += f" {absorption['desi_explanation']}"
        elif divergence["is_divergent"]:
            q1 += f" {divergence['desi_headline']}."

        q2 = f"{who_is_winning['desi_status']} (Buyers Score: {buyer_pressure:.0f} vs Sellers Score: {seller_pressure:.0f})."

        d30_b = pressure_change["deltas"]["30s"]["buy"]
        d30_s = pressure_change["deltas"]["30s"]["sell"]
        q3 = f"Buyers zor {'badha rahe hain (+' + str(d30_b) + ')' if d30_b > 0 else 'halka kar rahe hain (' + str(d30_b) + ')'}."
        q4 = f"Sellers zor {'badha rahe hain (+' + str(d30_s) + ')' if d30_s > 0 else 'halka kar rahe hain (' + str(d30_s) + ')'}."

        q5 = f"Buyers ka agla realistic target ${t1_up:,.0f} hai, aur uske baad ${t2_up:,.0f}."
        q6 = f"Sellers ka defence ${who_is_winning['key_resistance']:,.0f} (Range High / Supply Wall) par baithega."
        q7 = f"Agar sellers control le lete hain to price ${t1_down:,.0f} aur fir ${t2_down:,.0f} (Range Floor / Equal Lows) tak gir sakta hai."
        q8 = f"Invalidation: {next_decisive_event['invalidation_rule']}."
        q9 = f"Next Evidence Needed: {next_decisive_event['waiting_for']}."

        action_summary = "WAIT (Awaiting clean confirmation)" if "WAIT" in next_decisive_event["waiting_for"] else "ACTIVE MONITOR"

        return {
            "abhi_kya_ho_raha_hai": q1,
            "kaun_jeet_raha_hai": q2,
            "buyers_gaining_losing": q3,
            "sellers_gaining_losing": q4,
            "buyers_ka_agala_level": q5,
            "sellers_ka_defence_kahan": q6,
            "agar_rejection_hua_to_kahan_tak": q7,
            "kya_invalidation_hai": q8,
            "kya_confirmation_chahiye": q9,
            "abhi_trade_ya_wait": action_summary
        }


# Global instance
btc_market_battle_engine = BtcMarketBattleEngine()
