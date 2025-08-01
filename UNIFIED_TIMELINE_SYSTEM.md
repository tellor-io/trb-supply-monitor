# Unified Timeline System for Tellor Supply Analytics

## Overview

The Unified Timeline System redesigns the data collection architecture to use **Ethereum block timestamps as the primary timeline** by which all data is measured and organized. This ensures temporal consistency across all metrics and enables rich historical analysis for frontend charts and graphs.

## Design Goals Achieved

✅ **Ethereum block timestamp as the ruler**: All data is organized by Ethereum block timestamps  
✅ **Unified collection**: For any unique Ethereum block timestamp, all data columns are populated  
✅ **Temporal consistency**: Bridge data, supply data, and balance data are coordinated  
✅ **Historical analysis**: Rich data available for frontend charts and time-series analysis  
✅ **Data completeness tracking**: System tracks how complete each data collection is  

## Architecture

### Database Schema

#### New Tables

1. **`unified_snapshots`** - Core table with Ethereum block timestamp as primary timeline
   - `eth_block_number` - Ethereum block number
   - `eth_block_timestamp` - **Primary timeline ruler** (UNIQUE)
   - `eth_block_datetime` - Human-readable timestamp
   - Bridge data: `bridge_balance_trb`
   - Layer data: `layer_block_height`, `layer_total_supply_trb`, etc.
   - Staking data: `not_bonded_tokens`, `bonded_tokens`
   - Balance summary: `total_addresses`, `total_trb_balance`, etc.
   - Metadata: `data_completeness_score` (0-1)

2. **`unified_balance_snapshots`** - Individual address balances linked to Ethereum timestamps
   - `eth_block_timestamp` - Links to unified_snapshots
   - `address`, `account_type`, `loya_balance`, `loya_balance_trb`

### Core Components

1. **`UnifiedDataCollector`** - Main coordinator class
2. **Enhanced Database Methods** - New methods for unified operations
3. **Unified API Endpoints** - New REST endpoints for timeline data
4. **Runner Scripts** - Tools for collection and monitoring

## Usage

### 1. Basic Unified Collection

```bash
# Collect data for the last 24 hours
python run_unified_collection.py

# Collect data for specific time range
python run_unified_collection.py --hours-back 48 --block-interval 3600

# Show current status
python run_unified_collection.py --summary
```

### 2. Continuous Monitoring

```bash
# Run continuous collection every hour
python run_unified_collection.py --monitor --interval 3600

# Debug mode with detailed logging
python run_unified_collection.py --monitor --debug
```

### 3. Data Backfill

```bash
# Fill in missing data for existing snapshots
python run_unified_collection.py --backfill

# Limit backfill to specific number of snapshots
python run_unified_collection.py --backfill --max-backfill 10
```

### 4. API Access

#### Get Timeline Data for Charts
```bash
# Get 24 hours of timeline data
curl "http://localhost:8001/api/unified/timeline?hours_back=24"

# Get only complete data (score >= 0.8)
curl "http://localhost:8001/api/unified/timeline?hours_back=48&min_completeness=0.8"
```

#### Get Specific Snapshot
```bash
# Get data for specific Ethereum timestamp
curl "http://localhost:8001/api/unified/snapshot/1703788800"

# Get balances for specific timestamp
curl "http://localhost:8001/api/unified/balances/1703788800"
```

#### Trigger Collection
```bash
# Trigger unified collection via API
curl -X POST "http://localhost:8001/api/unified/collect?hours_back=6&max_blocks=20"
```

## Data Collection Process

### 1. Ethereum-Driven Timeline

The system starts with Ethereum blocks as the reference point:

1. **Query latest Ethereum blocks** - Get recent block numbers and timestamps
2. **Skip existing timestamps** - Avoid duplicate work by checking existing data
3. **Target specific intervals** - Collect data at configured intervals (e.g., hourly)

### 2. Coordinated Data Collection

