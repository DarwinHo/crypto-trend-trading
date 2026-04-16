"""OKX WebSocket 客户端"""

import asyncio
import json
from typing import Optional, Dict, Any, Callable, List
from dataclasses import dataclass
import time
import logging

from ..config import Config
from ..utils import RateLimiter


logger = logging.getLogger(__name__)


@dataclass
class WebSocketConfig:
    """WebSocket配置"""
    url: str = "wss://ws.okx.com:8443/ws/v5/public"
    reconnect_max_attempts: int = 5
    reconnect_base_interval: float = 1.0
    reconnect_multiplier: float = 2.0
    reconnect_max_interval: float = 16.0
    ping_interval: float = 20.0
    ping_timeout: float = 10.0


class WebSocketClient:
    """OKX WebSocket 客户端"""
    
    def __init__(self, config: Config):
        self.config = config
        self.testnet = config.exchange.testnet
        
        ws_config = WebSocketConfig()
        if self.testnet:
            ws_config.url = "wss://ws.okx.com:8443/ws/v5/public"
        
        self.url = ws_config.url
        self.reconnect_config = {
            "max_attempts": ws_config.reconnect_max_attempts,
            "base_interval": ws_config.reconnect_base_interval,
            "multiplier": ws_config.reconnect_multiplier,
            "max_interval": ws_config.reconnect_max_interval
        }
        self.ping_interval = ws_config.ping_interval
        self.ping_timeout = ws_config.ping_timeout
        
        self._ws: Optional[asyncio.WebSocketClientProtocol] = None
        self._connected = False
        self._subscriptions: Dict[str, List[str]] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._listener_task: Optional[asyncio.Task] = None
        self._ping_task: Optional[asyncio.Task] = None
        self._reconnect_attempts = 0
        
        self._lock = asyncio.Lock()
    
    @property
    def is_connected(self) -> bool:
        return self._connected
    
    async def connect(self) -> bool:
        """建立WebSocket连接"""
        try:
            async with asyncio.timeout(10.0):
                self._ws = await asyncio.get_event_loop().create_connection(
                    asyncio.WebSocketClientProtocol,
                    self.url
                )
                self._ws = self._ws[1]
                
                await self._ws.connect()
                self._connected = True
                self._reconnect_attempts = 0
                
                logger.info(f"WebSocket connected to {self.url}")
                
                self._listener_task = asyncio.create_task(self._listen())
                self._ping_task = asyncio.create_task(self._ping_loop())
                
                return True
        except Exception as e:
            logger.error(f"WebSocket connection failed: {e}")
            self._connected = False
            return False
    
    async def disconnect(self) -> None:
        """断开WebSocket连接"""
        self._connected = False
        
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
        
        if self._ping_task:
            self._ping_task.cancel()
            try:
                await self._ping_task
            except asyncio.CancelledError:
                pass
        
        if self._ws:
            await self._ws.close()
            self._ws = None
        
        logger.info("WebSocket disconnected")
    
    async def _listen(self) -> None:
        """监听消息"""
        while self._connected:
            try:
                async with asyncio.timeout(30.0):
                    message = await self._ws.receive()
                    
                    if message.type == asyncio.WSMsgType.TEXT:
                        await self._handle_message(message.data)
                    elif message.type == asyncio.WSMsgType.ERROR:
                        logger.error(f"WebSocket error: {message.data}")
                        break
                    elif message.type == asyncio.WSMsgType.CLOSED:
                        logger.warning("WebSocket closed")
                        break
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Listen error: {e}")
                break
        
        if self._connected:
            await self._handle_disconnect()
    
    async def _handle_message(self, data: str) -> None:
        """处理接收到的消息"""
        try:
            msg = json.loads(data)
            
            if "event" in msg:
                if msg["event"] == "subscribe":
                    logger.info(f"Subscribed: {msg.get('args', [])}")
                    return
                elif msg["event"] == "error":
                    logger.error(f"Subscribe error: {msg.get('msg', '')}")
                    return
            
            channel = msg.get("channel", "")
            data_list = msg.get("data", [])
            
            if channel in self._callbacks:
                for data_item in data_list:
                    await self._callbacks[channel](data_item)
                    
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
        except Exception as e:
            logger.error(f"Message handling error: {e}")
    
    async def _handle_disconnect(self) -> None:
        """处理断开连接"""
        self._connected = False
        
        if self._reconnect_attempts >= self.reconnect_config["max_attempts"]:
            logger.error("Max reconnection attempts reached")
            return
        
        self._reconnect_attempts += 1
        interval = min(
            self.reconnect_config["base_interval"] * (self.reconnect_config["multiplier"] ** (self._reconnect_attempts - 1)),
            self.reconnect_config["max_interval"]
        )
        
        logger.info(f"Reconnecting in {interval}s (attempt {self._reconnect_attempts})")
        await asyncio.sleep(interval)
        
        if await self.connect():
            await self._resubscribe()
    
    async def _resubscribe(self) -> None:
        """重新订阅"""
        for channel, args_list in self._subscriptions.items():
            for args in args_list:
                await self.subscribe(channel, args)
    
    async def _ping_loop(self) -> None:
        """心跳循环"""
        while self._connected:
            try:
                await asyncio.sleep(self.ping_interval)
                if self._connected and self._ws:
                    await self._ws.ping()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Ping error: {e}")
                break
    
    async def subscribe(self, channel: str, args: Dict) -> bool:
        """
        订阅频道
        
        Args:
            channel: 频道名称 (tickers, candle1m, etc.)
            args: 订阅参数 {"instId": "BTC-USDT"}
        """
        if not self._connected:
            logger.warning("Cannot subscribe: not connected")
            return False
        
        subscribe_msg = {
            "op": "subscribe",
            "args": [{"channel": channel, **args}]
        }
        
        await self._ws.send(json.dumps(subscribe_msg))
        
        key = f"{channel}:{args.get('instId', '')}"
        if channel not in self._subscriptions:
            self._subscriptions[channel] = []
        if args not in self._subscriptions[channel]:
            self._subscriptions[channel].append(args)
        
        return True
    
    async def unsubscribe(self, channel: str, args: Dict) -> bool:
        """取消订阅"""
        if not self._connected:
            return False
        
        unsubscribe_msg = {
            "op": "unsubscribe",
            "args": [{"channel": channel, **args}]
        }
        
        await self._ws.send(json.dumps(unsubscribe_msg))
        
        key = f"{channel}:{args.get('instId', '')}"
        if channel in self._subscriptions:
            if args in self._subscriptions[channel]:
                self._subscriptions[channel].remove(args)
        
        return True
    
    def register_callback(self, channel: str, callback: Callable) -> None:
        """注册消息回调"""
        self._callbacks[channel] = callback
    
    def unregister_callback(self, channel: str) -> None:
        """取消注册回调"""
        self._callbacks.pop(channel, None)
