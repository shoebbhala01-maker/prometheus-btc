# PROMETHEUS BTC TERMINAL — COMPREHENSIVE ARCHITECTURAL AUDIT & SPECIFICATION

**System:** Prometheus BTC Terminal for Delta Exchange India  
**Target Markets:** BTC Perpetual Futures (`BTCUSD`) & Dynamic BTC Options (Calls/Puts)  
**Reference Codebase:** Prometheus Quant Terminal v2.0 (`D:\Grav`, `https://prometheus-terminal.onrender.com/`)  
**Workspace:** `d:\BITCOIN`  
**Date of Audit:** October 2026  

---

## 1. EXECUTIVE AUDIT OF REFERENCE CODEBASE (`D:\Grav`)

| Dimension | Existing Prometheus Terminal (`D:\Grav`) | Prometheus BTC Terminal Adaptation (`d:\BITCOIN`) |
| :--- | :--- | :--- |
| **Frontend Framework** | Vanilla HTML5 / Modern ES6+ / Modular CSS3. Zero framework bloat. High refresh responsiveness. | Preserved & enhanced with 9 specialized analytical tabs, SVG/Canvas depth & CVD charts, interactive formula tooltips. |
| **Backend Framework** | Python 3.10+, Flask 3.1.3, Flask-SocketIO 5.6.1, threading/gevent, requests, pandas, numpy, scipy. | Python 3.10+, Flask, Flask-SocketIO, websocket-client 1.8.0, pandas, numpy, scipy, SQLite3 WAL mode. |
| **Data Ingestion** | Angel One SmartAPI (NIFTY/BANKNIFTY Indian equities). Fixed token mappings, market session 09:15–15:30 IST. | Delta Exchange India official REST (`https://api.india.delta.exchange`) & WebSocket (`wss://socket.india.delta.exchange` / `wss://public-socket.india.delta.exchange`). 24/7/365 streaming. |
| **Contract Discovery** | Hardcoded symbol lists & static token master download. | Fully dynamic discovery via `GET /v2/products` & `GET /v2/tickers?underlying_asset_symbols=BTC`. Zero hardcoded IDs. |
| **Candles & Timeframes** | 1m, 3m, 5m local resampling from tick buffer. | Native exchange support for `1m`, `3m`, `5m`, `15m`, `30m`, `1h`, `2h`, `4h`, `1d`. UTC internal timestamps, IST display. |
| **VWAP Distance Metric** | Fixed Nifty index points (e.g. 25 pts, 55 pts). Disastrous for BTC ($85,000). | Volatility-adaptive ATR-normalized distance: `(Price - VWAP) / ATR_14`. |
| **Price Velocity** | Fixed points/minute (e.g. >18 pts/min). | Percentage velocity (%/min) & Rolling Z-Score against 60-minute standard deviation. |
| **Breakout Detection** | 6-stage heuristic with fixed point buffers. | 8-stage rigorous state machine with dynamic ATR buffers (0.2 * ATR_14) and confirmed candle close gate. |
| **Spike & Exhaustion** | 3-tier heuristic (Low/Med/High) with Nifty point thresholds. | 7-stage state machine (`NORMAL` → `MOVE_ACCELERATING` → `SPIKE_DETECTED` → `EXHAUSTION_RISK` → `REVERSAL_RISK` → `REVERSAL_CONFIRMED` → `RESET`). |
| **Order Flow & Delta** | Estimated bid/ask size heuristic from quotes. | Exact trade-level aggressor classification: `seller_role == 'taker'` (sell), `buyer_role == 'taker'` (buy). Cumulative Volume Delta (CVD), Depth Imbalance at ±10/25/50/100 bps bands. |
| **Derivatives Analytics** | NIFTY weekly/monthly options, India VIX, FII/DII net open interest contracts. | BTC perpetual basis %, 8-hour funding rate with countdown, real-time options chain, Greeks (Delta, Gamma, Theta, Vega), IV, PCR, Max Pain. |
| **Contract Units & Sizing**| Indian lot sizes (25 units per lot for NIFTY). | Delta India BTC Perpetual: `contract_value = 0.001 BTC` per contract ($84.60 per contract at $84,600). Precise equity risk allocation. |
| **Frictions & Fees** | Indian regulatory charges: STT 0.125%, GST 18%, Stamp Duty, Brokerage ₹20/order. | Delta Exchange India fee schedule: Maker 0.02% (0.0002), Taker 0.05% (0.0005), Options Taker 0.03% (capped at 10% premium). |
| **Database & Persistence** | SQLite3 database `prometheus_quant.db` with WAL mode. | SQLite3 database `prometheus_btc.db` with WAL mode, storing ticks, 1m candles, paper trades, and audit events. |