For each Ethereum timestamp, collect:

- **Bridge Balance**: TRB balance in bridge contract at that exact Ethereum block
- **Layer Supply Data**: Tellor Layer supply metrics from corresponding time
- **Balance Data**: Active address balances from Tellor Layer
- **Staking Data**: Bonded/unbonded token amounts

### 3. Data Completeness Scoring

Each snapshot gets a completeness score (0-1) based on available data fields:
- **1.0**: All data fields populated
- **0.7**: Most data available, some fields missing
- **0.0**: Only basic timestamp data

### 4. Incremental Updates

The system supports:
- **Backfill**: Fill missing data for existing timestamps
- **Incremental collection**: Add new data without duplicates
- **Partial updates**: Update specific fields for existing snapshots

## Frontend Integration

### Timeline Visualization

The unified system enables rich frontend charts:

```javascript
// Fetch timeline data
const response = await fetch('/api/unified/timeline?hours_back=24');
const data = await response.json();

// data.timeline contains array of snapshots with:
// - eth_timestamp (x-axis for all charts)
// - bridge_balance_trb (bridge balance over time)
// - layer_total_supply_trb (supply changes)
// - total_trb_balance (active balance changes)
// - data_completeness_score (data quality indicator)
```

### Chart Examples

1. **Supply Over Time**: `layer_total_supply_trb` vs `eth_timestamp`
2. **Bridge Balance Changes**: `bridge_balance_trb` vs `eth_timestamp`  
3. **Active Balance Trends**: `total_trb_balance` vs `eth_timestamp`
4. **Staking Metrics**: `bonded_tokens` + `not_bonded_tokens` vs `eth_timestamp`
5. **Data Quality**: `data_completeness_score` to show collection health

### Historical Analysis

```javascript
// Compare current vs historical values
const current = data.timeline[0];  // Most recent
const historical = data.timeline[23]; // 24 hours ago

const supplyChange = current.layer_total_supply_trb - historical.layer_total_supply_trb;
const bridgeChange = current.bridge_balance_trb - historical.bridge_balance_trb;
```

## Configuration

### Environment Variables

```bash
# Ethereum RPC (primary timeline source)
ETHEREUM_RPC_URL=https://rpc.sepolia.org

# Contract addresses
SEPOLIA_TRB_CONTRACT=0x80fc34a2f9FfE86F41580F47368289C402DEc660
SEPOLIA_BRIDGE_CONTRACT=0x5acb5977f35b1A91C4fE0F4386eB669E046776F2

# Tellor Layer RPC
TELLOR_LAYER_RPC_URL=https://node-palmito.tellorlayer.com/rpc/
LAYER_GRPC_URL=https://node-palmito.tellorlayer.com
```

### Collection Parameters

- `--hours-back`: How far back to collect data (default: 24)
- `--block-interval`: Target interval between Ethereum blocks (default: 3600 seconds)
- `--max-blocks`: Maximum blocks to process per run (default: 50)
- `--min-completeness`: Minimum completeness score to consider (default: 0.0)

## Monitoring and Health

### Data Quality Metrics

1. **Completeness Score**: Percentage of fields populated
2. **Collection Coverage**: Time range covered by data
3. **Update Frequency**: How often new data is collected
4. **Backfill Status**: Number of incomplete snapshots

### Health Checks

```bash
# System status
curl "http://localhost:8001/api/status"

# Unified data summary
curl "http://localhost:8001/api/unified/summary"

# Incomplete snapshots (need backfill)
curl "http://localhost:8001/api/unified/incomplete"
```

### Logs

- **Application logs**: `logs/unified_collection.log`
- **Debug mode**: `--debug` flag for detailed logging
- **Error tracking**: Failed collections logged with context

## Migration from Legacy System

### Backward Compatibility

