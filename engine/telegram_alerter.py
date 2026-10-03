"""
PROMETHEUS BTC TERMINAL: Telegram Alert Dispatcher
Sends real-time high-conviction trade signals directly to user's Telegram phone app.
Works 24/7 even when phone is locked or browser is closed.
"""

import os
import json
import time
import requests
import threading
from pathlib import Path
from typing import Dict, Any, Optional

CONFIG_FILE = Path(__file__).resolve().parent.parent / "config" / "telegram_config.json"


class TelegramAlerter:
    def __init__(self):
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        self.enabled = True
        self.last_sent_signal = ""
        self.last_sent_time = 0.0
        self.cooldown_seconds = 180  # 3 min cooldown between identical alerts
        self._load_config()

    def _load_config(self):
        try:
            if CONFIG_FILE.exists():
                with open(CONFIG_FILE, "r") as f:
                    data = json.load(f)
                    self.bot_token = data.get("bot_token") or self.bot_token
                    self.chat_id = data.get("chat_id") or self.chat_id
                    self.enabled = data.get("enabled", True)
        except Exception as e:
            print(f"[Telegram] Failed to load config: {e}")

    def save_config(self, bot_token: str, chat_id: str, enabled: bool = True):
        self.bot_token = bot_token.strip()
        self.chat_id = chat_id.strip()
        self.enabled = enabled
        try:
            CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(CONFIG_FILE, "w") as f:
                json.dump({
                    "bot_token": self.bot_token,
                    "chat_id": self.chat_id,
                    "enabled": self.enabled
                }, f, indent=2)
            return True
        except Exception as e:
            print(f"[Telegram] Failed to save config: {e}")
            return False

    def is_configured(self) -> bool:
        return bool(self.bot_token and self.chat_id)

    def send_message(self, text: str, sync: bool = False) -> Dict[str, Any]:
        """Dispatches text message via official Telegram Bot API."""
        if not self.is_configured():
            return {"ok": False, "description": "Bot token or Chat ID not configured"}
        if not self.enabled:
            return {"ok": False, "description": "Telegram alerts disabled"}

        def _do_send():
            try:
                url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
                payload = {
                    "chat_id": self.chat_id,
                    "text": text,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True
                }
                res = requests.post(url, json=payload, timeout=8)
                r_json = res.json()
                if not r_json.get("ok"):
                    desc = r_json.get("description", "")
                    if "chat not found" in desc.lower():
                        return {
                            "ok": False,
                            "description": "❌ चैट नहीं मिली! आपने अभी तक अपने नए बॉट को खोलकर START नहीं दबाया है। कृपया टेलीग्राम में @shoeb_btc_signal_bot खोलकर START दबाएं।"
                        }
                    return {"ok": False, "description": desc}
                return r_json
            except Exception as e:
                print(f"[Telegram] Send error: {e}")
                return {"ok": False, "description": str(e)}

        if sync:
            return _do_send()

        # Run async in background thread so market calculation is never blocked
        t = threading.Thread(target=_do_send, daemon=True)
        t.start()
        return {"status": "DISPATCHED", "message": "Alert queued for Telegram"}

    def send_signal_alert(
        self,
        decision: str,
        spot: float,
        score: float,
        entry: str,
        sl: str,
        tp1: str,
        tp2: str,
        reason: str
    ):
        """Sends rich formatted trade signal alert."""
        if not self.is_configured() or not self.enabled:
            return

        now = time.time()
        # Cooldown check
        if decision == self.last_sent_signal and (now - self.last_sent_time) < self.cooldown_seconds:
            return

        self.last_sent_signal = decision
        self.last_sent_time = now

        if decision == "LONG SETUP":
            emoji = "🟢"
            action = "BUY (LONG) KARO"
        elif decision == "SHORT SETUP":
            emoji = "🔴"
            action = "SELL (SHORT) KARO"
        else:
            return

        msg = (
            f"⚡ <b>PROMETHEUS BTC ALERT</b> ⚡\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"{emoji} <b>ACTION: {action}</b>\n"
            f"📊 <b>Setup Score:</b> {score:.0f} / 100\n"
            f"💰 <b>BTC Price:</b> ${spot:,.1f}\n\n"
            f"🎯 <b>Entry Zone:</b> {entry}\n"
            f"🛑 <b>Stop Loss:</b> {sl}\n"
            f"💰 <b>Target 1 (50% Book):</b> {tp1}\n"
            f"🏆 <b>Target 2 (Full Exit):</b> {tp2}\n\n"
            f"💡 <b>Wajah (Reason):</b> {reason}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"⏰ <i>Time: {time.strftime('%d-%b-%Y %H:%M:%S IST', time.localtime())}</i>\n"
            f"📱 Delta Exchange India | 1 Lot = 0.001 BTC"
        )

        self.send_message(msg, sync=False)

    def send_test_alert(self) -> Dict[str, Any]:
        """Sends a verification message to confirm phone notifications are ringing."""
        test_msg = (
            f"🔔 <b>PROMETHEUS BTC TERMINAL: TEST ALERT</b> 🔔\n\n"
            f"✅ <b>बधाई हो! आपका Telegram Alert सक्रिय हो चुका है!</b>\n\n"
            f"अब जब भी Bitcoin में 75+ स्कोर का कोई बड़ा BUY या SELL सिग्नल बनेगा, "
            f"तो आपका फोन जेब में या लॉक होने पर भी जोर से रिंग करेगा!\n\n"
            f"⏰ <i>Time: {time.strftime('%d-%b-%Y %H:%M:%S IST', time.localtime())}</i>"
        )
        return self.send_message(test_msg, sync=True)


telegram_alerter = TelegramAlerter()

