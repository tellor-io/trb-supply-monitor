# Supply Data Database Integration

## Overview

The supply data collection system has been successfully integrated with the database. Supply data is now stored in a dedicated `supply_data` table alongside the existing active balance tracking.

## Key Changes

### 1. Database Schema
- **New table**: `supply_data` - stores all supply collector metrics
- **Indexes**: Added for performance on `collection_time`, `layer_block_height`, and `collection_run_id`
- **Foreign key**: Links to `collection_runs` table for coordinated collections

### 2. Enhanced Supply Collector
- **Database storage**: Supply data is now saved to database by default
- **CSV compatibility**: Still supports CSV output for backward compatibility
- **Integrated queries**: Uses database for historical lookups (24-hour comparisons, etc.)

### 3. New Features
- **Historical queries**: Query supply data by time range, block height, etc.
- **Data migration**: Script to import existing CSV data
- **Combined collection**: Supply and balance data can be linked to collection runs

## Usage

### Basic Supply Collection
```bash
# Collect current data (saves to database + CSV)
python -m src.tellor_supply_analytics.supply_collector

# Database only (no CSV)
python -m src.tellor_supply_analytics.supply_collector --no-csv

# Custom database path
python -m src.tellor_supply_analytics.supply_collector --db-path custom.db
```

### Migration from CSV
```bash
# Migrate existing CSV data to database
python migrate_csv_to_db.py --csv-files supply_data_all.csv

# Dry run to see what would be migrated
python migrate_csv_to_db.py --dry-run
```

### Database Queries
```python
from src.tellor_supply_analytics.database import BalancesDatabase

db = BalancesDatabase()

# Get latest supply data
latest = db.get_latest_supply_data()

# Get historical data
history = db.get_supply_data_history(limit=100)

# Get data by time range
from datetime import datetime, timedelta
end_time = datetime.now()
start_time = end_time - timedelta(days=7)
recent = db.get_supply_data_by_timerange(start_time.isoformat(), end_time.isoformat())

# Match supply data with collection runs
matched = db.get_matched_collection_data(collection_run_id)
```

## Database Structure

### Supply Data Table
```sql
CREATE TABLE supply_data (
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
);
```

## Current Status

✅ **Database integration**: Complete and tested  
✅ **CSV migration**: 101 historical records migrated  
✅ **Backward compatibility**: CSV output still supported  
✅ **Active balance integration**: Both systems use same database  
✅ **Historical queries**: Database-powered lookups working  

### Statistics
- **Supply records**: 103+ (including migrated historical data)
- **Balance collections**: 11+ (existing active balance data)
- **Database**: `tellor_balances.db` (shared between systems)

## Benefits

1. **Centralized storage**: All data in one database
2. **Better performance**: Indexed queries vs CSV scanning
3. **Relational data**: Link supply data to balance collections
4. **Historical analysis**: Easy time-range and block-height queries
5. **Data integrity**: Database constraints and transactions
6. **Scalability**: Handles large datasets efficiently

## Migration Notes

- Existing CSV files remain functional
- Database storage is additive (doesn't replace CSV initially)
- Use `--no-csv` flag to disable CSV output once confident in database
- Migration script preserves all historical data with proper type conversion

## Future Enhancements

- Link supply data to specific collection runs
- Dashboard integration for combined supply + balance views
- API endpoints for historical data queries
- Automated data archival and cleanup 