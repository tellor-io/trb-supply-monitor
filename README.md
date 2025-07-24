# Tellor Supply Analytics

A Python-based blockchain data collection system that gathers token supply information from multiple sources:

1. **Tellor Layer blockchain** - Block information and total supply data
2. **Ethereum Sepolia** - TRB bridge contract balances
3. **Historical data collection** - Going back in time until RPC limits are reached

## Features

- Automated data collection from multiple blockchain RPCs
- CSV export with timestamped supply data
- Historical data backfill capability
- Error handling for RPC limitations
- Configurable via environment variables

## Installation

### Option 1: Using uv (Recommended)

1. **Install uv** (if not already installed):
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

2. **Install the project and dependencies:**
   ```bash
   uv sync
   ```

3. **Activate the environment:**
   ```bash
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

### Option 2: Using pip

1. **Install the project in development mode:**
   ```bash
   pip install -e .
   ```

2. **Set up environment variables:**
   
   Copy the example environment file and configure it:
   ```bash
   cp .env.example .env
   ```
   
   Or create a `.env` file manually with the following configuration:
   ```bash
   # Tellor Layer RPC Configuration
   TELLOR_LAYER_RPC_URL=https://node-palmito.tellorlayer.com/rpc/
   
   # Ethereum RPC Configuration (Sepolia)
   ETHEREUM_RPC_URL=https://ethereum-sepolia-rpc.publicnode.com
   
   # Contract Addresses (Sepolia)
   SEPOLIA_TRB_CONTRACT=0x80fc34a2f9FfE86F41580F47368289C402DEc660
   SEPOLIA_BRIDGE_CONTRACT=0x5acb5977f35b1A91C4fE0F4386eB669E046776F2
   ```

3. **Ensure the `layerd` binary is executable:**
   ```bash
   chmod +x ./layerd
   ```

## Usage

### Basic Usage (Current Data Only)

Collect current supply data from all sources:

```bash
# Using uv run (recommended)
uv run tellor-supply-analytics

# Or activate the environment and run directly
source .venv/bin/activate
tellor-supply-analytics
```

Or run using the runner script:

```bash
python run_supply_analytics.py
```

Or run directly from the source:

```bash
python src/tellor_supply_analytics/supply_collector.py
```

### Historical Data Collection

Collect current data plus historical data going back in time:

```bash
# Using uv run (recommended)
uv run tellor-supply-analytics --historical

# Or with activated environment
tellor-supply-analytics --historical
```

Or using the runner script:

```bash
python run_supply_analytics.py --historical
```

### Monitoring Mode

Run continuous data collections every 3600 seconds:

```bash
# Using uv run (recommended)
uv run python run_unified_collections.py --monitor 3600


### Discord Alerts

The system supports Discord webhook notifications for important events. Currently, alerts are sent when:

- **Bonded Tokens Increase**: When the bonded tokens value increases compared to the previous measurement, showing the percentage increase.
- **Bonded Tokens Decrease**: When the bonded tokens value decreases compared to the previous measurement, showing the percentage decrease.

To enable Discord alerts:

1. Create a Discord webhook in your Discord server
2. Set the `DISCORD_WEBHOOK_URL` environment variable to your webhook URL
3. Run the collector (alerts work in both single-run and monitoring modes)

Example alert formats:
```
🚀 Bonded Tokens Increased!
Previous Bonded Tokens: 9,150,103,229
Current Bonded Tokens: 9,152,512,989
Increase: 2,409,760 (+0.03%)

Block Height: 4670804
Timestamp: Mon, 23 Jun 2025 19:02:49 GMT
```

```
📉 Bonded Tokens Decreased!
Previous Bonded Tokens: 9,152,512,989
Current Bonded Tokens: 9,150,103,229
Decrease: 2,409,760 (-0.03%)

Block Height: 4670805
Timestamp: Mon, 23 Jun 2025 19:03:49 GMT
```

### Debug Mode

Enable detailed logging for troubleshooting:

```bash
# Using uv run (recommended)  
uv run tellor-supply-analytics --debug

# Or with activated environment
tellor-supply-analytics --debug
```

Or using the runner script:

```bash
python run_supply_analytics.py --debug
```

## Output

The system creates a CSV file named `supply_data.csv` with the following columns:

