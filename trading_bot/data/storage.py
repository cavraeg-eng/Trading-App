"""Data storage implementations."""

import json
import sqlite3
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from trading_bot.config import get_logger

logger = get_logger(__name__)


class DataStorage(ABC):
    """Abstract base class for data storage."""
    
    @abstractmethod
    def save_ohlcv(self, symbol: str, timeframe: str, data: pd.DataFrame) -> None:
        """Save OHLCV data."""
        pass
    
    @abstractmethod
    def load_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> pd.DataFrame:
        """Load OHLCV data."""
        pass
    
    @abstractmethod
    def save_trade(self, trade: Dict[str, Any]) -> None:
        """Save trade record."""
        pass
    
    @abstractmethod
    def load_trades(
        self,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> pd.DataFrame:
        """Load trade records."""
        pass


class ParquetStorage(DataStorage):
    """Parquet-based storage for OHLCV data."""
    
    def __init__(self, base_path: Path):
        """Initialize Parquet storage.
        
        Args:
            base_path: Base directory for parquet files
        """
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
    
    def _get_file_path(self, symbol: str, timeframe: str) -> Path:
        """Get file path for symbol/timeframe."""
        # Clean symbol for filename
        clean_symbol = symbol.replace("/", "_")
        return self.base_path / f"{clean_symbol}_{timeframe}.parquet"
    
    def save_ohlcv(self, symbol: str, timeframe: str, data: pd.DataFrame) -> None:
        """Save OHLCV data to Parquet.
        
        Args:
            symbol: Trading pair
            timeframe: Candle timeframe
            data: OHLCV DataFrame
        """
        if data.empty:
            logger.warning("Empty data, skipping save", symbol=symbol, timeframe=timeframe)
            return
        
        file_path = self._get_file_path(symbol, timeframe)
        
        try:
            # Load existing data if present
            if file_path.exists():
                existing_df = pq.read_table(file_path).to_pandas()
                existing_df.index = pd.to_datetime(existing_df.index)
                
                # Merge and remove duplicates
                combined = pd.concat([existing_df, data])
                combined = combined[~combined.index.duplicated(keep="last")]
                combined = combined.sort_index()
            else:
                combined = data
            
            # Save to parquet
            table = pa.Table.from_pandas(combined)
            pq.write_table(table, file_path)
            
            logger.info(
                "Saved OHLCV to Parquet",
                symbol=symbol,
                timeframe=timeframe,
                records=len(combined),
                path=str(file_path),
            )
            
        except Exception as e:
            logger.error(
                "Failed to save OHLCV",
                symbol=symbol,
                error=str(e),
            )
            raise
    
    def load_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> pd.DataFrame:
        """Load OHLCV data from Parquet.
        
        Args:
            symbol: Trading pair
            timeframe: Candle timeframe
            start: Start datetime filter
            end: End datetime filter
            
        Returns:
            OHLCV DataFrame
        """
        file_path = self._get_file_path(symbol, timeframe)
        
        if not file_path.exists():
            logger.warning("Parquet file not found", path=str(file_path))
            return pd.DataFrame()
        
        try:
            df = pq.read_table(file_path).to_pandas()
            df.index = pd.to_datetime(df.index)
            
            # Apply filters
            if start:
                df = df[df.index >= start]
            if end:
                df = df[df.index <= end]
            
            logger.info(
                "Loaded OHLCV from Parquet",
                symbol=symbol,
                timeframe=timeframe,
                records=len(df),
            )
            
            return df
            
        except Exception as e:
            logger.error(
                "Failed to load OHLCV",
                symbol=symbol,
                error=str(e),
            )
            raise
    
    def save_trade(self, trade: Dict[str, Any]) -> None:
        """Not implemented for Parquet storage."""
        raise NotImplementedError("Use SQLiteStorage for trade records")
    
    def load_trades(
        self,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> pd.DataFrame:
        """Not implemented for Parquet storage."""
        raise NotImplementedError("Use SQLiteStorage for trade records")
    
    def list_available_data(self) -> List[Dict[str, str]]:
        """List all available symbol/timeframe combinations.
        
        Returns:
            List of dictionaries with symbol and timeframe
        """
        available = []
        for file_path in self.base_path.glob("*.parquet"):
            # Parse filename: SYMBOL_TIMEFRAME.parquet
            name = file_path.stem
            parts = name.rsplit("_", 1)
            if len(parts) == 2:
                symbol = parts[0].replace("_", "/")
                timeframe = parts[1]
                available.append({"symbol": symbol, "timeframe": timeframe})
        
        return available


class SQLiteStorage(DataStorage):
    """SQLite storage for trades and metadata."""
    
    def __init__(self, db_path: Path):
        """Initialize SQLite storage.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def _init_db(self) -> None:
        """Initialize database schema."""
        with self._get_connection() as conn:
            # Trades table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    entry_price REAL NOT NULL,
                    exit_price REAL,
                    quantity REAL NOT NULL,
                    pnl REAL,
                    pnl_pct REAL,
                    fees REAL DEFAULT 0,
                    status TEXT NOT NULL,
                    strategy TEXT,
                    metadata TEXT
                )
            """)
            
            # OHLCV cache table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ohlcv_cache (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    open REAL NOT NULL,
                    high REAL NOT NULL,
                    low REAL NOT NULL,
                    close REAL NOT NULL,
                    volume REAL NOT NULL,
                    UNIQUE(symbol, timeframe, timestamp)
                )
            """)
            
            # Performance metrics table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    total_return REAL,
                    sharpe_ratio REAL,
                    max_drawdown REAL,
                    win_rate REAL,
                    profit_factor REAL,
                    num_trades INTEGER
                )
            """)
            
            conn.commit()
        
        logger.info("SQLite database initialized", path=str(self.db_path))
    
    def save_ohlcv(self, symbol: str, timeframe: str, data: pd.DataFrame) -> None:
        """Save OHLCV data to SQLite cache.
        
        Args:
            symbol: Trading pair
            timeframe: Candle timeframe
            data: OHLCV DataFrame
        """
        if data.empty:
            return
        
        records = []
        for timestamp, row in data.iterrows():
            records.append((
                symbol,
                timeframe,
                timestamp.isoformat(),
                float(row["open"]),
                float(row["high"]),
                float(row["low"]),
                float(row["close"]),
                float(row["volume"]),
            ))
        
        with self._get_connection() as conn:
            conn.executemany("""
                INSERT OR REPLACE INTO ohlcv_cache
                (symbol, timeframe, timestamp, open, high, low, close, volume)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, records)
            conn.commit()
        
        logger.info(
            "Saved OHLCV to SQLite",
            symbol=symbol,
            timeframe=timeframe,
            records=len(records),
        )
    
    def load_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> pd.DataFrame:
        """Load OHLCV data from SQLite cache.
        
        Args:
            symbol: Trading pair
            timeframe: Candle timeframe
            start: Start datetime filter
            end: End datetime filter
            
        Returns:
            OHLCV DataFrame
        """
        query = """
            SELECT timestamp, open, high, low, close, volume
            FROM ohlcv_cache
            WHERE symbol = ? AND timeframe = ?
        """
        params = [symbol, timeframe]
        
        if start:
            query += " AND timestamp >= ?"
            params.append(start.isoformat())
        if end:
            query += " AND timestamp <= ?"
            params.append(end.isoformat())
        
        query += " ORDER BY timestamp"
        
        with self._get_connection() as conn:
            df = pd.read_sql_query(query, conn, params=params)
        
        if df.empty:
            return df
        
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df.set_index("timestamp", inplace=True)
        
        return df
    
    def save_trade(self, trade: Dict[str, Any]) -> None:
        """Save trade record.
        
        Args:
            trade: Trade dictionary
        """
        metadata = trade.get("metadata", {})
        if isinstance(metadata, dict):
            metadata = json.dumps(metadata)
        
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO trades
                (timestamp, symbol, side, entry_price, exit_price, quantity,
                 pnl, pnl_pct, fees, status, strategy, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                trade.get("timestamp", datetime.now().isoformat()),
                trade.get("symbol"),
                trade.get("side"),
                trade.get("entry_price"),
                trade.get("exit_price"),
                trade.get("quantity"),
                trade.get("pnl"),
                trade.get("pnl_pct"),
                trade.get("fees", 0),
                trade.get("status", "open"),
                trade.get("strategy"),
                metadata,
            ))
            conn.commit()
        
        logger.info(
            "Trade saved",
            symbol=trade.get("symbol"),
            side=trade.get("side"),
            status=trade.get("status"),
        )
    
    def load_trades(
        self,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        symbol: Optional[str] = None,
        status: Optional[str] = None,
    ) -> pd.DataFrame:
        """Load trade records.
        
        Args:
            start: Start datetime filter
            end: End datetime filter
            symbol: Symbol filter
            status: Status filter (open, closed)
            
        Returns:
            Trades DataFrame
        """
        query = "SELECT * FROM trades WHERE 1=1"
        params = []
        
        if start:
            query += " AND timestamp >= ?"
            params.append(start.isoformat())
        if end:
            query += " AND timestamp <= ?"
            params.append(end.isoformat())
        if symbol:
            query += " AND symbol = ?"
            params.append(symbol)
        if status:
            query += " AND status = ?"
            params.append(status)
        
        query += " ORDER BY timestamp DESC"
        
        with self._get_connection() as conn:
            df = pd.read_sql_query(query, conn, params=params)
        
        if not df.empty and "metadata" in df.columns:
            df["metadata"] = df["metadata"].apply(
                lambda x: json.loads(x) if x else {}
            )
        
        return df
    
    def save_metrics(self, metrics: Dict[str, Any]) -> None:
        """Save performance metrics.
        
        Args:
            metrics: Metrics dictionary
        """
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO metrics
                (timestamp, total_return, sharpe_ratio, max_drawdown,
                 win_rate, profit_factor, num_trades)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                datetime.now().isoformat(),
                metrics.get("total_return"),
                metrics.get("sharpe_ratio"),
                metrics.get("max_drawdown"),
                metrics.get("win_rate"),
                metrics.get("profit_factor"),
                metrics.get("num_trades"),
            ))
            conn.commit()
    
    def load_metrics(self, limit: int = 100) -> pd.DataFrame:
        """Load historical metrics.
        
        Args:
            limit: Maximum number of records
            
        Returns:
            Metrics DataFrame
        """
        with self._get_connection() as conn:
            df = pd.read_sql_query(
                "SELECT * FROM metrics ORDER BY timestamp DESC LIMIT ?",
                conn,
                params=[limit],
            )
        
        return df
