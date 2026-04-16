"""异步工具"""

import asyncio
from typing import Callable, Any, Optional
from functools import wraps
import time


def async_retry(
    max_attempts: int = 3,
    initial_delay: float = 1.0,
    backoff_multiplier: float = 2.0,
    max_delay: float = 60.0,
    exceptions: tuple = (Exception,)
):
    """
    异步重试装饰器
    
    Args:
        max_attempts: 最大重试次数
        initial_delay: 初始延迟(秒)
        backoff_multiplier: 退避倍数
        max_delay: 最大延迟(秒)
        exceptions: 需要重试的异常类型
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            delay = initial_delay
            last_exception = None
            
            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_attempts - 1:
                        await asyncio.sleep(delay)
                        delay = min(delay * backoff_multiplier, max_delay)
                    else:
                        raise last_exception
            
            raise last_exception
        
        return wrapper
    return decorator


class RateLimiter:
    """速率限制器"""
    
    def __init__(self, rate_limit: float, burst: int = 1):
        """
        Args:
            rate_limit: 每秒允许的请求数
            burst: 突发容量
        """
        self.rate_limit = rate_limit
        self.burst = burst
        self.tokens = burst
        self.last_update = time.monotonic()
        self.lock = asyncio.Lock()
    
    async def acquire(self) -> None:
        """获取许可"""
        async with self.lock:
            now = time.monotonic()
            elapsed = now - self.last_update
            self.last_update = now
            
            self.tokens = min(self.burst, self.tokens + elapsed * self.rate_limit)
            
            if self.tokens < 1:
                wait_time = (1 - self.tokens) / self.rate_limit
                await asyncio.sleep(wait_time)
                self.tokens = 0
            else:
                self.tokens -= 1


class AsyncTaskManager:
    """异步任务管理器"""
    
    def __init__(self):
        self._tasks: set[asyncio.Task] = set()
        self._shutdown = False
    
    def create_task(self, coro, name: Optional[str] = None) -> asyncio.Task:
        """创建并跟踪任务"""
        if self._shutdown:
            raise RuntimeError("Task manager is shutting down")
        
        task = asyncio.create_task(coro, name=name)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task
    
    async def cancel_all(self) -> None:
        """取消所有任务"""
        self._shutdown = True
        
        for task in self._tasks:
            if not task.done():
                task.cancel()
        
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        
        self._tasks.clear()
    
    @property
    def task_count(self) -> int:
        """获取当前任务数"""
        return len(self._tasks)


class TimeoutError(Exception):
    """超时错误"""
    pass


async def wait_for(
    coro,
    timeout: float,
    default: Any = None
) -> Any:
    """
    等待协程完成，带超时
    
    Args:
        coro: 协程
        timeout: 超时时间(秒)
        default: 超时默认值
        
    Returns:
        协程结果或默认值
    """
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        return default


class CircuitBreaker:
    """熔断器"""
    
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        expected_exception: type = Exception
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        
        self._failure_count = 0
        self._last_failure_time: Optional[float] = None
        self._state = "closed"
        self._lock = asyncio.Lock()
    
    @property
    def state(self) -> str:
        return self._state
    
    async def call(self, coro) -> Any:
        """执行协程，带熔断保护"""
        async with self._lock:
            if self._state == "open":
                if self._last_failure_time:
                    elapsed = time.monotonic() - self._last_failure_time
                    if elapsed > self.recovery_timeout:
                        self._state = "half-open"
                    else:
                        raise RuntimeError("Circuit breaker is OPEN")
        
        try:
            result = await coro
            async with self._lock:
                if self._state == "half-open":
                    self._state = "closed"
                    self._failure_count = 0
            return result
        except self.expected_exception as e:
            async with self._lock:
                self._failure_count += 1
                self._last_failure_time = time.monotonic()
                
                if self._failure_count >= self.failure_threshold:
                    self._state = "open"
            
            raise e