The unified system maintains full backward compatibility:
- **Legacy endpoints**: All existing API endpoints still work
- **Legacy tables**: `balance_snapshots`, `collection_runs`, `supply_data` unchanged
- **Gradual migration**: Can run both systems in parallel

### Migration Steps

1. **Start unified collection**: Begin collecting unified data
2. **Verify data quality**: Check completeness scores and coverage
3. **Update frontend**: Gradually switch to unified timeline endpoints
4. **Monitor performance**: Ensure unified system meets requirements
5. **Deprecate legacy**: Once confident, reduce legacy collection frequency

### Data Consistency

- **Cross-validation**: Compare unified vs legacy data for accuracy
- **Overlap period**: Run both systems to ensure data integrity
- **Rollback capability**: Can fall back to legacy system if issues arise

## Performance Considerations

### Optimization Strategies

1. **Batch processing**: Collect multiple blocks in single run
2. **Incremental updates**: Only collect missing data
3. **Rate limiting**: Avoid overwhelming RPC endpoints
4. **Database indexing**: Optimized queries on eth_timestamp
5. **Parallel collection**: Can run multiple collection processes

### Resource Usage

- **Database size**: Unified tables add ~30% storage overhead
- **RPC calls**: More coordinated but similar total volume
- **Memory usage**: Minimal increase due to better organization
- **CPU usage**: Slight increase due to coordination logic

## Troubleshooting

### Common Issues

1. **Ethereum RPC unavailable**: System gracefully falls back
2. **Layer RPC timeout**: Retries with exponential backoff
3. **Incomplete data**: Tracked and backfilled automatically
4. **Timestamp gaps**: System detects and fills missing periods

### Debug Commands

```bash
# Detailed logging
python run_unified_collection.py --debug

# Check specific timestamp
python -c "
from src.tellor_supply_analytics.database import BalancesDatabase
db = BalancesDatabase()
print(db.get_unified_snapshot_by_eth_timestamp(1703788800))
"

# Manual backfill
python run_unified_collection.py --backfill --max-backfill 5 --debug
```

### Log Analysis

Look for these log patterns:
- `Saved unified snapshot for ETH block X` - Successful collection
- `Failed to collect data for ETH block X` - Collection failure
- `Completeness score 0.XX` - Data quality indicator
- `Found X Ethereum blocks to process` - Collection scope

## Future Enhancements

### Planned Features

1. **Historical Layer Data**: Collect historical Tellor Layer data by block height
2. **Cross-chain Support**: Extend to mainnet Ethereum when available
3. **Real-time Streaming**: WebSocket support for live data updates
4. **Advanced Analytics**: Statistical analysis and anomaly detection
5. **Data Export**: CSV/JSON export functionality for unified data

### Scalability Improvements

1. **Distributed Collection**: Multiple collectors for different time ranges
2. **Data Partitioning**: Partition large tables by time periods
3. **Caching Layer**: Redis cache for frequently accessed data
4. **API Rate Limiting**: Protect against high-frequency requests

---

## Quick Start Guide

### 1. Initialize the System

```bash
# Test the unified collector
python run_unified_collection.py --summary

# Run a small collection test
python run_unified_collection.py --hours-back 2 --max-blocks 5
```

### 2. Start Monitoring

```bash
# Begin continuous collection (every hour)
python run_unified_collection.py --monitor --interval 3600
```

### 3. Check the API

```bash
# View available unified data
curl "http://localhost:8001/api/unified/summary"

# Get timeline data for frontend
curl "http://localhost:8001/api/unified/timeline?hours_back=6"
```

### 4. Access Frontend

The unified timeline data is now available through the API endpoints and ready for frontend visualization with charts showing how all metrics change over time using Ethereum block timestamps as the unified ruler.

---

**The unified timeline system successfully transforms your data collection from arbitrary wall-clock-time-driven snapshots to a coherent, Ethereum-block-timestamp-driven historical record that enables rich temporal analysis and frontend visualizations.** 