"""策略引擎

执行趋势跟踪策略逻辑，计算技术指标并生成交易信号。
"""

import uuid
import logging
from typing import Optional, List, Dict
from dataclasses import dataclass, field

from ..config import Config
from ..models import (
    KLine, Ticker, TrendSignal, SignalDirection, IndicatorSet,
    KLineCache, IndicatorCalculator, calculate_confidence, calculate_stop_loss_take_profit
)
from ..utils import get_current_timestamp_ms, get_current_timestamp_s

logger = logging.getLogger(__name__)


@dataclass
class StrategyState:
    """策略状态"""
    symbol: str
    last_signal: Optional[TrendSignal] = None
    signal_cooldown: bool = False
    cooldown_until: int = 0


class StrategyEngine:
    """
    策略引擎
    
    负责：
    - 计算技术指标
    - 生成交易信号
    - 管理信号冷却期
    """
    
    def __init__(self, config: Config):
        self.config = config
        self.strategy_config = config.strategy
        
        self.indicator_config = self.strategy_config.indicators
        self.entry_config = self.strategy_config.entry
        self.exit_config = self.strategy_config.exit
        
        self.calculator = IndicatorCalculator(
            ema_periods=self.indicator_config.ema_periods,
            rsi_period=self.indicator_config.rsi_period,
            atr_period=self.indicator_config.atr_period,
            macd_fast=self.indicator_config.macd_fast,
            macd_slow=self.indicator_config.macd_slow,
            macd_signal=self.indicator_config.macd_signal
        )
        
        self._kline_cache = KLineCache(max_klines=100)
        self._state: Dict[str, StrategyState] = {}
        self._signal_validity_seconds = 300
    
    async def process_kline(self, kline: KLine) -> Optional[TrendSignal]:
        """
        处理K线数据并生成信号
        
        Args:
            kline: K线数据
            
        Returns:
            交易信号，如果没有信号则返回None
        """
        symbol = kline.symbol
        
        self._kline_cache.add(symbol, "1m", kline)
        
        klines = self._kline_cache.get_all(symbol, "1m")
        if len(klines) < 50:
            return None
        
        highs = [k.high for k in klines]
        lows = [k.low for k in klines]
        closes = [k.close for k in klines]
        
        indicators = self._calculate_indicators(highs, lows, closes)
        
        signal = self._generate_signal(symbol, kline.close, indicators)
        
        return signal
    
    def _calculate_indicators(self, highs: List[float], lows: List[float], closes: List[float]) -> IndicatorSet:
        """计算技术指标"""
        result = self.calculator.calculate_all(highs, lows, closes)
        
        return IndicatorSet(
            ema5=result["ema5"],
            ema20=result["ema20"],
            ema50=result["ema50"],
            ema_convergence=result["ema_convergence"],
            rsi=result["rsi"],
            atr=result["atr"],
            atr_percent=result["atr_percent"],
            macd=result["macd"],
            macd_signal=result["macd_signal"],
            macd_histogram=result["macd_histogram"],
            trend_strength=result["trend_strength"]
        )
    
    def _generate_signal(
        self,
        symbol: str,
        current_price: float,
        indicators: IndicatorSet
    ) -> Optional[TrendSignal]:
        """
        生成交易信号
        
        买入条件:
        1. EMA5 > EMA20 > EMA50 (上升趋势)
        2. EMA收敛度 > 阈值
        3. RSI < 70 (非超买)
        4. 置信度 >= 最低阈值
        
        卖出条件:
        1. EMA5 < EMA20 < EMA50 (下降趋势)
        2. EMA收敛度 < -阈值
        3. RSI > 30 (非超卖)
        4. 置信度 >= 最低阈值
        """
        if symbol not in self._state:
            self._state[symbol] = StrategyState(symbol=symbol)
        
        state = self._state[symbol]
        
        current_time = get_current_timestamp_ms()
        if state.signal_cooldown and current_time < state.cooldown_until:
            return None
        
        confidence = calculate_confidence(
            indicators.ema_convergence,
            indicators.rsi,
            indicators.atr_percent
        )
        
        if confidence < self.entry_config.min_confidence:
            return None
        
        direction = SignalDirection.NEUTRAL
        reason = ""
        
        if self._is_uptrend(indicators):
            direction = SignalDirection.BUY
            reason = f"BUY: EMA bullish crossover, RSI={indicators.rsi:.1f}, confidence={confidence:.2f}"
        elif self._is_downtrend(indicators):
            direction = SignalDirection.SELL
            reason = f"SELL: EMA bearish crossover, RSI={indicators.rsi:.1f}, confidence={confidence:.2f}"
        else:
            state.last_signal = None
            return None
        
        stop_loss, take_profit = calculate_stop_loss_take_profit(
            entry_price=current_price,
            atr=indicators.atr,
            direction=direction.value,
            stop_multiplier=self.exit_config.stop_loss_atr_multiplier,
            tp_multiplier=self.exit_config.take_profit_atr_multiplier
        )
        
        signal = TrendSignal(
            id=str(uuid.uuid4()),
            symbol=symbol,
            direction=direction,
            entry_price=current_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            confidence=confidence,
            indicators=indicators,
            reason=reason,
            timestamp=current_time,
            expires_at=current_time + self._signal_validity_seconds * 1000
        )
        
        state.last_signal = signal
        state.signal_cooldown = True
        state.cooldown_until = current_time + self._signal_validity_seconds * 1000
        
        logger.info(f"Signal generated: {reason}")
        
        return signal
    
    def _is_uptrend(self, indicators: IndicatorSet) -> bool:
        """判断是否处于上升趋势"""
        return (
            indicators.ema5 > indicators.ema20 > indicators.ema50 and
            indicators.ema_convergence > self.entry_config.ema_convergence_threshold and
            indicators.rsi < 70 and
            indicators.trend_strength > self.entry_config.trend_strength_threshold
        )
    
    def _is_downtrend(self, indicators: IndicatorSet) -> bool:
        """判断是否处于下降趋势"""
        return (
            indicators.ema5 < indicators.ema20 < indicators.ema50 and
            indicators.ema_convergence < -self.entry_config.ema_convergence_threshold and
            indicators.rsi > 30 and
            indicators.trend_strength > self.entry_config.trend_strength_threshold
        )
    
    def get_last_signal(self, symbol: str) -> Optional[TrendSignal]:
        """获取最近一次信号"""
        state = self._state.get(symbol)
        if state:
            return state.last_signal
        return None
    
    def clear_signal_cooldown(self, symbol: str) -> None:
        """清除信号冷却期"""
        if symbol in self._state:
            self._state[symbol].signal_cooldown = False
    
    def get_state(self, symbol: str) -> Optional[StrategyState]:
        """获取策略状态"""
        return self._state.get(symbol)
