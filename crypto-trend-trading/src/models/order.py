"""订单相关模型"""

from dataclasses import dataclass, field
from typing import Optional
from enum import Enum
import uuid
import time

from .types import OrderRequest, OrderResponse, OrderStatus, OrderSide, OrderType


def generate_client_order_id(prefix: str = "ord") -> str:
    """生成客户端订单ID"""
    return f"{prefix}_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"


def parse_order_status_from_okx(status: str) -> OrderStatus:
    """解析OKX订单状态"""
    status_mapping = {
        "live": OrderStatus.SUBMITTED,
        "partially_filled": OrderStatus.PARTIAL_FILLED,
        "filled": OrderStatus.FILLED,
        "canceled": OrderStatus.CANCELLED,
        "rejected": OrderStatus.REJECTED,
        "expired": OrderStatus.EXPIRED
    }
    return status_mapping.get(status.lower(), OrderStatus.UNKNOWN)


def create_order_request(
    symbol: str,
    side: OrderSide,
    quantity: float,
    order_type: OrderType = OrderType.MARKET,
    price: Optional[float] = None,
    reduce_only: bool = False,
    signal_id: Optional[str] = None
) -> OrderRequest:
    """创建订单请求"""
    return OrderRequest(
        symbol=symbol,
        side=side,
        order_type=order_type,
        price=price,
        quantity=quantity,
        client_order_id=generate_client_order_id(),
        reduce_only=reduce_only,
        signal_id=signal_id,
        submitted_at=int(time.time() * 1000)
    )


def format_order_for_okx(order: OrderRequest) -> dict:
    """格式化订单为OKX API请求格式"""
    return {
        "instId": order.symbol,
        "tdMode": "isolated",
        "side": order.side.value,
        "ordType": order.order_type.value,
        "sz": str(order.quantity),
        "clOrdId": order.client_order_id,
        "reduceOnly": "true" if order.reduce_only else "false"
    }


@dataclass
class OrderBook:
    """订单簿，管理订单状态"""
    
    def __init__(self):
        self._orders: dict[str, OrderResponse] = {}
        self._by_symbol: dict[str, list[str]] = {}
    
    def add(self, response: OrderResponse) -> None:
        self._orders[response.client_order_id] = response
        if response.symbol not in self._by_symbol:
            self._by_symbol[response.symbol] = []
        self._by_symbol[response.symbol].append(response.client_order_id)
    
    def update(self, client_order_id: str, response: OrderResponse) -> None:
        self._orders[client_order_id] = response
    
    def get(self, client_order_id: str) -> Optional[OrderResponse]:
        return self._orders.get(client_order_id)
    
    def get_by_symbol(self, symbol: str) -> list[OrderResponse]:
        order_ids = self._by_symbol.get(symbol, [])
        return [self._orders[oid] for oid in order_ids if oid in self._orders]
    
    def get_open_orders(self, symbol: Optional[str] = None) -> list[OrderResponse]:
        open_statuses = {OrderStatus.PENDING, OrderStatus.SUBMITTED, OrderStatus.PARTIAL_FILLED}
        if symbol:
            orders = self.get_by_symbol(symbol)
        else:
            orders = list(self._orders.values())
        return [o for o in orders if o.status in open_statuses]
    
    def remove(self, client_order_id: str) -> None:
        order = self._orders.pop(client_order_id, None)
        if order and order.symbol in self._by_symbol:
            if client_order_id in self._by_symbol[order.symbol]:
                self._by_symbol[order.symbol].remove(client_order_id)
    
    def clear(self) -> None:
        self._orders.clear()
        self._by_symbol.clear()
