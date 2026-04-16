"""K线数据相关模型"""

from dataclasses import dataclass
from typing import Optional
from .types import KLine, Ticker


def parse_kline_from_okx(data: dict) -> KLine:
    """从OKX API响应解析K线数据"""
    return KLine(
        timestamp=int(data["ts"]),
        open=float(data["open"]),
        high=float(data["high"]),
        low=float(data["low"]),
        close=float(data["close"]),
        volume=float(data["vol"]),
        quote_volume=float(data.get("quoteVol", 0.0))
    )


def parse_ticker_from_okx(data: dict) -> Ticker:
    """从OKX WebSocket响应解析行情数据"""
    return Ticker(
        symbol=data["instId"],
        last_price=float(data["last"]),
        bid_price=float(data["bidPx"]),
        bid_qty=float(data["bidSz"]),
        ask_price=float(data["askPx"]),
        ask_qty=float(data["askSz"]),
        high_24h=float(data["high24h"]),
        low_24h=float(data["low24h"]),
        volume_24h=float(data["vol24h"]),
        timestamp=int(data["ts"])
    )


@dataclass
class KLineCache:
    """K线缓存，管理不同周期和交易对的K线数据"""
    
    max_klines: int = 1000
    
    def __post_init__(self):
        self._klines: dict[str, list[KLine]] = {}
    
    def add(self, symbol: str, interval: str, kline: KLine) -> None:
        key = f"{symbol}:{interval}"
        if key not in self._klines:
            self._klines[key] = []
        
        self._klines[key].append(kline)
        
        if len(self._klines[key]) > self.max_klines:
            self._klines[key].pop(0)
    
    def get(self, symbol: str, interval: str, limit: int = 100) -> list[KLine]:
        key = f"{symbol}:{interval}"
        klines = self._klines.get(key, [])
        return klines[-limit:] if len(klines) >= limit else klines
    
    def get_all(self, symbol: str, interval: str) -> list[KLine]:
        key = f"{symbol}:{interval}"
        return self._klines.get(key, [])
    
    def clear(self, symbol: Optional[str] = None, interval: Optional[str] = None) -> None:
        if symbol and interval:
            key = f"{symbol}:{interval}"
            self._klines.pop(key, None)
        elif symbol:
            keys_to_remove = [k for k in self._klines if k.startswith(f"{symbol}:")]
            for key in keys_to_remove:
                self._klines.pop(key, None)
        else:
            self._klines.clear()
