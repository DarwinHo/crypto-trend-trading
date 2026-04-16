"""SQLite存储"""

import aiosqlite
import json
import logging
from typing import Optional, Any, Dict
from pathlib import Path

from ..config import Config
from ..utils import get_current_timestamp_ms

logger = logging.getLogger(__name__)


class SQLiteStorage:
    """SQLite存储"""
    
    def __init__(self, config: Config):
        self.config = config
        self.db_path = config.storage.path
        
        self._db: Optional[aiosqlite.Connection] = None
    
    async def connect(self) -> None:
        """连接数据库"""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self.db_path)
        await self._init_tables()
        logger.info(f"Database connected: {self.db_path}")
    
    async def close(self) -> None:
        """关闭连接"""
        if self._db:
            await self._db.close()
            self._db = None
    
    async def _init_tables(self) -> None:
        """初始化表"""
        await self._db.executescript("""
            CREATE TABLE IF NOT EXISTS positions (
                id TEXT PRIMARY KEY,
                symbol TEXT NOT NULL UNIQUE,
                side TEXT NOT NULL,
                quantity REAL NOT NULL,
                entry_price REAL NOT NULL,
                leverage REAL DEFAULT 1.0,
                margin REAL NOT NULL,
                opening_timestamp INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            );
            
            CREATE TABLE IF NOT EXISTS orders (
                id TEXT PRIMARY KEY,
                client_order_id TEXT UNIQUE NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                order_type TEXT NOT NULL,
                price REAL,
                quantity REAL NOT NULL,
                filled_qty REAL DEFAULT 0,
                avg_price REAL,
                fee REAL DEFAULT 0,
                status TEXT NOT NULL,
                signal_id TEXT,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            );
            
            CREATE TABLE IF NOT EXISTS trades (
                id TEXT PRIMARY KEY,
                order_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                price REAL NOT NULL,
                quantity REAL NOT NULL,
                fee REAL NOT NULL,
                realized_pnl REAL,
                executed_at INTEGER NOT NULL
            );
            
            CREATE TABLE IF NOT EXISTS system_state (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at INTEGER NOT NULL
            );
            
            CREATE INDEX IF NOT EXISTS idx_orders_symbol ON orders(symbol);
            CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
            CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol);
        """)
        await self._db.commit()
    
    async def save(self, key: str, value: Any) -> None:
        """保存数据"""
        if not self._db:
            await self.connect()
        
        data = json.dumps(value)
        timestamp = get_current_timestamp_ms()
        
        await self._db.execute("""
            INSERT OR REPLACE INTO system_state (key, value, updated_at)
            VALUES (?, ?, ?)
        """, (key, data, timestamp))
        
        await self._db.commit()
    
    async def load(self, key: str) -> Optional[Any]:
        """加载数据"""
        if not self._db:
            await self.connect()
        
        async with self._db.execute(
            "SELECT value FROM system_state WHERE key = ?",
            (key,)
        ) as cursor:
            row = await cursor.fetchone()
        
        if row:
            return json.loads(row[0])
        return None
    
    async def save_position(self, position: Dict) -> None:
        """保存持仓"""
        if not self._db:
            await self.connect()
        
        await self._db.execute("""
            INSERT OR REPLACE INTO positions 
            (id, symbol, side, quantity, entry_price, leverage, margin, opening_timestamp, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            position["id"],
            position["symbol"],
            position["side"],
            position["quantity"],
            position["entry_price"],
            position.get("leverage", 1.0),
            position["margin"],
            position["opening_timestamp"],
            get_current_timestamp_ms()
        ))
        
        await self._db.commit()
    
    async def load_positions(self) -> list:
        """加载所有持仓"""
        if not self._db:
            await self.connect()
        
        async with self._db.execute(
            "SELECT * FROM positions WHERE quantity > 0"
        ) as cursor:
            rows = await cursor.fetchall()
        
        return [
            {
                "id": row[0],
                "symbol": row[1],
                "side": row[2],
                "quantity": row[3],
                "entry_price": row[4],
                "leverage": row[5],
                "margin": row[6],
                "opening_timestamp": row[7]
            }
            for row in rows
        ]
    
    async def delete_position(self, symbol: str) -> None:
        """删除持仓"""
        if not self._db:
            await self.connect()
        
        await self._db.execute("DELETE FROM positions WHERE symbol = ?", (symbol,))
        await self._db.commit()
