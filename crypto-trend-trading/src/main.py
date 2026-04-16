"""量化交易系统主程序"""

import asyncio
import signal
import logging
import sys
from typing import Optional

from .config import load_config, Config
from .core import (
    DataAggregator, StrategyEngine, RiskEngine,
    OrderExecutor, PositionManager, TickEvent
)
from .storage import StateManager
from .monitor import MetricsCollector, create_default_alerter, get_logger
from .models import (
    OrderSide, OrderType, PositionSide,
    create_order_request, SignalDirection
)
from .utils import get_current_timestamp_ms

logger = get_logger("main")


class TradingSystem:
    """量化交易系统主类"""
    
    def __init__(self, config: Config):
        self.config = config
        
        self.data_aggregator = DataAggregator(config)
        self.strategy_engine = StrategyEngine(config)
        self.risk_engine = RiskEngine(config)
        self.order_executor = OrderExecutor(config)
        self.position_manager = PositionManager(config)
        
        self.state_manager = StateManager(config)
        self.metrics_collector = MetricsCollector()
        self.alerter = create_default_alerter()
        
        self._running = False
        self._shutdown_event = asyncio.Event()
    
    async def initialize(self) -> None:
        """初始化系统"""
        logger.info("Initializing trading system...")
        
        await self.state_manager.initialize()
        
        saved_state = await self.state_manager.load_state()
        if saved_state:
            self.position_manager.load_state(saved_state)
        
        await self.order_executor.initialize()
        
        balance = await self.order_executor.get_balance()
        self.position_manager.balance = balance.total_equity
        self.risk_engine.update_balance(balance.total_equity)
        
        for position in self.position_manager.get_all_positions():
            self.risk_engine.update_position(position)
        
        self.data_aggregator.on_tick(self.on_tick)
        
        logger.info("Trading system initialized")
    
    async def start(self) -> None:
        """启动系统"""
        logger.info("Starting trading system...")
        
        self._running = True
        
        connected = await self.data_aggregator.connect()
        if not connected:
            logger.error("Failed to connect to data feed")
            return
        
        await self.data_aggregator.subscribe()
        
        asyncio.create_task(self._monitor_loop())
        asyncio.create_task(self._persist_loop())
        
        await self._shutdown_event.wait()
        
        logger.info("Trading system stopped")
    
    async def stop(self) -> None:
        """停止系统"""
        logger.info("Stopping trading system...")
        self._running = False
        
        logger.info("Cancelling all open orders...")
        await self.order_executor.cancel_all_orders()
        
        logger.info("Closing all positions...")
        for position in self.position_manager.get_all_positions():
            await self.order_executor.submit_order(
                create_order_request(
                    symbol=position.symbol,
                    side=OrderSide.SELL if position.side == PositionSide.LONG else OrderSide.BUY,
                    quantity=position.quantity,
                    order_type=OrderType.MARKET,
                    reduce_only=True
                )
            )
        
        await self.save_state()
        
        await self.data_aggregator.disconnect()
        await self.order_executor.close()
        await self.state_manager.close()
        
        self._shutdown_event.set()
    
    async def on_tick(self, event: TickEvent) -> None:
        """
        处理行情事件
        
        Args:
            event: 行情事件
        """
        start_time = get_current_timestamp_ms()
        
        if event.ticker:
            latency_us = event.latency_us
            await self.metrics_collector.record_data_processing(latency_us / 1000)
            
            self.position_manager.update_position_price(event.symbol, event.ticker.last_price)
        
        if event.kline:
            calc_start = get_current_timestamp_ms()
            
            signal = await self.strategy_engine.process_kline(event.kline)
            
            calc_latency = get_current_timestamp_ms() - calc_start
            await self.metrics_collector.record_strategy_calculation(calc_latency)
            
            if signal and signal.direction != SignalDirection.NEUTRAL:
                await self._process_signal(signal)
        
        end_to_end = get_current_timestamp_ms() - start_time
        await self.metrics_collector.record_end_to_end(end_to_end)
    
    async def _process_signal(self, signal) -> None:
        """处理交易信号"""
        if self.risk_engine.is_strategy_paused:
            logger.warning("Strategy paused, skipping signal")
            return
        
        balance = await self.order_executor.get_balance()
        
        check_result = self.risk_engine.check_order(signal, balance.total_equity)
        
        if not check_result.passed:
            logger.warning(f"Risk check failed: {check_result.rejected_reason}")
            return
        
        position = self.position_manager.get_position(signal.symbol)
        
        if position and position.quantity > 0:
            if (position.side == PositionSide.LONG and signal.direction == SignalDirection.SELL) or \
               (position.side == PositionSide.SHORT and signal.direction == SignalDirection.BUY):
                order_side = OrderSide.SELL if position.side == PositionSide.LONG else OrderSide.BUY
                
                order = create_order_request(
                    symbol=signal.symbol,
                    side=order_side,
                    quantity=position.quantity,
                    order_type=OrderType.MARKET,
                    reduce_only=True,
                    signal_id=signal.id
                )
            else:
                return
        else:
            order = create_order_request(
                symbol=signal.symbol,
                side=OrderSide.BUY if signal.direction == SignalDirection.BUY else OrderSide.SELL,
                quantity=check_result.risk_metrics.order_amount / signal.entry_price,
                order_type=OrderType.MARKET,
                signal_id=signal.id
            )
        
        execution_price = self.order_executor.calculate_execution_price(
            order.side, signal.entry_price, order.order_type
        )
        order.price = execution_price
        
        submit_start = get_current_timestamp_ms()
        response = await self.order_executor.submit_order(order)
        submit_latency = get_current_timestamp_ms() - submit_start
        
        await self.metrics_collector.record_order_submission(submit_latency)
        
        if response.status.value in ["filled", "submitted"]:
            self.risk_engine.record_trade(response.quantity * response.price)
            
            if response.status.value == "filled":
                if order.side == OrderSide.BUY:
                    self.position_manager.open_position(
                        symbol=signal.symbol,
                        side=PositionSide.LONG,
                        quantity=response.filled_qty,
                        entry_price=response.avg_price
                    )
                else:
                    self.position_manager.close_position(signal.symbol, response.avg_price, response.fee)
    
    async def _monitor_loop(self) -> None:
        """监控循环"""
        while self._running:
            try:
                await asyncio.sleep(self.config.monitoring.metrics_interval)
                
                metrics = await self.metrics_collector.collect_system_metrics()
                
                positions = self.position_manager.get_all_positions()
                metrics.total_positions = len(positions)
                metrics.total_unrealized_pnl = self.position_manager.get_total_unrealized_pnl()
                
                open_orders = self.order_executor.get_open_orders()
                metrics.open_orders_count = len(open_orders)
                
                self.metrics_collector.update_trading_metrics(
                    total_positions=len(positions),
                    open_orders_count=len(open_orders),
                    websocket_connected=self.data_aggregator.is_connected
                )
                
                await self.alerter.check_and_alert(metrics)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Monitor loop error: {e}")
    
    async def _persist_loop(self) -> None:
        """持久化循环"""
        while self._running:
            try:
                await asyncio.sleep(self.config.storage.backup_interval)
                await self.save_state()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Persist loop error: {e}")
    
    async def save_state(self) -> None:
        """保存状态"""
        state = {
            "positions": self.position_manager.get_state(),
            "balance": self.position_manager.balance,
            "daily_stats": {}
        }
        
        await self.state_manager.save_state(
            positions=state["positions"],
            balance=state["balance"],
            daily_stats=state["daily_stats"]
        )


async def main() -> None:
    """主函数"""
    import os
    
    os.environ.setdefault("OKX_API_KEY", os.getenv("OKX_API_KEY", ""))
    os.environ.setdefault("OKX_SECRET_KEY", os.getenv("OKX_SECRET_KEY", ""))
    os.environ.setdefault("OKX_PASSPHRASE", os.getenv("OKX_PASSPHRASE", ""))
    
    if not all([
        os.getenv("OKX_API_KEY"),
        os.getenv("OKX_SECRET_KEY"),
        os.getenv("OKX_PASSPHRASE")
    ]):
        logger.error("Missing required environment variables: OKX_API_KEY, OKX_SECRET_KEY, OKX_PASSPHRASE")
        sys.exit(1)
    
    try:
        config = load_config()
        
        system = TradingSystem(config)
        
        loop = asyncio.get_event_loop()
        
        def signal_handler():
            if loop.is_running():
                asyncio.create_task(system.stop())
        
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, signal_handler)
        
        await system.initialize()
        await system.start()
        
    except Exception as e:
        logger.critical(f"System error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
