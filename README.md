# Tellor Supply Analytics

A Python-based blockchain analytics system that collects and monitors TRB token supply data across multiple sources, with a real-time web dashboard.

1. **Tellor Layer blockchain** — Block information, total supply, and validator/reporter stakes
2. **Ethereum mainnet** — TRB bridge contract balances (Bridge V1 and V2)
3. **Historical backfill** — Walks backwards through Ethereum blocks until RPC limits are reached
4. **Block size/time analytics** — Tracks Tellor Layer block frequency and transaction throughput

## Features

- Unified timeline: Ethereum blocks as the primary anchor for all data
- Real-time web dashboard with supply metrics, balance analytics, and block time charts
- Periodic background collection with configurable intervals
- Bridge V1 / Bridge V2 balances tracked separately
- Discord webhook alerts for bonded token changes
- SQLite database for historical snapshots
- Block size anomaly detection with z-score alerting

## Installation

### Option 1: Using uv (Recommended)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync
source .venv/bin/activate
```

### Option 2: Using pip

```bash
pip install -e .
```

### layerd binary

The `layerd` Tellor Layer CLI binary must be present in the project root and executable:

```bash
chmod +x ./layerd
```

## Configuration

Copy the example environment file and fill in your values:

```bash
cp .env.example .env
```

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `TELLOR_LAYER_RPC_URL` | Yes | Tellor Layer RPC endpoint |
| `LAYER_API_URL` | Yes | Tellor Layer REST API base URL |
| `ETHEREUM_RPC_URL` | Yes | Ethereum mainnet RPC (archive node recommended for backfill) |
| `TRB_CONTRACT` | Yes | TRB token contract address on Ethereum mainnet |
| `CURRENT_BRIDGE_CONTRACT` | Yes | Current Bridge V2 contract address |
| `OLD_BRIDGE_CONTRACT_1` | No | Legacy Bridge V1 contract address |
| `TRBBRIDGEV2_CONTRACT_ADDRESS` | No | Explicit Bridge V2 address (falls back to `CURRENT_BRIDGE_CONTRACT`) |
| `CURRENT_DATA_INTERVAL` | No | Collection interval in seconds (default: `300`) |
| `DISCORD_WEBHOOK_URL` | No | Discord webhook URL for bonded token alerts |
| `BLOCK_SIZE_ALERT_WINDOW` | No | Rolling window (blocks) for block size z-score baseline (default: `100`) |
| `BLOCK_SIZE_ALERT_THRESHOLD` | No | Z-score threshold for block size anomaly alerts (default: `3.0`) |
| `BLOCK_SIZE_ALERT_COOLDOWN` | No | Seconds between repeated block size alerts (default: `300`) |
| `BRIDGE_DEPOSITS_CSV_PATH` | No | CSV of bridge deposit transactions for historical calculations (default: `example_bridge_deposits.csv`) |
| `BRIDGE_WITHDRAWALS_CSV_PATH` | No | CSV of bridge withdrawal transactions (default: `example_bridge_withdrawals.csv`) |

> **Note:** `ROOT_PATH` is not read from `.env`. Pass it as a CLI flag: `python app.py --root-path /supply-mainnet`

### Bridge Contract Balances

The dashboard tracks two bridge balances independently:

- `bridge_balance_trb` — Legacy TRBBridge V1 balance (`OLD_BRIDGE_CONTRACT_1`)
- `bridge_v2_balance_trb` — Current Bridge V2 balance (`TRBBRIDGEV2_CONTRACT_ADDRESS` or `CURRENT_BRIDGE_CONTRACT`)

The system switches which contract is queried for historical snapshots based on Tellor Layer block height (threshold: 9,569,214).

## Usage

### Web Dashboard

```bash
# Web server only (port 8669 by default)
python app.py --host 0.0.0.0 --port 8669 --root-path /supply-mainnet

