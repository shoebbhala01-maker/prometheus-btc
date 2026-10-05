"""
PROMETHEUS BTC TERMINAL: Central Orchestrator & State Service
Coordinates all quantitative modules, ingests Delta India market data, and emits authoritative terminal telemetry.
"""

from typing import Dict, List, Optional, Any
import time
import threading
from datetime import datetime, timezone
import zoneinfo

from config.settings import config
from config.constants import FeedStatus, DecisionState
from database.db_manager import db
from ingestion.delta_rest_client import delta_rest_client
from ingestion.delta_ws_manager import ws_manager
from ingestion.product_discovery import product_discovery
from ingestion.data_health import health_watchdog
from quant.candle_builder import candle_builder
from quant.indicator_engine import indicator_engine
from quant.orderflow_engine import orderflow_engine
from quant.options_analytics import options_analytics
from engine.market_regime_engine import regime_engine
from engine.breakout_engine import breakout_engine
from engine.spike_radar import spike_radar
from engine.liquidity_engine import liquidity_engine
from engine.setup_scoring_engine import setup_scoring_engine
from engine.risk_governor import risk_governor
from engine.telegram_alerter import telegram_alerter
from backtest.paper_trading_engine import paper_trader

IST = zoneinfo.ZoneInfo("Asia/Kolkata")


