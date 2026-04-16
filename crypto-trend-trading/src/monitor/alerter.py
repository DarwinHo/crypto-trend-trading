"""告警管理"""

import asyncio
import logging
from typing import Callable, List, Dict, Any
from dataclasses import dataclass, field

from ..models import AlertLevel, AlertEvent, SystemMetrics
from ..utils import get_current_timestamp_ms

logger = logging.getLogger(__name__)


@dataclass
class AlertRule:
    """告警规则"""
    name: str
    message: str
    condition: Callable[[SystemMetrics], bool]
    level: AlertLevel


class Alerter:
    """告警管理器"""
    
    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self._rules: List[AlertRule] = []
        self._last_alert_time: Dict[str, int] = {}
        self._alert_cooldown_ms: int = 60000
    
    def add_rule(self, rule: AlertRule) -> None:
        """添加告警规则"""
        self._rules.append(rule)
    
    def remove_rule(self, name: str) -> None:
        """移除告警规则"""
        self._rules = [r for r in self._rules if r.name != name]
    
    async def check_and_alert(
        self,
        metrics: SystemMetrics,
        callback: Callable[[AlertEvent], None] = None
    ) -> List[AlertEvent]:
        """
        检查指标并发送告警
        
        Args:
            metrics: 系统指标
            callback: 告警回调函数
            
        Returns:
            触发的告警列表
        """
        if not self.enabled:
            return []
        
        alerts = []
        current_time = get_current_timestamp_ms()
        
        for rule in self._rules:
            if rule.name in self._last_alert_time:
                elapsed = current_time - self._last_alert_time[rule.name]
                if elapsed < self._alert_cooldown_ms:
                    continue
            
            try:
                if rule.condition(metrics):
                    alert = AlertEvent(
                        level=rule.level,
                        source="alerter",
                        message=rule.message,
                        details={"rule": rule.name, "metrics": self._metrics_to_dict(metrics)},
                        timestamp=current_time
                    )
                    
                    alerts.append(alert)
                    self._last_alert_time[rule.name] = current_time
                    
                    if callback:
                        await callback(alert)
                    
                    self._log_alert(alert)
                    
            except Exception as e:
                logger.error(f"Alert rule check failed: {rule.name} - {e}")
        
        return alerts
    
    def _log_alert(self, alert: AlertEvent) -> None:
        """记录告警"""
        log_level = {
            AlertLevel.INFO: logger.info,
            AlertLevel.WARN: logger.warning,
            AlertLevel.ERROR: logger.error,
            AlertLevel.FATAL: logger.critical
        }.get(alert.level, logger.info)
        
        log_level(f"[{alert.level.value.upper()}] {alert.message} - {alert.details}")
    
    def _metrics_to_dict(self, metrics: SystemMetrics) -> Dict[str, Any]:
        """转换指标为字典"""
        return {
            "cpu_usage_percent": metrics.cpu_usage_percent,
            "memory_usage_percent": metrics.memory_usage_percent,
            "websocket_connected": metrics.websocket_connected,
            "order_success_rate": metrics.order_success_rate,
            "daily_pnl": metrics.daily_pnl,
            "end_to_end_latency_p99_ms": metrics.end_to_end_latency_p99_ms
        }
    
    def set_cooldown(self, cooldown_ms: int) -> None:
        """设置告警冷却时间"""
        self._alert_cooldown_ms = cooldown_ms


def create_default_alerter() -> Alerter:
    """创建默认告警器"""
    alerter = Alerter(enabled=True)
    
    alerter.add_rule(AlertRule(
        "high_cpu",
        "CPU使用率过高",
        lambda m: m.cpu_usage_percent > 70
    ))
    
    alerter.add_rule(AlertRule(
        "high_memory",
        "内存使用率过高",
        lambda m: m.memory_usage_percent > 75
    ))
    
    alerter.add_rule(AlertRule(
        "ws_disconnected",
        "WebSocket连接断开",
        lambda m: not m.websocket_connected
    ))
    
    alerter.add_rule(AlertRule(
        "low_order_success_rate",
        "订单成功率过低",
        lambda m: m.order_success_rate < 0.97
    ))
    
    alerter.add_rule(AlertRule(
        "high_latency",
        "延迟过高",
        lambda m: m.end_to_end_latency_p99_ms > 50
    ))
    
    alerter.add_rule(AlertRule(
        "high_daily_loss",
        "日亏损过大",
        lambda m: m.daily_pnl < -0.05
    ))
    
    return alerter