# Web server + background collection every 30 minutes
python app.py --host 0.0.0.0 --port 8669 --root-path /supply-mainnet --collect-interval 1800
```

Dashboard pages:
- `/supply-mainnet/` — Main TRB supply tracker
- `/supply-mainnet/analytics/block-time` — Block frequency and size analytics
- `/supply-mainnet/snapshot/<eth_timestamp>` — Snapshot detail for a specific Ethereum block

### Unified Data Collection

```bash
# Collect at the current Tellor Layer block
python run_unified_collection.py --current-block-only

# Collect every 30 minutes
python run_unified_collection.py --current-block-only --interval 1800

# Monitor mode: collect current + fill any gaps
python run_unified_collection.py --monitor 1800

# Collect at a specific Ethereum block
python run_unified_collection.py --eth-block 20123456

# Collect at a specific Tellor Layer block
python run_unified_collection.py --layer-block 5730721
```

### Block Size Collector

```bash
python run_block_size_collector.py
```

Streams live Tellor Layer blocks, records size and transaction counts, and fires Discord alerts when z-score anomalies are detected.

### Supply Analytics (CSV output)

```bash
# Current data only
uv run tellor-supply-analytics

# With historical backfill
uv run tellor-supply-analytics --historical

# Debug logging
uv run tellor-supply-analytics --debug
```

Output: `supply_data.csv`

## Discord Alerts

Set `DISCORD_WEBHOOK_URL` in `.env` to receive notifications. Current alert types:

- **Bonded Tokens Increased / Decreased** — sent by the balance collector when the bonded token total changes
- **Block Size Anomaly** — sent by the block size collector when z-score exceeds `BLOCK_SIZE_ALERT_THRESHOLD`

Example bonded token alert:
```
🚀 Bonded Tokens Increased!
Previous Bonded Tokens: 9,150,103,229
Current Bonded Tokens:  9,152,512,989
Increase: 2,409,760 (+0.03%)

Block Height: 4670804
Timestamp: Mon, 23 Jun 2025 19:02:49 GMT
```

## Project Structure

```
trb-supply-monitor/
├── src/tellor_supply_analytics/
│   ├── unified_collector.py      # Main orchestrator (Ethereum-anchored timeline)
│   ├── supply_collector.py       # Supply + bridge balance collection → supply_data.csv
│   ├── get_active_balances.py    # Validator/reporter balance snapshots → SQLite
│   ├── find_layer_block.py       # Binary search: Ethereum timestamp → Tellor Layer block
│   └── database.py               # SQLite manager (balance_snapshots, unified_snapshots)
├── templates/
│   ├── dashboard.html            # Main supply tracker dashboard
│   ├── block-time-analytics.html # Block frequency and size charts
│   └── snapshot-detail.html      # Per-snapshot detail view
├── static/
│   ├── css/
│   └── js/
├── app.py                        # FastAPI web dashboard
├── run_unified_collection.py     # CLI for unified data collection
├── run_block_size_collector.py   # Live block size streaming + alerts
├── run_supply_analytics.py       # Legacy CSV collection runner
├── layerd                        # Tellor Layer CLI binary (must be executable)
├── supply_data.csv               # Generated CSV output
├── tellor_balances.db            # SQLite database
├── .env                          # Environment variables (create from .env.example)
└── .env.example                  # Environment variable template
```

## Troubleshooting

**`layerd` not found**
Verify the binary exists in the project root and is executable:
```bash
ls -la layerd
chmod +x ./layerd
```

**RPC connection failures**
- Check that `TELLOR_LAYER_RPC_URL`, `LAYER_API_URL`, and `ETHEREUM_RPC_URL` are reachable
- For historical backfill, use an archive-capable Ethereum RPC
- `InvalidArgument` errors from the Tellor Layer RPC when querying old blocks are expected and handled gracefully

**SQLite "database is locked"**
Only one collection process should write to `tellor_balances.db` at a time. Check for stuck processes:
```bash
ps aux | grep python
```

**Dashboard shows no data**
Trigger a manual collection via the API:
```bash
curl -X POST http://localhost:8669/api/collect
```

## Development

```bash
uv sync --extra dev

uv run black src/
uv run isort src/
uv run mypy src/
uv run flake8 src/

uv run pytest
```