| Column | Description |
|--------|-------------|
| `eth_block_number` | Ethereum block number |
| `eth_block_timestamp` | Unix timestamp of Ethereum block |
| `eth_block_datetime` | ISO datetime of Ethereum block |
| `bridge_balance_trb` | TRB balance in bridge contract (in TRB units) |
| `layer_block_height` | Tellor Layer block height |
| `layer_block_timestamp` | Unix timestamp of Tellor Layer block |
| `layer_total_supply_trb` | Total TRB supply on Tellor Layer (in TRB units) |

## System Architecture

### Goals Implemented

1. **Goal 1**: Query Tellor Layer for block information
   - Uses `layerd query block --type height <HEIGHT>` command
   - Extracts timestamp from block data

2. **Goal 2**: Query Tellor Layer for total supply
   - Uses `layerd query bank total-supply --height <HEIGHT>` command
   - Extracts loya denomination amounts

3. **Goal 3**: Query Ethereum for bridge balances
   - Uses web3.py to call TRB contract `balanceOf` function
   - Queries balance of bridge contract address

4. **Goal 4**: Historical data collection
   - Iterates backwards through block heights
   - Stops when RPC returns `InvalidArgument` errors
   - Implements rate limiting to avoid overwhelming RPCs

### Error Handling

- **RPC Unavailable**: Graceful fallback and retry logic
- **Invalid Block Heights**: Automatic detection via `InvalidArgument` errors
- **Network Issues**: Timeout handling and logging
- **Data Parsing**: JSON parsing error recovery

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `TELLOR_LAYER_RPC_URL` | `https://node-palmito.tellorlayer.com/rpc/` | Tellor Layer RPC endpoint |
| `ETHEREUM_RPC_URL` | `https://rpc.sepolia.org` | Ethereum Sepolia RPC endpoint |
| `SEPOLIA_TRB_CONTRACT` | `0x80fc34a2f9FfE86F41580F47368289C402DEc660` | TRB token contract address |
| `SEPOLIA_BRIDGE_CONTRACT` | `0x5acb5977f35b1A91C4fE0F4386eB669E046776F2` | Bridge contract address |
| `CURRENT_DATA_INTERVAL` | `300` | Monitoring interval in seconds (5 minutes) |
| `DISCORD_WEBHOOK_URL` | (empty) | Discord webhook URL for alerts (optional) |

### RPC Endpoints

- **Tellor Layer**: Uses the provided palmito node
- **Ethereum Sepolia**: Uses public RPC (can be replaced with Infura/Alchemy)

For production use, consider using dedicated RPC endpoints with higher rate limits.

## Troubleshooting

### Common Issues

1. **`layerd` not found**
   - Ensure the binary is in the root directory and executable
   - Check file permissions: `ls -la layerd`

2. **RPC connection failures**
   - Verify network connectivity
   - Check if RPC endpoints are accessible
   - Try alternative RPC providers

3. **`InvalidArgument` errors**
   - This is expected when querying very old or future blocks
   - The system handles this gracefully and stops collection

4. **Web3 connection issues**
   - Verify Ethereum RPC URL in `.env` file
   - Check if the RPC supports the required block height

### Logging

The system provides detailed logging at different levels:

- **INFO**: Normal operation status
- **WARNING**: Non-critical issues (expected RPC limitations)
- **ERROR**: Critical failures requiring attention
- **DEBUG**: Detailed execution information

## Development

### Quick Start with uv

```bash
# Install dependencies and set up the project
uv sync

# Run the analytics collector
uv run tellor-supply-analytics

# Run with historical data collection
uv run tellor-supply-analytics --historical

# Install development dependencies
uv sync --extra dev

# Run code formatting
uv run black src/
uv run isort src/

# Run type checking
uv run mypy src/
```

### Project Structure

```
tellor-supply-analytics/
├── src/
│   └── tellor_supply_analytics/
│       ├── __init__.py
│       └── supply_collector.py       # Main collection logic
├── layerd                            # Tellor Layer CLI binary
├── run_supply_analytics.py          # Executable runner script
├── pyproject.toml                    # Modern Python packaging config
├── requirements.txt                  # Legacy dependencies (optional)
├── supply_data.csv                   # Generated data file
└── README.md                         # This file
```

### Adding New Data Sources

To add new blockchain data sources:

1. Create new methods in `SupplyDataCollector` class
2. Update `CSV_HEADERS` with new columns
3. Modify `collect_current_data()` to include new sources
4. Update the CSV writing logic accordingly

## License

This project is part of the Tellor blockchain backend engineering team's analytics infrastructure. 