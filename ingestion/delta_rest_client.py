"""
PROMETHEUS BTC TERMINAL: Delta Exchange India REST Client
Production-quality client with rate limiting, retries, exponential backoff, and error handling.
"""

import time
import requests
from typing import Dict, List, Optional, Any
from urllib.parse import urlencode

from config.settings import config


class DeltaRestClient:
    def __init__(self, base_url: Optional[str] = None):
        self.base_url = (base_url or config.rest_base_url).rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Prometheus-BTC-Terminal/1.0",
            "Accept": "application/json"
        })
        self.last_request_time = 0.0
        self.min_interval = 0.05  # Max 20 requests per sec per IP
        self.api_errors_count = 0
        self.rate_limit_warnings = 0

    def _throttle(self):
        elapsed = time.time() - self.last_request_time
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self.last_request_time = time.time()

    def _request(self, method: str, endpoint: str, params: Optional[Dict[str, Any]] = None, timeout: float = 8.0) -> Dict[str, Any]:
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        max_retries = config.max_rate_limit_retries
        backoff = 0.5

        for attempt in range(max_retries):
            self._throttle()
            try:
                response = self.session.request(method, url, params=params, timeout=timeout)
                
                if response.status_code == 429:
                    self.rate_limit_warnings += 1
                    time.sleep(backoff)
                    backoff *= 2.0
                    continue

                if response.status_code >= 500:
                    self.api_errors_count += 1
                    time.sleep(backoff)
                    backoff *= 2.0
                    continue

                response.raise_for_status()
                data = response.json()
                return data

            except requests.exceptions.RequestException as e:
                self.api_errors_count += 1
                if attempt == max_retries - 1:
                    raise RuntimeError(f"Delta REST API request failed after {max_retries} attempts: {url} -> {e}")
                time.sleep(backoff)
                backoff *= 2.0

        raise RuntimeError(f"Delta REST API request exhausted retries: {url}")

    # ==========================================
    # Documented Delta India Endpoints
    # ==========================================
    def get_products(self, contract_types: Optional[str] = None) -> List[Dict[str, Any]]:
        """GET /v2/products - Discovers contracts dynamically."""
        params = {}
        if contract_types:
            params["contract_types"] = contract_types
        res = self._request("GET", "v2/products", params=params)
        return res.get("result", [])

    def get_ticker(self, symbol: str) -> Dict[str, Any]:
        """GET /v2/tickers/{symbol} - Retrieves single product ticker."""
        res = self._request("GET", f"v2/tickers/{symbol}")
        return res.get("result", {})

    def get_tickers(self, underlying_asset_symbols: Optional[str] = "BTC", contract_types: Optional[str] = None) -> List[Dict[str, Any]]:
        """GET /v2/tickers - Retrieves tickers array."""
        params = {}
        if underlying_asset_symbols:
            params["underlying_asset_symbols"] = underlying_asset_symbols
        if contract_types:
            params["contract_types"] = contract_types
        res = self._request("GET", "v2/tickers", params=params)
        return res.get("result", [])

    def get_candles(self, symbol: str, resolution: str, start: int, end: int) -> List[Dict[str, Any]]:
        """
        GET /v2/history/candles
        Supported resolutions: 1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h, 1d
        Timestamps are UTC unix epoch in seconds.
        """
        params = {
            "symbol": symbol,
            "resolution": resolution,
            "start": start,
            "end": end
        }
        res = self._request("GET", "v2/history/candles", params=params)
        candles = res.get("result", [])
        # Sort chronologically ascending
        candles.sort(key=lambda x: x.get("time", 0))
        return candles

    def get_l2_orderbook(self, symbol: str) -> Dict[str, Any]:
        """GET /v2/l2orderbook/{symbol} - Deep Level 2 snapshot."""
        res = self._request("GET", f"v2/l2orderbook/{symbol}")
        return res.get("result", {})

    def get_trades(self, symbol: str) -> List[Dict[str, Any]]:
        """GET /v2/trades/{symbol} - Recent trade executions."""
        res = self._request("GET", f"v2/trades/{symbol}")
        return res.get("result", [])


delta_rest_client = DeltaRestClient()
