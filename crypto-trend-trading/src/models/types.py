"""数据类型定义"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import time


class SignalDirection(Enum):
    BUY = "buy"
    SELL = "sell"
    NEUTRAL = "neutral"


class OrderSide(Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(Enum):
    MARKET = "market"
    LIMIT = "limit"


class OrderStatus(Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    PARTIAL_FILLED = "partial_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"
    FAILED = "failed"


class PositionSide(Enum):
    LONG = "long"
    SHORT = "short"


class AlertLevel(Enum):
    INFO = "info"
    WARN = "warn"
    ERROR = "error"
    FATAL = "fatal"


@dataclass(slots=True)
class KLine:
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    quote_volume: float = 0.0


@dataclass(slots=True)
class Ticker:
    symbol: str
    last_price: float
    bid_price: float
    bid_qty: float
    ask_price: float
    ask_qty: float
    high_24h: float
    low_24h: float
    volume_24h: float
    timestamp: int


@dataclass(slots=True)
class IndicatorSet:
    ema5: float = 0.0
    ema20: float = 0.0
    ema50: float = 0.0
    ema_convergence: float = 0.0
    rsi: float = 50.0
    atr: float = 0.0
    atr_percent: float = 0.0
    macd: float = 0.0
    macd_signal: float = 0.0
    macd_histogram: float = 0.0
    trend_strength: float = 0.0


@dataclass(slots=True)
class TrendSignal:
    id: str
    symbol: str
    direction: SignalDirection
    entry_price: float
    stop_loss: float
    take_profit: float
    confidence: float
    indicators: IndicatorSet
    reason: str
    timestamp: int
    expires_at: int
    signal_type: str = "trend"


@dataclass(slots=True)
class OrderRequest:
    symbol: str
    side: OrderSide
    order_type: OrderType
    price: Optional[float]
    quantity: float
    client_order_id: str
    reduce_only: bool = False
    signal_id: Optional[str] = None
    submitted_at: Optional[int] = None


@dataclass(slots=True)
class OrderResponse:
    order_id: str
    client_order_id: str
    symbol: str
    status: OrderStatus
    side: OrderSide
    order_type: OrderType
    price: float
    quantity: float
    filled_qty: float
    avg_price: float
    fee: float
    timestamp: int
    updated_at: int
    submit_latency_ms: float = 0.0
    fill_latency_ms: float = 0.0


@dataclass(slots=True)
class Position:
    id: str
    symbol: str
    side: PositionSide
    quantity: float
    entry_price: float
    current_price: float
    mark_price: float
    liquidation_price: float
    leverage: float
    margin: float
    unrealized_pnl: float
    realized_pnl: float
    opening_timestamp: int
    updated_at: int


@dataclass(slots=True)
class Balance:
    total_equity: float
    available: float
    margin_used: float
    margin_available: float
    positions: list = field(default_factory=list)


@dataclass(slots=True)
class CheckResult:
    passed: bool
    rejected_by: Optional[str]
    rejected_reason: Optional[str]
    risk_metrics: Optional['RiskMetrics'] = None
    timestamp: int = field(default_factory=lambda: int(time.time() * 1000))


@dataclass(slots=True)
class RiskMetrics:
    order_amount: float = 0.0
    position_value: float = 0.0
    daily_trade_value: float = 0.0
    position_count: int = 0
    concentration: float = 0.0
    unrealized_pnl_ratio: float = 0.0
    margin_ratio: float = 0.0


@dataclass(slots=True)
class PortfolioRisk:
    total_exposure: float
    net_exposure: float
    margin_used: float
    margin_available: float
    margin_ratio: float
    risk_level: str


@dataclass(slots=True)
class SystemMetrics:
    data_processing_latency_p99_ms: float = 0.0
    strategy_calculation_latency_p99_ms: float = 0.0
    order_submission_latency_p99_ms: float = 0.0
    end_to_end_latency_p99_ms: float = 0.0
    total_positions: int = 0
    open_orders_count: int = 0
    daily_trade_count: int = 0
    daily_trade_volume: float = 0.0
    total_realized_pnl: float = 0.0
    total_unrealized_pnl: float = 0.0
    daily_pnl: float = 0.0
    cpu_usage_percent: float = 0.0
    memory_usage_mb: float = 0.0
    memory_usage_percent: float = 0.0
    network_latency_ms: float = 0.0
    websocket_connected: bool = False
    database_connected: bool = False
    order_success_rate: float = 1.0
    avg_fill_slippage: float = 0.0
    avg_order_latency_ms: float = 0.0
    total_orders_today: int = 0
    failed_orders_today: int = 0


@dataclass(slots=True)
class AlertEvent:
    level: AlertLevel
    source: str
    message: str
    details: dict
    timestamp: int
    recovered: bool = False


@dataclass
class PnLReport:
    total_realized_pnl: float = 0.0
    total_unrealized_pnl: float = 0.0
    total_trade_count: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    profit_factor: float = 0.0
    max_drawdown: float = 0.0
    max_drawdown_ratio: float = 0.0
    current_drawdown: float = 0.0
    current_drawdown_ratio: float = 0.0
    avg_holding_time_hours: float = 0.0
    largest_position: float = 0.0
    avg_position: float = 0.0


@dataclass
class BacktestConfig:
    initial_capital: float = 100000.0
    commission_rate: float = 0.0005
    slippage: float = 0.0005
    start_date: str = "2024-01-01"
    end_date: str = "2024-12-31"
    symbols: list = field(default_factory=lambda: ["BTC-USDT"])
    timeframe: str = "1h"
    progress_interval: int = 1000
    checkpoint_enabled: bool = True
    checkpoint_path: str = "./data/backtest/checkpoint.json"


@dataclass
class BacktestResult:
    initial_capital: float
    final_capital: float
    total_return: float
    annualized_return: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    max_drawdown_ratio: float
    max_drawdown_duration: int
    current_drawdown: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    avg_win: float
    avg_loss: float
    profit_factor: float
    avg_trade_duration: float
    monthly_returns: dict
    config: BacktestConfig = None
    start_date: str = ""
    end_date: str = ""
    total_days: int = 0
