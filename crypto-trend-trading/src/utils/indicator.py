"""技术指标计算"""

import numpy as np
from typing import List, Tuple
from dataclasses import dataclass


@dataclass
class IndicatorCalculator:
    """技术指标计算器"""
    
    ema_periods: List[int] = None
    rsi_period: int = 14
    atr_period: int = 14
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    
    def __post_init__(self):
        if self.ema_periods is None:
            self.ema_periods = [5, 20, 50]
        
        self._ema_cache: dict = {}
        self._rsi_cache: dict = {}
        self._atr_cache: dict = {}
        self._macd_cache: dict = {}
    
    def calculate_ema(self, prices: List[float], period: int) -> float:
        """
        计算指数移动平均线 (EMA)
        
        Formula: EMA_t = price_t * k + EMA_{t-1} * (1-k)
        where k = 2 / (period + 1)
        """
        if len(prices) < period:
            return sum(prices) / len(prices) if prices else 0.0
        
        k = 2 / (period + 1)
        ema = sum(prices[:period]) / period
        
        for price in prices[period:]:
            ema = price * k + ema * (1 - k)
        
        return ema
    
    def calculate_ema_series(self, prices: List[float], period: int) -> List[float]:
        """
        计算EMA序列
        """
        if len(prices) < period:
            return [sum(prices) / len(prices)] * len(prices)
        
        k = 2 / (period + 1)
        result = [sum(prices[:period]) / period]
        
        for i in range(period, len(prices)):
            ema = prices[i] * k + result[-1] * (1 - k)
            result.append(ema)
        
        return result
    
    def calculate_rsi(self, prices: List[float], period: int = None) -> float:
        """
        计算相对强弱指数 (RSI)
        
        Formula: RSI = 100 - 100 / (1 + RS)
        where RS = AvgGain / AvgLoss
        """
        period = period or self.rsi_period
        
        if len(prices) < period + 1:
            return 50.0
        
        gains = []
        losses = []
        
        for i in range(1, len(prices)):
            change = prices[i] - prices[i - 1]
            if change > 0:
                gains.append(change)
                losses.append(0)
            else:
                gains.append(0)
                losses.append(abs(change))
        
        if len(gains) < period:
            return 50.0
        
        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period
        
        if avg_loss == 0:
            return 100.0
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
    
    def calculate_atr(self, highs: List[float], lows: List[float], closes: List[float], period: int = None) -> float:
        """
        计算平均真实波幅 (ATR)
        
        True Range = max(H-L, |H-PC|, |L-PC|)
        where PC = Previous Close
        """
        period = period or self.atr_period
        
        if len(highs) < period + 1:
            return 0.0
        
        true_ranges = []
        for i in range(1, len(highs)):
            high_low = highs[i] - lows[i]
            high_pc = abs(highs[i] - closes[i - 1])
            low_pc = abs(lows[i] - closes[i - 1])
            true_ranges.append(max(high_low, high_pc, low_pc))
        
        if len(true_ranges) < period:
            return sum(true_ranges) / len(true_ranges) if true_ranges else 0.0
        
        atr = sum(true_ranges[-period:]) / period
        return atr
    
    def calculate_macd(
        self, 
        prices: List[float], 
        fast: int = None, 
        slow: int = None, 
        signal: int = None
    ) -> Tuple[float, float, float]:
        """
        计算MACD
        
        MACD Line = EMA(fast) - EMA(slow)
        Signal Line = EMA(MACD, signal)
        Histogram = MACD - Signal
        """
        fast = fast or self.macd_fast
        slow = slow or self.macd_slow
        signal = signal or self.macd_signal
        
        if len(prices) < slow:
            return 0.0, 0.0, 0.0
        
        ema_fast = self.calculate_ema(prices, fast)
        ema_slow = self.calculate_ema(prices, slow)
        macd_line = ema_fast - ema_slow
        
        macd_series = []
        for i in range(slow, len(prices)):
            ef = self.calculate_ema(prices[:i + 1], fast)
            es = self.calculate_ema(prices[:i + 1], slow)
            macd_series.append(ef - es)
        
        if len(macd_series) < signal:
            signal_line = macd_line
        else:
            signal_line = self.calculate_ema(macd_series, signal)
        
        histogram = macd_line - signal_line
        
        return macd_line, signal_line, histogram
    
    def calculate_all(
        self,
        highs: List[float],
        lows: List[float],
        closes: List[float]
    ) -> dict:
        """
        计算所有指标
        """
        ema5 = self.calculate_ema(closes, 5)
        ema20 = self.calculate_ema(closes, 20)
        ema50 = self.calculate_ema(closes, 50)
        
        ema_convergence = (ema5 - ema20) / ema50 if ema50 != 0 else 0.0
        
        rsi = self.calculate_rsi(closes)
        
        atr = self.calculate_atr(highs, lows, closes)
        atr_percent = (atr / closes[-1] * 100) if closes[-1] != 0 else 0.0
        
        macd, macd_signal, macd_histogram = self.calculate_macd(closes)
        
        trend_strength = min(abs(ema_convergence) * 10, 1.0) if abs(ema_convergence) < 0.1 else 1.0
        
        return {
            "ema5": ema5,
            "ema20": ema20,
            "ema50": ema50,
            "ema_convergence": ema_convergence,
            "rsi": rsi,
            "atr": atr,
            "atr_percent": atr_percent,
            "macd": macd,
            "macd_signal": macd_signal,
            "macd_histogram": macd_histogram,
            "trend_strength": trend_strength
        }


def calculate_confidence(
    ema_convergence: float,
    rsi: float,
    atr_percent: float,
    ema_weight: float = 0.4,
    rsi_weight: float = 0.3,
    atr_weight: float = 0.3
) -> float:
    """
    计算信号置信度
    
    Args:
        ema_convergence: EMA收敛度
        rsi: RSI值
        atr_percent: ATR百分比
        ema_weight: EMA权重
        rsi_weight: RSI权重
        atr_weight: ATR权重
        
    Returns:
        置信度 (0.0 - 1.0)
    """
    ema_score = min(abs(ema_convergence) / 0.01, 1.0)
    
    rsi_score = 1.0 - abs(rsi - 50) / 50
    
    atr_score = min(atr_percent / 5.0, 1.0) if atr_percent < 5.0 else 1.0
    
    confidence = ema_weight * ema_score + rsi_weight * rsi_score + atr_weight * atr_score
    
    return max(0.0, min(1.0, confidence))


def calculate_stop_loss_take_profit(
    entry_price: float,
    atr: float,
    direction: str,
    stop_multiplier: float = 2.0,
    tp_multiplier: float = 3.0
) -> Tuple[float, float]:
    """
    计算止损和止盈价格
    
    Args:
        entry_price: 入场价格
        atr: ATR值
        direction: 交易方向 ('buy' or 'sell')
        stop_multiplier: 止损ATR倍数
        tp_multiplier: 止盈ATR倍数
        
    Returns:
        (止损价格, 止盈价格)
    """
    if direction == "buy":
        stop_loss = entry_price - atr * stop_multiplier
        take_profit = entry_price + atr * tp_multiplier
    else:
        stop_loss = entry_price + atr * stop_multiplier
        take_profit = entry_price - atr * tp_multiplier
    
    return stop_loss, take_profit
