"""
PROMETHEUS BTC TERMINAL: Quantitative Indicator Engine
Computes EMA 9/21/50/200, Session VWAP, ATR 14, ADX 14, RSI 14, RVOL, Swings, and ATR-distance from VWAP.
Documented warm-up periods and mathematical rigor. Never uses future data.
"""

from typing import Dict, List, Optional, Any, Tuple
import math
import numpy as np


class IndicatorEngine:
    """
    Authoritative indicator computation engine.
    Warm-up periods:
    - EMA 9: 9 bars
    - EMA 21: 21 bars
    - EMA 50: 50 bars
    - EMA 200: 200 bars (falls back gracefully if bars < 200)
    - ATR 14: 15 bars (Wilder's RMA)
    - RSI 14: 15 bars (Wilder's RMA)
    - ADX 14: 28 bars (14 for DI + 14 for ADX smoothing)
    - RVOL 20: 20 bars
    - Realized Volatility: 20 bars
    """

    @staticmethod
    def calculate_ema(prices: List[float], period: int) -> List[float]:
        """Calculates Exponential Moving Average with standard multiplier 2/(N+1)."""
        if len(prices) < period:
            return [float("nan")] * len(prices)
        
        ema = [float("nan")] * len(prices)
        # Seed first EMA with SMA
        sma = sum(prices[:period]) / period
        ema[period - 1] = sma
        k = 2.0 / (period + 1.0)

        for i in range(period, len(prices)):
            ema[i] = (prices[i] * k) + (ema[i - 1] * (1.0 - k))
        return ema

    @staticmethod
    def calculate_atr(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> List[float]:
        """Calculates Average True Range using Wilder's smoothing."""
        n = len(closes)
        if n <= period:
            return [float("nan")] * n

        tr = [0.0] * n
        tr[0] = highs[0] - lows[0]
        for i in range(1, n):
            h_l = highs[i] - lows[i]
            h_pc = abs(highs[i] - closes[i - 1])
            l_pc = abs(lows[i] - closes[i - 1])
            tr[i] = max(h_l, h_pc, l_pc)

        atr = [float("nan")] * n
        # Initial ATR is SMA of True Range
        atr[period - 1] = sum(tr[:period]) / period
        for i in range(period, n):
            atr[i] = ((atr[i - 1] * (period - 1)) + tr[i]) / period
        return atr

    @staticmethod
    def calculate_rsi(closes: List[float], period: int = 14) -> List[float]:
        """Calculates Wilder's Relative Strength Index (RSI)."""
        n = len(closes)
        if n <= period:
            return [float("nan")] * n

        gains = [0.0] * n
        losses = [0.0] * n

        for i in range(1, n):
            change = closes[i] - closes[i - 1]
            if change > 0:
                gains[i] = change
            else:
                losses[i] = abs(change)

        rsi = [float("nan")] * n
        avg_gain = sum(gains[1:period + 1]) / period
        avg_loss = sum(losses[1:period + 1]) / period

        if avg_loss == 0:
            rsi[period] = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi[period] = 100.0 - (100.0 / (1.0 + rs))

        for i in range(period + 1, n):
            avg_gain = ((avg_gain * (period - 1)) + gains[i]) / period
            avg_loss = ((avg_loss * (period - 1)) + losses[i]) / period

            if avg_loss == 0:
                rsi[i] = 100.0
            else:
                rs = avg_gain / avg_loss
                rsi[i] = 100.0 - (100.0 / (1.0 + rs))

        return rsi

    @staticmethod
    def calculate_adx(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> Tuple[List[float], List[float], List[float]]:
        """
        Calculates Average Directional Index (ADX) along with +DI and -DI.
        Returns: (adx_list, plus_di_list, minus_di_list)
        """
        n = len(closes)
        if n < (period * 2):
            nan_arr = [float("nan")] * n
            return nan_arr, nan_arr, nan_arr

        tr = [0.0] * n
        plus_dm = [0.0] * n
        minus_dm = [0.0] * n

        tr[0] = highs[0] - lows[0]
        for i in range(1, n):
            h_l = highs[i] - lows[i]
            h_pc = abs(highs[i] - closes[i - 1])
            l_pc = abs(lows[i] - closes[i - 1])
            tr[i] = max(h_l, h_pc, l_pc)

            up_move = highs[i] - highs[i - 1]
            down_move = lows[i - 1] - lows[i]

            if up_move > down_move and up_move > 0:
                plus_dm[i] = up_move
            else:
                plus_dm[i] = 0.0

            if down_move > up_move and down_move > 0:
                minus_dm[i] = down_move
            else:
                minus_dm[i] = 0.0

        # Wilder's smoothing for TR, +DM, -DM
        smoothed_tr = [0.0] * n
        smoothed_plus_dm = [0.0] * n
        smoothed_minus_dm = [0.0] * n

        smoothed_tr[period] = sum(tr[1:period + 1])
        smoothed_plus_dm[period] = sum(plus_dm[1:period + 1])
        smoothed_minus_dm[period] = sum(minus_dm[1:period + 1])

        plus_di = [float("nan")] * n
        minus_di = [float("nan")] * n
        dx = [float("nan")] * n

        for i in range(period, n):
            if i > period:
                smoothed_tr[i] = smoothed_tr[i - 1] - (smoothed_tr[i - 1] / period) + tr[i]
                smoothed_plus_dm[i] = smoothed_plus_dm[i - 1] - (smoothed_plus_dm[i - 1] / period) + plus_dm[i]
                smoothed_minus_dm[i] = smoothed_minus_dm[i - 1] - (smoothed_minus_dm[i - 1] / period) + minus_dm[i]

            p_di = 100.0 * (smoothed_plus_dm[i] / smoothed_tr[i]) if smoothed_tr[i] > 0 else 0.0
            m_di = 100.0 * (smoothed_minus_dm[i] / smoothed_tr[i]) if smoothed_tr[i] > 0 else 0.0
            plus_di[i] = p_di
            minus_di[i] = m_di

            di_sum = p_di + m_di
            dx[i] = (100.0 * abs(p_di - m_di) / di_sum) if di_sum > 0 else 0.0

        # ADX smoothing
        adx = [float("nan")] * n
        adx_start = period * 2 - 1
        adx[adx_start] = sum(dx[period:adx_start + 1]) / period
        for i in range(adx_start + 1, n):
            adx[i] = ((adx[i - 1] * (period - 1)) + dx[i]) / period

        return adx, plus_di, minus_di

    @staticmethod
    def calculate_vwap(candles: List[Dict[str, Any]], anchor_utc_midnight: bool = True) -> Dict[str, Any]:
        """
        Calculates Session VWAP anchored to 00:00 UTC with standard deviation bands.
        """
        if not candles:
            return {"vwap": 0.0, "std_dev": 0.0, "upper_1": 0.0, "lower_1": 0.0, "upper_2": 0.0, "lower_2": 0.0}

        cum_pv = 0.0
        cum_v = 0.0
        cum_p2v = 0.0

        # Identify current day anchor
        last_t = candles[-1]["time"]
        day_start_t = (last_t // 86400) * 86400 if anchor_utc_midnight else candles[0]["time"]

        for c in candles:
            if c["time"] < day_start_t:
                continue
            typical_price = (c["high"] + c["low"] + c["close"]) / 3.0
            vol = max(1.0, c.get("volume", 1.0))

            cum_pv += (typical_price * vol)
            cum_v += vol
            cum_p2v += ((typical_price ** 2) * vol)

        if cum_v == 0:
            return {"vwap": candles[-1]["close"], "std_dev": 0.0, "upper_1": 0.0, "lower_1": 0.0, "upper_2": 0.0, "lower_2": 0.0}

        vwap = cum_pv / cum_v
        variance = max(0.0, (cum_p2v / cum_v) - (vwap ** 2))
        std_dev = math.sqrt(variance)

        return {
            "vwap": round(vwap, 2),
            "std_dev": round(std_dev, 2),
            "upper_1": round(vwap + std_dev, 2),
            "lower_1": round(vwap - std_dev, 2),
            "upper_2": round(vwap + (2.0 * std_dev), 2),
            "lower_2": round(vwap - (2.0 * std_dev), 2)
        }

    @staticmethod
    def calculate_rvol(volumes: List[float], period: int = 20) -> float:
        """Calculates Relative Volume (current bar volume vs 20-period moving average)."""
        if len(volumes) < period or period == 0:
            return 1.0
        avg_vol = sum(volumes[-period - 1:-1]) / period
        if avg_vol <= 0:
            return 1.0
        return round(volumes[-1] / avg_vol, 2)

    @staticmethod
    def find_swing_levels(highs: List[float], lows: List[float], lookback: int = 5) -> Tuple[List[float], List[float]]:
        """Identifies fractal swing highs and swing lows."""
        n = len(highs)
        swing_highs = []
        swing_lows = []
        if n < (lookback * 2 + 1):
            return swing_highs, swing_lows

        for i in range(lookback, n - lookback):
            current_h = highs[i]
            if all(current_h > highs[i - j] for j in range(1, lookback + 1)) and \
               all(current_h >= highs[i + j] for j in range(1, lookback + 1)):
                swing_highs.append(current_h)

            current_l = lows[i]
            if all(current_l < lows[i - j] for j in range(1, lookback + 1)) and \
               all(current_l <= lows[i + j] for j in range(1, lookback + 1)):
                swing_lows.append(current_l)

        return swing_highs, swing_lows

    @staticmethod
    def calculate_realized_volatility(closes: List[float], period: int = 20) -> float:
        """Calculates annualized realized volatility from close-to-close log returns."""
        if len(closes) < period + 1:
            return 0.0
        log_returns = [math.log(closes[i] / closes[i - 1]) for i in range(len(closes) - period, len(closes))]
        std_ret = float(np.std(log_returns))
        # Annualize assuming 5-min intervals: sqrt(365 * 24 * 12) = sqrt(105120) ≈ 324.22
        annualized_vol = std_ret * math.sqrt(105120) * 100.0
        return round(annualized_vol, 2)

    def evaluate_all(self, candles: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Evaluates full suite of quantitative indicators on confirmed candle series."""
        if len(candles) < 20:
            return {"status": "INSUFFICIENT_DATA", "bars_count": len(candles)}

        closes = [float(c["close"]) for c in candles]
        highs = [float(c["high"]) for c in candles]
        lows = [float(c["low"]) for c in candles]
        volumes = [float(c.get("volume", 0.0)) for c in candles]

        # EMAs
        ema9 = self.calculate_ema(closes, 9)
        ema21 = self.calculate_ema(closes, 21)
        ema50 = self.calculate_ema(closes, 50)
        ema200 = self.calculate_ema(closes, 200)

        # Volatility & Momentum
        atr14 = self.calculate_atr(highs, lows, closes, 14)
        rsi14 = self.calculate_rsi(closes, 14)
        adx14, plus_di, minus_di = self.calculate_adx(highs, lows, closes, 14)
        vwap_data = self.calculate_vwap(candles)
        rvol = self.calculate_rvol(volumes, 20)
        realized_vol = self.calculate_realized_volatility(closes, 20)
        swing_highs, swing_lows = self.find_swing_levels(highs, lows, 3)

        curr_close = closes[-1]
        curr_atr = atr14[-1] if not math.isnan(atr14[-1]) else (curr_close * 0.005)
        vwap_val = vwap_data["vwap"]
        
        # Distance from VWAP normalized in ATR units: (Price - VWAP) / ATR_14
        dist_vwap_atr = round((curr_close - vwap_val) / curr_atr, 2) if curr_atr > 0 else 0.0

        return {
            "status": "VALID",
            "bars_count": len(candles),
            "close": curr_close,
            "ema9": round(ema9[-1], 2) if not math.isnan(ema9[-1]) else None,
            "ema21": round(ema21[-1], 2) if not math.isnan(ema21[-1]) else None,
            "ema50": round(ema50[-1], 2) if not math.isnan(ema50[-1]) else None,
            "ema200": round(ema200[-1], 2) if not math.isnan(ema200[-1]) else None,
            "atr14": round(curr_atr, 2),
            "rsi14": round(rsi14[-1], 1) if not math.isnan(rsi14[-1]) else None,
            "adx14": round(adx14[-1], 1) if not math.isnan(adx14[-1]) else None,
            "plus_di": round(plus_di[-1], 1) if not math.isnan(plus_di[-1]) else None,
            "minus_di": round(minus_di[-1], 1) if not math.isnan(minus_di[-1]) else None,
            "vwap": vwap_val,
            "vwap_bands": vwap_data,
            "dist_vwap_atr": dist_vwap_atr,
            "rvol": rvol,
            "realized_vol_pct": realized_vol,
            "recent_swing_high": swing_highs[-1] if swing_highs else None,
            "recent_swing_low": swing_lows[-1] if swing_lows else None
        }


indicator_engine = IndicatorEngine()
