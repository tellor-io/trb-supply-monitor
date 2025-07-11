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
        # Export balance_snapshots table
        print("Exporting balance_snapshots...")
        cursor = conn.execute("SELECT * FROM balance_snapshots ORDER BY snapshot_time DESC")
        columns = [desc[0] for desc in cursor.description]
        
        with open(exports_dir / f"balance_snapshots_{timestamp}.csv", 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(columns)
            writer.writerows(cursor.fetchall())
        
        # Export collection_runs table
        print("Exporting collection_runs...")
        cursor = conn.execute("SELECT * FROM collection_runs ORDER BY run_time DESC")
        columns = [desc[0] for desc in cursor.description]
        
        with open(exports_dir / f"collection_runs_{timestamp}.csv", 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(columns)
            writer.writerows(cursor.fetchall())
        
        # Export latest balances summary
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
        
        # Export account type summary
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
        
        # Show latest collection info
        cursor = conn.execute("SELECT * FROM collection_runs ORDER BY run_time DESC LIMIT 1")
        latest = cursor.fetchone()
        if latest:
            print(f"\nLatest Collection:")
            print(f"  - Time: {latest[1]}")
            print(f"  - Total Addresses: {latest[2]:,}")
            print(f"  - With Balance: {latest[3]:,}")
            print(f"  - Total TRB: {latest[5]:,.2f}")

if __name__ == "__main__":
    print("Tellor Database Export Tool")
    print("=" * 40)
    
    show_database_info()
    print("\n" + "=" * 40)
    export_to_csv()