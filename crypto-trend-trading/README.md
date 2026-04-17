# CRYPTO-TREND 加密货币量化交易系统

专注于 OKX 交易所的加密货币趋势跟踪量化交易系统，采用事件驱动架构，实现从市场数据采集、策略信号生成、订单执行到风险管理的全流程自动化。

## 核心特性

- **智能化趋势识别**：通过 EMA/RSI/ATR 多指标组合确认趋势方向
- **严格风险管理**：多层次风控规则确保资金安全
- **毫秒级响应**：异步事件驱动架构，低延迟执行
- **模块化设计**：各组件独立，便于扩展和维护

## 系统架构

```
┌─────────────────────────────────────────────────────────┐
│                      数据层                              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐   │
│  │  WebSocket   │  │  REST API    │  │  本地存储    │   │
│  └─────────────┘  └─────────────┘  └─────────────┘   │
└─────────────────────────────────────────────────────────┘
                           │
┌─────────────────────────────────────────────────────────┐
│                      核心层                              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐   │
│  │ 数据聚合器   │→ │ 策略引擎    │→ │  风控引擎    │   │
│  └─────────────┘  └─────────────┘  └─────────────┘   │
│                           │                │          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐   │
│  │ 仓位管理器   │← │ 订单执行器   │← │  监控告警    │   │
│  └─────────────┘  └─────────────┘  └─────────────┘   │
└─────────────────────────────────────────────────────────┘
```

## 技术栈

- Python 3.10+
- asyncio - 异步事件驱动
- aiohttp - HTTP 客户端
- websockets - WebSocket 客户端
- SQLite - 数据持久化
- numpy/pandas - 数据处理

## 目录结构

```
crypto-trend-trading/
├── src/
│   ├── main.py                 # 程序入口
│   ├── config/                 # 配置管理
│   │   ├── settings.py        # 配置加载
│   │   ├── validator.py       # 配置验证
│   │   └── config.yaml         # 配置文件
│   ├── core/                  # 核心组件
│   │   ├── data_aggregator.py  # 数据聚合器
│   │   ├── strategy_engine.py # 策略引擎
│   │   ├── risk_engine.py      # 风控引擎
│   │   ├── order_executor.py   # 订单执行器
│   │   └── position_manager.py # 仓位管理器
│   ├── api/                   # API 客户端
│   │   ├── rest_client.py      # REST API
│   │   └── websocket_client.py # WebSocket
│   ├── models/                # 数据模型
│   ├── storage/              # 存储层
│   ├── monitor/             # 监控告警
│   └── utils/               # 工具函数
├── data/                    # 数据目录
├── requirements.txt
└── README.md
```

## 安装

### 1. 克隆仓库

```bash
git clone https://github.com/DarwinHo/crypto-trend-trading.git
cd crypto-trend-trading
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置环境变量

```bash
export OKX_API_KEY="your_api_key"
export OKX_SECRET_KEY="your_secret_key"
export OKX_PASSPHRASE="your_passphrase"
```

### 4. 修改配置文件

编辑 `src/config/config.yaml`：

```yaml
exchange:
  testnet: false  # 生产环境设为 false

symbols:
  - BTC-USDT
  - ETH-USDT
  # 添加更多交易对

strategy:
  indicators:
    ema_periods: [5, 20, 50]
    rsi_period: 14
    atr_period: 14
```

## 运行

### 生产环境

```bash
python -m src.main
```

### 回测模式

```bash
python scripts/backtest.py
```

## 策略说明

### 趋势跟踪策略

**买入信号**：
- EMA5 > EMA20 > EMA50（上升趋势）
- EMA 收敛度超过阈值
- RSI < 70（非超买）
- 置信度 >= 最低阈值

**卖出信号**：
- EMA5 < EMA20 < EMA50（下降趋势）
- EMA 收敛度低于负阈值
- RSI > 30（非超卖）
- 置信度 >= 最低阈值

**止损止盈**：
- 止损：入场价 ± 2×ATR
- 止盈：入场价 ± 3×ATR

## 风控规则

| 规则 | 阈值 | 动作 |
|------|------|------|
| 单笔金额上限 | 余额 10% | 拒绝订单 |
| 持仓上限 | 余额 20% | 拒绝开仓 |
| 日交易额上限 | 余额 200% | 暂停交易 |
| 最大持仓数 | 5 个 | 拒绝新开仓 |
| 自动止损线 | 亏损 10% | 自动平仓 |

## 监控告警

系统支持以下监控指标：

- 数据处理延迟
- 策略计算延迟
- 订单提交延迟
- 端到端延迟
- CPU/内存使用率
- 订单成功率

告警级别：INFO / WARN / ERROR / FATAL

## 性能指标

| 指标 | 目标值 |
|------|--------|
| 数据处理延迟 P99 | < 1ms |
| 策略计算延迟 P99 | < 5ms |
| 订单提交延迟 P99 | < 10ms |
| 端到端延迟 P99 | < 20ms |
| 系统可用性 | 99.9% |

## 开发

### 运行测试

```bash
pytest tests/
```

### 代码规范

```bash
ruff check src/
```

## 许可证

MIT License

## 联系方式

- GitHub Issues: https://github.com/DarwinHo/crypto-trend-trading/issues
