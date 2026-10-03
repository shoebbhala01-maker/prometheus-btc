"""
PROMETHEUS BTC TERMINAL: Database Manager
High-performance SQLite engine with WAL mode, connection pooling, and optimized queries.
"""

import sqlite3
import threading
from pathlib import Path
from contextlib import contextmanager
from typing import List, Dict, Any, Optional
import time

from config.settings import config


class DatabaseManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(DatabaseManager, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self, db_path: Optional[Path] = None):
        if self._initialized:
            return
        self.db_path = db_path or config.db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.local = threading.local()
        self._init_database()
        self._initialized = True

    def _get_connection(self) -> sqlite3.Connection:
        if not hasattr(self.local, "conn") or self.local.conn is None:
            conn = sqlite3.connect(
                str(self.db_path),
                timeout=30.0,
                check_same_thread=False
            )
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA synchronous = NORMAL;")
            conn.execute("PRAGMA foreign_keys = ON;")
            conn.execute("PRAGMA cache_size = -32000;")  # 32MB memory cache
            self.local.conn = conn
        return self.local.conn

    @contextmanager
    def get_cursor(self):
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            yield cursor
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()

    def _init_database(self):
        schema_path = Path(__file__).resolve().parent / "schema.sql"
        if not schema_path.exists():
            raise FileNotFoundError(f"Schema file not found at {schema_path}")

        with open(schema_path, "r", encoding="utf-8") as f:
            schema_sql = f.read()

        with self.get_cursor() as cursor:
            cursor.executescript(schema_sql)

    # ==========================================
    # Candles Storage & Retrieval
    # ==========================================
    def upsert_candles(self, symbol: str, candles: List[Dict[str, Any]]):
        """Batch inserts or replaces OHLCV candles."""
        if not candles:
            return
        sql = """
        INSERT OR REPLACE INTO candles_1m (timestamp, symbol, open, high, low, close, volume)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        records = [
            (
                int(c["time"]),
                symbol,
                float(c["open"]),
                float(c["high"]),
                float(c["low"]),
                float(c["close"]),
                float(c["volume"])
            )
            for c in candles
        ]
        with self.get_cursor() as cursor:
            cursor.executemany(sql, records)

    def get_recent_candles(self, symbol: str, limit: int = 500) -> List[Dict[str, Any]]:
        sql = """
        SELECT timestamp as time, open, high, low, close, volume
        FROM candles_1m
        WHERE symbol = ?
        ORDER BY timestamp ASC
        LIMIT ?
        """
        # Fetch last N candles
        sub_sql = f"""
        SELECT * FROM (
            SELECT timestamp as time, open, high, low, close, volume
            FROM candles_1m
            WHERE symbol = ?
            ORDER BY timestamp DESC
            LIMIT ?
        ) ORDER BY time ASC
        """
        with self.get_cursor() as cursor:
            cursor.execute(sub_sql, (symbol, limit))
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

    # ==========================================
    # Snapshots & Paper Trades
    # ==========================================
    def insert_tick_snapshot(self, snapshot: Dict[str, Any]):
        sql = """
        INSERT OR REPLACE INTO ticks_snapshot (
            timestamp, symbol, mark_price, close_price, spot_price,
            funding_rate, oi, oi_value_usd, best_bid, best_ask,
            bid_size, ask_size, regime, setup_score
        ) VALUES (
            :timestamp, :symbol, :mark_price, :close_price, :spot_price,
            :funding_rate, :oi, :oi_value_usd, :best_bid, :best_ask,
            :bid_size, :ask_size, :regime, :setup_score
        )
        """
        with self.get_cursor() as cursor:
            cursor.execute(sql, snapshot)

    def insert_paper_trade(self, trade: Dict[str, Any]):
        sql = """
        INSERT OR REPLACE INTO paper_trades (
            trade_id, symbol, direction, entry_time, entry_price, exit_time, exit_price,
            size_contracts, stop_loss, target1, target2, status, exit_reason,
            gross_pnl, net_pnl, total_fees, slippage_cost, mfe, mae, setup_score, regime_at_entry
        ) VALUES (
            :trade_id, :symbol, :direction, :entry_time, :entry_price, :exit_time, :exit_price,
            :size_contracts, :stop_loss, :target1, :target2, :status, :exit_reason,
            :gross_pnl, :net_pnl, :total_fees, :slippage_cost, :mfe, :mae, :setup_score, :regime_at_entry
        )
        """
        with self.get_cursor() as cursor:
            cursor.execute(sql, trade)

    def get_paper_trades(self, limit: int = 100) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM paper_trades ORDER BY entry_time DESC LIMIT ?"
        with self.get_cursor() as cursor:
            cursor.execute(sql, (limit,))
            return [dict(r) for r in cursor.fetchall()]

    def log_audit_event(self, event_type: str, component: str, details: str, is_anomaly: bool = False):
        sql = """
        INSERT INTO audit_logs (timestamp, event_type, component, details, is_anomaly)
        VALUES (?, ?, ?, ?, ?)
        """
        with self.get_cursor() as cursor:
            cursor.execute(sql, (int(time.time()), event_type, component, str(details), int(is_anomaly)))


db = DatabaseManager()