---

## 2. API ENDPOINTS & SCHEMAS VERIFIED

### A. REST Endpoints (Base: `https://api.india.delta.exchange`)

1. **`GET /v2/products`**
   - Discovers `BTCUSD` perpetual futures: `id: 27`, `contract_type: perpetual_futures`, `contract_value: 0.001`, `tick_size: 0.5`, `quoting_asset: USD`, `settling_asset: USD`.
   - Discovers all active BTC call & put options: `contract_type: call_options` and `put_options`, `strike_price`, `settlement_time`, `symbol` (e.g. `C-BTC-85000-031026`).

2. **`GET /v2/tickers/BTCUSD`**
   - Returns live `mark_price`, `close` (LTP), `spot_price`, `funding_rate`, `quotes` (`best_bid`, `best_ask`, `bid_size`, `ask_size`), `oi` (BTC amount), `oi_contracts`, `oi_value_usd`, `size`, `volume`, `timestamp`.

3. **`GET /v2/tickers?underlying_asset_symbols=BTC`**
   - Returns complete array of all active BTC options and futures tickers with real-time `greeks` (`delta`, `gamma`, `theta`, `vega`), `mark_vol`, `quotes` (`bid_iv`, `ask_iv`, `mark_iv`), `strike_price`, `oi`.

4. **`GET /v2/history/candles?resolution={res}&symbol=BTCUSD&start={start}&end={end}`**
   - Verified resolutions: `1m`, `3m`, `5m`, `15m`, `30m`, `1h`, `2h`, `4h`, `1d`. Returns array of `[time, open, high, low, close, volume]`.

5. **`GET /v2/l2orderbook/BTCUSD`**
   - Returns deep L2 book with `buy` and `sell` lists containing `limit_price`, `size`, and cumulative `depth`.

6. **`GET /v2/trades/BTCUSD`**
   - Returns last 50 public trades with `price`, `size`, `timestamp`, `buyer_role` (`maker` vs `taker`), and `seller_role` (`maker` vs `taker`).

### B. WebSocket Channels (Base: `wss://socket.india.delta.exchange`)

1. **`l2_orderbook`**: Streaming real-time Level 2 book updates (depth, best bid/ask).
2. **`all_trades`**: Streaming public trade executions with `buyer_role` and `seller_role`.
3. **`v2/ticker`**: Streaming real-time mark price, last price, open interest, and funding rate.
4. **`candlestick_1m`**: Streaming 1-minute OHLCV bar updates.

---

## 3. AUDIT OF QUANTITATIVE FORMULAS & CALCULATION ENGINE

### A. Volume Delta & Aggressor Classification
$$\text{Direction} = \begin{cases} \text{Aggressive Buy}, & \text{if } \text{buyer\_role} = \text{'taker'} \\ \text{Aggressive Sell}, & \text{if } \text{seller\_role} = \text{'taker'} \\ \text{UNAVAILABLE}, & \text{otherwise} \end{cases}$$
$$\text{Volume Delta} = \sum \text{Aggressive Buy Volume} - \sum \text{Aggressive Sell Volume}$$
$$\text{Normalized Delta} = \frac{\text{Volume Delta}}{\text{Total Classified Aggressive Volume}}$$
$$\text{Cumulative Volume Delta (CVD)}_t = \text{CVD}_{t-1} + \text{Volume Delta}_t$$

