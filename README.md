# ⚡ PROMETHEUS BTC TERMINAL (DELTA EXCHANGE INDIA)

Production-quality Bitcoin trading analysis dashboard and quantitative decision-support system built for **Delta Exchange India**.

---

## 1. System Overview

- **Exchange:** Delta Exchange India
- **Production REST Base:** `https://api.india.delta.exchange`
- **Public & Streaming WebSocket:** `wss://socket.india.delta.exchange` / `wss://public-socket.india.delta.exchange`
- **Target Markets:**
  1. `BTCUSD` Perpetual Futures (`contract_value = 0.001 BTC`, `tick_size = 0.5`)
  2. Dynamic BTC Options (Calls & Puts across all active daily, weekly, monthly expiries)
- **Primary Architecture:** Multi-factor quantitative decision-support system with 9 specialized analytical tabs, real-time Level 2 orderbook synchronization, trade aggressor volume classification, 8-stage breakout state machine, 7-stage spike/reversal radar, options Greeks & Max Pain, risk governor, and walk-forward historical backtesting.

---

## 2. 9 Navigation Tabs

1. **Command Center:** Executive trade conviction state, 100-point setup score, battle map (closest resistance & support in ATR units), evidence, and conflicts.
2. **Futures Engine:** Live BTCUSD perpetual orderbook depth, spread, tick size ($0.5), contract multiplier (0.001 BTC), and 5m candlestick chart.
3. **Options Engine:** Dynamic expiry selector, real-time strike ladder, ATM identification, Calls vs Puts, Delta, Gamma, Theta, Vega, IV, PCR (OI & Vol), and Max Pain strike.
4. **Breakout & Breakdown:** 8-stage state machine (`RANGE_IDENTIFIED` → `LEVEL_APPROACHING` → `BREAKOUT_ATTEMPT` → `BREAKOUT_CANDLE_CLOSED` → `CONFIRMATION_PENDING` → `RETEST_OR_ACCEPTANCE` → `CONFIRMED` → `FAILED_BREAKOUT`), dynamic ATR buffers, proposal stop-loss and targets.
5. **Spike/Reversal Radar:** 7-stage velocity radar (`NORMAL` → `MOVE_ACCELERATING` → `SPIKE_DETECTED` → `EXHAUSTION_RISK` → `REVERSAL_RISK` → `REVERSAL_CONFIRMED` → `RESET`), 5m velocity, 5m return, ATR-normalized displacement, and tactical guidance.
6. **Liquidity & Order Flow:** Cumulative Volume Delta (CVD) chart, Depth Imbalance at 10, 25, 50, 100 bps bands, Previous UTC Day H/L, 8h Session H/L, EQH/EQL, and Volume Profile Point of Control (POC).
7. **Paper Trading:** Virtual capital portfolio ($10,000 default), active simulated position tracking with real-time bid/ask fills, stop-loss, targets, MFE/MAE, P&L, and audit log.
8. **Backtesting & Performance:** Chronological walk-forward simulator running on real Delta India historical candles with realistic taker fees (0.05%), maker fees (0.02%), slippage (0.02%), and metrics reporting.
9. **Data Quality & Calculation Audit:** Per-feed watchdog (REST, WebSocket, Ticker, Book, Trades, Candles), circuit breaker status, formula-by-formula calculation audit table.

---

## 3. Quick Start & Execution

### Installation:
```bash
pip install -r requirements.txt
```

### Run Server:
```bash
python run.py
```
Open browser at `http://127.0.0.1:5000`.

### Run Automated Test Suite:
```bash
python -m pytest tests -v
```

---

## 4. Delta India REST Endpoints & WebSocket Channels Verified

- `GET /v2/products`: Dynamic contract discovery (discovered `BTCUSD` id: 27 and 600+ BTC options).
- `GET /v2/tickers/BTCUSD`: Real-time mark price, close, spot price, funding rate, quotes, open interest.
- `GET /v2/tickers?underlying_asset_symbols=BTC`: Full option chain tickers with live Delta, Gamma, Theta, Vega, mark IV.
- `GET /v2/history/candles?resolution=5m&symbol=BTCUSD&start=...&end=...`: Multi-timeframe OHLCV candles (1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h, 1d).
- `GET /v2/l2orderbook/BTCUSD`: Level 2 depth snapshot.
- `GET /v2/trades/BTCUSD`: Recent trade executions with maker/taker aggressor roles.
- `WebSocket wss://socket.india.delta.exchange`: Real-time channels `v2/ticker`, `l2_orderbook`, `all_trades`, `candlestick_1m`.
