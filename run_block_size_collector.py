#!/usr/bin/env python3
"""
Tellor Layer Block Size Collector

Continuously polls the Tellor Layer REST API for new blocks, records per-block
metrics (size, tx count, gas, events), detects anomalously large blocks via
rolling z-score analysis, and fires Discord alerts when anomalies are found.

All data is stored in tellor_balances.db alongside the existing supply and balance data.

Usage Examples:
    # First activate the virtual environment:
    source .venv/bin/activate

    # Continuous collection (polls every 3 seconds by default):
    python run_block_size_collector.py

    # Catch up the last 500 blocks before entering the continuous loop:
    python run_block_size_collector.py --backfill 500

    # Custom poll interval (seconds):
    python run_block_size_collector.py --interval 5

    # Tune anomaly detection sensitivity:
    python run_block_size_collector.py --alert-window 200 --alert-threshold 4.0

    # Use a different database file:
    python run_block_size_collector.py --db-path /path/to/custom.db

Environment variables (read from .env):
    LAYER_API_URL          Tellor Layer REST base URL (required)
    DISCORD_WEBHOOK_URL    Discord webhook for anomaly alerts (optional)
    BLOCK_SIZE_ALERT_WINDOW      Override default alert_window (default 100)
    BLOCK_SIZE_ALERT_THRESHOLD   Override default z-score threshold (default 3.0)
    BLOCK_SIZE_ALERT_COOLDOWN    Override default cooldown seconds (default 300)
"""

import argparse
import asyncio
import logging
import os
import signal
import sys
from pathlib import Path

from dotenv import load_dotenv

# Ensure the package is importable when run from the project root
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("block_size_collector")

# Suppress noisy httpx INFO logs
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


def _require_env(key: str) -> str:
    val = os.environ.get(key, "").strip()
    if not val:
        logger.error("Required environment variable %s is not set", key)
        sys.exit(1)
    return val


def _optional_env(key: str, default: str) -> str:
    return os.environ.get(key, default).strip() or default


# ---------------------------------------------------------------------------
# Main collect loop
# ---------------------------------------------------------------------------