### B. Dynamic Depth Imbalance
$$\text{Imbalance}_{\text{band}} = \frac{\text{Bid Depth}_{\text{band}} - \text{Ask Depth}_{\text{band}}}{\text{Bid Depth}_{\text{band}} + \text{Ask Depth}_{\text{band}}}$$
Evaluated at $\pm 10 \text{ bps}$, $\pm 25 \text{ bps}$, $\pm 50 \text{ bps}$, and $\pm 100 \text{ bps}$ from mid-price.

### C. Distance from VWAP in ATR Units
$$\text{VWAP} = \frac{\sum (P_i \times V_i)}{\sum V_i}, \quad \text{Anchor: 00:00 UTC Midnight}$$
$$\text{ATR Distance} = \frac{\text{Spot Price} - \text{VWAP}}{\text{ATR}_{14}}$$
- Normal: $|\text{ATR Distance}| \le 1.5$
- Extended: $1.5 < |\text{ATR Distance}| \le 2.5$
- Severe Overextension: $|\text{ATR Distance}| > 2.5$ (Mean reversion rubber-band stretched)

### D. 8-Stage Breakout State Machine
1. `RANGE_IDENTIFIED`: Swing high/low or session range established with minimum 10 candles.
2. `LEVEL_APPROACHING`: Price within $0.5 \times \text{ATR}_{14}$ of key level.
3. `BREAKOUT_ATTEMPT`: Intraday price penetrates level by $> 0.1 \times \text{ATR}_{14}$.
4. `BREAKOUT_CANDLE_CLOSED`: Confirmed candle close beyond level + buffer.
5. `CONFIRMATION_PENDING`: RVOL $> 1.5\times$ and Normalized Volume Delta $> +0.20$.
6. `RETEST_OR_ACCEPTANCE`: Pullback tests broken level and holds above it.
7. `CONFIRMED`: Expansion candle departs retest level in breakout direction.
8. `FAILED_BREAKOUT`: Price drops back inside prior range by $> 0.3 \times \text{ATR}_{14}$ (Trap Triggered).

### E. 7-Stage Spike & Reversal Radar
1. `NORMAL`: Price velocity $< 0.15\%/\text{min}$, RVOL $< 1.5$.
2. `MOVE_ACCELERATING`: 5-min velocity $> 0.25\%/\text{min}$, RVOL $> 1.8$.
3. `SPIKE_DETECTED`: 5-min move $> 1.5 \times \text{ATR}_{14}$ or Z-Score $> +2.5$.
4. `EXHAUSTION_RISK`: VWAP ATR distance $> 2.5$, CVD flattening or diverging, upper/lower rejection wick $> 40\%$ of candle range.
5. `REVERSAL_RISK`: Opposite aggressor flow enters (delta shifts sign), failed attempt to push new extreme.
6. `REVERSAL_CONFIRMED`: Closed candle in opposite direction crossing recent 5-min micro-pivot.
7. `RESET`: Cooldown period after move exhaustion.

### F. 100-Point Setup Score Matrix
| Component | Weight | Key Raw Inputs | Normalization & Conditions |
| :--- | :---: | :--- | :--- |
| 1. Market Structure & Levels | 20 | HTF Swings (1h/4h), Breakout stage, PDH/PDL distance | Range location, higher-highs vs lower-lows (+20 max) |
| 2. Momentum & Alignment | 15 | EMA 9/21/50/200 slope, RSI 14, ADX 14 | Bullish/Bearish stack, ADX > 25 (+15 max) |
| 3. VWAP & Trend Confirmation | 10 | VWAP slope, ATR distance from VWAP | Holding correct side of VWAP with healthy distance (+10 max) |
| 4. Trade Flow & Volume | 15 | Taker Volume Delta, 5m CVD change, RVOL | Aggressive flow matching setup direction (+15 max) |
| 5. OI, Funding & Basis | 15 | 5m OI change, Funding Rate percentile, Basis % | Fresh positioning (OI rising + price moving), healthy funding (+15 max) |
| 6. Liquidity & Execution | 10 | Bid/Ask spread, Book depth imbalance at 25 bps | Tight spread (<$2), favorable depth (+10 max) |
| 7. Volatility & Exhaustion | 15 | ATR-14 expansion, Spike Radar state | Penalty (-15) if EXHAUSTION_RISK / SPIKE_DETECTED (+15 if clean) |
| **Total** | **100** | | |

