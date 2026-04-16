"""配置管理"""

import os
import yaml
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from pathlib import Path

from .validator import ConfigValidator, ConfigError


REQUIRED_ENV_VARS = ["OKX_API_KEY", "OKX_SECRET_KEY", "OKX_PASSPHRASE"]


@dataclass
class ExchangeConfig:
    api_key: str = ""
    secret_key: str = ""
    passphrase: str = ""
    testnet: bool = False
    rate_limit_requests_per_second: int = 10
    rate_limit_burst: int = 20


@dataclass
class StrategyIndicatorsConfig:
    ema_periods: List[int] = field(default_factory=lambda: [5, 20, 50])
    rsi_period: int = 14
    atr_period: int = 14
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9


@dataclass
class StrategyEntryConfig:
    min_confidence: float = 0.65
    ema_convergence_threshold: float = 0.002
    trend_strength_threshold: float = 0.6


@dataclass
class StrategyExitConfig:
    stop_loss_atr_multiplier: float = 2.0
    take_profit_atr_multiplier: float = 3.0
    trailing_stop_enabled: bool = False
    trailing_stop_atr_multiplier: float = 1.5


@dataclass
class StrategyConfig:
    indicators: StrategyIndicatorsConfig = field(default_factory=StrategyIndicatorsConfig)
    entry: StrategyEntryConfig = field(default_factory=StrategyEntryConfig)
    exit: StrategyExitConfig = field(default_factory=StrategyExitConfig)


@dataclass
class RiskOrderConfig:
    max_single_order_ratio: float = 0.1
    max_position_ratio: float = 0.2
    max_daily_trade_ratio: float = 2.0
    max_positions: int = 5
    max_concentration: float = 0.3


@dataclass
class RiskStopLossConfig:
    warning_ratio: float = 0.05
    auto_stop_ratio: float = 0.10


@dataclass
class RiskEmergencyConfig:
    max_drawdown_limit: float = 0.20
    circuit_breaker_trades: int = 10
    circuit_breaker_period: int = 300


@dataclass
class RiskConfig:
    order: RiskOrderConfig = field(default_factory=RiskOrderConfig)
    stop_loss: RiskStopLossConfig = field(default_factory=RiskStopLossConfig)
    emergency: RiskEmergencyConfig = field(default_factory=RiskEmergencyConfig)


@dataclass
class ExecutionConfig:
    slippage: float = 0.0005
    timeout: int = 30
    retry_max_attempts: int = 3
    retry_initial_delay: float = 1.0
    order_type: str = "market"


@dataclass
class BacktestConfig:
    initial_capital: float = 100000.0
    commission_rate: float = 0.0005
    slippage: float = 0.0005
    benchmark: str = "BTC-USDT"


@dataclass
class MonitoringConfig:
    log_level: str = "INFO"
    metrics_interval: int = 1
    alert_enabled: bool = True


@dataclass
class StorageConfig:
    type: str = "sqlite"
    path: str = "./data/trading.db"
    backup_interval: int = 300


@dataclass
class Config:
    exchange: ExchangeConfig = field(default_factory=ExchangeConfig)
    symbols: List[str] = field(default_factory=lambda: ["BTC-USDT", "ETH-USDT"])
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    backtest: BacktestConfig = field(default_factory=BacktestConfig)
    monitoring: MonitoringConfig = field(default_factory=MonitoringConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)