async def run_collector(
    api_url: str,
    db_path: str,
    discord_webhook_url: str,
    poll_interval: float,
    backfill: int,
    alert_window: int,
    alert_threshold: float,
    alert_cooldown: int,
    shutdown_event: asyncio.Event,
) -> None:
    from src.tellor_supply_analytics.database import BalancesDatabase
    from src.tellor_supply_analytics.block_size_collector import (
        fetch_block_metrics,
        get_latest_height,
        BlockNotAvailable,
    )
    from src.tellor_supply_analytics.block_size_analyzer import check_anomaly
    from src.tellor_supply_analytics.block_size_alerter import process_anomalies

    db = BalancesDatabase(db_path)

    logger.info("Starting Tellor Layer block size collector")
    logger.info("  API URL       : %s", api_url)
    logger.info("  Database      : %s", db_path)
    logger.info("  Poll interval : %ss", poll_interval)
    logger.info("  Alert window  : %d blocks", alert_window)
    logger.info("  Alert z-threshold: %.1f", alert_threshold)
    logger.info("  Alert cooldown: %ds", alert_cooldown)
    logger.info("  Discord alerts: %s", "enabled" if discord_webhook_url else "disabled")

    # Determine starting height
    latest_stored = db.get_latest_block_size_height()

    if backfill > 0:
        try:
            head = await get_latest_height(api_url)
            start_height = max(1, head - backfill)
            if latest_stored is not None:
                start_height = min(start_height, latest_stored + 1)
            logger.info("Backfilling from height %d to %d (%d blocks, newest first)", start_height, head, head - start_height + 1)
            # Process newest heights first so the chart shows data immediately
            for h in reversed(range(start_height, head + 1)):
                if shutdown_event.is_set():
                    return
                try:
                    metrics = await fetch_block_metrics(api_url, h)
                    db.insert_block_size(
                        metrics.height, metrics.timestamp,
                        metrics.block_size_bytes, metrics.tx_count,
                        metrics.gas_used, metrics.num_events,
                    )
                    logger.debug("backfill height=%d size=%d", h, metrics.block_size_bytes)
                except BlockNotAvailable:
                    logger.debug("Block %d not available during backfill, skipping", h)
                except Exception as exc:
                    logger.warning("Error fetching block %d during backfill: %s", h, exc)
            latest_stored = db.get_latest_block_size_height()
        except Exception as exc:
            logger.warning("Failed to determine head for backfill: %s", exc)

    last_seen: int = latest_stored if latest_stored is not None else -1

    # Continuous collection loop
    while not shutdown_event.is_set():
        try:
            latest = await get_latest_height(api_url)
        except Exception as exc:
            logger.warning("Failed to fetch latest height: %s", exc)
            try:
                await asyncio.wait_for(shutdown_event.wait(), timeout=poll_interval)
            except asyncio.TimeoutError:
                pass
            continue

        if last_seen < 0:
            last_seen = latest - 1

        for height in range(last_seen + 1, latest + 1):
            if shutdown_event.is_set():
                break
            try:
                metrics = await fetch_block_metrics(api_url, height)
                db.insert_block_size(
                    metrics.height, metrics.timestamp,
                    metrics.block_size_bytes, metrics.tx_count,
                    metrics.gas_used, metrics.num_events,
                )
                logger.info(
                    "%s  height=%d  size=%8d B  txs=%4d  gas=%10d  events=%5d",
                    metrics.timestamp[:19],
                    metrics.height,
                    metrics.block_size_bytes,
                    metrics.tx_count,
                    metrics.gas_used,
                    metrics.num_events,
                )

                anomalies = check_anomaly(
                    db, height, window=alert_window, threshold=alert_threshold
                )
                if anomalies:
                    for a in anomalies:
                        logger.warning(
                            "ANOMALY  metric=%s  height=%d  value=%.0f  z=%+.2f",
                            a.metric, a.height, a.value, a.zscore,
                        )
                    await process_anomalies(
                        db, discord_webhook_url, anomalies, alert_cooldown
                    )

            except BlockNotAvailable:
                logger.debug("Block %d not yet available", height)
            except Exception as exc:
                logger.warning("Error processing height %d: %s", height, exc)

        last_seen = latest

        try:
            await asyncio.wait_for(shutdown_event.wait(), timeout=poll_interval)
        except asyncio.TimeoutError:
            pass

    logger.info("Block size collector stopped gracefully")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Tellor Layer block size collector with anomaly detection",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--interval", type=float,
        default=float(_optional_env("POLL_INTERVAL_SECONDS", "3")),
        help="Poll interval in seconds",
    )
    parser.add_argument(
        "--backfill", type=int, default=0,
        help="Number of recent blocks to backfill before entering the continuous loop",
    )
    parser.add_argument(
        "--alert-window", type=int,
        default=int(_optional_env("BLOCK_SIZE_ALERT_WINDOW", "100")),
        help="Rolling window size (blocks) for z-score anomaly detection",
    )
    parser.add_argument(
        "--alert-threshold", type=float,
        default=float(_optional_env("BLOCK_SIZE_ALERT_THRESHOLD", "3.0")),
        help="Z-score threshold for anomaly alerts",
    )
    parser.add_argument(
        "--alert-cooldown", type=int,
        default=int(_optional_env("BLOCK_SIZE_ALERT_COOLDOWN", "300")),
        help="Minimum seconds between repeated alerts for the same metric",
    )
    parser.add_argument(
        "--db-path", type=str, default="tellor_balances.db",
        help="Path to the SQLite database file",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    api_url = _require_env("LAYER_API_URL").rstrip("/")
    discord_webhook_url = _optional_env("DISCORD_WEBHOOK_URL", "")

    shutdown_event = asyncio.Event()

    def _handle_signal(signum, frame):  # type: ignore[type-arg]
        logger.info("Received signal %s, shutting down…", signal.Signals(signum).name)
        shutdown_event.set()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    asyncio.run(
        run_collector(
            api_url=api_url,
            db_path=args.db_path,
            discord_webhook_url=discord_webhook_url,
            poll_interval=args.interval,
            backfill=args.backfill,
            alert_window=args.alert_window,
            alert_threshold=args.alert_threshold,
            alert_cooldown=args.alert_cooldown,
            shutdown_event=shutdown_event,
        )
    )


if __name__ == "__main__":
    main()
