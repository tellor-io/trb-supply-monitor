#!/usr/bin/env python3
"""
Migration script to import existing CSV supply data into the database.

This script reads the existing supply_data.csv and supply_data_all.csv files
and imports them into the new supply_data table in the database.
"""

import csv
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List
import argparse

# Import the database class
try:
    from src.tellor_supply_analytics.database import BalancesDatabase
except ImportError:
    print("Error: Could not import BalancesDatabase. Make sure you're running from the project root.")
    exit(1)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def parse_csv_row(row: Dict) -> Dict:
    """Parse a CSV row and convert values to appropriate types."""
    try:
        return {
            'eth_block_number': int(row.get('eth_block_number', 0)) if row.get('eth_block_number') else None,
            'eth_block_timestamp': int(row.get('eth_block_timestamp', 0)) if row.get('eth_block_timestamp') else None,
            'bridge_balance_trb': float(row.get('bridge_balance_trb', 0)) if row.get('bridge_balance_trb') else None,
            'layer_block_height': int(row.get('layer_block_height', 0)) if row.get('layer_block_height') else None,
            'layer_block_timestamp': int(row.get('layer_block_timestamp', 0)) if row.get('layer_block_timestamp') else None,
            'layer_total_supply_trb': float(row.get('layer_total_supply_trb', 0)) if row.get('layer_total_supply_trb') else None,
            'not_bonded_tokens': float(row.get('not_bonded_tokens', 0)) if row.get('not_bonded_tokens') else None,
            'bonded_tokens': float(row.get('bonded_tokens', 0)) if row.get('bonded_tokens') else None,
            'free_floating_trb': float(row.get('free_floating_trb', 0)) if row.get('free_floating_trb') else None,
        }
    except (ValueError, TypeError) as e:
        logger.error(f"Error parsing row: {e}")
        return None

def migrate_csv_file(csv_file: str, db: BalancesDatabase) -> int:
    """
    Migrate data from a CSV file to the database.
    
    Args:
        csv_file: Path to the CSV file
        db: Database instance
        
    Returns:
        Number of records migrated
    """
    if not Path(csv_file).exists():
        logger.warning(f"CSV file not found: {csv_file}")
        return 0
    
    logger.info(f"Migrating data from {csv_file}")
    
    migrated_count = 0
    skipped_count = 0
    
    try:
        with open(csv_file, 'r', newline='') as f:
            reader = csv.DictReader(f)
            
            for row_num, row in enumerate(reader, 1):
                parsed_row = parse_csv_row(row)
                
                if parsed_row is None:
                    logger.warning(f"Skipping row {row_num} due to parsing error")
                    skipped_count += 1
                    continue
                
                try:
                    supply_data_id = db.save_supply_data(parsed_row)
                    migrated_count += 1
                    
                    if migrated_count % 100 == 0:
                        logger.info(f"Migrated {migrated_count} records...")
                        
                except Exception as e:
                    logger.error(f"Error saving row {row_num}: {e}")
                    skipped_count += 1
                    
    except Exception as e:
        logger.error(f"Error reading CSV file: {e}")
        return migrated_count
    
    logger.info(f"Migration completed: {migrated_count} migrated, {skipped_count} skipped")
    return migrated_count

def main():
    parser = argparse.ArgumentParser(description='Migrate CSV supply data to database')
    parser.add_argument(
        '--db-path',
        default='tellor_balances.db',
        help='Path to SQLite database file'
    )
    parser.add_argument(
        '--csv-files',
        nargs='+',
        default=['supply_data.csv', 'supply_data_all.csv'],
        help='CSV files to migrate'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be migrated without actually doing it'
    )
    
    args = parser.parse_args()
    
    if args.dry_run:
        logger.info("DRY RUN MODE - No data will be written to database")
        for csv_file in args.csv_files:
            if Path(csv_file).exists():
                with open(csv_file, 'r') as f:
                    reader = csv.DictReader(f)
                    row_count = sum(1 for _ in reader)
                logger.info(f"Would migrate {row_count} rows from {csv_file}")
            else:
                logger.info(f"CSV file not found: {csv_file}")
        return
    
    # Initialize database
    logger.info(f"Initializing database: {args.db_path}")
    db = BalancesDatabase(args.db_path)
    
    # Check if supply_data table already has data
    try:
        existing_data = db.get_latest_supply_data()
        if existing_data:
            logger.warning("Database already contains supply data!")
            response = input("Continue migration anyway? This may create duplicates. (y/N): ")
            if response.lower() != 'y':
                logger.info("Migration cancelled")
                return
    except Exception as e:
        logger.error(f"Error checking existing data: {e}")
    
    # Migrate each CSV file
    total_migrated = 0
    for csv_file in args.csv_files:
        migrated = migrate_csv_file(csv_file, db)
        total_migrated += migrated
    
    logger.info(f"Total migration completed: {total_migrated} records migrated")
    
    # Show some statistics
    try:
        latest = db.get_latest_supply_data()
        if latest:
            logger.info(f"Latest record: Block {latest.get('layer_block_height')} at {latest.get('collection_time')}")
        
        history = db.get_supply_data_history(limit=5)
        logger.info(f"Total records in database: {len(history)} (showing last 5)")
        
    except Exception as e:
        logger.error(f"Error getting migration statistics: {e}")

if __name__ == '__main__':
    main() 