"""订单执行器

将交易信号转化为实际订单，与OKX API交互。
"""

import asyncio
import logging
from typing import Optional, List, Dict
from dataclasses import dataclass
import time

from ..config import Config
from ..models import (
    OrderRequest, OrderResponse, OrderStatus, OrderSide, OrderType,
    TrendSignal, SignalDirection, Balance,
    format_order_for_okx, parse_order_status_from_okx, OrderBook,
    generate_client_order_id
)
from ..api import RESTClient
from ..utils import get_current_timestamp_ms, async_retry

logger = logging.getLogger(__name__)


class OrderExecutor:
    """
    订单执行器
    
    负责：
    - 订单创建和提交
    - 订单状态跟踪
    - 订单取消管理
    - 滑点控制
    """
    
    def __init__(self, config: Config):
        self.config = config
        self.execution_config = config.execution
        
        self.rest_client = RESTClient(config)
        
        self._order_book = OrderBook()
        self._slippage_rate = self.execution_config.slippage
        self._timeout = self.execution_config.timeout
        self._retry_attempts = self.execution_config.retry_max_attempts
        
        self._balance: Balance = Balance(
            total_equity=0.0,
            available=0.0,
            margin_used=0.0,
            margin_available=0.0
        )
        
        self._pending_orders: Dict[str, asyncio.Task] = {}
    
    @property
    def balance(self) -> Balance:
        return self._balance
    
    async def initialize(self) -> None:
        """初始化"""
        await self._update_balance()
    
    @async_retry(max_attempts=3, initial_delay=1.0)
    async def submit_order(self, order: OrderRequest) -> OrderResponse:
        """
        提交订单
        
        Args:
            order: 订单请求
            
        Returns:
            订单响应
        """
        start_time = time.monotonic()
        order.submitted_at = get_current_timestamp_ms()
        
        okx_order = format_order_for_okx(order)
        
        try:
            result = await self.rest_client.place_order(okx_order)
            
            submit_latency_ms = (time.monotonic() - start_time) * 1000
            
            if result.get("sCode") != "0":
                return OrderResponse(
                    order_id="",
                    client_order_id=order.client_order_id,
                    symbol=order.symbol,
                    status=OrderStatus.REJECTED,
                    side=order.side,
                    order_type=order.order_type,
                    price=order.price or 0.0,
                    quantity=order.quantity,
                    filled_qty=0.0,
                    avg_price=0.0,
                    fee=0.0,
                    timestamp=order.submitted_at,
                    updated_at=get_current_timestamp_ms(),
                    submit_latency_ms=submit_latency_ms
                )
            
            response = OrderResponse(
                order_id=result.get("ordId", ""),
                client_order_id=order.client_order_id,
                symbol=order.symbol,
                status=OrderStatus.SUBMITTED,
                side=order.side,
                order_type=order.order_type,
                price=order.price or 0.0,
                quantity=order.quantity,
                filled_qty=0.0,
                avg_price=0.0,
                fee=0.0,
                timestamp=order.submitted_at,
                updated_at=get_current_timestamp_ms(),
                submit_latency_ms=submit_latency_ms
            )
            
            self._order_book.add(response)
            
            asyncio.create_task(self._track_order(response))
            
            logger.info(f"Order submitted: {response.client_order_id} {response.side.value} {response.quantity}")
            
            return response
            
        except Exception as e:
            logger.error(f"Order submission failed: {e}")
            
            return OrderResponse(
                order_id="",
                client_order_id=order.client_order_id,
                symbol=order.symbol,
                status=OrderStatus.FAILED,
                side=order.side,
                order_type=order.order_type,
                price=order.price or 0.0,
                quantity=order.quantity,
                filled_qty=0.0,
                avg_price=0.0,
                fee=0.0,
                timestamp=order.submitted_at,
                updated_at=get_current_timestamp_ms(),
                submit_latency_ms=(time.monotonic() - start_time) * 1000
            )
    
    async def cancel_order(self, order_id: str, symbol: str, client_order_id: Optional[str] = None) -> bool:
        """
        取消订单
        
        Args:
            order_id: 交易所订单ID
            symbol: 交易对
            client_order_id: 客户端订单ID
            
        Returns:
            是否成功
        """
        try:
            result = await self.rest_client.cancel_order(symbol, order_id, client_order_id)
            
            if result.get("sCode") == "0":
                order = self._order_book.get(client_order_id or order_id)
                if order:
                    order.status = OrderStatus.CANCELLED
                    order.updated_at = get_current_timestamp_ms()
                
                logger.info(f"Order cancelled: {client_order_id or order_id}")
                return True
            else:
                logger.error(f"Cancel failed: {result.get('sMsg', '')}")
                return False
                
        except Exception as e:
            logger.error(f"Cancel order error: {e}")
            return False
    
    async def cancel_all_orders(self, symbol: Optional[str] = None) -> int:
        """
        取消所有订单
        
        Args:
            symbol: 交易对，None表示取消所有
            
        Returns:
            取消的订单数
        """
        open_orders = self._order_book.get_open_orders(symbol)
        cancelled_count = 0
        
        for order in open_orders:
            success = await self.cancel_order(order.order_id, order.symbol, order.client_order_id)
            if success:
                cancelled_count += 1
        
        logger.info(f"Cancelled {cancelled_count} orders")
        return cancelled_count
    
    async def get_order_status(self, order_id: str, symbol: str) -> Optional[OrderStatus]:
        """查询订单状态"""
        try:
            result = await self.rest_client.get_order(symbol, order_id)
            if result:
                return parse_order_status_from_okx(result.get("state", ""))
            return None
        except Exception as e:
            logger.error(f"Get order status error: {e}")
            return None
    
    async def get_balance(self) -> Balance:
        """获取账户余额"""
        await self._update_balance()
        return self._balance
    
    async def _update_balance(self) -> None:
        """更新余额"""
        try:
            result = await self.rest_client.get_balance()
            
            details = result.get("details", [{}])[0]
            
            self._balance = Balance(
                total_equity=float(details.get("totalEq", 0)),
                available=float(details.get("availBal", 0)),
                margin_used=float(details.get("marginUsed", 0)),
                margin_available=float(details.get("marginAvailable", 0))
            )
            
        except Exception as e:
            logger.error(f"Update balance error: {e}")
    
    async def _track_order(self, order: OrderResponse) -> None:
        """跟踪订单状态"""
        max_wait = self._timeout
        check_interval = 0.5
        waited = 0
        
        while waited < max_wait:
            await asyncio.sleep(check_interval)
            waited += check_interval
            
            status = await self.get_order_status(order.order_id, order.symbol)
            
            if status is None:
                continue
            
            order.status = status
            order.updated_at = get_current_timestamp_ms()
            
            if status in {OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED}:
                if status == OrderStatus.FILLED:
                    order.fill_latency_ms = (order.updated_at - order.timestamp)
                    logger.info(f"Order filled: {order.client_order_id}")
                break
        
        if order.status == OrderStatus.SUBMITTED:
            await self.cancel_order(order.order_id, order.symbol, order.client_order_id)
            order.status = OrderStatus.EXPIRED
            logger.warning(f"Order expired: {order.client_order_id}")
    
    def calculate_execution_price(
        self,
        side: OrderSide,
        market_price: float,
        order_type: OrderType
    ) -> float:
        """
        计算最优执行价格
        
        Args:
            side: 订单方向
            market_price: 市场当前价格
            order_type: 订单类型
            
        Returns:
            执行价格
        """
        if order_type == OrderType.MARKET:
            if side == OrderSide.BUY:
                return market_price * (1 + self._slippage_rate)
            else:
                return market_price * (1 - self._slippage_rate)
        else:
            return market_price
    
    def get_open_orders(self, symbol: Optional[str] = None) -> List[OrderResponse]:
        """获取挂单"""
        return self._order_book.get_open_orders(symbol)
    
    async def close(self) -> None:
        """关闭"""
        await self.rest_client.close()