*Penalties:*
- Counter-Trend Setup Penalty: -20 points (e.g. 5m Long while 1h/4h Structure is Bearish).
- Stale or Missing Feed Penalty: -30 points (and blocks trade execution).

---

## 4. SYSTEM MODULES & PROJECT BLUEPRINT

```
d:\BITCOIN\
├── config/
│   ├── __init__.py
│   ├── settings.py            # Global environment, API endpoints, risk parameters
│   └── constants.py           # Regimes, Breakout stages, Spike stages, Decision states
├── ingestion/
│   ├── __init__.py
│   ├── delta_rest_client.py   # Robust REST client with rate limiting, retries, exponential backoff
│   ├── delta_ws_manager.py    # Public & standard WebSocket manager with auto-reconnect & resync
│   ├── product_discovery.py   # Dynamic BTC futures & dynamic options discovery
│   └── data_health.py         # Latency, staleness, sequence, and integrity watchdog
├── quant/
│   ├── __init__.py
│   ├── candle_builder.py      # Multi-timeframe candle aggregator (1m to 1d) with boundary alignment
│   ├── indicator_engine.py    # EMA 9/21/50/200, VWAP, ATR 14, ADX 14, RSI 14, Swings, Volatility
│   ├── orderflow_engine.py    # Buyer/seller aggressor classification, CVD, 1m/5m/15m delta, book imbalance
│   └── options_analytics.py   # Real-time option chain, Greeks, ATM finder, PCR, Max Pain, P&L
├── engine/
│   ├── __init__.py
│   ├── market_regime_engine.py# Multi-factor regime classifier (TREND_UP, TREND_DOWN, RANGE, etc.)
│   ├── breakout_engine.py     # 8-stage Breakout & Breakdown state machine
│   ├── spike_radar.py         # 7-stage Spike, Exhaustion & Reversal Radar
│   ├── liquidity_engine.py    # Daily/session levels, EQH/EQL, swing pivots, ATR distances
│   ├── setup_scoring_engine.py# 100-point explainable setup score and decision engine
│   └── risk_governor.py       # Equity risk governor, contract sizing (0.001 BTC), drawdown limits
├── backtest/
│   ├── __init__.py
│   ├── backtest_engine.py     # Historical backtesting engine with walk-forward, fee & slippage modeling
│   └── paper_trading_engine.py# Real-time paper execution, bid/ask fills, position & P&L lifecycle
├── database/
│   ├── __init__.py
│   ├── schema.sql             # SQLite schema for candles, ticks, paper trades, backtests, audit logs
│   └── db_manager.py          # High-performance WAL mode connection manager
├── server/
│   ├── __init__.py
│   ├── terminal_service.py    # Central quantitative orchestrator emitting unified terminal state
│   └── app.py                 # Flask + Flask-SocketIO REST API & reactive WebSocket server
├── ui/
│   ├── index.html             # 9-tab quantitative trading terminal UI
│   ├── css/
│   │   └── terminal.css       # Clean, modern dark trading terminal theme
│   └── js/
│       ├── terminal.js        # UI controller, WebSocket client, tab switcher, tooltip manager
│       └── charts.js          # Lightweight SVG/Canvas depth chart, CVD, and price visuals
├── tests/
│   ├── __init__.py
│   ├── test_indicators.py     # Unit tests for EMA, VWAP, ATR, ADX, RSI, Swing detection
│   ├── test_delta_parsers.py  # Unit tests for trade aggressor role, ticker parser, option symbol parser
│   ├── test_state_machines.py # Unit tests for breakout engine & spike radar state transitions
│   ├── test_risk_governor.py  # Unit tests for position sizing, contract specs, and risk limits
│   ├── test_options_math.py   # Unit tests for PCR, Max Pain, options P&L with 0.001 BTC multiplier
│   └── test_backtest_paper.py # Unit tests for backtest walk-forward, friction calculation, paper fills
├── run.py                     # One-click launcher
├── requirements.txt           # Python dependencies
└── README.md                  # Comprehensive terminal user guide & documentation
```