class TerminalService:
    def __init__(self):
        self.latest_state: Dict[str, Any] = {}
        self.is_running = False
        self._lock = threading.Lock()
        self.last_resync_time = 0.0
        self.last_price_update = 0.0
        self.live_spot = 86350.0
        self.live_best_bid = 86349.5
        self.live_best_ask = 86350.5
        self.live_mark = 86350.0
        self.broadcast_cbs: List[Any] = []
        self._init_baseline_state()

        # Wire up WebSocket callbacks
        ws_manager.register_ticker_cb(self._on_ws_ticker)
        ws_manager.register_trade_cb(self._on_ws_trades)
        ws_manager.register_orderbook_cb(self._on_ws_orderbook)
        ws_manager.register_candle_cb(self._on_ws_candle)
        ws_manager.register_resync_cb(self.resync_market_data)

    def _init_baseline_state(self):
        now_dt_utc = datetime.now(timezone.utc)
        now_dt_ist = now_dt_utc.astimezone(IST)
        self.latest_state = {
            "timestamp": now_dt_utc.isoformat(),
            "timestamp_ist": now_dt_ist.strftime("%d-%b-%Y %H:%M:%S IST"),
            "contract": {
                "symbol": config.default_perp_symbol,
                "description": "Bitcoin Perpetual",
                "contract_value": 0.001,
                "tick_size": 0.5,
                "maker_fee_pct": 0.02,
                "taker_fee_pct": 0.05
            },
            "telemetry": {
                "spot": self.live_spot,
                "best_bid": self.live_best_bid,
                "best_ask": self.live_best_ask,
                "spread": 1.0,
                "spread_bps": 0.12,
                "vwap": self.live_spot,
                "dist_vwap_atr": 0.0,
                "atr14": 150.0,
                "rsi14": 52.0,
                "adx14": 22.0,
                "rvol": 1.1,
                "realized_vol_pct": 38.5,
                "cvd": 0.0,
                "imbalance_25bps": 0.0
            },
            "regime": {"regime": "RANGE", "confidence": 70.0, "sub_regime": "NEUTRAL_RANGE", "notes": "Initial state"},
            "breakout": {"stage": "MONITORING", "direction": "NEUTRAL"},
            "spike_radar": {"risk_level": "LOW"},
            "liquidity": {"closest_support": {"price": self.live_spot - 200, "name": "Key Sup"}, "closest_resistance": {"price": self.live_spot + 200, "name": "Key Res"}},
            "setup_decision": {"decision": "WAIT", "final_score": 50.0, "conviction": "NEUTRAL", "reasons": ["Bootstrapping live feeds"]},
            "paper_trading": {"active_trades": [], "daily_pnl_usd": 0.0, "account_equity": 10000.0, "trades_today": 0},
            "health": {"overall_status": "HEALTHY", "is_circuit_broken": False},
            "recent_candles": []
        }

    def register_broadcast_cb(self, cb):
        self.broadcast_cbs.append(cb)

    def start(self):
        if self.is_running:
            return
        self.is_running = True
        
        # 1. Discover products dynamically
        try:
            product_discovery.discover_products()
            health_watchdog.record_feed_update("REST_API", is_success=True)
        except Exception as e:
            health_watchdog.record_exception("PRODUCT_DISCOVERY", str(e))

        # 2. Fetch initial historical candles from REST
        self._bootstrap_historical_candles()

        # 3. Start WebSocket manager
        ws_manager.start()

        # 4. Start fallback price poller (ensures zero hang / always live BTC price)
        threading.Thread(target=self._poll_fallback_price, daemon=True).start()

        # 5. Start periodic background reconciliation loop
        threading.Thread(target=self._background_loop, daemon=True).start()

    def _bootstrap_historical_candles(self):
        try:
            now_ts = int(time.time())
            start_ts = now_ts - (86400 * 2)  # Last 48 hours of 5m candles
            candles = delta_rest_client.get_candles(
                symbol=config.default_perp_symbol,
                resolution="5m",
                start=start_ts,
                end=now_ts
            )
            if candles:
                candle_builder.seed_candles("5m", candles)
                health_watchdog.record_feed_update("CANDLES", is_success=True)

            # Also fetch 1m candles for orderflow and micro-structure
            candles_1m = delta_rest_client.get_candles(
                symbol=config.default_perp_symbol,
                resolution="1m",
                start=now_ts - 7200,
                end=now_ts
            )
            if candles_1m:
                candle_builder.seed_candles("1m", candles_1m)
                # Store in database
                db.upsert_candles(config.default_perp_symbol, candles_1m)
        except Exception as e:
            health_watchdog.record_exception("BOOTSTRAP_CANDLES", str(e))

    def resync_market_data(self):
        """Re-syncs REST snapshot after disconnect or on schedule."""
        try:
            ticker = delta_rest_client.get_ticker(config.default_perp_symbol)
            if ticker:
                self._on_ws_ticker(ticker)

            book = delta_rest_client.get_l2_orderbook(config.default_perp_symbol)
            if book:
                self._on_ws_orderbook(book)

            trades = delta_rest_client.get_trades(config.default_perp_symbol)
            if trades:
                self._on_ws_trades(trades)
        except Exception as e:
            health_watchdog.record_exception("REST_RESYNC", str(e))

    def _background_loop(self):
        """Runs periodic state synthesis every 1 second and REST reconciliation asynchronously."""
        last_reconcile = 0.0
        while self.is_running:
            try:
                time.sleep(1.0)
                now = time.time()
                # Run resync in a separate thread so network delays NEVER block state synthesis
                if now - last_reconcile > 30.0:
                    last_reconcile = now
                    threading.Thread(target=self.resync_market_data, daemon=True).start()

                self._compute_and_update_state()
            except Exception as e:
                health_watchdog.record_exception("BACKGROUND_LOOP", str(e))
                time.sleep(1.0)

    def _broadcast_tick(self):
        if not self.latest_state or not self.broadcast_cbs:
            return
        state = self.get_latest_state()
        for cb in self.broadcast_cbs:
            try:
                cb(state)
            except Exception:
                pass

    def _on_price_tick(self, spot: float, bid: float = 0.0, ask: float = 0.0):
        if spot <= 0:
            return
        self.last_price_update = time.time()
        now_dt_utc = datetime.now(timezone.utc)
        now_dt_ist = now_dt_utc.astimezone(IST)

        if not self.latest_state or "telemetry" not in self.latest_state:
            return

        t = self.latest_state["telemetry"]
        t["spot"] = round(spot, 1)
        if bid > 0:
            t["best_bid"] = round(bid, 1)
        if ask > 0:
            t["best_ask"] = round(ask, 1)
        
        if t["best_bid"] > 0 and t["best_ask"] > 0:
            t["spread"] = round(max(0.0, t["best_ask"] - t["best_bid"]), 1)
            t["spread_bps"] = round((t["spread"] / spot) * 10000.0, 2)

        self.latest_state["timestamp"] = now_dt_utc.isoformat()
        self.latest_state["timestamp_ist"] = now_dt_ist.strftime("%d-%b-%Y %H:%M:%S IST")

        self._broadcast_tick()

    def _on_ws_ticker(self, tick: Dict[str, Any]):
        try:
            close = float(tick.get("close") or 0.0)
            mark = float(tick.get("mark_price") or 0.0)
            quotes = tick.get("quotes") or {}
            bid = float(quotes.get("best_bid") or 0.0)
            ask = float(quotes.get("best_ask") or 0.0)

            if close > 0:
                self.live_spot = close
            elif bid > 0 and ask > 0:
                self.live_spot = (bid + ask) / 2.0

            if bid > 0:
                self.live_best_bid = bid
            if ask > 0:
                self.live_best_ask = ask
            if mark > 0:
                self.live_mark = mark

            self._on_price_tick(self.live_spot, self.live_best_bid, self.live_best_ask)
        except Exception:
            pass

    def _on_ws_trades(self, trades: List[Dict[str, Any]]):
        try:
            orderflow_engine.process_trades(trades)
            if trades:
                last_p = float(trades[0].get("price", 0.0))
                if last_p > 0:
                    self.live_spot = last_p
                    self._on_price_tick(self.live_spot, self.live_best_bid, self.live_best_ask)
        except Exception:
            pass

    def _on_ws_orderbook(self, book: Dict[str, Any]):
        try:
            res = orderflow_engine.update_orderbook(book)
            bid = res.get("best_bid", 0.0)
            ask = res.get("best_ask", 0.0)
            if bid > 0:
                self.live_best_bid = bid
            if ask > 0:
                self.live_best_ask = ask
            if self.live_spot <= 0 and bid > 0 and ask > 0:
                self.live_spot = (bid + ask) / 2.0
            self._on_price_tick(self.live_spot, self.live_best_bid, self.live_best_ask)
        except Exception:
            pass

    def _on_ws_candle(self, c_msg: Dict[str, Any]):
        try:
            candle_builder.on_1m_candle(c_msg)
        except Exception:
            pass

    def _compute_and_update_state(self):
        try:
                # 1. Pull latest market telemetry
                perp_info = product_discovery.perp_contract or {"symbol": config.default_perp_symbol}
                book = orderflow_engine.current_orderbook
                best_bid = book.get("best_bid", 0.0)
                best_ask = book.get("best_ask", 0.0)
                mid_p = book.get("mid_price", 0.0)

                # Fallback to live_spot if book is empty
                if mid_p <= 0 and self.live_spot > 0:
                    mid_p = self.live_spot
                    best_bid = self.live_best_bid or (mid_p - 0.5)
                    best_ask = self.live_best_ask or (mid_p + 0.5)
                elif mid_p <= 0:
                    mid_p = 86350.0
                    best_bid = 86349.5
                    best_ask = 86350.5

                candles_5m = candle_builder.get_confirmed_candles("5m")
                candles_1m = candle_builder.get_confirmed_candles("1m")

                # 2. Indicators
                indicators = indicator_engine.evaluate_all(candles_5m)
                atr = indicators.get("atr14", max(20.0, mid_p * 0.005))
                vwap = indicators.get("vwap", mid_p)
                dist_vwap_atr = indicators.get("dist_vwap_atr", 0.0)

                # 3. Orderflow & CVD
                of_data = {
                    "cvd": orderflow_engine.cumulative_volume_delta,
                    "normalized_delta": 0.0,
                    "delta_1m": 0.0,
                    "delta_5m": 0.0,
                    "delta_15m": 0.0,
                    "spread": book.get("spread", 0.5),
                    "spread_bps": book.get("spread_bps", 1.0),
                    "imbalance_10bps": book.get("imbalance_10bps", 0.0),
                    "imbalance_25bps": book.get("imbalance_25bps", 0.0),
                    "imbalance_50bps": book.get("imbalance_50bps", 0.0),
                    "imbalance_100bps": book.get("imbalance_100bps", 0.0),
                    "large_bids": book.get("large_bids", []),
                    "large_asks": book.get("large_asks", [])
                }
                if orderflow_engine.delta_history:
                    now = time.time()
                    of_data["delta_1m"] = sum(d for t, d, _ in orderflow_engine.delta_history if t >= now - 60)
                    of_data["delta_5m"] = sum(d for t, d, _ in orderflow_engine.delta_history if t >= now - 300)
                    of_data["delta_15m"] = sum(d for t, d, _ in orderflow_engine.delta_history if t >= now - 900)

                # 4. Liquidity & Key Levels
                liq = liquidity_engine.evaluate_levels(candles_1m or candles_5m, mid_p, atr)
                closest_res = liq.get("closest_resistance", {"price": mid_p + atr, "name": "Key Res"})
                closest_sup = liq.get("closest_support", {"price": mid_p - atr, "name": "Key Sup"})

                # 5. Market Regime
                reg_out = regime_engine.evaluate_regime(
                    spot=mid_p,
                    vwap=vwap,
                    dist_vwap_atr=dist_vwap_atr,
                    ema21=indicators.get("ema21"),
                    ema50=indicators.get("ema50"),
                    ema200=indicators.get("ema200"),
                    adx14=indicators.get("adx14"),
                    plus_di=indicators.get("plus_di"),
                    minus_di=indicators.get("minus_di"),
                    realized_vol=indicators.get("realized_vol_pct", 40.0)
                )

                # 6. Breakout Engine
                last_c = candles_5m[-1] if candles_5m else {"close": mid_p, "high": mid_p, "low": mid_p}
                b_out = breakout_engine.evaluate(
                    spot=mid_p,
                    last_closed_candle=last_c,
                    key_resistance=closest_res["price"],
                    key_support=closest_sup["price"],
                    res_name=closest_res["name"],
                    sup_name=closest_sup["name"],
                    atr14=atr,
                    rvol=indicators.get("rvol", 1.0),
                    norm_delta=of_data.get("normalized_delta", 0.0),
                    oi_change_pct=0.0
                )

                # 7. Spike Radar
                spike_out = spike_radar.evaluate(
                    spot=mid_p,
                    vwap=vwap,
                    dist_vwap_atr=dist_vwap_atr,
                    atr14=atr,
                    rvol=indicators.get("rvol", 1.0),
                    norm_delta=of_data.get("normalized_delta", 0.0),
                    delta_5m=of_data.get("delta_5m", 0.0),
                    oi_change_5m_pct=0.0
                )

                # 8. Setup Score & Decision Engine
                health = health_watchdog.evaluate_health()
                is_healthy = not health.get("is_circuit_broken", False)
                setup_out = setup_scoring_engine.evaluate_score(
                    regime_output=reg_out,
                    breakout_output=b_out,
                    spike_output=spike_out,
                    orderflow_output=of_data,
                    oi_data={"oi_change_5m_pct": 0.1, "funding_rate": 0.0001, "basis_pct": 0.02},
                    liquidity_output=liq,
                    indicator_output=indicators,
                    is_feed_healthy=is_healthy
                )

                # 8b. Dispatch Telegram Alert if signal triggered (Score >= 75)
                dec = setup_out.get("decision", "WAIT")
                if dec in ("LONG SETUP", "SHORT SETUP"):
                    res_p = closest_res.get("price", mid_p + atr)
                    sup_p = closest_sup.get("price", mid_p - atr)
                    if dec == "LONG SETUP":
                        e_str = f"${min(mid_p - 10, sup_p - 2):.1f} – ${max(mid_p + 5, sup_p + 15):.1f}"
                        sl_str = f"${sup_p - max(8.0, 0.4 * atr):.1f}"
                        tp1_str = f"${mid_p + max(40.0, 2.0 * atr):.1f}"
                        tp2_str = f"${res_p:.1f}"
                        r_str = f"Strong buyer flow bouncing from support ${sup_p:.1f}"
                    else:
                        e_str = f"${min(mid_p - 5, res_p - 15):.1f} – ${max(mid_p + 10, res_p + 2):.1f}"
                        sl_str = f"${res_p + max(8.0, 0.4 * atr):.1f}"
                        tp1_str = f"${mid_p - max(40.0, 2.0 * atr):.1f}"
                        tp2_str = f"${sup_p:.1f}"
                        r_str = f"Price testing ceiling ${res_p:.1f} in {reg_out.get('regime', 'RANGE')} with fading momentum"

                    telegram_alerter.send_signal_alert(
                        decision=dec,
                        spot=mid_p,
                        score=setup_out.get("final_score", 0.0),
                        entry=e_str,
                        sl=sl_str,
                        tp1=tp1_str,
                        tp2=tp2_str,
                        reason=r_str
                    )

                # 9. Paper Trading Engine
                paper_summary = paper_trader.evaluate_live_market(
                    best_bid=best_bid,
                    best_ask=best_ask,
                    setup_decision=setup_out,
                    regime=reg_out.get("regime", "RANGE"),
                    atr=atr
                )

                # 10. Format UTC & IST timestamps
                now_dt_utc = datetime.now(timezone.utc)
                now_dt_ist = now_dt_utc.astimezone(IST)

                self.latest_state = {
                    "timestamp": now_dt_utc.isoformat(),
                    "timestamp_ist": now_dt_ist.strftime("%d-%b-%Y %H:%M:%S IST"),
                    "contract": {
                        "symbol": perp_info.get("symbol", config.default_perp_symbol),
                        "description": perp_info.get("description", "Bitcoin Perpetual"),
                        "contract_value": perp_info.get("contract_value", 0.001),
                        "tick_size": perp_info.get("tick_size", 0.5),
                        "maker_fee_pct": perp_info.get("maker_commission_rate", 0.0002) * 100.0,
                        "taker_fee_pct": perp_info.get("taker_commission_rate", 0.0005) * 100.0
                    },
                    "telemetry": {
                        "spot": round(mid_p, 1),
                        "best_bid": round(best_bid, 1),
                        "best_ask": round(best_ask, 1),
                        "spread": round(book.get("spread", 0.5), 1),
                        "spread_bps": round(book.get("spread_bps", 1.0), 2),
                        "vwap": round(vwap, 1),
                        "dist_vwap_atr": round(dist_vwap_atr, 2),
                        "atr14": round(atr, 1),
                        "rsi14": indicators.get("rsi14"),
                        "adx14": indicators.get("adx14"),
                        "rvol": indicators.get("rvol", 1.0),
                        "realized_vol_pct": indicators.get("realized_vol_pct", 0.0),
                        "cvd": round(of_data["cvd"], 2),
                        "imbalance_25bps": round(of_data["imbalance_25bps"], 3)
                    },
                    "regime": reg_out,
                    "breakout": b_out,
                    "spike_radar": spike_out,
                    "liquidity": liq,
                    "setup_decision": setup_out,
                    "paper_trading": paper_summary,
                    "health": health,
                    "recent_candles": candle_builder.get_display_candles("5m", 60)
                }

        except Exception as e:
            health_watchdog.record_exception("STATE_COMPUTATION", str(e))

    def _poll_fallback_price(self):
        """Runs in separate background thread: ensures live BTC spot is always fresh even if Delta WS drops."""
        while self.is_running:
            try:
                now = time.time()
                # If WS ticker arrived in the last 4 seconds, sleep
                if self.live_spot > 0 and (now - self.last_price_update < 4.0):
                    time.sleep(1.0)
                    continue

                p = 0.0
                # 1. Delta India REST ticker (non-blocking fast attempt)
                try:
                    tick = delta_rest_client.get_ticker(config.default_perp_symbol)
                    p = float(tick.get("close") or tick.get("quotes", {}).get("best_bid") or 0.0)
                except Exception:
                    pass

                # 2. Public high-speed backup (Binance)
                if p <= 0:
                    try:
                        import urllib.request, json
                        req = urllib.request.Request("https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT", headers={"User-Agent": "Mozilla/5.0"})
                        with urllib.request.urlopen(req, timeout=3) as resp:
                            data = json.loads(resp.read().decode())
                            p = float(data.get("price", 0.0))
                    except Exception:
                        pass

                # 3. Public high-speed backup (Coinbase)
                if p <= 0:
                    try:
                        import urllib.request, json
                        req = urllib.request.Request("https://api.coinbase.com/v2/prices/BTC-USD/spot", headers={"User-Agent": "Mozilla/5.0"})
                        with urllib.request.urlopen(req, timeout=3) as resp:
                            data = json.loads(resp.read().decode())
                            p = float(data.get("data", {}).get("amount", 0.0))
                    except Exception:
                        pass

                if p > 0:
                    self.live_spot = round(p, 1)
                    self.last_price_update = time.time()
                    if self.live_best_bid <= 0 or abs(self.live_best_bid - p) > 50:
                        self.live_best_bid = round(p - 0.5, 1)
                    if self.live_best_ask <= 0 or abs(self.live_best_ask - p) > 50:
                        self.live_best_ask = round(p + 0.5, 1)
                    health_watchdog.record_feed_update("TICKER", is_success=True)
                    self._on_price_tick(self.live_spot, self.live_best_bid, self.live_best_ask)
                    try:
                        self._compute_and_update_state()
                    except Exception:
                        pass
            except Exception:
                pass
            time.sleep(2.0)

    def get_latest_state(self) -> Dict[str, Any]:
        return self.latest_state or {}


terminal_service = TerminalService()
