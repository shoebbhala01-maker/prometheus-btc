-- Prometheus BTC Terminal Database Schema

CREATE TABLE IF NOT EXISTS candles_1m (
    timestamp INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume REAL NOT NULL,
    PRIMARY KEY (symbol, timestamp)
);

CREATE TABLE IF NOT EXISTS ticks_snapshot (
    timestamp INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    mark_price REAL NOT NULL,
    close_price REAL NOT NULL,
    spot_price REAL NOT NULL,
    funding_rate REAL NOT NULL,
    oi REAL NOT NULL,
    oi_value_usd REAL NOT NULL,
    best_bid REAL,
    best_ask REAL,
    bid_size REAL,
    ask_size REAL,
    regime TEXT,
    setup_score REAL,
    PRIMARY KEY (symbol, timestamp)
);

CREATE TABLE IF NOT EXISTS orderflow_snapshots (
    timestamp INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    volume_delta REAL NOT NULL,
    cumulative_delta REAL NOT NULL,
    aggressive_buy_vol REAL NOT NULL,
    aggressive_sell_vol REAL NOT NULL,
    depth_imbalance_25bps REAL,
    depth_imbalance_100bps REAL,
    PRIMARY KEY (symbol, timestamp)
);

CREATE TABLE IF NOT EXISTS paper_trades (
    trade_id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL,
    entry_time INTEGER NOT NULL,
    entry_price REAL NOT NULL,
    exit_time INTEGER,
    exit_price REAL,
    size_contracts INTEGER NOT NULL,
    stop_loss REAL NOT NULL,
    target1 REAL NOT NULL,
    target2 REAL NOT NULL,
    status TEXT NOT NULL,
    exit_reason TEXT,
    gross_pnl REAL,
    net_pnl REAL,
    total_fees REAL,
    slippage_cost REAL,
    mfe REAL,
    mae REAL,
    setup_score REAL,
    regime_at_entry TEXT
);

CREATE TABLE IF NOT EXISTS spike_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    spike_state TEXT NOT NULL,
    return_5m REAL,
    velocity_pct_per_min REAL,
    rvol REAL,
    vwap_atr_dist REAL,
    delta_direction TEXT,
    subsequent_reversal BOOLEAN,
    outcome_desc TEXT
);

CREATE TABLE IF NOT EXISTS breakout_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    level_name TEXT NOT NULL,
    level_price REAL NOT NULL,
    direction TEXT NOT NULL,
    stage TEXT NOT NULL,
    is_confirmed BOOLEAN,
    is_failed_trap BOOLEAN,
    outcome_desc TEXT
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    component TEXT NOT NULL,
    details TEXT NOT NULL,
    is_anomaly BOOLEAN DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_candles_time ON candles_1m (symbol, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_ticks_time ON ticks_snapshot (symbol, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_paper_status ON paper_trades (status);
