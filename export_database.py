#!/usr/bin/env python3
"""
Export Tellor Balance Database to CSV files for spreadsheet analysis
"""

import sqlite3
import csv
import signal
import sys
import logging
from pathlib import Path
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

DATABASE_FILE = 'tellor_balances.db'

def signal_handler(signum, frame):
    """Handle interrupt signals gracefully."""
    logger.info("\nReceived interrupt signal. Shutting down gracefully...")
    sys.exit(0)

def export_table_to_csv(conn, table_name, exports_dir, timestamp, order_by=None):
    """
    Export a single table to CSV.
    
    Args:
        conn: SQLite connection
        table_name: Name of the table to export
        exports_dir: Directory to save exports
        timestamp: Timestamp string for filename
        order_by: Optional ORDER BY clause
    """
    try:
        query = f"SELECT * FROM {table_name}"
        if order_by:
            query += f" ORDER BY {order_by}"
            
        cursor = conn.execute(query)
        columns = [desc[0] for desc in cursor.description]
        
        output_file = exports_dir / f"{table_name}_{timestamp}.csv"
        with open(output_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(columns)
            writer.writerows(cursor.fetchall())
            
        logger.info(f"Exported {table_name} to {output_file}")
        return True
        
    except sqlite3.OperationalError as e:
        logger.warning(f"Could not export {table_name}: {e}")
        return False
    except Exception as e:
        logger.error(f"Error exporting {table_name}: {e}")
        return False

def export_to_csv():
    """Export all database tables to CSV files."""
    
    if not Path(DATABASE_FILE).exists():
        logger.error(f"Database file {DATABASE_FILE} not found!")
        return
    
    # Create exports directory
    exports_dir = Path("database_exports")
    exports_dir.mkdir(exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    try:
        with sqlite3.connect(DATABASE_FILE) as conn:
            # Define tables and their sorting
            tables_to_export = [
                ("unified_snapshots", "eth_block_timestamp DESC"),
                ("unified_balance_snapshots", "eth_block_timestamp DESC"),
            ]
            
            # Export each table
            for table_name, order_by in tables_to_export:
                export_table_to_csv(conn, table_name, exports_dir, timestamp, order_by)
            
            # Export latest unified balances summary
            logger.info("Exporting latest unified balances summary...")
            latest_query = """
                SELECT 
                    address,
                    account_type,
                    loya_balance,
                    loya_balance_trb,
                    eth_block_timestamp
                FROM unified_balance_snapshots 
                WHERE eth_block_timestamp = (
                    SELECT MAX(eth_block_timestamp) 
                    FROM unified_balance_snapshots
                )
                ORDER BY loya_balance_trb DESC
            """
            cursor = conn.execute(latest_query)
            columns = [desc[0] for desc in cursor.description]
            
            with open(exports_dir / f"latest_balances_{timestamp}.csv", 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(columns)
                writer.writerows(cursor.fetchall())
            
            # Export account type summary
            logger.info("Exporting account type summary...")
            summary_query = """
                SELECT 
                    account_type,
                    COUNT(*) as address_count,
                    SUM(loya_balance) as total_loya,
                    SUM(loya_balance_trb) as total_trb,
                    AVG(loya_balance_trb) as avg_trb,
                    MAX(loya_balance_trb) as max_trb
                FROM unified_balance_snapshots 
                WHERE eth_block_timestamp = (
                    SELECT MAX(eth_block_timestamp) 
                    FROM unified_balance_snapshots
                )
                GROUP BY account_type
                ORDER BY total_trb DESC
            """
            cursor = conn.execute(summary_query)
            columns = [desc[0] for desc in cursor.description]
            
            with open(exports_dir / f"account_summary_{timestamp}.csv", 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(columns)
                writer.writerows(cursor.fetchall())
        
        logger.info(f"\nExport complete! Files saved to {exports_dir}/")
        logger.info("Files exported:")
        for file in exports_dir.glob(f"*_{timestamp}.csv"):
            logger.info(f"  - {file.name}")
            
    except KeyboardInterrupt:
        logger.info("\nExport interrupted by user.")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Unexpected error during export: {e}")
        sys.exit(1)

def show_database_info():
    """Show basic information about the database."""
    
    if not Path(DATABASE_FILE).exists():
        logger.error(f"Database file {DATABASE_FILE} not found!")
        return
    
    try:
        with sqlite3.connect(DATABASE_FILE) as conn:
            # Show table info
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = cursor.fetchall()
            
            logger.info("Database Tables:")
            for table in tables:
                table_name = table[0]
                cursor = conn.execute(f"SELECT COUNT(*) FROM {table_name}")
                count = cursor.fetchone()[0]
                logger.info(f"  - {table_name}: {count:,} rows")
            
            # Show latest unified snapshot info
            cursor = conn.execute("""
                SELECT 
                    eth_block_number,
                    eth_block_timestamp,
                    eth_block_datetime,
                    bridge_balance_trb,
                    layer_block_height,
                    layer_total_supply_trb,
                    total_addresses,
                    total_trb_balance,
                    data_completeness_score
                FROM unified_snapshots 
                ORDER BY eth_block_timestamp DESC 
                LIMIT 1
            """)
            latest = cursor.fetchone()
            
            if latest:
                logger.info("\nLatest Unified Snapshot:")
                logger.info(f"  - ETH Block: {latest[0]}")
                logger.info(f"  - ETH DateTime: {latest[2]}")
                logger.info(f"  - Bridge Balance: {latest[3]:.2f} TRB" if latest[3] else "  - Bridge Balance: N/A")
                logger.info(f"  - Layer Block: {latest[4]}")
                logger.info(f"  - Total Supply: {latest[5]:.2f} TRB" if latest[5] else "  - Total Supply: N/A")
                logger.info(f"  - Total Addresses: {latest[6]:,}" if latest[6] else "  - Total Addresses: N/A")
                logger.info(f"  - Total TRB Balance: {latest[7]:.2f}" if latest[7] else "  - Total TRB Balance: N/A")
                logger.info(f"  - Data Completeness: {latest[8]:.1%}" if latest[8] else "  - Data Completeness: N/A")
                
    except KeyboardInterrupt:
        logger.info("\nDatabase info display interrupted by user.")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Error showing database info: {e}")
        sys.exit(1)

def main():
    """Main function."""
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)   # Ctrl+C
    signal.signal(signal.SIGTERM, signal_handler)  # Termination request
    
    logger.info("Tellor Database Export Tool")
    logger.info("=" * 40)
    
    show_database_info()
    logger.info("\n" + "=" * 40)
    export_to_csv()

if __name__ == "__main__":
    main()