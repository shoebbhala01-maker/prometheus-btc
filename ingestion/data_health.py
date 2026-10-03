"""
PROMETHEUS BTC TERMINAL: Data Quality & Observability Watchdog
Monitors per-feed health, latency, staleness, book integrity, and acts as a circuit breaker for signals.
"""

from typing import Dict, List, Optional, Any
import time
from datetime import datetime
import zoneinfo

from config.constants import FeedStatus
from config.settings import config

IST = zoneinfo.ZoneInfo("Asia/Kolkata")


class DataHealthWatchdog:
    CRITICAL_FEEDS = ["REST_API", "WEBSOCKET", "TICKER", "ORDERBOOK", "TRADES", "CANDLES"]

    def __init__(self):
        self.feed_stats: Dict[str, Dict[str, Any]] = {
            f: {
                "last_update_ts": 0.0,
                "status": FeedStatus.UNAVAILABLE.value,
                "error_count": 0,
                "msg_count": 0,
                "latency_ms": 0.0
            }
            for f in self.CRITICAL_FEEDS
        }
        self.reconnect_count = 0
        self.calculation_exceptions = 0
        self.anomalies_detected: List[str] = []
        self.is_circuit_broken: bool = False
        self.circuit_break_reason: str = ""

    def record_feed_update(self, feed_name: str, latency_ms: float = 0.0, is_success: bool = True):
        now = time.time()
        if feed_name not in self.feed_stats:
            self.feed_stats[feed_name] = {
                "last_update_ts": now,
                "status": FeedStatus.HEALTHY.value,
                "error_count": 0,
                "msg_count": 1,
                "latency_ms": latency_ms
            }
            return

        stat = self.feed_stats[feed_name]
        stat["msg_count"] += 1
        stat["latency_ms"] = round(latency_ms, 1)

        if is_success:
            stat["last_update_ts"] = now
            stat["status"] = FeedStatus.HEALTHY.value
        else:
            stat["error_count"] += 1
            stat["status"] = FeedStatus.DEGRADED.value

    def record_exception(self, component: str, error_msg: str):
        self.calculation_exceptions += 1
        anomaly = f"[{component}] {error_msg}"
        self.anomalies_detected.append(anomaly)
        if len(self.anomalies_detected) > 50:
            self.anomalies_detected.pop(0)

    def evaluate_health(self) -> Dict[str, Any]:
        """Evaluates overall health and triggers circuit breaker if critical feeds are stale."""
        now = time.time()
        critical_stale = False
        stale_reasons = []

        summary_feeds = {}
        for feed, stat in self.feed_stats.items():
            age = (now - stat["last_update_ts"]) if stat["last_update_ts"] > 0 else 999.0
            
            if stat["last_update_ts"] == 0:
                current_status = FeedStatus.UNAVAILABLE.value
            elif age > config.staleness_critical_seconds:
                current_status = FeedStatus.STALE.value
                critical_stale = True
                stale_reasons.append(f"{feed} stale ({age:.1f}s)")
            elif age > config.staleness_warning_seconds:
                current_status = FeedStatus.DEGRADED.value
            else:
                current_status = FeedStatus.HEALTHY.value

            stat["status"] = current_status
            last_dt = datetime.fromtimestamp(stat["last_update_ts"], tz=IST) if stat["last_update_ts"] > 0 else None
            
            summary_feeds[feed] = {
                "status": current_status,
                "age_seconds": round(age, 1) if age < 900 else None,
                "last_update_ist": last_dt.strftime("%H:%M:%S IST") if last_dt else "NEVER",
                "latency_ms": stat["latency_ms"],
                "error_count": stat["error_count"]
            }

        # Circuit breaker trigger
        if critical_stale and ("TICKER" in stale_reasons or "WEBSOCKET" in stale_reasons or "REST_API" in stale_reasons):
            self.is_circuit_broken = True
            self.circuit_break_reason = f"CRITICAL FEED STALENESS: {', '.join(stale_reasons)}"
        else:
            self.is_circuit_broken = False
            self.circuit_break_reason = ""

        overall_status = FeedStatus.DISCONNECTED.value if self.is_circuit_broken else (
            FeedStatus.DEGRADED.value if any(s["status"] == FeedStatus.DEGRADED.value for s in summary_feeds.values()) else FeedStatus.HEALTHY.value
        )

        return {
            "overall_status": overall_status,
            "is_circuit_broken": self.is_circuit_broken,
            "circuit_break_reason": self.circuit_break_reason,
            "reconnect_count": self.reconnect_count,
            "calculation_exceptions": self.calculation_exceptions,
            "feeds": summary_feeds,
            "recent_anomalies": self.anomalies_detected[-5:]
        }

    def validate_orderbook(self, best_bid: float, best_ask: float) -> bool:
        """Validates that orderbook is not crossed or zero."""
        if best_bid <= 0 or best_ask <= 0:
            self.record_exception("ORDERBOOK", "Invalid zero price in orderbook")
            return False
        if best_bid >= best_ask:
            self.record_exception("ORDERBOOK", f"Crossed book detected! Bid ({best_bid}) >= Ask ({best_ask})")
            return False
        return True


health_watchdog = DataHealthWatchdog()
