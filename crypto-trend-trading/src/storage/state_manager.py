"""状态管理器"""

import logging
from typing import Optional, Dict

from .sqlite_storage import SQLiteStorage
from ..config import Config

logger = logging.getLogger(__name__)


class StateManager:
    """状态管理器"""
    
    STATE_KEY = "system_state"
    
    def __init__(self, config: Config):
        self.config = config
        self.storage = SQLiteStorage(config)
        self._state_version = 1
    
    async def initialize(self) -> None:
        """初始化"""
        await self.storage.connect()
    
    async def save_state(
        self,
        positions: Dict,
        balance: float,
        daily_stats: Dict
    ) -> None:
        """保存状态"""
        state = {
            "version": self._state_version,
            "timestamp": int(__import__("time").time() * 1000),
            "balance": balance,
            "positions": positions,
            "daily_stats": daily_stats
        }
        
        await self.storage.save(self.STATE_KEY, state)
        logger.info("State saved")
    
    async def load_state(self) -> Optional[Dict]:
        """加载状态"""
        state = await self.storage.load(self.STATE_KEY)
        
        if state:
            if state.get("version") != self._state_version:
                logger.warning(f"State version mismatch: {state.get('version')} != {self._state_version}")
            
            logger.info("State loaded")
        
        return state
    
    async def close(self) -> None:
        """关闭"""
        await self.storage.close()
