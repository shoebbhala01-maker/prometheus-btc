"""
PROMETHEUS BTC TERMINAL: BTC Options Analytics Engine
Builds live strike ladder, ATM finder, Greeks aggregator, PCR, Max Pain, and P&L simulator.
Respects Delta Exchange India contract multiplier (0.001 BTC) and fee schedule.
"""

from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timezone
import math
import zoneinfo

from config.settings import config
from ingestion.product_discovery import product_discovery

IST = zoneinfo.ZoneInfo("Asia/Kolkata")


class OptionsAnalyticsEngine:
    def __init__(self):
        self.cached_chain: Dict[str, Any] = {}

    def build_option_chain(self, raw_tickers: List[Dict[str, Any]], spot_price: float, selected_expiry: Optional[str] = None) -> Dict[str, Any]:
        """
        Organizes raw Delta options tickers into a structured strike ladder.
        Computes ATM strike, PCR, Max Pain, and Greeks summary.
        """
        if not product_discovery.is_discovered:
            product_discovery.discover_products()

        active_expiry = selected_expiry or product_discovery.get_nearest_expiry()
        if not active_expiry:
            return {"status": "NO_EXPIRIES_FOUND", "strikes": []}

        # Index tickers by symbol
        ticker_map = {t.get("symbol"): t for t in raw_tickers if t.get("symbol")}

        calls_meta, puts_meta = product_discovery.get_options_for_expiry(active_expiry)
        
        # Combine strikes
        all_strikes = sorted(list(set([c["strike_price"] for c in calls_meta] + [p["strike_price"] for p in puts_meta])))
        if not all_strikes:
            return {"status": "EMPTY_STRIKES", "strikes": []}

        # Identify ATM strike (closest to spot)
        atm_strike = min(all_strikes, key=lambda s: abs(s - spot_price)) if spot_price > 0 else all_strikes[len(all_strikes)//2]

        # Calculate time to expiry in seconds
        sample_opt = calls_meta[0] if calls_meta else (puts_meta[0] if puts_meta else None)
        settlement_ts = sample_opt["settlement_timestamp"] if sample_opt else 0
        now_ts = datetime.now(timezone.utc).timestamp()
        seconds_to_expiry = max(0, settlement_ts - now_ts)
        hours_to_expiry = round(seconds_to_expiry / 3600.0, 1)

        ladder = []
        total_call_oi = 0.0
        total_put_oi = 0.0
        total_call_vol = 0.0
        total_put_vol = 0.0

        for strike in all_strikes:
            call_m = next((c for c in calls_meta if c["strike_price"] == strike), None)
            put_m = next((p for p in puts_meta if p["strike_price"] == strike), None)

            call_tick = ticker_map.get(call_m["symbol"], {}) if call_m else {}
            put_tick = ticker_map.get(put_m["symbol"], {}) if put_m else {}

            # Parse Call Data
            call_oi = float(call_tick.get("oi") or 0.0)
            call_vol = float(call_tick.get("volume") or 0.0)
            call_greeks = call_tick.get("greeks") or {}
            call_quotes = call_tick.get("quotes") or {}

            # Parse Put Data
            put_oi = float(put_tick.get("oi") or 0.0)
            put_vol = float(put_tick.get("volume") or 0.0)
            put_greeks = put_tick.get("greeks") or {}
            put_quotes = put_tick.get("quotes") or {}

            total_call_oi += call_oi
            total_put_oi += put_oi
            total_call_vol += call_vol
            total_put_vol += put_vol

            ladder.append({
                "strike": strike,
                "is_atm": (strike == atm_strike),
                "distance_pct": round(((strike - spot_price) / spot_price) * 100.0, 2) if spot_price > 0 else 0.0,
                "call": {
                    "symbol": call_m["symbol"] if call_m else None,
                    "ltp": float(call_tick.get("close") or 0.0),
                    "mark_price": float(call_tick.get("mark_price") or 0.0),
                    "bid": float(call_quotes.get("best_bid") or 0.0),
                    "ask": float(call_quotes.get("best_ask") or 0.0),
                    "iv": round(float(call_quotes.get("mark_iv") or call_tick.get("mark_vol") or 0.0) * 100.0, 1),
                    "delta": float(call_greeks.get("delta") or 0.0),
                    "gamma": float(call_greeks.get("gamma") or 0.0),
                    "theta": float(call_greeks.get("theta") or 0.0),
                    "vega": float(call_greeks.get("vega") or 0.0),
                    "oi": round(call_oi, 3),
                    "volume": round(call_vol, 3)
                },
                "put": {
                    "symbol": put_m["symbol"] if put_m else None,
                    "ltp": float(put_tick.get("close") or 0.0),
                    "mark_price": float(put_tick.get("mark_price") or 0.0),
                    "bid": float(put_quotes.get("best_bid") or 0.0),
                    "ask": float(put_quotes.get("best_ask") or 0.0),
                    "iv": round(float(put_quotes.get("mark_iv") or put_tick.get("mark_vol") or 0.0) * 100.0, 1),
                    "delta": float(put_greeks.get("delta") or 0.0),
                    "gamma": float(put_greeks.get("gamma") or 0.0),
                    "theta": float(put_greeks.get("theta") or 0.0),
                    "vega": float(put_greeks.get("vega") or 0.0),
                    "oi": round(put_oi, 3),
                    "volume": round(put_vol, 3)
                }
            })

        # Put-Call Ratio
        pcr_oi = round(total_put_oi / total_call_oi, 3) if total_call_oi > 0 else 1.0
        pcr_vol = round(total_put_vol / total_call_vol, 3) if total_call_vol > 0 else 1.0

        # Max Pain calculation across all active strikes
        max_pain_strike = self._calculate_max_pain(ladder)

        # Expiry formatting in IST
        exp_dt_utc = datetime.fromtimestamp(settlement_ts, tz=timezone.utc)
        exp_dt_ist = exp_dt_utc.astimezone(IST)

        self.cached_chain = {
            "status": "VALID",
            "selected_expiry": active_expiry,
            "available_expiries": product_discovery.expiry_dates,
            "settlement_time_ist": exp_dt_ist.strftime("%d-%b-%Y %H:%M IST"),
            "hours_to_expiry": hours_to_expiry,
            "seconds_to_expiry": int(seconds_to_expiry),
            "spot_price": spot_price,
            "atm_strike": atm_strike,
            "max_pain_strike": max_pain_strike,
            "pcr_oi": pcr_oi,
            "pcr_vol": pcr_vol,
            "total_call_oi_btc": round(total_call_oi, 2),
            "total_put_oi_btc": round(total_put_oi, 2),
            "strikes_count": len(ladder),
            "ladder": ladder
        }

        return self.cached_chain

    def _calculate_max_pain(self, ladder: List[Dict[str, Any]]) -> float:
        """
        Finds the strike price that causes the least total option intrinsic payout for option buyers.
        """
        if not ladder:
            return 0.0

        min_loss = float("inf")
        best_strike = ladder[0]["strike"]

        for test_s in ladder:
            k = test_s["strike"]
            total_payout = 0.0
            for item in ladder:
                s = item["strike"]
                c_oi = item["call"]["oi"]
                p_oi = item["put"]["oi"]

                # If market settles at k:
                # Calls with strike s payout max(0, k - s) * c_oi
                if k > s:
                    total_payout += (k - s) * c_oi
                # Puts with strike s payout max(0, s - k) * p_oi
                if s > k:
                    total_payout += (s - k) * p_oi

            if total_payout < min_loss:
                min_loss = total_payout
                best_strike = k

        return best_strike

    @staticmethod
    def calculate_option_pnl(
        entry_price: float,
        exit_price: float,
        contracts: int,
        is_call: bool,
        is_long: bool = True
    ) -> Dict[str, Any]:
        """
        Simulates exact option P&L using Delta Exchange specifications:
        1 contract = 0.001 BTC
        Taker fee = 0.03% (capped at 10% premium)
        """
        multiplier = config.risk.contract_value_btc
        premium_diff = (exit_price - entry_price) if is_long else (entry_price - exit_price)
        gross_pnl = premium_diff * contracts * multiplier

        # Fees
        fee_rate = config.risk.options_taker_fee
        entry_fee = min(entry_price * fee_rate, entry_price * 0.10) * contracts * multiplier
        exit_fee = min(exit_price * fee_rate, exit_price * 0.10) * contracts * multiplier
        total_fees = entry_fee + exit_fee

        net_pnl = gross_pnl - total_fees
        return {
            "gross_pnl_usd": round(gross_pnl, 2),
            "net_pnl_usd": round(net_pnl, 2),
            "fees_usd": round(total_fees, 2),
            "contracts": contracts,
            "btc_exposure": round(contracts * multiplier, 4)
        }


options_analytics = OptionsAnalyticsEngine()
