"""
PROMETHEUS BTC TERMINAL: Order Flow, Volume Delta & Microstructure Engine
Computes trade aggressor volume, CVD, delta changes, and depth imbalance across price bands.
"""

from typing import Dict, List, Optional, Any, Tuple
from collections import deque
import time


class OrderflowEngine:
    def __init__(self, history_len: int = 100):
        self.history_len = history_len
        self.cumulative_volume_delta = 0.0
        # Rolling minute buckets for 1m, 5m, 15m delta changes: [(timestamp, delta, price), ...]
        self.delta_history: deque = deque(maxlen=900)  # 15 minutes of 1-sec/event aggregates
        self.current_orderbook: Dict[str, Any] = {"buy": [], "sell": [], "best_bid": 0.0, "best_ask": 0.0}
        self.total_buy_vol = 0.0
        self.total_sell_vol = 0.0

    def process_trades(self, trades: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Classifies aggressive buy and sell volume from Delta India trade execution role.
        taker buyer = aggressive buy
        taker seller = aggressive sell
        """
        buy_vol = 0.0
        sell_vol = 0.0
        unclassified_vol = 0.0
        last_price = 0.0

        for t in trades:
            size = float(t.get("size", 0.0))
            price = float(t.get("price", 0.0))
            if price > 0:
                last_price = price

            buyer_role = t.get("buyer_role")
            seller_role = t.get("seller_role")

            if buyer_role == "taker":
                buy_vol += size
            elif seller_role == "taker":
                sell_vol += size
            else:
                unclassified_vol += size

        volume_delta = buy_vol - sell_vol
        total_classified = buy_vol + sell_vol
        norm_delta = (volume_delta / total_classified) if total_classified > 0 else 0.0

        self.cumulative_volume_delta += volume_delta
        self.total_buy_vol += buy_vol
        self.total_sell_vol += sell_vol

        now = time.time()
        if last_price > 0:
            self.delta_history.append((now, volume_delta, last_price))

        # Calculate 1m, 5m, 15m delta changes
        d_1m = sum(d for t_ts, d, _ in self.delta_history if t_ts >= now - 60)
        d_5m = sum(d for t_ts, d, _ in self.delta_history if t_ts >= now - 300)
        d_15m = sum(d for t_ts, d, _ in self.delta_history if t_ts >= now - 900)

        return {
            "buy_volume": round(buy_vol, 3),
            "sell_volume": round(sell_vol, 3),
            "volume_delta": round(volume_delta, 3),
            "normalized_delta": round(norm_delta, 3),
            "cvd": round(self.cumulative_volume_delta, 3),
            "delta_1m": round(d_1m, 3),
            "delta_5m": round(d_5m, 3),
            "delta_15m": round(d_15m, 3),
            "aggressor_status": "AVAILABLE" if total_classified > 0 else "NO_TRADES"
        }

    def update_orderbook(self, book_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Updates L2 book and computes spread, depth, and depth imbalance at basis-point bands.
        """
        buys = book_data.get("buy", [])
        sells = book_data.get("sell", [])

        if not buys or not sells:
            return {
                "best_bid": 0.0,
                "best_ask": 0.0,
                "spread": 0.0,
                "spread_bps": 0.0,
                "imbalance_25bps": 0.0,
                "imbalance_50bps": 0.0,
                "imbalance_100bps": 0.0
            }

        # Delta orderbook: buy and sell arrays sorted by limit_price
        best_bid = float(buys[0].get("limit_price", 0.0))
        best_ask = float(sells[0].get("limit_price", 0.0))
        mid_price = (best_bid + best_ask) / 2.0 if (best_bid + best_ask) > 0 else 1.0

        spread = max(0.0, best_ask - best_bid)
        spread_bps = (spread / mid_price) * 10000.0

        # Calculate Depth Imbalance at 10, 25, 50, 100 bps
        imbalance_10bps = self._calc_band_imbalance(buys, sells, mid_price, 10.0)
        imbalance_25bps = self._calc_band_imbalance(buys, sells, mid_price, 25.0)
        imbalance_50bps = self._calc_band_imbalance(buys, sells, mid_price, 50.0)
        imbalance_100bps = self._calc_band_imbalance(buys, sells, mid_price, 100.0)

        # Detect large resting orders (>= 5 BTC or 5000 contracts)
        large_bids = [
            {"price": float(b["limit_price"]), "size": float(b.get("size", 0.0))}
            for b in buys[:20] if float(b.get("size", 0.0)) >= 5000.0
        ]
        large_asks = [
            {"price": float(s["limit_price"]), "size": float(s.get("size", 0.0))}
            for s in sells[:20] if float(s.get("size", 0.0)) >= 5000.0
        ]

        self.current_orderbook = {
            "best_bid": best_bid,
            "best_ask": best_ask,
            "mid_price": round(mid_price, 2),
            "spread": round(spread, 2),
            "spread_bps": round(spread_bps, 2),
            "imbalance_10bps": imbalance_10bps,
            "imbalance_25bps": imbalance_25bps,
            "imbalance_50bps": imbalance_50bps,
            "imbalance_100bps": imbalance_100bps,
            "large_bids": large_bids,
            "large_asks": large_asks,
            "top_10_bids": [{"price": float(b["limit_price"]), "size": float(b.get("size", 0.0))} for b in buys[:10]],
            "top_10_asks": [{"price": float(s["limit_price"]), "size": float(s.get("size", 0.0))} for s in sells[:10]]
        }

        return self.current_orderbook

    def _calc_band_imbalance(self, buys: List[Dict[str, Any]], sells: List[Dict[str, Any]], mid_price: float, bps: float) -> float:
        threshold = mid_price * (bps / 10000.0)
        bid_depth = sum(float(b.get("size", 0.0)) for b in buys if (mid_price - float(b.get("limit_price", 0.0))) <= threshold)
        ask_depth = sum(float(s.get("size", 0.0)) for s in sells if (float(s.get("limit_price", 0.0)) - mid_price) <= threshold)

        total_depth = bid_depth + ask_depth
        if total_depth <= 0:
            return 0.0
        return round((bid_depth - ask_depth) / total_depth, 3)


orderflow_engine = OrderflowEngine()
