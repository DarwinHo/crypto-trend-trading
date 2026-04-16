"""监控指标采集"""

import asyncio
import psutil
import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime

from ..models import SystemMetrics
from ..utils import get_current_timestamp_ms

logger = logging.getLogger(__name__)


@dataclass
class MetricsCollector:
    """指标采集器"""
    
    _metrics: SystemMetrics = field(default_factory=SystemMetrics)
    _latencies: Dict[str, list] = field(default_factory=lambda: {
        "data_processing": [],
        "strategy_calculation": [],
        "order_submission": [],
        "end_to_end": []
    })
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    
    async def record_latency(self, category: str, latency_ms: float) -> None:
        """记录延迟"""
        async with self._lock:
            if category in self._latencies:
                self._latencies[category].append(latency_ms)
                
                if len(self._latencies[category]) > 100:
                    self._latencies[category].pop(0)
    
    async def record_data_processing(self, latency_ms: float) -> None:
        await self.record_latency("data_processing", latency_ms)
    
    async def record_strategy_calculation(self, latency_ms: float) -> None:
        await self.record_latency("strategy_calculation", latency_ms)
    
    async def record_order_submission(self, latency_ms: float) -> None:
        await self.record_latency("order_submission", latency_ms)
    
    async def record_end_to_end(self, latency_ms: float) -> None:
        await self.record_latency("end_to_end", latency_ms)
    
    def _calculate_p99(self, values: list) -> float:
        """计算P99"""
        if not values:
            return 0.0
        sorted_values = sorted(values)
        index = int(len(sorted_values) * 0.99)
        return sorted_values[min(index, len(sorted_values) - 1)]
    
    async def collect_system_metrics(self) -> SystemMetrics:
        """采集系统指标"""
        try:
            process = psutil.Process()
            
            cpu_percent = process.cpu_percent(interval=0.1)
            memory_info = process.memory_info()
            memory_mb = memory_info.rss / 1024 / 1024
            
            self._metrics.cpu_usage_percent = cpu_percent
            self._metrics.memory_usage_mb = memory_mb
            self._metrics.memory_usage_percent = (memory_mb / psutil.virtual_memory().total) * 100
            
            self._metrics.data_processing_latency_p99_ms = self._calculate_p99(self._latencies.get("data_processing", []))
            self._metrics.strategy_calculation_latency_p99_ms = self._calculate_p99(self._latencies.get("strategy_calculation", []))
            self._metrics.order_submission_latency_p99_ms = self._calculate_p99(self._latencies.get("order_submission", []))
            self._metrics.end_to_end_latency_p99_ms = self._calculate_p99(self._latencies.get("end_to_end", []))
            
        except Exception as e:
            logger.error(f"Failed to collect system metrics: {e}")
        
        return self._metrics
    
    def update_trading_metrics(
        self,
        total_positions: int = 0,
        open_orders_count: int = 0,
        daily_trade_count: int = 0,
        daily_trade_volume: float = 0.0,
        daily_pnl: float = 0.0,
        websocket_connected: bool = False,
        order_success_rate: float = 1.0,
        total_orders_today: int = 0,
        failed_orders_today: int = 0
    ) -> None:
        """更新交易指标"""
        self._metrics.total_positions = total_positions
        self._metrics.open_orders_count = open_orders_count
        self._metrics.daily_trade_count = daily_trade_count
        self._metrics.daily_trade_volume = daily_trade_volume
        self._metrics.daily_pnl = daily_pnl
        self._metrics.websocket_connected = websocket_connected
        self._metrics.order_success_rate = order_success_rate
        self._metrics.total_orders_today = total_orders_today
        self._metrics.failed_orders_today = failed_orders_today
    
    def get_metrics(self) -> SystemMetrics:
        """获取当前指标"""
        return self._metrics
