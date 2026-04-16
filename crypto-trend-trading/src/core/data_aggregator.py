"""数据聚合器

负责从OKX WebSocket和REST API采集市场数据，并进行标准化处理。
"""

import asyncio
import logging
from typing import Optional, Callable, Dict, List
from dataclasses import dataclass, field

from ..config import Config
from ..api import WebSocketClient, RESTClient
from ..models import KLine, Ticker, KLineCache, parse_kline_from_okx, parse_ticker_from_okx
from ..utils import get_current_timestamp_ms

logger = logging.getLogger(__name__)


@dataclass
class TickEvent:
    """行情事件"""
    symbol: str
    ticker: Optional[Ticker] = None
    kline: Optional[KLine] = None
    timestamp: int = field(default_factory=get_current_timestamp_ms)
    latency_us: int = 0


class DataAggregator:
    """
    数据聚合器
    
    负责：
    - 管理WebSocket连接和订阅
    - 从REST API获取历史数据
    - 标准化和缓存数据
    - 分发行情事件
    """
    
    def __init__(self, config: Config):
        self.config = config
        self.symbols = config.symbols
        
        self.ws_client = WebSocketClient(config)
        self.rest_client = RESTClient(config)
        
        self._kline_cache = KLineCache(max_klines=1000)
        self._ticker_cache: Dict[str, Ticker] = {}
        self._callbacks: List[Callable] = []
        self._running = False
        self._connected = False
    
    @property
    def is_connected(self) -> bool:
        return self._connected
    
    async def connect(self) -> bool:
        """建立WebSocket连接"""
        if self._connected:
            return True
        
        success = await self.ws_client.connect()
        if success:
            self._connected = True
            self._running = True
            
            self.ws_client.register_callback("tickers", self._on_ticker)
            self.ws_client.register_callback("candle1m", self._on_kline)
            
            logger.info("DataAggregator connected")
        else:
            logger.error("DataAggregator connection failed")
        
        return success
    
    async def disconnect(self) -> None:
        """断开连接"""
        self._running = False
        self._connected = False
        
        await self.ws_client.disconnect()
        await self.rest_client.close()
        
        logger.info("DataAggregator disconnected")
    
    async def subscribe(self, symbols: Optional[List[str]] = None) -> bool:
        """
        订阅行情
        
        Args:
            symbols: 交易对列表，默认使用配置中的symbols
        """
        if not self._connected:
            logger.warning("Cannot subscribe: not connected")
            return False
        
        symbols = symbols or self.symbols
        success = True
        
        for symbol in symbols:
            await self.ws_client.subscribe("tickers", {"instId": symbol})
            await self.ws_client.subscribe("candle1m", {"instId": symbol})
        
        logger.info(f"Subscribed to {len(symbols)} symbols")
        return success
    
    async def _on_ticker(self, data: dict) -> None:
        """处理行情数据"""
        try:
            ticker = parse_ticker_from_okx(data)
            self._ticker_cache[ticker.symbol] = ticker
            
            latency_us = (get_current_timestamp_ms() - ticker.timestamp) * 1000
            
            event = TickEvent(
                symbol=ticker.symbol,
                ticker=ticker,
                timestamp=ticker.timestamp,
                latency_us=latency_us
            )
            
            await self._dispatch_event(event)
            
        except Exception as e:
            logger.error(f"Ticker parse error: {e}")
    
    async def _on_kline(self, data: dict) -> None:
        """处理K线数据"""
        try:
            kline = parse_kline_from_okx(data)
            
            interval = "1m"
            self._kline_cache.add(kline.symbol, interval, kline)
            
            event = TickEvent(
                symbol=kline.symbol,
                kline=kline,
                timestamp=kline.timestamp
            )
            
            await self._dispatch_event(event)
            
        except Exception as e:
            logger.error(f"Kline parse error: {e}")
    
    async def _dispatch_event(self, event: TickEvent) -> None:
        """分发事件到所有回调"""
        for callback in self._callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(event)
                else:
                    callback(event)
            except Exception as e:
                logger.error(f"Callback error: {e}")
    
    def on_tick(self, callback: Callable) -> None:
        """注册行情回调"""
        self._callbacks.append(callback)
    
    def remove_callback(self, callback: Callable) -> None:
        """移除回调"""
        if callback in self._callbacks:
            self._callbacks.remove(callback)
    
    async def get_klines(
        self,
        symbol: str,
        interval: str = "1h",
        limit: int = 100
    ) -> List[KLine]:
        """
        获取K线数据
        
        优先从缓存获取，缓存不足时从API获取
        """
        cached = self._kline_cache.get(symbol, interval, limit)
        
        if len(cached) >= limit:
            return cached
        
        try:
            data = await self.rest_client.get_klines(
                symbol=symbol,
                interval=interval,
                limit=limit
            )
            
            klines = []
            for item in reversed(data):
                kline = parse_kline_from_okx(item)
                self._kline_cache.add(symbol, interval, kline)
                klines.append(kline)
            
            return klines
            
        except Exception as e:
            logger.error(f"Failed to fetch klines: {e}")
            return cached
    
    def get_ticker(self, symbol: str) -> Optional[Ticker]:
        """获取最新行情"""
        return self._ticker_cache.get(symbol)
    
    def get_cached_klines(self, symbol: str, interval: str = "1m", limit: int = 100) -> List[KLine]:
        """获取缓存的K线"""
        return self._kline_cache.get(symbol, interval, limit)
