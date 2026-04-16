"""日期时间工具"""

from datetime import datetime, timezone
from typing import Optional


def get_current_timestamp_ms() -> int:
    """获取当前时间戳(毫秒)"""
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def get_current_timestamp_s() -> int:
    """获取当前时间戳(秒)"""
    return int(datetime.now(timezone.utc).timestamp())


def timestamp_ms_to_datetime(timestamp_ms: int) -> datetime:
    """毫秒时间戳转datetime"""
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)


def timestamp_s_to_datetime(timestamp_s: int) -> datetime:
    """秒时间戳转datetime"""
    return datetime.fromtimestamp(timestamp_s, tz=timezone.utc)


def datetime_to_timestamp_ms(dt: datetime) -> int:
    """datetime转毫秒时间戳"""
    return int(dt.timestamp() * 1000)


def format_timestamp_ms(timestamp_ms: int, fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """格式化时间戳(毫秒)"""
    dt = timestamp_ms_to_datetime(timestamp_ms)
    return dt.strftime(fmt)


def format_timestamp_s(timestamp_s: int, fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """格式化时间戳(秒)"""
    dt = timestamp_s_to_datetime(timestamp_s)
    return dt.strftime(fmt)


def parse_datetime(dt_str: str, fmt: str = "%Y-%m-%d %H:%M:%S") -> datetime:
    """解析datetime字符串"""
    return datetime.strptime(dt_str, fmt)


def get_date_str(dt: Optional[datetime] = None) -> str:
    """获取日期字符串 YYYY-MM-DD"""
    if dt is None:
        dt = datetime.now(timezone.utc)
    return dt.strftime("%Y-%m-%d")


def get_time_str(dt: Optional[datetime] = None) -> str:
    """获取时间字符串 HH:MM:SS"""
    if dt is None:
        dt = datetime.now(timezone.utc)
    return dt.strftime("%H:%M:%S")


def is_same_day(ts1_ms: int, ts2_ms: int) -> bool:
    """判断两个时间戳是否为同一天"""
    dt1 = timestamp_ms_to_datetime(ts1_ms)
    dt2 = timestamp_ms_to_datetime(ts2_ms)
    return dt1.date() == dt2.date()


def get_milliseconds(seconds: float) -> int:
    """秒转毫秒"""
    return int(seconds * 1000)


def get_seconds(milliseconds: int) -> float:
    """毫秒转秒"""
    return milliseconds / 1000


def add_days(timestamp_ms: int, days: int) -> int:
    """时间戳加天数"""
    dt = timestamp_ms_to_datetime(timestamp_ms)
    dt = dt.replace(hour=0, minute=0, second=0, microsecond=0)
    from datetime import timedelta
    dt = dt + timedelta(days=days)
    return datetime_to_timestamp_ms(dt)
