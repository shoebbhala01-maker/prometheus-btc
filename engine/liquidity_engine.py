"""
PROMETHEUS BTC TERMINAL: Liquidity Map & Key Levels Engine
Tracks Previous UTC Day H/L, Session H/L, Swing pivots, EQH/EQL, Volume Profile nodes, and ATR distances.
Clearly separates Observed price levels vs Inferred liquidity zones.
"""

from typing import Dict, List, Optional, Any, Tuple
import math
from datetime import datetime, timezone


class LiquidityEngine:
    def evaluate_levels(
        self,
        candles_1m: List[Dict[str, Any]],
        spot_price: float,
        atr14: float
    ) -> Dict[str, Any]:
        """Computes comprehensive liquidity structure and distances."""
        if not candles_1m or spot_price <= 0:
            return {"status": "INSUFFICIENT_DATA", "levels": []}

        now_t = candles_1m[-1]["time"]
        curr_utc_day_start = (now_t // 86400) * 86400
        prev_utc_day_start = curr_utc_day_start - 86400

        # 1. Previous Completed UTC Day High & Low
        prev_day_candles = [c for c in candles_1m if prev_utc_day_start <= c["time"] < curr_utc_day_start]
        pdh = max((c["high"] for c in prev_day_candles), default=spot_price * 1.01)
        pdl = min((c["low"] for c in prev_day_candles), default=spot_price * 0.99)

        # 2. Current UTC Day High & Low
        curr_day_candles = [c for c in candles_1m if c["time"] >= curr_utc_day_start]
        cdh = max((c["high"] for c in curr_day_candles), default=spot_price)
        cdl = min((c["low"] for c in curr_day_candles), default=spot_price)

        # 3. Previous 8-Hour Session High & Low (Funding Sessions: 00:00, 08:00, 16:00 UTC)
        session_len = 28800  # 8 hours in seconds
        curr_session_start = (now_t // session_len) * session_len
        prev_session_start = curr_session_start - session_len
        prev_session_candles = [c for c in candles_1m if prev_session_start <= c["time"] < curr_session_start]
        psh = max((c["high"] for c in prev_session_candles), default=pdh)
        psl = min((c["low"] for c in prev_session_candles), default=pdl)

        # 4. Detect Equal Highs (EQH) and Equal Lows (EQL)
        eqh_list, eql_list = self._detect_equal_highs_lows(candles_1m[-120:], atr14)

        # 5. Volume Profile Value Area & Point of Control (POC)
        poc, val_area_high, val_area_low = self._calculate_volume_profile(candles_1m[-240:])

        # 6. Map all levels with ATR distances
        atr_safe = max(5.0, atr14)

        def make_level(name: str, price: float, level_type: str, category: str = "OBSERVED") -> Dict[str, Any]:
            dist_pts = round(price - spot_price, 1)
            dist_atr = round(dist_pts / atr_safe, 2)
            return {
                "name": name,
                "price": round(price, 1),
                "dist_pts": dist_pts,
                "dist_atr": dist_atr,
                "level_type": level_type,     # "RESISTANCE" or "SUPPORT"
                "category": category          # "OBSERVED" or "INFERRED_ZONE"
            }

        levels = [
            make_level("Prev UTC Day High (PDH)", pdh, "RESISTANCE", "OBSERVED"),
            make_level("Prev UTC Day Low (PDL)", pdl, "SUPPORT", "OBSERVED"),
            make_level("Current Day High (CDH)", cdh, "RESISTANCE", "OBSERVED"),
            make_level("Current Day Low (CDL)", cdl, "SUPPORT", "OBSERVED"),
            make_level("Prev 8h Session High", psh, "RESISTANCE", "OBSERVED"),
            make_level("Prev 8h Session Low", psl, "SUPPORT", "OBSERVED"),
            make_level("Volume Profile POC", poc, "SUPPORT" if spot_price > poc else "RESISTANCE", "INFERRED_ZONE"),
            make_level("Value Area High (VAH)", val_area_high, "RESISTANCE", "INFERRED_ZONE"),
            make_level("Value Area Low (VAL)", val_area_low, "SUPPORT", "INFERRED_ZONE"),
        ]

        for idx, eqh in enumerate(eqh_list):
            levels.append(make_level(f"Equal Highs (EQH #{idx+1})", eqh, "RESISTANCE", "INFERRED_ZONE"))
        for idx, eql in enumerate(eql_list):
            levels.append(make_level(f"Equal Lows (EQL #{idx+1})", eql, "SUPPORT", "INFERRED_ZONE"))

        # 5b. Local Intraday Swing High and Swing Low (Crucial for tight realistic SL & triggers)
        recent_c = candles_1m[-45:] if len(candles_1m) >= 45 else candles_1m
        if len(recent_c) >= 5:
            local_high = max(c["high"] for c in recent_c)
            local_low = min(c["low"] for c in recent_c)
            if local_high > spot_price:
                levels.append(make_level("Local Range Resistance", local_high, "RESISTANCE", "OBSERVED"))
            if local_low < spot_price:
                levels.append(make_level("Local Range Support", local_low, "SUPPORT", "OBSERVED"))

        # Sort by price descending
        levels.sort(key=lambda x: x["price"], reverse=True)

        # Find closest resistance above spot and closest support below spot
        res_above = [l for l in levels if l["price"] > spot_price]
        sup_below = [l for l in levels if l["price"] < spot_price]

        closest_res = min(res_above, key=lambda x: x["price"]) if res_above else make_level("Estimated Res", spot_price + atr_safe, "RESISTANCE")
        closest_sup = max(sup_below, key=lambda x: x["price"]) if sup_below else make_level("Estimated Sup", spot_price - atr_safe, "SUPPORT")

        return {
            "status": "VALID",
            "spot_price": round(spot_price, 1),
            "closest_resistance": closest_res,
            "closest_support": closest_sup,
            "range_span_pts": round(closest_res["price"] - closest_sup["price"], 1),
            "levels": levels,
            "liquidation_feed_status": "UNAVAILABLE (Exchange feed does not provide public individual account liquidation stream)"
        }

    def _detect_equal_highs_lows(self, candles: List[Dict[str, Any]], atr: float) -> Tuple[List[float], List[float]]:
        if len(candles) < 20:
            return [], []

        tolerance = max(2.0, 0.15 * atr)
        highs = [c["high"] for c in candles]
        lows = [c["low"] for c in candles]

        eqh = []
        eql = []

        # Find pairs of peaks within tolerance
        for i in range(5, len(highs) - 5):
            for j in range(i + 5, len(highs)):
                if abs(highs[i] - highs[j]) <= tolerance and highs[i] > max(highs[i-2:i]) and highs[j] > max(highs[j-2:j]):
                    eqh.append((highs[i] + highs[j]) / 2.0)
                if abs(lows[i] - lows[j]) <= tolerance and lows[i] < min(lows[i-2:i]) and lows[j] < min(lows[j-2:j]):
                    eql.append((lows[i] + lows[j]) / 2.0)

        # Deduplicate
        eqh_unique = []
        for h in eqh:
            if not any(abs(h - x) <= tolerance for x in eqh_unique):
                eqh_unique.append(round(h, 1))

        eql_unique = []
        for l in eql:
            if not any(abs(l - x) <= tolerance for x in eql_unique):
                eql_unique.append(round(l, 1))

        return eqh_unique[:3], eql_unique[:3]

    def _calculate_volume_profile(self, candles: List[Dict[str, Any]], num_bins: int = 24) -> Tuple[float, float, float]:
        if not candles:
            return 0.0, 0.0, 0.0

        min_p = min(c["low"] for c in candles)
        max_p = max(c["high"] for c in candles)
        if max_p <= min_p:
            return min_p, max_p, min_p

        bin_size = (max_p - min_p) / num_bins
        bins = [0.0] * num_bins

        for c in candles:
            typ_p = (c["high"] + c["low"] + c["close"]) / 3.0
            v = c.get("volume", 1.0)
            bin_idx = min(num_bins - 1, int((typ_p - min_p) / bin_size))
            bins[bin_idx] += v

        max_bin_idx = bins.index(max(bins))
        poc = min_p + (max_bin_idx + 0.5) * bin_size

        # Value Area 70% of total volume
        total_vol = sum(bins)
        target_vol = total_vol * 0.70
        curr_vol = bins[max_bin_idx]
        up_idx = max_bin_idx
        dn_idx = max_bin_idx

        while curr_vol < target_vol and (up_idx < num_bins - 1 or dn_idx > 0):
            up_v = bins[up_idx + 1] if up_idx < num_bins - 1 else 0.0
            dn_v = bins[dn_idx - 1] if dn_idx > 0 else 0.0
            if up_v >= dn_v:
                curr_vol += up_v
                up_idx += 1
            else:
                curr_vol += dn_v
                dn_idx -= 1

        val_area_high = min_p + (up_idx + 1) * bin_size
        val_area_low = min_p + dn_idx * bin_size

        return round(poc, 1), round(val_area_high, 1), round(val_area_low, 1)


liquidity_engine = LiquidityEngine()
