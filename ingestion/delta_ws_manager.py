"""
PROMETHEUS BTC TERMINAL: Delta Exchange India WebSocket Manager
Manages real-time feeds, auto-reconnection, heartbeat, subscriptions, and REST resync.
"""

import json
import time
import threading
from typing import Dict, List, Optional, Any, Callable
import websocket

from config.settings import config
from ingestion.data_health import health_watchdog


class DeltaWebSocketManager:
    def __init__(self):
        self.ws_url = config.ws_primary_url
        self.fallback_url = config.ws_fallback_url
        self.ws: Optional[websocket.WebSocketApp] = None
        self.thread: Optional[threading.Thread] = None
        self.is_running = False
        self.is_connected = False
        self.reconnect_delay = 1.0

        # Subscribed Callbacks
        self.ticker_callbacks: List[Callable[[Dict[str, Any]], None]] = []
        self.trade_callbacks: List[Callable[[List[Dict[str, Any]]], None]] = []
        self.orderbook_callbacks: List[Callable[[Dict[str, Any]], None]] = []
        self.candle_callbacks: List[Callable[[Dict[str, Any]], None]] = []
        self.resync_callbacks: List[Callable[[], None]] = []

    def register_ticker_cb(self, cb: Callable[[Dict[str, Any]], None]):
        self.ticker_callbacks.append(cb)

    def register_trade_cb(self, cb: Callable[[List[Dict[str, Any]]], None]):
        self.trade_callbacks.append(cb)

    def register_orderbook_cb(self, cb: Callable[[Dict[str, Any]], None]):
        self.orderbook_callbacks.append(cb)

    def register_candle_cb(self, cb: Callable[[Dict[str, Any]], None]):
        self.candle_callbacks.append(cb)

    def register_resync_cb(self, cb: Callable[[], None]):
        self.resync_callbacks.append(cb)

    def start(self):
        if self.is_running:
            return
        self.is_running = True
        self.thread = threading.Thread(target=self._connection_loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.is_running = False
        if self.ws:
            self.ws.close()

    def _connection_loop(self):
        while self.is_running:
            try:
                t0 = time.time()
                self.ws = websocket.WebSocketApp(
                    self.ws_url,
                    on_open=self._on_open,
                    on_message=self._on_message,
                    on_error=self._on_error,
                    on_close=self._on_close
                )
                health_watchdog.record_feed_update("WEBSOCKET", latency_ms=(time.time() - t0) * 1000, is_success=True)
                self.ws.run_forever(ping_interval=15, ping_timeout=10)
            except Exception as e:
                health_watchdog.record_exception("WEBSOCKET_LOOP", str(e))
                health_watchdog.record_feed_update("WEBSOCKET", is_success=False)

            if not self.is_running:
                break

            health_watchdog.reconnect_count += 1
            time.sleep(self.reconnect_delay)
            self.reconnect_delay = min(15.0, self.reconnect_delay * 1.5)

    def _on_open(self, ws):
        self.is_connected = True
        self.reconnect_delay = 1.0
        health_watchdog.record_feed_update("WEBSOCKET", is_success=True)

        # Send subscriptions
        symbols = [config.default_perp_symbol]
        sub_msg = {
            "type": "subscribe",
            "payload": {
                "channels": [
                    {"name": "l2_orderbook", "symbols": symbols},
                    {"name": "all_trades", "symbols": symbols},
                    {"name": "v2/ticker", "symbols": symbols},
                    {"name": "candlestick_1m", "symbols": symbols}
                ]
            }
        }
        try:
            ws.send(json.dumps(sub_msg))
        except Exception as e:
            health_watchdog.record_exception("WS_SUB", str(e))

        # Trigger REST resynchronization upon connection or reconnection
        for cb in self.resync_callbacks:
            try:
                cb()
            except Exception as e:
                health_watchdog.record_exception("RESYNC_CB", str(e))

    def _on_message(self, ws, message_str: str):
        try:
            msg = json.loads(message_str)
            msg_type = msg.get("type")
            t_now = time.time()

            if msg_type in ("l2_orderbook", "l2_updates") or ("buy" in msg and "sell" in msg):
                health_watchdog.record_feed_update("ORDERBOOK", is_success=True)
                for cb in self.orderbook_callbacks:
                    cb(msg)

            elif msg_type in ("v2/ticker", "ticker") or ("symbol" in msg and "quotes" in msg) or ("close" in msg and "mark_price" in msg):
                health_watchdog.record_feed_update("TICKER", is_success=True)
                for cb in self.ticker_callbacks:
                    cb(msg)

            elif msg_type in ("all_trades", "trades", "all_trades_snapshot") or ("trades" in msg):
                health_watchdog.record_feed_update("TRADES", is_success=True)
                trades = msg.get("trades", [])
                if not trades and "p" in msg:
                    # Single trade format on public socket
                    trades = [{
                        "price": msg.get("p"),
                        "size": msg.get("s"),
                        "timestamp": msg.get("t"),
                        "buyer_role": "taker" if msg.get("r") == "t" else "maker",
                        "seller_role": "taker" if msg.get("r") != "t" else "maker"
                    }]
                if trades:
                    for cb in self.trade_callbacks:
                        cb(trades)

            elif msg_type == "candlestick_1m" or ("candle" in msg):
                health_watchdog.record_feed_update("CANDLES", is_success=True)
                for cb in self.candle_callbacks:
                    cb(msg)

        except Exception as e:
            health_watchdog.record_exception("WS_MSG_PARSE", str(e))

    def _on_error(self, ws, error):
        self.is_connected = False
        health_watchdog.record_exception("WEBSOCKET_ERR", str(error))
        health_watchdog.record_feed_update("WEBSOCKET", is_success=False)

    def _on_close(self, ws, close_status_code, close_msg):
        self.is_connected = False
        health_watchdog.record_feed_update("WEBSOCKET", is_success=False)


ws_manager = DeltaWebSocketManager()
