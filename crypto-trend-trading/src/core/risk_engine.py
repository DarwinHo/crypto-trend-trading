"""风控引擎

实时监控交易活动的风险指标，执行风控规则。
"""

import logging
from typing import Optional, List, Dict
from dataclasses import dataclass, field
from datetime import datetime

from ..config import Config
from ..models import (
    TrendSignal, Position, Balance, CheckResult, RiskMetrics, PortfolioRisk,
    SignalDirection, OrderSide, PositionSide
)

logger = logging.getLogger(__name__)


@dataclass
class RiskLimits:
    """风控限额配置"""
    max_single_order_ratio: float = 0.10
    max_position_ratio: float = 0.20
    max_daily_trade_ratio: float = 2.0
    max_positions: int = 5
    max_concentration: float = 0.30
    warning_ratio: float = 0.05
    auto_stop_ratio: float = 0.10
    max_drawdown_limit: float = 0.20


@dataclass
class DailyStats:
    """每日交易统计"""
    date: str
    total_volume: float = 0.0
    trade_count: int = 0
    
    def add_trade(self, volume: float) -> None:
        self.total_volume += volume
        self.trade_count += 1


class RiskEngine:
    """
    风控引擎
    
    负责：
    - 订单风控前置检查
    - 持仓风险监控
    - 动态风控限额调整
    - 紧急止损触发
    """
    
    def __init__(self, config: Config):
        self.config = config
        self.risk_config = config.risk
        
        self._limits = RiskLimits(
            max_single_order_ratio=self.risk_config.order.max_single_order_ratio,
            max_position_ratio=self.risk_config.order.max_position_ratio,
            max_daily_trade_ratio=self.risk_config.order.max_daily_trade_ratio,
            max_positions=self.risk_config.order.max_positions,
            max_concentration=self.risk_config.order.max_concentration,
            warning_ratio=self.risk_config.stop_loss.warning_ratio,
            auto_stop_ratio=self.risk_config.stop_loss.auto_stop_ratio,
            max_drawdown_limit=self.risk_config.emergency.max_drawdown_limit
        )
        
        self._balance: float = 0.0
        self._positions: Dict[str, Position] = {}
        self._daily_stats = DailyStats(date=datetime.now().strftime("%Y-%m-%d"))
        self._strategy_paused = False
        self._last_warning_time = 0
    
    def check_order(self, signal: TrendSignal, balance: float) -> CheckResult:
        """
        订单风控前置检查 (< 1ms)
        
        检查规则顺序:
        R001 -> R002 -> R003 -> R004 -> R005
        """
        self._balance = balance
        
        order_amount = signal.entry_price * self._calculate_order_size(signal)
        
        metrics = RiskMetrics(
            order_amount=order_amount,
            position_value=self._get_total_position_value(),
            daily_trade_value=self._daily_stats.total_volume,
            position_count=len([p for p in self._positions.values() if p.quantity > 0]),
            unrealized_pnl_ratio=self._get_unrealized_pnl_ratio()
        )
        
        if order_amount > balance * self._limits.max_single_order_ratio:
            return self._reject("R001", "单笔金额超限", metrics)
        
        new_position_value = self._get_total_position_value() + order_amount
        if new_position_value > balance * self._limits.max_position_ratio:
            return self._reject("R002", "持仓金额超限", metrics)
        
        new_daily_volume = self._daily_stats.total_volume + order_amount
        if new_daily_volume > balance * self._limits.max_daily_trade_ratio:
            return self._reject("R003", "日交易额超限", metrics)
        
        if signal.direction != SignalDirection.NEUTRAL:
            active_positions = len([p for p in self._positions.values() if p.quantity > 0])
            if active_positions >= self._limits.max_positions:
                return self._reject("R004", "持仓数量超限", metrics)
        
        symbol_value = self._get_position_value(signal.symbol) + order_amount
        concentration = symbol_value / balance if balance > 0 else 0
        if concentration > self._limits.max_concentration:
            return self._reject("R005", "品种集中度超限", metrics)
        
        logger.info(f"Risk check passed for {signal.symbol} {signal.direction.value}")
        
        return CheckResult(
            passed=True,
            rejected_by=None,
            rejected_reason=None,
            risk_metrics=metrics
        )
    
    def check_portfolio(self) -> PortfolioRisk:
        """组合风险检查"""
        total_exposure = self._get_total_unrealized_pnl()
        margin_used = sum(p.margin for p in self._positions.values() if p.quantity > 0)
        margin_available = self._balance - margin_used
        margin_ratio = margin_used / self._balance if self._balance > 0 else 0
        
        long_exposure = sum(
            p.unrealized_pnl for p in self._positions.values() 
            if p.quantity > 0 and p.side == PositionSide.LONG
        )
        short_exposure = sum(
            p.unrealized_pnl for p in self._positions.values() 
            if p.quantity > 0 and p.side == PositionSide.SHORT
        )
        net_exposure = long_exposure - short_exposure
        
        risk_level = self._evaluate_risk_level(margin_ratio, self._get_unrealized_pnl_ratio())
        
        return PortfolioRisk(
            total_exposure=total_exposure,
            net_exposure=net_exposure,
            margin_used=margin_used,
            margin_available=margin_available,
            margin_ratio=margin_ratio,
            risk_level=risk_level
        )
    
    def check_stop_loss(self, position: Position) -> Optional[str]:
        """
        检查是否触发止损
        
        Returns:
            触发原因，如果有的话
        """
        if position.quantity <= 0:
            return None
        
        pnl_ratio = abs(position.unrealized_pnl) / position.margin if position.margin > 0 else 0
        
        if position.unrealized_pnl < 0 and pnl_ratio >= self._limits.auto_stop_ratio:
            return f"Auto stop loss triggered: loss ratio={pnl_ratio:.2%}"
        
        if position.unrealized_pnl < 0 and pnl_ratio >= self._limits.warning_ratio:
            return f"Warning: loss ratio={pnl_ratio:.2%}"
        
        return None
    
    def update_limits(self, new_limits: RiskLimits) -> None:
        """更新风控限额"""
        old_limits = self._limits
        self._limits = new_limits
        logger.info(f"Risk limits updated: {old_limits} -> {new_limits}")
    
    def get_limits(self) -> RiskLimits:
        """获取当前风控限额"""
        return self._limits
    
    def update_balance(self, balance: float) -> None:
        """更新账户余额"""
        self._balance = balance
    
    def update_position(self, position: Position) -> None:
        """更新持仓"""
        self._positions[position.symbol] = position
    
    def remove_position(self, symbol: str) -> None:
        """移除持仓"""
        if symbol in self._positions:
            del self._positions[symbol]
    
    def get_position(self, symbol: str) -> Optional[Position]:
        """获取持仓"""
        return self._positions.get(symbol)
    
    def get_all_positions(self) -> List[Position]:
        """获取所有持仓"""
        return [p for p in self._positions.values() if p.quantity > 0]
    
    def record_trade(self, volume: float) -> None:
        """记录交易"""
        today = datetime.now().strftime("%Y-%m-%d")
        if self._daily_stats.date != today:
            self._daily_stats = DailyStats(date=today)
        self._daily_stats.add_trade(volume)
    
    def pause_strategy(self, reason: str) -> None:
        """暂停策略"""
        self._strategy_paused = True
        logger.warning(f"Strategy paused: {reason}")
    
    def resume_strategy(self) -> None:
        """恢复策略"""
        self._strategy_paused = False
        logger.info("Strategy resumed")
    
    @property
    def is_strategy_paused(self) -> bool:
        return self._strategy_paused
    
    def _calculate_order_size(self, signal: TrendSignal) -> float:
        """计算订单数量"""
        max_order_value = self._balance * self._limits.max_single_order_ratio
        return max_order_value / signal.entry_price
    
    def _get_total_position_value(self) -> float:
        """获取总持仓价值"""
        return sum(
            p.quantity * p.current_price 
            for p in self._positions.values() 
            if p.quantity > 0
        )
    
    def _get_position_value(self, symbol: str) -> float:
        """获取指定品种持仓价值"""
        position = self._positions.get(symbol)
        if position and position.quantity > 0:
            return position.quantity * position.current_price
        return 0.0
    
    def _get_total_unrealized_pnl(self) -> float:
        """获取总浮动盈亏"""
        return sum(
            p.unrealized_pnl for p in self._positions.values() 
            if p.quantity > 0
        )
    
    def _get_unrealized_pnl_ratio(self) -> float:
        """获取浮动盈亏比例"""
        if self._balance == 0:
            return 0.0
        return abs(self._get_total_unrealized_pnl()) / self._balance
    
    def _evaluate_risk_level(self, margin_ratio: float, pnl_ratio: float) -> str:
        """评估风险等级"""
        if margin_ratio > 0.8 or pnl_ratio > 0.1:
            return "HIGH"
        elif margin_ratio > 0.5 or pnl_ratio > 0.05:
            return "MEDIUM"
        else:
            return "LOW"
    
    def _reject(self, rule_id: str, reason: str, metrics: RiskMetrics) -> CheckResult:
        """返回拒绝结果"""
        logger.warning(f"Risk rejected: {rule_id} - {reason}")
        return CheckResult(
            passed=False,
            rejected_by=rule_id,
            rejected_reason=reason,
            risk_metrics=metrics
        )
