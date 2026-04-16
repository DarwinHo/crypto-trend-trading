"""日志系统"""

import logging
import json
import sys
from datetime import datetime, timezone
from typing import Any, Dict

from ..models import AlertLevel


class JSONFormatter(logging.Formatter):
    """JSON日志格式化器"""
    
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        if hasattr(record, "extra"):
            log_data["extra"] = record.extra
        
        return json.dumps(log_data)


class Logger:
    """结构化日志器"""
    
    def __init__(self, name: str, level: str = "INFO"):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(getattr(logging, level.upper()))
        
        if not self.logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(JSONFormatter())
            self.logger.addHandler(handler)
    
    def _log(self, level: str, message: str, **kwargs: Any) -> None:
        """记录日志"""
        extra = {"extra": kwargs} if kwargs else {}
        getattr(self.logger, level.lower())(message, extra=extra)
    
    def debug(self, message: str, **kwargs: Any) -> None:
        self._log("DEBUG", message, **kwargs)
    
    def info(self, message: str, **kwargs: Any) -> None:
        self._log("INFO", message, **kwargs)
    
    def warning(self, message: str, **kwargs: Any) -> None:
        self._log("WARNING", message, **kwargs)
    
    def error(self, message: str, **kwargs: Any) -> None:
        self._log("ERROR", message, **kwargs)
    
    def critical(self, message: str, **kwargs: Any) -> None:
        self._log("CRITICAL", message, **kwargs)


def get_logger(name: str, level: str = "INFO") -> Logger:
    """获取日志器"""
    return Logger(name, level)


class AlertLogger:
    """告警日志"""
    
    def __init__(self):
        self.logger = get_logger("alert")
    
    def alert(
        self,
        level: AlertLevel,
        source: str,
        message: str,
        **details: Any
    ) -> None:
        """记录告警"""
        self.logger._log(
            level.value.upper(),
            f"[{source}] {message}",
            level=level.value,
            source=source,
            **details
        )
    
    def info(self, source: str, message: str, **details: Any) -> None:
        self.alert(AlertLevel.INFO, source, message, **details)
    
    def warn(self, source: str, message: str, **details: Any) -> None:
        self.alert(AlertLevel.WARN, source, message, **details)
    
    def error(self, source: str, message: str, **details: Any) -> None:
        self.alert(AlertLevel.ERROR, source, message, **details)
    
    def fatal(self, source: str, message: str, **details: Any) -> None:
        self.alert(AlertLevel.FATAL, source, message, **details)
