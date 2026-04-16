"""OKX REST API 客户端"""

import aiohttp
import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone

from ..config import Config
from ..utils import async_retry, RateLimiter
from .okx_signer import OKXSigner


class RESTClient:
    """OKX REST API 客户端"""
    
    BASE_URL = "https://www.okx.com"
    TESTNET_URL = "https://www.okx.com"
    
    def __init__(self, config: Config):
        self.config = config
        self.api_key = config.exchange.api_key
        self.secret_key = config.exchange.secret_key
        self.passphrase = config.exchange.passphrase
        self.testnet = config.exchange.testnet
        
        self.signer = OKXSigner(self.api_key, self.secret_key, self.passphrase)
        
        self.rate_limiter = RateLimiter(
            rate_limit=config.exchange.rate_limit_requests_per_second,
            burst=config.exchange.rate_limit_burst
        )
        
        self._session: Optional[aiohttp.ClientSession] = None
    
    @property
    def base_url(self) -> str:
        return self.TESTNET_URL if self.testnet else self.BASE_URL
    
    async def get_session(self) -> aiohttp.ClientSession:
        """获取或创建会话"""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.config.execution.timeout)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session
    
    async def close(self) -> None:
        """关闭会话"""
        if self._session and not self._session.closed:
            await self._session.close()
    
    def _get_headers(self, timestamp: str, method: str, path: str, body: str = "") -> Dict[str, str]:
        """获取请求头"""
        return self.signer.sign_request(timestamp, method, path, body)
    
    @async_retry(max_attempts=3, initial_delay=1.0)
    async def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict] = None,
        data: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """发送请求"""
        await self.rate_limiter.acquire()
        
        session = await self.get_session()
        url = f"{self.base_url}{path}"
        
        timestamp = datetime.now(timezone.utc).isoformat()
        body_str = ""
        if data:
            import json
            body_str = json.dumps(data)
        
        headers = self._get_headers(timestamp, method, path, body_str)
        
        async with session.request(
            method,
            url,
            params=params,
            json=data if data else None,
            headers=headers
        ) as response:
            result = await response.json()
            
            if response.status != 200:
                raise APIError(
                    code=response.status,
                    message=f"HTTP {response.status}: {result.get('msg', '')}"
                )
            
            if result.get("code") != "0":
                raise APIError(
                    code=int(result.get("code", 0)),
                    message=result.get("msg", "Unknown error")
                )
            
            return result
    
    async def get_klines(
        self,
        symbol: str,
        interval: str = "1h",
        limit: int = 100,
        start: Optional[str] = None,
        end: Optional[str] = None
    ) -> List[Dict]:
        """
        获取K线数据
        
        Args:
            symbol: 交易对 (如 BTC-USDT)
            interval: 周期 (1m, 5m, 1h, 4h, 1d)
            limit: 数据条数
            start: 开始时间 (ISO格式)
            end: 结束时间 (ISO格式)
        """
        path = "/api/v5/market/candles"
        params = {
            "instId": symbol,
            "bar": interval,
            "limit": limit
        }
        if start:
            params["after"] = start
        if end:
            params["before"] = end
        
        result = await self._request("GET", path, params=params)
        return result.get("data", [])
    
    async def get_ticker(self, symbol: str) -> Dict:
        """获取行情数据"""
        path = "/api/v5/market/ticker"
        params = {"instId": symbol}
        
        result = await self._request("GET", path, params=params)
        data = result.get("data", [])
        return data[0] if data else None
    
    async def get_balance(self) -> Dict:
        """获取账户余额"""
        path = "/api/v5/account/balance"
        result = await self._request("GET", path)
        return result.get("data", [{}])[0]
    
    async def get_positions(self) -> List[Dict]:
        """获取持仓"""
        path = "/api/v5/account/positions"
        result = await self._request("GET", path)
        return result.get("data", [])
    
    async def place_order(self, order: Dict) -> Dict:
        """下单"""
        path = "/api/v5/trade/order"
        result = await self._request("POST", path, data=order)
        data = result.get("data", [])
        return data[0] if data else None
    
    async def cancel_order(self, symbol: str, order_id: str, client_order_id: Optional[str] = None) -> Dict:
        """取消订单"""
        path = "/api/v5/trade/cancel-order"
        data = {"instId": symbol, "ordId": order_id}
        if client_order_id:
            data["clOrdId"] = client_order_id
        
        result = await self._request("POST", path, data=data)
        return result.get("data", [{}])[0]
    
    async def get_order(self, symbol: str, order_id: str, client_order_id: Optional[str] = None) -> Dict:
        """查询订单"""
        path = "/api/v5/trade/order"
        params = {"instId": symbol}
        if order_id:
            params["ordId"] = order_id
        if client_order_id:
            params["clOrdId"] = client_order_id
        
        result = await self._request("GET", path, params=params)
        data = result.get("data", [])
        return data[0] if data else None


class APIError(Exception):
    """API错误"""
    
    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message
        super().__init__(f"[{code}] {message}")
