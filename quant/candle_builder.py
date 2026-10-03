"""
PROMETHEUS BTC TERMINAL: Candle Builder & Multi-Timeframe Resampler
Maintains UTC-aligned OHLCV candles across 1m, 3m, 5m, 15m, 30m, 1h, 4h, 1d.
Enforces strict confirmation gates: never treats an unfinished candle as confirmed close.
"""

from typing import Dict, List, Optional, Any, Tuple
from collections import defaultdict
import time
from datetime import datetime, timezone
import zoneinfo

IST = zoneinfo.ZoneInfo("Asia/Kolkata")

TIMEFRAME_SECONDS = {
    "1m": 60,
    "3m": 180,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "4h": 14400,
    "1d": 86400
}


class CandleBuilder:
    def __init__(self, max_candles: int = 500):
        self.max_candles = max_candles
        # Stores confirmed candles by timeframe: {tf: [candle_dict, ...]}
        self.candles: Dict[str, List[Dict[str, Any]]] = {tf: [] for tf in TIMEFRAME_SECONDS}
        # Current active (unclosed) candle per timeframe: {tf: candle_dict}
        self.active_candle: Dict[str, Optional[Dict[str, Any]]] = {tf: None for tf in TIMEFRAME_SECONDS}

    def seed_candles(self, timeframe: str, raw_candles: List[Dict[str, Any]]):
        """Seeds historical candles (sorted ascending by time)."""
        clean = []
        for c in raw_candles:
            t = int(c.get("time", 0))
            clean.append({
                "time": t,
                "open": float(c.get("open", 0.0)),
                "high": float(c.get("high", 0.0)),
                "low": float(c.get("low", 0.0)),
                "close": float(c.get("close", 0.0)),
                "volume": float(c.get("volume", 0.0)),
                "is_closed": True
            })
        clean.sort(key=lambda x: x["time"])
        self.candles[timeframe] = clean[-self.max_candles:]

    def on_1m_candle(self, c_1m: Dict[str, Any]):
        """Processes incoming 1-minute candle and rolls into multi-timeframe aggregations."""
        t = int(c_1m.get("time", 0))
        o = float(c_1m.get("open", 0.0))
        h = float(c_1m.get("high", 0.0))
        l = float(c_1m.get("low", 0.0))
        c = float(c_1m.get("close", 0.0))
        v = float(c_1m.get("volume", 0.0))

        c_dict = {
            "time": t,
            "open": o,
            "high": h,
            "low": l,
            "close": c,
            "volume": v,
            "is_closed": True
        }

        # Update 1m list
        if not self.candles["1m"] or self.candles["1m"][-1]["time"] < t:
            self.candles["1m"].append(c_dict)
            if len(self.candles["1m"]) > self.max_candles:
                self.candles["1m"].pop(0)
        elif self.candles["1m"][-1]["time"] == t:
            self.candles["1m"][-1] = c_dict

        # Roll into higher timeframes
        for tf, period_sec in TIMEFRAME_SECONDS.items():
            if tf == "1m":
                continue
            bucket_time = (t // period_sec) * period_sec
            self._aggregate_candle(tf, bucket_time, period_sec, c_dict)

    def _aggregate_candle(self, tf: str, bucket_time: int, period_sec: int, c_1m: Dict[str, Any]):
        active = self.active_candle[tf]

        if active is None or active["time"] != bucket_time:
            # If previous active candle was finished, push to confirmed
            if active is not None and (c_1m["time"] >= active["time"] + period_sec):
                active["is_closed"] = True
                self.candles[tf].append(active)
                if len(self.candles[tf]) > self.max_candles:
                    self.candles[tf].pop(0)

            # Start new candle
            self.active_candle[tf] = {
                "time": bucket_time,
                "open": c_1m["open"],
                "high": c_1m["high"],
                "low": c_1m["low"],
                "close": c_1m["close"],
                "volume": c_1m["volume"],
                "is_closed": False
            }
        else:
            # Update existing active candle
            active["high"] = max(active["high"], c_1m["high"])
            active["low"] = min(active["low"], c_1m["low"])
            active["close"] = c_1m["close"]
            active["volume"] += c_1m["volume"]

            # If this 1m bar completes the boundary
            if c_1m["time"] + 60 >= bucket_time + period_sec:
                active["is_closed"] = True
                self.candles[tf].append(active)
                if len(self.candles[tf]) > self.max_candles:
                    self.candles[tf].pop(0)
                self.active_candle[tf] = None

    def get_confirmed_candles(self, tf: str = "5m") -> List[Dict[str, Any]]:
        """Returns confirmed closed candles for reliable indicator calculation."""
        return list(self.candles.get(tf, []))

    def get_display_candles(self, tf: str = "5m", count: int = 100) -> List[Dict[str, Any]]:
        """Returns candles with timestamps formatted in IST and UTC for UI charts."""
        candles = list(self.candles.get(tf, []))
        if self.active_candle.get(tf):
            candles.append(self.active_candle[tf])

        res = []
        for c in candles[-count:]:
            dt_utc = datetime.fromtimestamp(c["time"], tz=timezone.utc)
            dt_ist = dt_utc.astimezone(IST)
            res.append({
                **c,
                "time_utc_iso": dt_utc.isoformat(),
                "time_ist": dt_ist.strftime("%d-%b %H:%M"),
                "time_display": dt_ist.strftime("%H:%M")
            })
        return res


candle_builder = CandleBuilder()
