#!/usr/bin/env python3
"""
SQLite Database Module for Tellor Layer Active Balances

This module provides database operations for storing and retrieving
balance snapshots with historical tracking.
"""

import sqlite3
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)

DATABASE_FILE = 'tellor_balances.db'


class BalancesDatabase:
    """Manages SQLite database for balance snapshots."""
    
    def __init__(self, db_path: str = DATABASE_FILE):
        """Initialize database connection and create tables if needed."""
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialize database tables."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS balance_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    snapshot_time TIMESTAMP NOT NULL,
                    address TEXT NOT NULL,
                    account_type TEXT NOT NULL,
                    loya_balance INTEGER NOT NULL,
                    loya_balance_trb REAL NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Create indexes for better query performance
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_snapshot_time 
                ON balance_snapshots (snapshot_time)
            ''')
            
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_address 
                ON balance_snapshots (address)
            ''')
            
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_account_type 
                ON balance_snapshots (account_type)
            ''')
            
            # Create collection runs table to track when collections were made
            conn.execute('''
                CREATE TABLE IF NOT EXISTS collection_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_time TIMESTAMP NOT NULL,
                    total_addresses INTEGER NOT NULL,
                    addresses_with_balance INTEGER NOT NULL,
                    total_loya_balance INTEGER NOT NULL,
                    total_trb_balance REAL NOT NULL,
                    bridge_balance_trb REAL DEFAULT 0.0,
                    layer_block_height INTEGER DEFAULT 0,
                    free_floating_trb REAL DEFAULT 0.0,
                    status TEXT NOT NULL DEFAULT 'completed',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Create supply data table for supply collector data
            conn.execute('''
                CREATE TABLE IF NOT EXISTS supply_data (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    collection_time TIMESTAMP NOT NULL,
                    eth_block_number INTEGER,
                    eth_block_timestamp INTEGER,
                    bridge_balance_trb REAL,
                    layer_block_height INTEGER,
                    layer_block_timestamp INTEGER,
                    layer_total_supply_trb REAL,
                    not_bonded_tokens REAL,
                    bonded_tokens REAL,
                    free_floating_trb REAL,
                    collection_run_id INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (collection_run_id) REFERENCES collection_runs (id)
                )
            ''')
            
            # Create indexes for supply data table
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_supply_collection_time 
                ON supply_data (collection_time)
            ''')
            
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_supply_layer_block_height 
                ON supply_data (layer_block_height)
            ''')
            
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_supply_collection_run_id 
                ON supply_data (collection_run_id)
            ''')
            
            # Add new columns to existing table if they don't exist (for backward compatibility)
            try:
                conn.execute('ALTER TABLE collection_runs ADD COLUMN bridge_balance_trb REAL DEFAULT 0.0')
            except sqlite3.OperationalError:
                pass  # Column already exists
            
            try:
                conn.execute('ALTER TABLE collection_runs ADD COLUMN layer_block_height INTEGER DEFAULT 0')
            except sqlite3.OperationalError:
                pass  # Column already exists
                
            try:
                conn.execute('ALTER TABLE collection_runs ADD COLUMN free_floating_trb REAL DEFAULT 0.0')
            except sqlite3.OperationalError:
                pass  # Column already exists
        
        logger.info(f"Database initialized: {self.db_path}")
    
    def save_snapshot(self, addresses_with_balances: List[Tuple[str, str, int, float]], 
                      bridge_balance_trb: float = 0.0, layer_block_height: int = 0, 
                      free_floating_trb: float = 0.0):
        """
        Save a complete balance snapshot to the database.
        
        Args:
            addresses_with_balances: List of tuples (address, account_type, loya_balance, loya_balance_trb)
            bridge_balance_trb: Bridge balance in TRB
            layer_block_height: Tellor Layer block height
            free_floating_trb: Free floating TRB calculated from addresses
        """
        snapshot_time = datetime.now(timezone.utc)
        
        with sqlite3.connect(self.db_path) as conn:
            # Insert all balance records
            for address, account_type, loya_balance, loya_balance_trb in addresses_with_balances:
                conn.execute('''
                    INSERT INTO balance_snapshots 
                    (snapshot_time, address, account_type, loya_balance, loya_balance_trb)
                    VALUES (?, ?, ?, ?, ?)
                ''', (snapshot_time, address, account_type, loya_balance, loya_balance_trb))
            
            # Calculate summary statistics
            total_addresses = len(addresses_with_balances)
            addresses_with_balance = sum(1 for _, _, loya, _ in addresses_with_balances if loya > 0)
            total_loya_balance = sum(loya for _, _, loya, _ in addresses_with_balances)
            total_trb_balance = sum(trb for _, _, _, trb in addresses_with_balances)
            
            # Insert collection run record with additional data
            conn.execute('''
                INSERT INTO collection_runs 
                (run_time, total_addresses, addresses_with_balance, total_loya_balance, total_trb_balance,
                 bridge_balance_trb, layer_block_height, free_floating_trb)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (snapshot_time, total_addresses, addresses_with_balance, total_loya_balance, total_trb_balance,
                  bridge_balance_trb, layer_block_height, free_floating_trb))
        
        logger.info(f"Saved snapshot with {total_addresses} addresses, block height {layer_block_height}, "
                   f"bridge balance {bridge_balance_trb:.2f} TRB, free floating {free_floating_trb:.2f} TRB at {snapshot_time}")
    
    def save_supply_data(self, supply_data: Dict, collection_run_id: Optional[int] = None) -> int:
        """
        Save supply data to the database.
        
        Args:
            supply_data: Dictionary containing supply metrics
            collection_run_id: Optional ID of related collection run
            
        Returns:
            The ID of the inserted supply data record
        """
        collection_time = datetime.now(timezone.utc)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute('''
                INSERT INTO supply_data 
                (collection_time, eth_block_number, eth_block_timestamp, bridge_balance_trb,
                 layer_block_height, layer_block_timestamp, layer_total_supply_trb,
                 not_bonded_tokens, bonded_tokens, free_floating_trb, collection_run_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                collection_time,
                supply_data.get('eth_block_number'),
                supply_data.get('eth_block_timestamp'),
                supply_data.get('bridge_balance_trb'),
                supply_data.get('layer_block_height'),
                supply_data.get('layer_block_timestamp'),
                supply_data.get('layer_total_supply_trb'),
                supply_data.get('not_bonded_tokens'),
                supply_data.get('bonded_tokens'),
                supply_data.get('free_floating_trb'),
                collection_run_id
            ))
            
            supply_data_id = cursor.lastrowid
            if supply_data_id is None:
                raise RuntimeError("Failed to get ID for inserted supply data record")
        
        logger.info(f"Saved supply data with ID {supply_data_id} at {collection_time}")
        return supply_data_id
    
    def get_latest_supply_data(self) -> Optional[Dict]:
        """Get the most recent supply data record."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute('''
                SELECT * FROM supply_data 
                ORDER BY collection_time DESC 
                LIMIT 1
            ''')
            
            row = cursor.fetchone()
            if not row:
                return None
            
            columns = [desc[0] for desc in cursor.description]
            return dict(zip(columns, row))
    
    def get_supply_data_history(self, limit: int = 100) -> List[Dict]:
        """Get historical supply data records."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute('''
                SELECT * FROM supply_data 
                ORDER BY collection_time DESC 
                LIMIT ?
            ''', (limit,))
            
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
    
    def get_supply_data_by_timerange(self, start_time: str, end_time: str) -> List[Dict]:
        """Get supply data within a specific time range."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute('''
                SELECT * FROM supply_data 
                WHERE collection_time BETWEEN ? AND ?
                ORDER BY collection_time ASC
            ''', (start_time, end_time))
            
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
    
    def get_matched_collection_data(self, collection_run_id: int) -> Dict:
        """
        Get both balance snapshot summary and supply data for a specific collection run.
        
        Args:
            collection_run_id: The collection run ID to match
            
        Returns:
            Dictionary containing both balance summary and supply data
        """
        with sqlite3.connect(self.db_path) as conn:
            # Get collection run data
            cursor = conn.execute('''
                SELECT * FROM collection_runs WHERE id = ?
            ''', (collection_run_id,))
            
            run_row = cursor.fetchone()
            if not run_row:
                return {}
            
            run_columns = [desc[0] for desc in cursor.description]
            result = {'collection_run': dict(zip(run_columns, run_row))}
            
            # Get associated supply data
            cursor = conn.execute('''
                SELECT * FROM supply_data WHERE collection_run_id = ?
            ''', (collection_run_id,))
            
            supply_row = cursor.fetchone()
            if supply_row:
                supply_columns = [desc[0] for desc in cursor.description]
                result['supply_data'] = dict(zip(supply_columns, supply_row))
            
            return result
    
    def get_latest_snapshot(self) -> Dict:
        """Get summary of the latest snapshot."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute('''
                SELECT * FROM collection_runs 
                ORDER BY run_time DESC 
                LIMIT 1
            ''')
            
            row = cursor.fetchone()
            if not row:
                return {}
            
            columns = [desc[0] for desc in cursor.description]
            return dict(zip(columns, row))
    
    def get_snapshots_history(self, limit: int = 100) -> List[Dict]:
        """Get historical snapshots."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute('''
                SELECT * FROM collection_runs 
                ORDER BY run_time DESC 
                LIMIT ?
            ''', (limit,))
            
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
    
    def get_address_history(self, address: str, limit: int = 50) -> List[Dict]:
        """Get balance history for a specific address."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute('''
                SELECT * FROM balance_snapshots 
                WHERE address = ? 
                ORDER BY snapshot_time DESC 
                LIMIT ?
            ''', (address, limit))
            
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
    
    def get_latest_balances(self, limit: int = 1000, offset: int = 0) -> List[Dict]:
        """Get latest balances for all addresses."""
        with sqlite3.connect(self.db_path) as conn:
            # Get the latest snapshot time
            cursor = conn.execute('''
                SELECT MAX(snapshot_time) FROM balance_snapshots
            ''')
            latest_time = cursor.fetchone()[0]
            
            if not latest_time:
                return []
            
            # Get all balances from the latest snapshot
            cursor = conn.execute('''
                SELECT * FROM balance_snapshots 
                WHERE snapshot_time = ? 
                ORDER BY loya_balance_trb DESC
                LIMIT ? OFFSET ?
            ''', (latest_time, limit, offset))
            
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
    
    def search_addresses(self, search_term: str, limit: int = 100) -> List[Dict]:
        """Search addresses by partial match."""
        with sqlite3.connect(self.db_path) as conn:
            # Get the latest snapshot time
            cursor = conn.execute('''
                SELECT MAX(snapshot_time) FROM balance_snapshots
            ''')
            latest_time = cursor.fetchone()[0]
            
            if not latest_time:
                return []
            
            cursor = conn.execute('''
                SELECT * FROM balance_snapshots 
                WHERE snapshot_time = ? AND address LIKE ?
                ORDER BY loya_balance_trb DESC
                LIMIT ?
            ''', (latest_time, f'%{search_term}%', limit))
            
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
    
    def get_account_type_summary(self) -> List[Dict]:
        """Get summary by account type from latest snapshot."""
        with sqlite3.connect(self.db_path) as conn:
            # Get the latest snapshot time
            cursor = conn.execute('''
                SELECT MAX(snapshot_time) FROM balance_snapshots
            ''')
            latest_time = cursor.fetchone()[0]
            
            if not latest_time:
                return []
            
            cursor = conn.execute('''
                SELECT 
                    account_type,
                    COUNT(*) as address_count,
                    SUM(loya_balance) as total_loya,
                    SUM(loya_balance_trb) as total_trb,
                    AVG(loya_balance_trb) as avg_trb,
                    MAX(loya_balance_trb) as max_trb
                FROM balance_snapshots 
                WHERE snapshot_time = ?
                GROUP BY account_type
                ORDER BY total_trb DESC
            ''', (latest_time,))
            
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
    
    def backup_database(self, backup_path: str):
        """Create a backup of the database."""
        import shutil
        shutil.copy2(self.db_path, backup_path)
        logger.info(f"Database backed up to: {backup_path}") 