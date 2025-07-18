# Data Management for Tellor Supply Monitor

This guide explains how to manage data in the Tellor Supply Monitor database, including removing and re-collecting data when issues are detected.

## Overview

Sometimes data collection may result in inconsistent or incorrect data due to various factors:
- RPC endpoint issues during collection
- Network timeouts
- Blockchain reorganizations
- Data processing errors

The system provides tools to identify and fix these data quality issues by allowing you to remove and re-collect data for specific Tellor Layer blocks.

## Command Line Tools

### List Layer Blocks in Database

View all Tellor Layer blocks that have data in the database:

```bash
python -m src.tellor_supply_analytics.unified_collector --list-layer-blocks --list-limit 50
```

This shows:
- Layer block height
- Layer block timestamp
- Corresponding Ethereum block
- Data completeness score
- Collection time

### Remove Data for a Specific Layer Block

Remove all data associated with a specific Tellor Layer block:

```bash
python -m src.tellor_supply_analytics.unified_collector --remove-layer-block 12345
```

This will:
- Remove the unified snapshot for that layer block
- Remove all associated balance data
- Remove any other related data

### Re-collect Data for a Layer Block

Re-collect data for a specific Tellor Layer block:

```bash
python -m src.tellor_supply_analytics.unified_collector --rerun-layer-block 12345
```

This will:
- Find the corresponding Ethereum timestamp
- Collect supply data from Tellor Layer
- Collect balance data from Tellor Layer
- Collect bridge data from Ethereum
- Save a new unified snapshot

### Remove and Re-collect (Recommended)

The safest option combines both operations:

```bash
python -m src.tellor_supply_analytics.unified_collector --remove-and-rerun 12345
```

This ensures old data is completely removed before collecting new data.

## API Endpoints

### List Layer Blocks

```http
GET /api/unified/layer-blocks?limit=100
```

Response:
```json
{
  "layer_blocks": [
    {
      "layer_block_height": 12345,
      "layer_block_timestamp": 1704067200,
      "eth_block_number": 18850000,
      "eth_block_timestamp": 1704067180,
      "data_completeness_score": 1.0,
      "snapshot_id": 123,
      "collection_time": "2024-01-01T00:00:00"
    }
  ],
  "count": 1,
  "limit": 100
}
```

### Remove Layer Block Data

```http
DELETE /api/unified/layer-block/12345
```

Response:
```json
{
  "status": "success",
  "message": "Successfully removed data for Tellor Layer block 12345",
  "layer_block_height": 12345
}
```

### Re-collect Layer Block Data

```http
POST /api/unified/layer-block/12345/rerun
```

Response:
```json
{
  "status": "success",
  "message": "Successfully re-collected data for Tellor Layer block 12345",
  "layer_block_height": 12345
}
```

### Remove and Re-collect

```http
POST /api/unified/layer-block/12345/remove-and-rerun
```

Response:
```json
{
  "status": "success",
  "message": "Successfully removed and re-collected data for Tellor Layer block 12345",
  "layer_block_height": 12345
}
```

## Use Cases

### 1. Data Quality Issues

If you notice inconsistent data in your charts or reports:

1. List recent layer blocks to identify the problematic block
2. Remove and re-collect data for that specific block
3. Verify the data looks correct

### 2. RPC Endpoint Problems

If data collection failed due to RPC issues:

1. Fix the RPC endpoint configuration
2. Identify the blocks that were collected during the problem period
3. Remove and re-collect those blocks

### 3. Blockchain Reorganizations

If there was a blockchain reorganization affecting your data:

1. Identify the affected block range
2. Remove data for all affected blocks
3. Re-collect the data with the correct blockchain state

### 4. Missing Data

If some layer blocks are missing data:

1. Use the backfill command to identify incomplete data
2. Or manually re-collect specific blocks

## Best Practices

### 1. Always Use Remove-and-Rerun

The `--remove-and-rerun` option is safest because it ensures:
- Old data is completely removed
- No partial data remains
- Fresh data is collected
- Database consistency is maintained

### 2. Verify Data After Collection

After re-collecting data, check:
- Data completeness score is 1.0
- Supply numbers look reasonable
- Balance counts are consistent
- Timestamps are aligned

### 3. Monitor Data Quality

Regularly check for:
- Incomplete snapshots (completeness score < 1.0)
- Misaligned timestamps between Ethereum and Tellor Layer
- Unexpected jumps or drops in supply data
- Missing recent data

### 4. Keep Logs

The unified collector logs all operations, so you can:
- Track what was removed and when
- Debug collection issues
- Audit data changes

## Example Workflow

Here's a typical workflow for fixing bad data:

```bash
# 1. List recent layer blocks to identify issues
python -m src.tellor_supply_analytics.unified_collector --list-layer-blocks --list-limit 20

# 2. Check data completeness
python -m src.tellor_supply_analytics.unified_collector --summary

# 3. Remove and re-collect problematic block
python -m src.tellor_supply_analytics.unified_collector --remove-and-rerun 12345

# 4. Verify the fix
python -m src.tellor_supply_analytics.unified_collector --list-layer-blocks --list-limit 5
```

## Database Backup

Before performing bulk data operations, consider backing up your database:

```bash
cp tellor_balances.db tellor_balances_backup_$(date +%Y%m%d_%H%M%S).db
```

This allows you to restore if something goes wrong during data management operations.

## Troubleshooting

### Collection Fails for Specific Block

If re-collection fails for a specific block:

1. Check RPC endpoints are accessible
2. Verify the block height exists on Tellor Layer
3. Check for sufficient disk space
4. Review logs for specific error messages

### Data Still Looks Wrong

If data still appears incorrect after re-collection:

1. Verify the block height corresponds to the correct time period
2. Check if there were any blockchain issues at that time
3. Compare with external data sources
4. Consider the possibility of correct but unexpected data

### Performance Issues

If data operations are slow:

1. Limit the number of blocks processed
2. Run operations during low-traffic periods
3. Monitor database size and performance
4. Consider database optimization

## Related Commands

- `--backfill`: Fill in missing data for incomplete snapshots
- `--cleanup`: Remove snapshots with misaligned timestamps
- `--summary`: Get overview of data collection status
- Standard collection: `--hours-back` and `--max-blocks` for regular data collection 