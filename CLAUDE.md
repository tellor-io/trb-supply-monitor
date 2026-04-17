# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Tellor Layer blockchain analytics system that collects and monitors token supply data from multiple blockchain sources. The system uses **Ethereum block timestamps as the primary timeline** for all data collection, ensuring temporal consistency across Tellor Layer, Ethereum bridge contracts, and historical data.

## Architecture

### Core Data Collection Philosophy

The system is built around a **unified timeline concept**:
- Ethereum blocks serve as the "ruler" by which everything is measured
- For any unique Ethereum block timestamp, all data columns must be populated
- Supports both historical backfill and real-time collection
- Tracks data completeness and supports incremental updates

### Key Components

1. **UnifiedDataCollector** (`src/tellor_supply_analytics/unified_collector.py`)
   - Main orchestrator that coordinates all data collection
   - Uses Ethereum block timestamps as the primary timeline
   - Collects supply data, bridge balances, and validator stakes for specific Ethereum blocks
   - Handles both historical backfill and real-time collection

2. **SupplyDataCollector** (`src/tellor_supply_analytics/supply_collector.py`)
   - Queries Tellor Layer using the `layerd` binary for block info and total supply
   - Queries Ethereum for TRB bridge contract balances using web3.py
   - Handles multiple bridge contract addresses based on block height
   - Writes data to CSV file: `supply_data.csv`

3. **EnhancedActiveBalancesCollector** (`src/tellor_supply_analytics/get_active_balances.py`)
   - Collects all active addresses and their balances from Tellor Layer
   - Queries staking module for bonded/not-bonded validators
   - Queries reporters to calculate total reporter power
   - Stores data in SQLite database: `tellor_balances.db`

4. **TellorLayerBlockFinder** (`src/tellor_supply_analytics/find_layer_block.py`)
   - Uses binary search to find Tellor Layer blocks matching Ethereum timestamps
   - Critical for maintaining temporal consistency across chains
   - Queries Tellor Layer RPC endpoints using Cosmos SDK format

5. **BalancesDatabase** (`src/tellor_supply_analytics/database.py`)
   - SQLite database manager for storing balance snapshots
   - Tables: `balance_snapshots`, `collection_runs`, `unified_snapshots`
   - Supports historical tracking and data completeness queries

6. **Web Dashboard** (`app.py`)
   - FastAPI application serving the monitoring dashboard
   - Displays balance analytics, supply metrics, and historical trends
   - Can run periodic balance collection in the background
   - Serves static files from `static/` and templates from `templates/`

### Data Flow

1. **Ethereum blocks** → Primary timeline anchor
2. **TellorLayerBlockFinder** → Find corresponding Tellor Layer blocks
3. **UnifiedDataCollector** → Coordinate collection at specific Ethereum blocks
4. **SupplyDataCollector** → Collect supply and bridge balance data
5. **EnhancedActiveBalancesCollector** → Collect validator and reporter data
6. **BalancesDatabase** → Store unified snapshots with all metrics

### Bridge Contract History

The system automatically switches between bridge contracts based on Tellor Layer block height:
- Layer height < 9569214: Uses `OLD_BRIDGE_CONTRACT_1`
- Layer height >= 9569214: Uses `CURRENT_BRIDGE_CONTRACT`

This is handled by `get_bridge_contract_for_height()` in both `supply_collector.py` and `unified_collector.py`.

## Development Commands

### Environment Setup

```bash
# Install uv (recommended package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies
uv sync

# Activate virtual environment
source .venv/bin/activate

# Install development dependencies
uv sync --extra dev
```

### Running the System

```bash
# Collect current data only
uv run tellor-supply-analytics

# Collect with historical backfill
uv run tellor-supply-analytics --historical

# Run unified collection (current Tellor Layer block only)
python run_unified_collection.py --current-block-only

# Run unified collection with interval (every 30 minutes)
python run_unified_collection.py --current-block-only --interval 1800

# Run in monitoring mode (collect current + fill gaps)
python run_unified_collection.py --monitor 1800

# Collect specific Ethereum block
python run_unified_collection.py --eth-block 20123456

# Collect specific Tellor Layer block
python run_unified_collection.py --layer-block 5730721

# Run web dashboard
python app.py

# Run web dashboard with background collection (every hour)
python app.py --collect-interval 3600
```

### Testing

```bash
# Run all tests
uv run pytest

# Run specific test
uv run pytest tests/test_get_bridge_balance.py

# Run with debug output
uv run tellor-supply-analytics --debug
```

### Code Quality

```bash
# Format code
uv run black src/
uv run isort src/

# Type checking
uv run mypy src/

# Code style (line length: 100)
uv run flake8 src/
```

## Configuration

### Required Environment Variables

Create a `.env` file with:

```bash
# See .env.example for a full template — copy it to .env and fill in your values.
# Do not commit .env; it is listed in .gitignore.
```

### Key Files

- `layerd` - Tellor Layer CLI binary (must be executable: `chmod +x ./layerd`)
- `supply_data.csv` - Output CSV with supply and bridge balance data
- `tellor_balances.db` - SQLite database with balance snapshots
- `bridgeAbi.json` - Bridge contract ABI for parsing events
- `example_bridge_deposits.csv` - Bridge deposit transactions for historical collection
- `example_bridge_withdrawals.csv` - Bridge withdrawal transactions

## Important Implementation Details

### Binary Search for Block Matching

The `TellorLayerBlockFinder` uses binary search to find Tellor Layer blocks that match Ethereum timestamps. This is critical because the two chains have different block times, and we need temporal consistency for accurate analytics.

### Database Migrations

The `BalancesDatabase` class includes migration logic (e.g., `migrate_add_reporter_power_column()`). When adding new fields to the unified snapshot, add migration methods to handle existing databases.

### Graceful Shutdown

The `run_unified_collection.py` script uses signal handlers to catch SIGINT/SIGTERM and shut down gracefully. Always check `shutdown_requested` flag in long-running loops.

### Discord Alerts

The system sends Discord webhook notifications for:
- Bonded tokens increases/decreases
- Alerts include percentage changes and block information
- Only sends if `DISCORD_WEBHOOK_URL` is configured

### RPC Error Handling

When querying historical blocks, the system expects `InvalidArgument` errors from RPC when blocks are too old. This is normal and handled gracefully - the system stops collection when it hits these errors.

## Troubleshooting

### `layerd` Binary Issues

If you get "layerd not found" errors:
1. Verify binary exists: `ls -la layerd`
2. Make executable: `chmod +x ./layerd`
3. Binary must be in project root directory

### RPC Connection Failures

- Check network connectivity to RPC endpoints
- Verify URLs in `.env` file are accessible
- Consider using alternative RPC providers (Infura, Alchemy) for production
- Some public RPCs have rate limits - add delays if needed

### Database Lock Issues

If you get SQLite "database is locked" errors:
- Only one collection process should run at a time
- Check for stuck processes: `ps aux | grep python`
- Close the web dashboard if running collections manually

### Virtual Environment

All Python scripts require the virtual environment to be activated:
```bash
source .venv/bin/activate
```

The `run_unified_collection.py` script includes checks to ensure it's running in the correct virtual environment.
