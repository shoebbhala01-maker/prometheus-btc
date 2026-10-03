"""
PROMETHEUS BTC TERMINAL: Production Server Launcher
Run: python run.py
Exchange: Delta Exchange India
Markets: BTC Perpetual Futures & Dynamic Options
"""

import sys
import webbrowser
import threading
import time

def open_browser():
    time.sleep(2)
    try:
        webbrowser.open("http://127.0.0.1:5000")
    except Exception:
        pass

if __name__ == "__main__":
    print("==============================================================")
    print("   PROMETHEUS BTC TERMINAL v3.0 (Delta Exchange India)")
    print("   Server: http://127.0.0.1:5000")
    print("   Markets: BTCUSD Perpetual Futures & Dynamic Options")
    print("==============================================================")

    threading.Thread(target=open_browser, daemon=True).start()

    from server.app import start_server
    start_server(host="0.0.0.0", port=5000)
