"""持仓相关模型"""

from dataclasses import dataclass, field
from typing import Optional
from enum import Enum
import uuid
import time

from .types import Position, PositionSide, Balance


def calculate_unrealized_pnl(position: Position) -> float:
    """计算浮动盈亏"""
    if position.side == PositionSide.LONG:
        return (position.current_price - position.entry_price) * position.quantity
    else:
        return (position.entry_price - position.current_price) * position.quantity


def calculate_realized_pnl(
    entry_price: float,
    exit_price: float,
    quantity: float,
    side: PositionSide,
    fee: float
) -> float:
    """计算已实现盈亏"""
    if side == PositionSide.LONG:
        gross_pnl = (exit_price - entry_price) * quantity
    else:
        gross_pnl = (entry_price - exit_price) * quantity
    return gross_pnl - fee


def create_position(
    symbol: str,
    side: PositionSide,
    quantity: float,
    entry_price: float,
    leverage: float = 1.0,
    current_price: float = 0.0
) -> Position:
    """创建持仓"""
    margin = (entry_price * quantity) / leverage
    return Position(
        id=str(uuid.uuid4()),
        symbol=symbol,
        side=side,
        quantity=quantity,
        entry_price=entry_price,
        current_price=current_price or entry_price,
        mark_price=current_price or entry_price,
        liquidation_price=0.0,
        leverage=leverage,
        margin=margin,
        unrealized_pnl=0.0,
        realized_pnl=0.0,
        opening_timestamp=int(time.time() * 1000),
        updated_at=int(time.time() * 1000)
    )


@dataclass
class PositionBook:
    """持仓簿，管理所有持仓"""
    
    def __init__(self):
        self._positions: dict[str, Position] = {}
    
    def add(self, position: Position) -> None:
        self._positions[position.symbol] = position
    
    def update(
        self,
        symbol: str,
        quantity: float,
        current_price: float,
        realized_pnl: float = 0.0
    ) -> Optional[Position]:
        """更新持仓"""
        position = self._positions.get(symbol)
        if not position:
            return None
        
        position.quantity = quantity
        position.current_price = current_price
        position.mark_price = current_price
        position.unrealized_pnl = calculate_unrealized_pnl(position)
        position.realized_pnl += realized_pnl
        position.updated_at = int(time.time() * 1000)
        
        return position
    
    def get(self, symbol: str) -> Optional[Position]:
        return self._positions.get(symbol)
    
    def get_all(self) -> list[Position]:
        return list(self._positions.values())
    
    def remove(self, symbol: str) -> Optional[Position]:
        return self._positions.pop(symbol, None)
    
    def get_total_value(self) -> float:
        """获取总持仓价值"""
        return sum(p.quantity * p.current_price for p in self._positions.values())
    
    def get_total_unrealized_pnl(self) -> float:
        """获取总浮动盈亏"""
        return sum(p.unrealized_pnl for p in self._positions.values())
    
    def get_total_margin(self) -> float:
        """获取总保证金"""
        return sum(p.margin for p in self._positions.values())
    
    def get_long_value(self) -> float:
        """获取多头总价值"""
        return sum(
            p.quantity * p.current_price 
            for p in self._positions.values() 
            if p.side == PositionSide.LONG
        )
    
    def get_short_value(self) -> float:
        """获取空头总价值"""
        return sum(
            p.quantity * p.current_price 
            for p in self._positions.values() 
            if p.side == PositionSide.SHORT
        )
    
    def has_position(self, symbol: str) -> bool:
        """检查是否有持仓"""
        position = self._positions.get(symbol)
        return position is not None and position.quantity > 0
    
    def clear(self) -> None:
        self._positions.clear()


@dataclass
class DailyStats:
    """每日交易统计"""
    
    date: str
    total_volume: float = 0.0
    trade_count: int = 0
    realized_pnl: float = 0.0
    
    def add_trade(self, volume: float, pnl: float = 0.0) -> None:
        self.total_volume += volume
        self.trade_count += 1
        if pnl != 0.0:
            self.realized_pnl += pnl
    
    def to_dict(self) -> dict:
        return {
            "date": self.date,
            "total_volume": self.total_volume,
            "trade_count": self.trade_count,
            "realized_pnl": self.realized_pnl
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'DailyStats':
        return cls(
            date=data["date"],
            total_volume=data.get("total_volume", 0.0),
            trade_count=data.get("trade_count", 0),
            realized_pnl=data.get("realized_pnl", 0.0)
        )
