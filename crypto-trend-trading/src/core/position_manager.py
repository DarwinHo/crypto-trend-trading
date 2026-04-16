"""仓位管理器

管理当前持仓状态，跟踪盈亏，持久化仓位数据。
"""

import asyncio
import logging
from typing import Optional, List, Dict
from dataclasses import dataclass

from ..config import Config
from ..models import (
    Position, PositionSide, Balance, PnLReport,
    PositionBook, DailyStats,
    create_position, calculate_unrealized_pnl
)
from ..utils import get_current_timestamp_ms, get_date_str

logger = logging.getLogger(__name__)


class PositionManager:
    """
    仓位管理器
    
    负责：
    - 持仓状态管理
    - 盈亏计算
    - 保证金管理
    - 状态持久化
    """
    
    def __init__(self, config: Config):
        self.config = config
        
        self._position_book = PositionBook()
        self._balance = 0.0
        self._daily_stats: Dict[str, DailyStats] = {}
        
        self._total_realized_pnl = 0.0
        self._total_trade_count = 0
        self._winning_trades = 0
        self._losing_trades = 0
    
    @property
    def balance(self) -> float:
        return self._balance
    
    @balance.setter
    def balance(self, value: float) -> None:
        self._balance = value
    
    def open_position(
        self,
        symbol: str,
        side: PositionSide,
        quantity: float,
        entry_price: float,
        leverage: float = 1.0
    ) -> Position:
        """
        开仓
        
        Args:
            symbol: 交易对
            side: 持仓方向
            quantity: 数量
            entry_price: 开仓价格
            leverage: 杠杆倍数
            
        Returns:
            持仓对象
        """
        position = create_position(
            symbol=symbol,
            side=side,
            quantity=quantity,
            entry_price=entry_price,
            leverage=leverage,
            current_price=entry_price
        )
        
        self._position_book.add(position)
        self._balance -= position.margin
        
        logger.info(f"Position opened: {symbol} {side.value} {quantity} @ {entry_price}")
        
        return position
    
    def close_position(
        self,
        symbol: str,
        exit_price: float,
        fee: float = 0.0
    ) -> Optional[float]:
        """
        平仓
        
        Args:
            symbol: 交易对
            exit_price: 平仓价格
            fee: 手续费
            
        Returns:
            已实现盈亏
        """
        position = self._position_book.get(symbol)
        
        if not position or position.quantity <= 0:
            logger.warning(f"No position to close: {symbol}")
            return None
        
        realized_pnl = self._calculate_realized_pnl(position, exit_price, fee)
        
        self._balance += position.margin + realized_pnl
        
        self._record_trade(realized_pnl)
        
        self._position_book.remove(symbol)
        
        logger.info(f"Position closed: {symbol} PnL={realized_pnl:.2f}")
        
        return realized_pnl
    
    def update_position_price(self, symbol: str, current_price: float) -> Optional[Position]:
        """
        更新持仓价格
        
        Args:
            symbol: 交易对
            current_price: 当前价格
            
        Returns:
            更新后的持仓
        """
        position = self._position_book.get(symbol)
        
        if not position:
            return None
        
        position.current_price = current_price
        position.mark_price = current_price
        position.unrealized_pnl = calculate_unrealized_pnl(position)
        position.updated_at = get_current_timestamp_ms()
        
        return position
    
    def update_all_positions_prices(self, prices: Dict[str, float]) -> None:
        """
        批量更新持仓价格
        
        Args:
            prices: symbol -> current_price
        """
        for symbol, price in prices.items():
            self.update_position_price(symbol, price)
    
    def get_position(self, symbol: str) -> Optional[Position]:
        """获取持仓"""
        return self._position_book.get(symbol)
    
    def get_all_positions(self) -> List[Position]:
        """获取所有持仓"""
        return self._position_book.get_all()
    
    def has_position(self, symbol: str) -> bool:
        """检查是否有持仓"""
        return self._position_book.has_position(symbol)
    
    def get_position_count(self) -> int:
        """获取持仓数量"""
        return len([p for p in self._position_book.get_all() if p.quantity > 0])
    
    def get_total_position_value(self) -> float:
        """获取总持仓价值"""
        return self._position_book.get_total_value()
    
    def get_total_unrealized_pnl(self) -> float:
        """获取总浮动盈亏"""
        return self._position_book.get_total_unrealized_pnl()
    
    def calculate_pnl(self) -> PnLReport:
        """
        计算盈亏报告
        
        Returns:
            PnL报告
        """
        positions = self._position_book.get_all()
        active_positions = [p for p in positions if p.quantity > 0]
        
        total_realized = self._total_realized_pnl
        total_unrealized = sum(p.unrealized_pnl for p in active_positions)
        
        winning = self._winning_trades
        losing = self._losing_trades
        total_trades = self._total_trade_count
        
        win_rate = winning / total_trades if total_trades > 0 else 0.0
        
        avg_win = total_realized / winning if winning > 0 else 0.0
        avg_loss = abs(total_realized) / losing if losing > 0 else 0.0
        
        profit_factor = avg_win / avg_loss if avg_loss > 0 else 0.0
        
        largest_position = max((p.quantity * p.current_price for p in active_positions), default=0.0)
        avg_position = sum(p.quantity * p.current_price for p in active_positions) / len(active_positions) if active_positions else 0.0
        
        return PnLReport(
            total_realized_pnl=total_realized,
            total_unrealized_pnl=total_unrealized,
            total_trade_count=total_trades,
            winning_trades=winning,
            losing_trades=losing,
            win_rate=win_rate,
            avg_win=avg_win,
            avg_loss=avg_loss,
            profit_factor=profit_factor,
            max_drawdown=0.0,
            max_drawdown_ratio=0.0,
            current_drawdown=0.0,
            current_drawdown_ratio=0.0,
            avg_holding_time_hours=0.0,
            largest_position=largest_position,
            avg_position=avg_position
        )
    
    def get_daily_stats(self, date: Optional[str] = None) -> DailyStats:
        """获取每日统计"""
        if date is None:
            date = get_date_str()
        
        if date not in self._daily_stats:
            self._daily_stats[date] = DailyStats(date=date)
        
        return self._daily_stats[date]
    
    def _record_trade(self, realized_pnl: float) -> None:
        """记录交易"""
        self._total_realized_pnl += realized_pnl
        self._total_trade_count += 1
        
        if realized_pnl > 0:
            self._winning_trades += 1
        elif realized_pnl < 0:
            self._losing_trades += 1
        
        today = get_date_str()
        daily = self.get_daily_stats(today)
        
        if hasattr(self, '_last_trade_volume'):
            daily.add_trade(self._last_trade_volume)
    
    def get_state(self) -> Dict:
        """获取状态用于持久化"""
        return {
            "balance": self._balance,
            "total_realized_pnl": self._total_realized_pnl,
            "total_trade_count": self._total_trade_count,
            "winning_trades": self._winning_trades,
            "losing_trades": self._losing_trades,
            "positions": {
                p.symbol: {
                    "id": p.id,
                    "symbol": p.symbol,
                    "side": p.side.value,
                    "quantity": p.quantity,
                    "entry_price": p.entry_price,
                    "current_price": p.current_price,
                    "leverage": p.leverage,
                    "margin": p.margin,
                    "opening_timestamp": p.opening_timestamp
                }
                for p in self._position_book.get_all()
                if p.quantity > 0
            }
        }
    
    def load_state(self, state: Dict) -> None:
        """加载状态"""
        self._balance = state.get("balance", 0.0)
        self._total_realized_pnl = state.get("total_realized_pnl", 0.0)
        self._total_trade_count = state.get("total_trade_count", 0)
        self._winning_trades = state.get("winning_trades", 0)
        self._losing_trades = state.get("losing_trades", 0)
        
        positions_data = state.get("positions", {})
        for symbol, data in positions_data.items():
            position = Position(
                id=data["id"],
                symbol=data["symbol"],
                side=PositionSide(data["side"]),
                quantity=data["quantity"],
                entry_price=data["entry_price"],
                current_price=data["current_price"],
                mark_price=data["current_price"],
                liquidation_price=0.0,
                leverage=data["leverage"],
                margin=data["margin"],
                unrealized_pnl=0.0,
                realized_pnl=0.0,
                opening_timestamp=data["opening_timestamp"],
                updated_at=get_current_timestamp_ms()
            )
            self._position_book.add(position)
        
        logger.info(f"State loaded: {len(positions_data)} positions")
    
    def clear(self) -> None:
        """清除所有数据"""
        self._position_book.clear()
        self._daily_stats.clear()
        self._total_realized_pnl = 0.0
        self._total_trade_count = 0
        self._winning_trades = 0
        self._losing_trades = 0
