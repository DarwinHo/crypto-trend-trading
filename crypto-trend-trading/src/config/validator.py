"""配置验证器"""

from typing import Any, Callable, Dict, List
import re


class ConfigValidator:
    """配置验证器"""
    
    VALIDATORS: Dict[str, Callable[[Any], bool]] = {
        "exchange.api_key": lambda v: v is not None and len(str(v)) > 0,
        "exchange.secret_key": lambda v: v is not None and len(str(v)) > 0,
        "exchange.passphrase": lambda v: v is not None and len(str(v)) > 0,
        "exchange.testnet": lambda v: isinstance(v, bool),
        
        "symbols": lambda v: isinstance(v, list) and len(v) > 0,
        "symbols.*": lambda v: bool(re.match(r"^[A-Z]+-USDT$", str(v))),
        
        "strategy.min_confidence": lambda v: 0.0 <= float(v) <= 1.0,
        "strategy.ema_periods": lambda v: isinstance(v, list) and len(v) == 3,
        "strategy.rsi_period": lambda v: int(v) > 0,
        "strategy.atr_period": lambda v: int(v) > 0,
        "strategy.ema_convergence_threshold": lambda v: float(v) > 0,
        "strategy.trend_strength_threshold": lambda v: 0.0 <= float(v) <= 1.0,
        
        "risk.max_single_order_ratio": lambda v: 0.0 < float(v) <= 1.0,
        "risk.max_position_ratio": lambda v: 0.0 < float(v) <= 1.0,
        "risk.max_daily_trade_ratio": lambda v: float(v) > 0,
        "risk.max_positions": lambda v: int(v) > 0,
        "risk.max_concentration": lambda v: 0.0 < float(v) <= 1.0,
        "risk.warning_ratio": lambda v: 0.0 <= float(v) <= 1.0,
        "risk.auto_stop_ratio": lambda v: 0.0 <= float(v) <= 1.0,
        
        "execution.slippage": lambda v: 0.0 <= float(v) <= 0.01,
        "execution.timeout": lambda v: int(v) > 0,
        "execution.order_type": lambda v: v in ["market", "limit"],
        
        "backtest.initial_capital": lambda v: float(v) > 0,
        "backtest.commission_rate": lambda v: 0.0 <= float(v) <= 0.01,
        "backtest.slippage": lambda v: 0.0 <= float(v) <= 0.01,
        
        "monitoring.log_level": lambda v: v in ["DEBUG", "INFO", "WARN", "ERROR"],
        "monitoring.metrics_interval": lambda v: int(v) > 0,
        "monitoring.alert_enabled": lambda v: isinstance(v, bool),
        
        "storage.type": lambda v: v in ["sqlite", "memory"],
        "storage.backup_interval": lambda v: int(v) > 0,
    }
    
    def __init__(self):
        self._errors: List[str] = []
    
    def validate(self, config: dict, prefix: str = "") -> bool:
        """
        验证配置项
        
        Args:
            config: 配置字典
            prefix: 配置路径前缀
            
        Returns:
            是否通过验证
        """
        self._errors.clear()
        
        for key, value in config.items():
            full_key = f"{prefix}.{key}" if prefix else key
            
            if isinstance(value, dict):
                self.validate(value, full_key)
            elif full_key in self.VALIDATORS:
                validator = self.VALIDATORS[full_key]
                try:
                    if not validator(value):
                        self._errors.append(f"Validation failed for '{full_key}': {value}")
                except Exception as e:
                    self._errors.append(f"Error validating '{full_key}': {str(e)}")
            
            if key == "symbols" and isinstance(value, list):
                for i, symbol in enumerate(value):
                    symbol_key = f"{full_key}.*"
                    if symbol_key in self.VALIDATORS:
                        validator = self.VALIDATORS[symbol_key]
                        if not validator(symbol):
                            self._errors.append(f"Invalid symbol format: {symbol}")
        
        return len(self._errors) == 0
    
    def get_errors(self) -> List[str]:
        """获取验证错误列表"""
        return self._errors.copy()


class ConfigError(Exception):
    """配置错误异常"""
    pass
