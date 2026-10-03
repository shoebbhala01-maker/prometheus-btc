"""
PROMETHEUS BTC TERMINAL: Application Settings & Risk Parameters
"""

import os
from pathlib import Path
from dataclasses import dataclass, field


@dataclass
class RiskSettings:
    account_capital: float = 10000.0          # Virtual Capital in USD
    max_risk_per_trade_pct: float = 1.0       # 1% equity risk per trade
    max_daily_loss_pct: float = 3.0           # 3% max daily drawdown limit
    max_concurrent_positions: int = 2         # Max concurrent active trades
    max_consecutive_losses: int = 3           # Cooldown triggered after 3 consecutive losses
    cooldown_period_minutes: int = 60         # 1-hour cooldown
    max_slippage_bps: float = 5.0             # Rejects entry if spread/slippage exceeds 5 bps
    contract_value_btc: float = 0.001         # 1 BTCUSD perp contract = 0.001 BTC ($85 at $85,000)
    futures_taker_fee: float = 0.0005         # 0.05% taker fee
    futures_maker_fee: float = 0.0002         # 0.02% maker fee
    options_taker_fee: float = 0.0003         # 0.03% taker fee


@dataclass
class TerminalConfig:
    # Delta Exchange India Endpoints
    rest_base_url: str = os.getenv("DELTA_INDIA_REST_URL", "https://api.india.delta.exchange")
    ws_primary_url: str = os.getenv("DELTA_INDIA_WS_PRIMARY", "wss://socket.india.delta.exchange")
    ws_fallback_url: str = os.getenv("DELTA_INDIA_WS_FALLBACK", "wss://public-socket.india.delta.exchange")
    
    # Target Assets
    underlying_symbol: str = "BTC"
    default_perp_symbol: str = "BTCUSD"
    
    # Data Quality Thresholds
    staleness_warning_seconds: float = 5.0
    staleness_critical_seconds: float = 15.0
    max_rate_limit_retries: int = 4
    
    # Risk Governor
    risk: RiskSettings = field(default_factory=RiskSettings)
    
    # Paths
    root_dir: Path = field(default_factory=lambda: Path(__file__).resolve().parent.parent)
    db_path: Path = field(default_factory=lambda: Path(__file__).resolve().parent.parent / "database" / "prometheus_btc.db")
    log_dir: Path = field(default_factory=lambda: Path(__file__).resolve().parent.parent / "logs")


config = TerminalConfig()