class Settings:
    """配置管理器"""
    
    def __init__(self, config_path: Optional[str] = None):
        self._config_path = config_path or self._get_default_config_path()
        self._raw_config: Dict[str, Any] = {}
        self._config: Optional[Config] = None
        self._validator = ConfigValidator()
    
    def _get_default_config_path(self) -> str:
        """获取默认配置文件路径"""
        return os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "config",
            "config.yaml"
        )
    
    def load(self) -> Config:
        """加载配置"""
        if not os.path.exists(self._config_path):
            raise ConfigError(f"Config file not found: {self._config_path}")
        
        with open(self._config_path, "r") as f:
            self._raw_config = yaml.safe_load(f)
        
        self._load_env_vars()
        
        if not self._validator.validate(self._raw_config):
            errors = self._validator.get_errors()
            raise ConfigError(f"Config validation failed:\n" + "\n".join(errors))
        
        self._config = self._parse_config()
        return self._config
    
    def _load_env_vars(self) -> None:
        """从环境变量加载敏感配置"""
        for var_name in REQUIRED_ENV_VARS:
            value = os.environ.get(var_name)
            if value:
                key = var_name.lower().replace("okx_", "")
                if "exchange" not in self._raw_config:
                    self._raw_config["exchange"] = {}
                self._raw_config["exchange"][key] = value
        
        for var_name in REQUIRED_ENV_VARS:
            if not os.environ.get(var_name):
                raise ConfigError(f"Missing required environment variable: {var_name}")
    
    def _parse_config(self) -> Config:
        """解析配置为Config对象"""
        raw = self._raw_config
        
        exchange = ExchangeConfig(
            api_key=raw.get("exchange", {}).get("api_key", ""),
            secret_key=raw.get("exchange", {}).get("secret_key", ""),
            passphrase=raw.get("exchange", {}).get("passphrase", ""),
            testnet=raw.get("exchange", {}).get("testnet", False),
            rate_limit_requests_per_second=raw.get("exchange", {}).get("rate_limit", {}).get("requests_per_second", 10),
            rate_limit_burst=raw.get("exchange", {}).get("rate_limit", {}).get("burst", 20),
        )
        
        symbols = raw.get("symbols", ["BTC-USDT"])
        
        strat_raw = raw.get("strategy", {})
        strategy = StrategyConfig(
            indicators=StrategyIndicatorsConfig(
                ema_periods=strat_raw.get("indicators", {}).get("ema_periods", [5, 20, 50]),
                rsi_period=strat_raw.get("indicators", {}).get("rsi_period", 14),
                atr_period=strat_raw.get("indicators", {}).get("atr_period", 14),
                macd_fast=strat_raw.get("indicators", {}).get("macd_fast", 12),
                macd_slow=strat_raw.get("indicators", {}).get("macd_slow", 26),
                macd_signal=strat_raw.get("indicators", {}).get("macd_signal", 9),
            ),
            entry=StrategyEntryConfig(
                min_confidence=strat_raw.get("entry", {}).get("min_confidence", 0.65),
                ema_convergence_threshold=strat_raw.get("entry", {}).get("ema_convergence_threshold", 0.002),
                trend_strength_threshold=strat_raw.get("entry", {}).get("trend_strength_threshold", 0.6),
            ),
            exit=StrategyExitConfig(
                stop_loss_atr_multiplier=strat_raw.get("exit", {}).get("stop_loss_atr_multiplier", 2.0),
                take_profit_atr_multiplier=strat_raw.get("exit", {}).get("take_profit_atr_multiplier", 3.0),
                trailing_stop_enabled=strat_raw.get("exit", {}).get("trailing_stop_enabled", False),
                trailing_stop_atr_multiplier=strat_raw.get("exit", {}).get("trailing_stop_atr_multiplier", 1.5),
            )
        )
        
        risk_raw = raw.get("risk", {})
        risk = RiskConfig(
            order=RiskOrderConfig(
                max_single_order_ratio=risk_raw.get("order", {}).get("max_single_order_ratio", 0.1),
                max_position_ratio=risk_raw.get("order", {}).get("max_position_ratio", 0.2),
                max_daily_trade_ratio=risk_raw.get("order", {}).get("max_daily_trade_ratio", 2.0),
                max_positions=risk_raw.get("order", {}).get("max_positions", 5),
                max_concentration=risk_raw.get("order", {}).get("max_concentration", 0.3),
            ),
            stop_loss=RiskStopLossConfig(
                warning_ratio=risk_raw.get("stop_loss", {}).get("warning_ratio", 0.05),
                auto_stop_ratio=risk_raw.get("stop_loss", {}).get("auto_stop_ratio", 0.10),
            ),
            emergency=RiskEmergencyConfig(
                max_drawdown_limit=risk_raw.get("emergency", {}).get("max_drawdown_limit", 0.20),
                circuit_breaker_trades=risk_raw.get("emergency", {}).get("circuit_breaker_trades", 10),
                circuit_breaker_period=risk_raw.get("emergency", {}).get("circuit_breaker_period", 300),
            )
        )
        
        exec_raw = raw.get("execution", {})
        execution = ExecutionConfig(
            slippage=exec_raw.get("slippage", 0.0005),
            timeout=exec_raw.get("timeout", 30),
            retry_max_attempts=exec_raw.get("retry", {}).get("max_attempts", 3),
            retry_initial_delay=exec_raw.get("retry", {}).get("initial_delay", 1.0),
            order_type=exec_raw.get("order_type", "market"),
        )
        
        bt_raw = raw.get("backtest", {})
        backtest = BacktestConfig(
            initial_capital=bt_raw.get("initial_capital", 100000.0),
            commission_rate=bt_raw.get("commission_rate", 0.0005),
            slippage=bt_raw.get("slippage", 0.0005),
            benchmark=bt_raw.get("benchmark", "BTC-USDT"),
        )
        
        mon_raw = raw.get("monitoring", {})
        monitoring = MonitoringConfig(
            log_level=mon_raw.get("log_level", "INFO"),
            metrics_interval=mon_raw.get("metrics_interval", 1),
            alert_enabled=mon_raw.get("alert_enabled", True),
        )
        
        storage_raw = raw.get("storage", {})
        storage = StorageConfig(
            type=storage_raw.get("type", "sqlite"),
            path=storage_raw.get("path", "./data/trading.db"),
            backup_interval=storage_raw.get("backup_interval", 300),
        )
        
        return Config(
            exchange=exchange,
            symbols=symbols,
            strategy=strategy,
            risk=risk,
            execution=execution,
            backtest=backtest,
            monitoring=monitoring,
            storage=storage
        )
    
    def get(self) -> Config:
        """获取配置对象"""
        if self._config is None:
            return self.load()
        return self._config
    
    def get_raw(self, key: str, default: Any = None) -> Any:
        """获取原始配置值"""
        keys = key.split(".")
        value = self._raw_config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
        return value if value is not None else default


_settings: Optional[Settings] = None


def get_settings(config_path: Optional[str] = None) -> Settings:
    """获取全局配置实例"""
    global _settings
    if _settings is None:
        _settings = Settings(config_path)
    return _settings


def load_config(config_path: Optional[str] = None) -> Config:
    """加载配置并返回Config对象"""
    settings = get_settings(config_path)
    return settings.load()
