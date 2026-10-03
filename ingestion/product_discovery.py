"""
PROMETHEUS BTC TERMINAL: Dynamic Product Discovery Service
Discovers BTC perpetual futures and all listed BTC options dynamically without hardcoded IDs or dates.
Converts UTC settlement timestamps to Asia/Kolkata (IST) for display.
"""

from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timezone
import zoneinfo
import re

from config.settings import config
from ingestion.delta_rest_client import delta_rest_client

IST = zoneinfo.ZoneInfo("Asia/Kolkata")


class ProductDiscoveryService:
    def __init__(self):
        self.perp_contract: Dict[str, Any] = {}
        self.all_options: List[Dict[str, Any]] = []
        self.expiry_dates: List[str] = []
        self.last_discovery_time: float = 0.0
        self.is_discovered: bool = False

    def discover_products(self) -> Dict[str, Any]:
        """Fetches all product metadata from Delta Exchange India."""
        products = delta_rest_client.get_products()

        # 1. Discover BTC Perpetual Contract
        btc_perps = [
            p for p in products
            if p.get("contract_type") in ("perpetual_futures", "futures")
            and p.get("underlying_asset", {}).get("symbol") == "BTC"
            and p.get("state") == "live"
        ]

        if not btc_perps:
            # Fallback to symbol match
            btc_perps = [
                p for p in products
                if p.get("symbol") == config.default_perp_symbol
            ]

        if not btc_perps:
            raise RuntimeError("BTC perpetual contract could not be discovered from Delta metadata!")

        # Prefer BTCUSD perpetual
        selected_perp = next((p for p in btc_perps if p.get("symbol") == "BTCUSD"), btc_perps[0])
        self.perp_contract = {
            "id": selected_perp.get("id"),
            "symbol": selected_perp.get("symbol"),
            "contract_type": selected_perp.get("contract_type"),
            "contract_value": float(selected_perp.get("contract_value", 0.001)),
            "tick_size": float(selected_perp.get("tick_size", 0.5)),
            "quoting_asset": selected_perp.get("quoting_asset", {}).get("symbol", "USD"),
            "settling_asset": selected_perp.get("settling_asset", {}).get("symbol", "USD"),
            "maker_commission_rate": float(selected_perp.get("maker_commission_rate", 0.0002)),
            "taker_commission_rate": float(selected_perp.get("taker_commission_rate", 0.0005)),
            "description": selected_perp.get("description", "Bitcoin Perpetual Futures")
        }

        # 2. Discover BTC Options
        btc_options = [
            p for p in products
            if p.get("contract_type") in ("call_options", "put_options")
            and (p.get("underlying_asset", {}).get("symbol") == "BTC" or "BTC" in p.get("symbol", ""))
            and p.get("state") == "live"
        ]

        parsed_options = []
        unique_expiries = set()

        for opt in btc_options:
            symbol = opt.get("symbol", "")
            raw_settlement = opt.get("settlement_time")
            strike = float(opt.get("strike_price") or 0.0)

            # Parse expiry datetime
            dt_utc = None
            if raw_settlement:
                try:
                    dt_utc = datetime.fromisoformat(raw_settlement.replace("Z", "+00:00"))
                except Exception:
                    pass

            if dt_utc is None:
                continue

            dt_ist = dt_utc.astimezone(IST)
            expiry_str_utc = dt_utc.strftime("%Y-%m-%d")
            expiry_str_ist = dt_ist.strftime("%d-%b-%Y %H:%M IST")

            unique_expiries.add(expiry_str_utc)

            parsed_options.append({
                "id": opt.get("id"),
                "symbol": symbol,
                "contract_type": opt.get("contract_type"),
                "strike_price": strike,
                "contract_value": float(opt.get("contract_value", 0.001)),
                "tick_size": float(opt.get("tick_size", 0.1)),
                "settlement_time_utc_iso": dt_utc.isoformat(),
                "settlement_time_ist": expiry_str_ist,
                "settlement_timestamp": int(dt_utc.timestamp()),
                "expiry_date": expiry_str_utc
            })

        self.all_options = parsed_options
        self.expiry_dates = sorted(list(unique_expiries))
        self.last_discovery_time = datetime.now(timezone.utc).timestamp()
        self.is_discovered = True

        return {
            "perp": self.perp_contract,
            "options_count": len(self.all_options),
            "expiries": self.expiry_dates
        }

    def get_nearest_expiry(self) -> Optional[str]:
        """Returns the earliest active expiry date string (YYYY-MM-DD)."""
        now_ts = datetime.now(timezone.utc).timestamp()
        valid_expiries = []
        for exp in self.expiry_dates:
            # Check if any contract under this expiry has settlement > now
            settlement_ts = next((o["settlement_timestamp"] for o in self.all_options if o["expiry_date"] == exp), None)
            if settlement_ts and settlement_ts > now_ts:
                valid_expiries.append((settlement_ts, exp))
        
        if valid_expiries:
            valid_expiries.sort(key=lambda x: x[0])
            return valid_expiries[0][1]
        return self.expiry_dates[0] if self.expiry_dates else None

    def get_options_for_expiry(self, expiry_date: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Returns (calls, puts) sorted by strike price for the requested expiry."""
        opts = [o for o in self.all_options if o["expiry_date"] == expiry_date]
        calls = [o for o in opts if o["contract_type"] == "call_options"]
        puts = [o for o in opts if o["contract_type"] == "put_options"]
        calls.sort(key=lambda x: x["strike_price"])
        puts.sort(key=lambda x: x["strike_price"])
        return calls, puts


product_discovery = ProductDiscoveryService()
