#!/usr/bin/env python3
"""
Export Tellor Balance Database to CSV files for spreadsheet analysis
"""

import sqlite3
import csv
import pandas as pd
from pathlib import Path
from datetime import datetime

DATABASE_FILE = 'tellor_balances.db'

def export_to_csv():
    """Export all database tables to CSV files."""
    
    if not Path(DATABASE_FILE).exists():
        print(f"Error: Database file {DATABASE_FILE} not found!")
        return
    
    # Create exports directory
    exports_dir = Path("database_exports")
    exports_dir.mkdir(exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    with sqlite3.connect(DATABASE_FILE) as conn:
        # Export balance_snapshots table (legacy)
        print("Exporting balance_snapshots...")
        cursor = conn.execute("SELECT * FROM balance_snapshots ORDER BY snapshot_time DESC")
        columns = [desc[0] for desc in cursor.description]
        
        with open(exports_dir / f"balance_snapshots_{timestamp}.csv", 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(columns)
            writer.writerows(cursor.fetchall())
        
        # Export collection_runs table (legacy)
        print("Exporting collection_runs...")
        cursor = conn.execute("SELECT * FROM collection_runs ORDER BY run_time DESC")
        columns = [desc[0] for desc in cursor.description]
        
        with open(exports_dir / f"collection_runs_{timestamp}.csv", 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(columns)
            writer.writerows(cursor.fetchall())
        
        # Export supply_data table (NEW)
        print("Exporting supply_data...")
        try:
            cursor = conn.execute("SELECT * FROM supply_data ORDER BY collection_time DESC")
            columns = [desc[0] for desc in cursor.description]
            
            with open(exports_dir / f"supply_data_{timestamp}.csv", 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(columns)
                writer.writerows(cursor.fetchall())
        except sqlite3.OperationalError as e:
            print(f"  Warning: Could not export supply_data table: {e}")
        
        # Export unified_snapshots table (NEW)
        print("Exporting unified_snapshots...")
        try:
            cursor = conn.execute("SELECT * FROM unified_snapshots ORDER BY eth_block_timestamp DESC")
            columns = [desc[0] for desc in cursor.description]
            
            with open(exports_dir / f"unified_snapshots_{timestamp}.csv", 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(columns)
                writer.writerows(cursor.fetchall())
        except sqlite3.OperationalError as e:
            print(f"  Warning: Could not export unified_snapshots table: {e}")
        
        # Export unified_balance_snapshots table (NEW)
        print("Exporting unified_balance_snapshots...")
        try:
            cursor = conn.execute("SELECT * FROM unified_balance_snapshots ORDER BY eth_block_timestamp DESC")
            columns = [desc[0] for desc in cursor.description]
            
            with open(exports_dir / f"unified_balance_snapshots_{timestamp}.csv", 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(columns)
                writer.writerows(cursor.fetchall())
        except sqlite3.OperationalError as e:
            print(f"  Warning: Could not export unified_balance_snapshots table: {e}")
        
        # Export latest balances summary (legacy - from balance_snapshots)
        print("Exporting latest balances summary...")
        cursor = conn.execute("""
            SELECT 
                address,
                account_type,
                loya_balance,
                loya_balance_trb,
                snapshot_time
            FROM balance_snapshots 
            WHERE snapshot_time = (SELECT MAX(snapshot_time) FROM balance_snapshots)
            ORDER BY loya_balance_trb DESC
        """)
        columns = [desc[0] for desc in cursor.description]
        
        with open(exports_dir / f"latest_balances_{timestamp}.csv", 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(columns)
            writer.writerows(cursor.fetchall())
        
        # Export latest unified balances summary (NEW - from unified_balance_snapshots)
        print("Exporting latest unified balances summary...")
        try:
            cursor = conn.execute("""
                SELECT 
                    address,
                    account_type,
                    loya_balance,
                    loya_balance_trb,
                    eth_block_timestamp
                FROM unified_balance_snapshots 
                WHERE eth_block_timestamp = (SELECT MAX(eth_block_timestamp) FROM unified_balance_snapshots)
                ORDER BY loya_balance_trb DESC
            """)
            columns = [desc[0] for desc in cursor.description]
            
            with open(exports_dir / f"latest_unified_balances_{timestamp}.csv", 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(columns)
                writer.writerows(cursor.fetchall())
        except sqlite3.OperationalError as e:
            print(f"  Warning: Could not export latest unified balances: {e}")
        
        # Export account type summary (legacy)
        print("Exporting account type summary...")
        cursor = conn.execute("""
            SELECT 
                account_type,
                COUNT(*) as address_count,
                SUM(loya_balance) as total_loya,
                SUM(loya_balance_trb) as total_trb,
                AVG(loya_balance_trb) as avg_trb,
                MAX(loya_balance_trb) as max_trb
            FROM balance_snapshots 
            WHERE snapshot_time = (SELECT MAX(snapshot_time) FROM balance_snapshots)
            GROUP BY account_type
            ORDER BY total_trb DESC
        """)
        columns = [desc[0] for desc in cursor.description]
        
        with open(exports_dir / f"account_types_summary_{timestamp}.csv", 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(columns)
            writer.writerows(cursor.fetchall())
        
        # Export unified account type summary (NEW)
        print("Exporting unified account type summary...")
        try:
            cursor = conn.execute("""
                SELECT 
                    account_type,
                    COUNT(*) as address_count,
                    SUM(loya_balance) as total_loya,
                    SUM(loya_balance_trb) as total_trb,
                    AVG(loya_balance_trb) as avg_trb,
                    MAX(loya_balance_trb) as max_trb
                FROM unified_balance_snapshots 
                WHERE eth_block_timestamp = (SELECT MAX(eth_block_timestamp) FROM unified_balance_snapshots)
                GROUP BY account_type
                ORDER BY total_trb DESC
            """)
            columns = [desc[0] for desc in cursor.description]
            
            with open(exports_dir / f"unified_account_types_summary_{timestamp}.csv", 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(columns)
                writer.writerows(cursor.fetchall())
        except sqlite3.OperationalError as e:
            print(f"  Warning: Could not export unified account types summary: {e}")
        
        # Export latest supply data summary (NEW)
        print("Exporting latest supply data summary...")
        try:
            cursor = conn.execute("""
                SELECT 
                    collection_time,
                    eth_block_number,
                    eth_block_timestamp,
                    bridge_balance_trb,
                    layer_block_height,
                    layer_total_supply_trb,
                    not_bonded_tokens,
                    bonded_tokens,
                    free_floating_trb
                FROM supply_data 
                ORDER BY collection_time DESC 
                LIMIT 1
            """)
            columns = [desc[0] for desc in cursor.description]
            
            with open(exports_dir / f"latest_supply_data_{timestamp}.csv", 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(columns)
                writer.writerows(cursor.fetchall())
        except sqlite3.OperationalError as e:
            print(f"  Warning: Could not export latest supply data: {e}")
    
    print(f"\nExport complete! Files saved to {exports_dir}/")
    print("Files exported:")
    for file in exports_dir.glob(f"*_{timestamp}.csv"):
        print(f"  - {file.name}")

def show_database_info():
    """Show basic information about the database."""
    
    if not Path(DATABASE_FILE).exists():
        print(f"Error: Database file {DATABASE_FILE} not found!")
        return
    
    with sqlite3.connect(DATABASE_FILE) as conn:
        # Show table info
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        
        print("Database Tables:")
        for table in tables:
            table_name = table[0]
            cursor = conn.execute(f"SELECT COUNT(*) FROM {table_name}")
            count = cursor.fetchone()[0]
            print(f"  - {table_name}: {count:,} rows")
        
        # Show latest collection info (legacy)
        cursor = conn.execute("SELECT * FROM collection_runs ORDER BY run_time DESC LIMIT 1")
        latest = cursor.fetchone()
        if latest:
            print(f"\nLatest Collection (Legacy):")
            print(f"  - Time: {latest[1]}")
            print(f"  - Total Addresses: {latest[2]:,}")
            print(f"  - With Balance: {latest[3]:,}")
            print(f"  - Total TRB: {latest[5]:,.2f}")
            
            # Show additional fields if they exist
            if len(latest) > 6:
                print(f"  - Bridge Balance TRB: {latest[6]:.2f}" if latest[6] else "  - Bridge Balance TRB: N/A")
            if len(latest) > 7:
                print(f"  - Layer Block Height: {latest[7]}" if latest[7] else "  - Layer Block Height: N/A")
            if len(latest) > 8:
                print(f"  - Free Floating TRB: {latest[8]:.2f}" if latest[8] else "  - Free Floating TRB: N/A")
        
        # Show latest supply data info (NEW)
        try:
            cursor = conn.execute("SELECT * FROM supply_data ORDER BY collection_time DESC LIMIT 1")
            latest_supply = cursor.fetchone()
            if latest_supply:
                print(f"\nLatest Supply Data:")
                print(f"  - Collection Time: {latest_supply[1]}")
                print(f"  - ETH Block: {latest_supply[2]}")
                print(f"  - Layer Block Height: {latest_supply[5]}")
                print(f"  - Bridge Balance TRB: {latest_supply[4]:.2f}" if latest_supply[4] else "  - Bridge Balance TRB: N/A")
                print(f"  - Total Supply TRB: {latest_supply[7]:.2f}" if latest_supply[7] else "  - Total Supply TRB: N/A")
                print(f"  - Free Floating TRB: {latest_supply[10]:.2f}" if latest_supply[10] else "  - Free Floating TRB: N/A")
        except sqlite3.OperationalError:
            print("\nNo supply data table found")
        
        # Show latest unified snapshot info (NEW)
        try:
            cursor = conn.execute("SELECT * FROM unified_snapshots ORDER BY eth_block_timestamp DESC LIMIT 1")
            latest_unified = cursor.fetchone()
            if latest_unified:
                print(f"\nLatest Unified Snapshot:")
                print(f"  - ETH Block: {latest_unified[1]}")
                print(f"  - ETH Timestamp: {latest_unified[2]}")
                print(f"  - ETH DateTime: {latest_unified[3]}")
                try:
                    completeness = float(latest_unified[18]) if latest_unified[18] is not None else 0.0
                    print(f"  - Data Completeness: {completeness:.1%}")
                except (ValueError, TypeError):
                    print("  - Data Completeness: N/A")
                print(f"  - Total Addresses: {latest_unified[11]:,}" if latest_unified[11] else "  - Total Addresses: N/A")
                print(f"  - Total TRB Balance: {latest_unified[13]:.2f}" if latest_unified[13] else "  - Total TRB Balance: N/A")
        except sqlite3.OperationalError:
            print("\nNo unified snapshots table found")

if __name__ == "__main__":
    print("Tellor Database Export Tool")
    print("=" * 40)
    
    show_database_info()
    print("\n" + "=" * 40)
    export_to_csv()