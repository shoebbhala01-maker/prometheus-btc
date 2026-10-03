"""
PROMETHEUS BTC TERMINAL: Web Server & Real-Time Terminal API
Serves REST API and reactive WebSocket terminal stream via Flask and Flask-SocketIO.
"""

import os
import sys
from pathlib import Path
from typing import Optional
import time
import threading

# Add root directory to sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from flask import Flask, jsonify, request, send_from_directory
from flask_socketio import SocketIO

from config.settings import config
from server.terminal_service import terminal_service
from ingestion.delta_rest_client import delta_rest_client
from quant.options_analytics import options_analytics
from quant.candle_builder import candle_builder
from backtest.backtest_engine import backtest_engine
from backtest.paper_trading_engine import paper_trader

UI_DIR = Path(__file__).resolve().parent.parent / "ui"

app = Flask(__name__, static_folder=str(UI_DIR), static_url_path="")
app.config["SECRET_KEY"] = "prometheus_btc_secret_key"
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")


@app.route("/")
def index():
    return send_from_directory(str(UI_DIR), "index.html")


@app.route("/<path:path>")
def static_proxy(path):
    return send_from_directory(str(UI_DIR), path)


@app.route("/api/state", methods=["GET"])
def get_state():
    """Returns current unified terminal telemetry state."""
    state = terminal_service.get_latest_state()
    return jsonify(state)


@app.route("/api/options/chain", methods=["GET"])
def get_option_chain():
    """Discovers and returns live option chain for selected expiry."""
    selected_exp = request.args.get("expiry")
    try:
        raw_tickers = delta_rest_client.get_tickers(underlying_asset_symbols="BTC")
        spot = terminal_service.get_latest_state().get("telemetry", {}).get("spot", 0.0)
        chain = options_analytics.build_option_chain(raw_tickers, spot, selected_exp)
        return jsonify(chain)
    except Exception as e:
        return jsonify({"status": "ERROR", "message": str(e)}), 500


@app.route("/api/candles", methods=["GET"])
def get_candles():
    """Returns candles for chart display."""
    tf = request.args.get("timeframe", "5m")
    count = int(request.args.get("count", 100))
    candles = candle_builder.get_display_candles(tf, count)
    return jsonify({"timeframe": tf, "count": len(candles), "candles": candles})


@app.route("/api/settings/risk", methods=["POST"])
def update_risk():
    data = request.json or {}
    if "account_capital" in data:
        config.risk.account_capital = float(data["account_capital"])
        paper_trader.equity = config.risk.account_capital
    if "max_risk_per_trade_pct" in data:
        config.risk.max_risk_per_trade_pct = float(data["max_risk_per_trade_pct"])
    if "max_daily_loss_pct" in data:
        config.risk.max_daily_loss_pct = float(data["max_daily_loss_pct"])

    return jsonify({
        "status": "SUCCESS",
        "account_capital": config.risk.account_capital,
        "max_risk_per_trade_pct": config.risk.max_risk_per_trade_pct,
        "max_daily_loss_pct": config.risk.max_daily_loss_pct
    })


@app.route("/api/backtest/run", methods=["POST"])
def run_backtest():
    """Runs chronological walk-forward backtest over real historical candles."""
    try:
        now_ts = int(time.time())
        # Fetch 5 days of 5m candles (1440 candles)
        start_ts = now_ts - (86400 * 5)
        raw_candles = delta_rest_client.get_candles(
            symbol=config.default_perp_symbol,
            resolution="5m",
            start=start_ts,
            end=now_ts
        )
        data = request.json or {}
        min_score = float(data.get("min_setup_score", 70.0))
        result = backtest_engine.run_backtest(raw_candles, min_setup_score=min_score)
        return jsonify(result)
    except Exception as e:
        return jsonify({"status": "ERROR", "message": str(e)}), 500


@app.route("/api/paper/summary", methods=["GET"])
def get_paper_summary():
    return jsonify(paper_trader.get_summary())


@app.route("/api/health", methods=["GET"])
def get_health():
    from ingestion.data_health import health_watchdog
    return jsonify(health_watchdog.evaluate_health())


@app.route("/api/telegram/status", methods=["GET"])
def get_telegram_status():
    from engine.telegram_alerter import telegram_alerter
    return jsonify({
        "configured": telegram_alerter.is_configured(),
        "enabled": telegram_alerter.enabled,
        "chat_id": telegram_alerter.chat_id[-4:].rjust(len(telegram_alerter.chat_id), "*") if telegram_alerter.chat_id else ""
    })


@app.route("/api/telegram/config", methods=["POST"])
def set_telegram_config():
    from engine.telegram_alerter import telegram_alerter
    data = request.json or {}
    token = data.get("bot_token", "")
    chat_id = data.get("chat_id", "")
    enabled = data.get("enabled", True)
    success = telegram_alerter.save_config(token, chat_id, enabled)
    if success:
        return jsonify({"status": "SUCCESS", "message": "Telegram configuration saved"})
    return jsonify({"status": "ERROR", "message": "Failed to save configuration"}), 500


@app.route("/api/telegram/test", methods=["POST"])
def send_telegram_test():
    from engine.telegram_alerter import telegram_alerter
    res = telegram_alerter.send_test_alert()
    return jsonify(res)



@socketio.on("connect")
def on_client_connect():
    state = terminal_service.get_latest_state()
    if state:
        socketio.emit("terminal_state", state)


def _on_state_tick(state):
    try:
        socketio.emit("terminal_state", state)
    except Exception:
        pass


def _ws_broadcast_loop():
    """Heartbeat broadcast every 1s ensuring live clock and consistency."""
    while True:
        time.sleep(1.0)
        try:
            state = terminal_service.get_latest_state()
            if state:
                socketio.emit("terminal_state", state)
        except Exception:
            pass


def start_server(host: str = "0.0.0.0", port: Optional[int] = None):
    p = port or int(os.getenv("PORT", 5000))
    h = os.getenv("HOST", host)
    terminal_service.register_broadcast_cb(_on_state_tick)
    terminal_service.start()
    threading.Thread(target=_ws_broadcast_loop, daemon=True).start()
    print(f"Prometheus BTC Terminal starting at http://{h}:{p}")
    socketio.run(app, host=h, port=p, debug=False, use_reloader=False, allow_unsafe_werkzeug=True)



if __name__ == "__main__":
    start_server()
