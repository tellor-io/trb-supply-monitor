#!/usr/bin/env python3
"""
Unified Tellor Data Collection Runner

This script provides a comprehensive interface for running the unified data collection system.
It coordinates between Ethereum block timestamps and Tellor Layer data to ensure temporal consistency.

Features:
- Real-time data collection with configurable intervals
- Historical data backfill with automatic timeline discovery
- Bridge activity-based collection using transaction CSV files
- Data completeness tracking and incremental updates
- Monitoring mode for continuous operation
- Specific block height collection for targeted data snapshots

Usage Examples:
    # First activate the virtual environment:
    source .venv/bin/activate

    # Then run the collector:
    # Collect last 24 hours of data
    python run_unified_collection.py --hours-back 24

    # Run backfill for incomplete data
    python run_unified_collection.py --backfill

    # Collect data at bridge activity block heights
    python run_unified_collection.py --bridge-historic

    # Collect data at specific Ethereum block height
    python run_unified_collection.py --eth-block 20123456

    # Collect data at specific Tellor Layer block height
    python run_unified_collection.py --layer-block 5730721

    # Run in continuous monitoring mode
    python run_unified_collection.py --monitor --interval 3600
"""

import os
import sys
import csv
import argparse
import logging
import signal
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Tuple, Set

def check_virtual_env():
    """Check if running in the correct virtual environment."""
    venv_path = Path('.venv/bin/activate')
    if not venv_path.exists():
        print("Error: Virtual environment not found at .venv/")
        print("Please create and activate the virtual environment first:")
        print("  python -m venv .venv")
        print("  source .venv/bin/activate")
        sys.exit(1)
        
    # Check if we're running in a virtual environment
    if not hasattr(sys, 'real_prefix') and not (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
        print("Error: Script must be run within the virtual environment")
        print("Please activate the virtual environment first:")
        print("  source .venv/bin/activate")
        sys.exit(1)

# Check virtual environment before proceeding
check_virtual_env()

# Add project root to path for imports
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.tellor_supply_analytics.unified_collector import UnifiedDataCollector
from src.tellor_supply_analytics.supply_collector import TELLOR_LAYER_RPC_URL

# Configure logging
def setup_logging(debug: bool = False):
    """Set up logging configuration."""
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('logs/unified_collection.log') if Path('logs').exists() else logging.NullHandler()
        ]
    )

# Global variable for graceful shutdown
shutdown_requested = False

def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    global shutdown_requested
    logger.info("Shutdown signal received, stopping gracefully...")
    shutdown_requested = True

# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# Initialize logger
logger = logging.getLogger(__name__)

def check_shutdown():
    """Check if shutdown was requested and exit if so."""
    if shutdown_requested:
        logger.info("Shutdown requested, exiting...")
        sys.exit(0)

# Bridge CSV configuration with environment variable support
def get_bridge_csv_paths():
    """Get bridge CSV file paths from environment variables or defaults."""
    deposits_csv = os.getenv('BRIDGE_DEPOSITS_CSV_PATH', 'example_bridge_deposits.csv')
    withdrawals_csv = os.getenv('BRIDGE_WITHDRAWALS_CSV_PATH', 'example_bridge_withdrawals.csv')
    return deposits_csv, withdrawals_csv

def get_bridge_block_heights_from_csv(deposits_csv: str, withdrawals_csv: str) -> List[Tuple[int, int]]:
    """
    Extract block heights and timestamps from bridge CSV files.
    
    Returns:
        List of (block_height, timestamp) tuples sorted by timestamp (newest first)
    """
    bridge_data = []
    
    # Read deposits CSV - has Block Height column
    if os.path.exists(deposits_csv):
        try:
            with open(deposits_csv, 'r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if 'Block Height' in row and row['Block Height']:
                        try:
                            height = int(row['Block Height'])
                            # Parse timestamp (format: "2025-06-20 13:24:27")
                            timestamp_str = row.get('Timestamp', '')
                            if timestamp_str:
                                try:
                                    deposit_time = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                                    deposit_time = deposit_time.replace(tzinfo=timezone.utc)
                                    timestamp = int(deposit_time.timestamp())
                                    bridge_data.append((height, timestamp))
                                except ValueError as e:
                                    logger.warning(f"Error parsing timestamp '{timestamp_str}': {e}")
                                    continue
                        except ValueError:
                            continue
            logger.info(f"Found {len(bridge_data)} entries from {deposits_csv}")
        except Exception as e:
            logger.error(f"Error reading {deposits_csv}: {e}")
    else:
        logger.warning(f"Bridge deposits file not found: {deposits_csv}")
    
    # Read withdrawals CSV - check for block height columns
    if os.path.exists(withdrawals_csv):
        try:
            with open(withdrawals_csv, 'r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Check if there's a block height column (various possible names)
                    for col in ['Block Height', 'block_height', 'BlockHeight', 'block']:
                        if col in row and row[col]:
                            try:
                                height = int(row[col])
                                # Try to parse timestamp
                                timestamp_str = row.get('Timestamp', '')
                                if timestamp_str:
                                    try:
                                        withdrawal_time = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                                        withdrawal_time = withdrawal_time.replace(tzinfo=timezone.utc)
                                        timestamp = int(withdrawal_time.timestamp())
                                        bridge_data.append((height, timestamp))
                                    except ValueError as e:
                                        logger.warning(f"Error parsing timestamp '{timestamp_str}': {e}")
                                        continue
                            except ValueError:
                                continue
                            break
            logger.info(f"Total bridge data entries after including {withdrawals_csv}: {len(bridge_data)}")
        except Exception as e:
            logger.error(f"Error reading {withdrawals_csv}: {e}")
    else:
        logger.warning(f"Bridge withdrawals file not found: {withdrawals_csv}")
    
    # Remove duplicates and sort by timestamp (newest first)
    unique_data = list(set(bridge_data))
    unique_data.sort(key=lambda x: x[1], reverse=True)
    
    logger.info(f"Found {len(unique_data)} unique bridge block heights")
    if unique_data:
        logger.info(f"Bridge height range: {min(h for h, t in unique_data)} to {max(h for h, t in unique_data)}")
        logger.info(f"Timestamp range: {min(t for h, t in unique_data)} to {max(t for h, t in unique_data)}")
    
    return unique_data

def get_new_bridge_heights(collector: UnifiedDataCollector, bridge_data: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
    """
    Filter bridge heights to only include those not already in database.
    
    Args:
        collector: UnifiedDataCollector instance
        bridge_data: List of (block_height, timestamp) tuples
        
    Returns:
        List of (block_height, timestamp) tuples for new entries only
    """
    # Get existing Ethereum timestamps from database
    existing_timestamps = set(collector.db.get_existing_eth_timestamps())
    
    # Filter to only include bridge heights we don't have data for
    new_heights = []
    for block_height, timestamp in bridge_data:
        # Check if we have data within 60 seconds of this timestamp
        has_existing_data = any(abs(timestamp - existing_ts) <= 60 for existing_ts in existing_timestamps)
        if not has_existing_data:
            new_heights.append((block_height, timestamp))
    
    logger.info(f"Found {len(new_heights)} new bridge heights not in database (out of {len(bridge_data)} total)")
    return new_heights


def run_historic_collection(collector: UnifiedDataCollector, args):
    """Run historic data collection - one sample per day back to genesis."""
    logger.info("Starting historic data collection")
    
    # FIRST: Re-run any incomplete daily collections that already exist
    logger.info("Checking for incomplete snapshots to re-run...")
    incomplete_snapshots = collector.db.get_incomplete_snapshots(min_completeness=1.0)
    
    if incomplete_snapshots:
        logger.info(f"Found {len(incomplete_snapshots)} incomplete snapshots to re-run")
        updated_count = 0
        
        for i, snapshot in enumerate(incomplete_snapshots, 1):
            # Get values with proper type handling
            eth_block_number_raw = snapshot.get('eth_block_number')
            eth_timestamp_raw = snapshot.get('eth_block_timestamp')
            current_score = snapshot.get('data_completeness_score', 0)
            collection_time = snapshot.get('collection_time', 'Unknown')
            
            # Skip snapshots with missing required data
            if eth_block_number_raw is None or eth_timestamp_raw is None:
                logger.warning(f"Skipping incomplete snapshot with missing block number or timestamp")
                continue
            
            # Convert to int for the collection call (we know they're not None from check above)
            eth_block_number: int = int(eth_block_number_raw)  # type: ignore
            eth_timestamp: int = int(eth_timestamp_raw)  # type: ignore
            
            logger.info(f"Re-running incomplete snapshot {i}/{len(incomplete_snapshots)}: "
                       f"ETH block {eth_block_number} (timestamp {eth_timestamp}, "
                       f"collected {collection_time}, completeness: {current_score:.2f})")
            
            try:
                if collector.collect_unified_snapshot(eth_block_number, eth_timestamp):
                    updated_count += 1
                    logger.info(f"Successfully updated incomplete snapshot for ETH block {eth_block_number}")
                else:
                    logger.warning(f"Failed to update incomplete snapshot for ETH block {eth_block_number}")
                
                # Add delay between re-collections
                if i < len(incomplete_snapshots):
                    time.sleep(1)
                    
            except Exception as e:
                logger.error(f"Error re-running incomplete snapshot for ETH block {eth_block_number}: {e}")
                continue
                
            # Check for shutdown signal during incomplete snapshot processing
            if shutdown_requested:
                logger.info("Shutdown requested during incomplete snapshot re-run, stopping")
                return updated_count
        
        logger.info(f"Completed re-running incomplete snapshots: {updated_count}/{len(incomplete_snapshots)} updated")
    else:
        logger.info("No incomplete snapshots found to re-run")
    
    # SECOND: Proceed with normal historic collection for missing days
    logger.info("Starting daily historic data collection for missing days...")
    
    # Get node height information
    latest_height, earliest_height = get_node_height_info(collector)
    if latest_height is None or earliest_height is None:
        logger.error("Failed to get node height information")
        return 0
    
    logger.info(f"Historic collection range: {earliest_height} to {latest_height}")
    
    # Get the timestamp of the earliest block to calculate daily intervals
    earliest_block_info = collector.supply_collector.get_block_info(earliest_height)
    if not earliest_block_info:
        logger.error(f"Failed to get timestamp for earliest block {earliest_height}")
        return 0
    
    earliest_timestamp = earliest_block_info[1]  # Unix timestamp
    earliest_date = datetime.fromtimestamp(earliest_timestamp)
    
    # Get latest block timestamp
    latest_block_info = collector.supply_collector.get_block_info(latest_height)
    if not latest_block_info:
        logger.error(f"Failed to get timestamp for latest block {latest_height}")
        return 0
    
    latest_timestamp = latest_block_info[1]
    latest_date = datetime.fromtimestamp(latest_timestamp)
    
    logger.info(f"Time range: {earliest_date} to {latest_date}")
    
    # Calculate days to collect
    total_days = (latest_date - earliest_date).days + 1
    logger.info(f"Total days to collect: {total_days}")
    
    successful_collections = 0
    current_date = latest_date.replace(hour=12, minute=0, second=0, microsecond=0)  # Noon each day
    
    # Work backwards day by day
    for day_offset in range(total_days):
        if shutdown_requested:
            logger.info("Shutdown requested, stopping historic collection")
            break
            
        target_date = current_date - timedelta(days=day_offset)
        target_timestamp = int(target_date.timestamp())
        
        logger.info(f"=== DAY {day_offset + 1}/{total_days}: {target_date.strftime('%Y-%m-%d')} ===")
        
        # Check if we already have COMPLETE data for this day (within 12 hours)
        existing_timestamps = collector.db.get_existing_eth_timestamps()
        skip_day = False
        existing_completeness = 0.0
        
        for existing_ts in existing_timestamps:
            if abs(target_timestamp - existing_ts) <= 12 * 3600:  # 12 hour tolerance
                # Found existing data - check if it's complete
                existing_snapshot = collector.db.get_unified_snapshot_by_eth_timestamp(existing_ts)
                if existing_snapshot:
                    existing_completeness = existing_snapshot.get('data_completeness_score', 0.0)
                    if existing_completeness >= 1.0:
                        logger.info(f"Complete data already exists for {target_date.strftime('%Y-%m-%d')} (completeness: {existing_completeness:.2f}), skipping")
                        skip_day = True
                        break
                    else:
                        logger.info(f"Incomplete data found for {target_date.strftime('%Y-%m-%d')} (completeness: {existing_completeness:.2f}), will re-collect")
                        # Don't skip - we need to re-collect this day to fill in missing data
                        break
        
        if skip_day:
            continue
            
        # If target date is before earliest available data, stop
        if target_timestamp < earliest_timestamp:
            logger.info(f"Target date {target_date} is before earliest available data, stopping")
            break
        
        try:
            # Find the Tellor Layer block closest to this timestamp
            from tellor_supply_analytics.find_layer_block import TellorLayerBlockFinder
            from datetime import timezone
            
            # Create a single block finder instance and reuse it to avoid repeated status calls
            if not hasattr(run_historic_collection, '_block_finder'):
                class OptimizedBlockFinder(TellorLayerBlockFinder):
                    def __init__(self, rpc_url, latest_height, earliest_height):
                        super().__init__(rpc_url)
                        self._latest_height = latest_height
                        self._earliest_height = earliest_height
                    
                    def get_latest_height(self):
                        return self._latest_height
                
                run_historic_collection._block_finder = OptimizedBlockFinder(
                    TELLOR_LAYER_RPC_URL, latest_height, earliest_height
                )
                logger.info(f"Created optimized block finder with range {earliest_height} to {latest_height}")
            
            target_time = datetime.fromtimestamp(target_timestamp, tz=timezone.utc)
            layer_height = run_historic_collection._block_finder.find_block_by_timestamp(target_time)
            
            if layer_height is None:
                logger.warning(f"Could not find Tellor Layer block for {target_date}")
                continue
            
            # Get the block time for this height
            layer_time = run_historic_collection._block_finder.get_block_time(layer_height)
            if layer_time is None:
                logger.warning(f"Could not get block time for height {layer_height}")
                continue
                
            layer_timestamp = int(layer_time.timestamp())
            logger.info(f"Found Tellor Layer block {layer_height} for {target_date}")
            
            # Create a synthetic Ethereum block entry (since we're doing historic collection)
            # Use the layer timestamp as the "Ethereum" timestamp for consistency
            eth_block_result = collector.find_ethereum_block_for_timestamp(layer_timestamp)
            eth_block_number: int = eth_block_result if eth_block_result is not None else 0
            eth_timestamp = layer_timestamp
            
            # Collect unified snapshot for this day
            if collector.collect_unified_snapshot(eth_block_number, eth_timestamp):
                successful_collections += 1
                logger.info(f"Successfully collected data for {target_date.strftime('%Y-%m-%d')}")
            else:
                logger.warning(f"Failed to collect data for {target_date.strftime('%Y-%m-%d')}")
            
            # Add delay between collections
            time.sleep(2)
            
        except Exception as e:
            logger.error(f"Error collecting data for {target_date}: {e}")
            
            # If we get consistent errors, the node may not have this historical data
            if "not found" in str(e).lower() or "does not exist" in str(e).lower():
                logger.info("Node appears to have run out of historical data, stopping")
                break
            
            continue
    
    total_updated = (updated_count if 'updated_count' in locals() else 0) + successful_collections
    logger.info(f"Historic collection completed: {successful_collections} new days processed, "
               f"{updated_count if 'updated_count' in locals() else 0} incomplete snapshots re-run, "
               f"total: {total_updated}")
    return total_updated

def get_node_height_info(collector: UnifiedDataCollector):
    """Get current and earliest block heights from layerd status."""
    try:
        # Use the supply collector's method to get status
        cmd_args = [
            'status',
            '--output', 'json',
            '--node', TELLOR_LAYER_RPC_URL
        ]
        
        result = collector.supply_collector.run_layerd_command(cmd_args)
        if not result:
            logger.error("Failed to get node status")
            return None, None
        
        sync_info = result.get('sync_info', {})
        
        # Get latest height (always available)
        latest_height = int(sync_info.get('latest_block_height', 0))
        
        # Get earliest block height from status
        earliest_height = sync_info.get('earliest_block_height')
        if earliest_height:
            earliest_height = int(earliest_height)
            logger.info(f"Node height info - Latest: {latest_height}, Earliest: {earliest_height}")
        else:
            logger.error("earliest_block_height not available in layerd status")
            return None, None
        
        return latest_height, earliest_height
        
    except Exception as e:
        logger.error(f"Error getting node height info: {e}")
        return None, None


def run_bridge_historic_collection(collector: UnifiedDataCollector, args):
    """Run historic data collection based on bridge activity block heights."""
    logger.info("Starting bridge-based historic data collection")
    
    # Get bridge CSV file paths from environment or use defaults
    deposits_csv, withdrawals_csv = get_bridge_csv_paths()
    
    # Override with command line arguments if provided
    if hasattr(args, 'deposits_csv') and args.deposits_csv != 'example_bridge_deposits.csv':
        deposits_csv = args.deposits_csv
    if hasattr(args, 'withdrawals_csv') and args.withdrawals_csv != 'example_bridge_withdrawals.csv':
        withdrawals_csv = args.withdrawals_csv
    
    logger.info(f"Using bridge CSV files:")
    logger.info(f"  Deposits: {deposits_csv}")
    logger.info(f"  Withdrawals: {withdrawals_csv}")
    
    # Get all bridge block heights from CSV files
    all_bridge_heights = get_bridge_block_heights_from_csv(deposits_csv, withdrawals_csv)
    
    if not all_bridge_heights:
        logger.error("No bridge block heights found in CSV files")
        return 0
    
    # Filter to only new heights not in database
    new_bridge_heights = get_new_bridge_heights(collector, all_bridge_heights)
    
    if not new_bridge_heights:
        logger.info("No new bridge heights to process - all data already exists in database")
        return 0
    
    logger.info(f"Found {len(new_bridge_heights)} new bridge heights to process (out of {len(all_bridge_heights)} total)")
    logger.info(f"New heights range: {min(h for h, t in new_bridge_heights)} to {max(h for h, t in new_bridge_heights)}")
    
    # Use the new heights for processing
    block_heights = new_bridge_heights
    
    # Get existing timestamps for skip checking
    existing_timestamps = collector.db.get_existing_eth_timestamps()
    
    successful_collections = 0
    skipped_existing = 0
    
    # Process blocks starting with newest first to handle pruned nodes
    for i, (eth_block, eth_timestamp) in enumerate(block_heights):
        if shutdown_requested:
            logger.info("Shutdown requested, stopping bridge historic collection")
            break
            
        logger.info(f"=== BLOCK {i + 1}/{len(block_heights)}: ETH Block {eth_block} (timestamp: {eth_timestamp}) ===")
        
        try:
            # Check if we already have data for this timestamp (within 1 hour tolerance)
            skip_block = False
            for existing_ts in existing_timestamps:
                if abs(eth_timestamp - existing_ts) <= 3600:  # 1 hour tolerance
                    logger.info(f"Data already exists for ETH block {eth_block}, skipping")
                    skipped_existing += 1
                    skip_block = True
                    break
                    
            if skip_block:
                continue
            
            # Collect unified snapshot for this Ethereum block
            logger.info(f"Collecting data for ETH block {eth_block} (timestamp: {datetime.fromtimestamp(eth_timestamp)})")
            
            if collector.collect_unified_snapshot(eth_block, eth_timestamp):
                successful_collections += 1
                logger.info(f"Successfully collected data for ETH block {eth_block}")
            else:
                logger.warning(f"Failed to collect data for ETH block {eth_block}")
            
            # Add delay between collections to avoid overwhelming the nodes
            time.sleep(1)
            
        except Exception as e:
            error_msg = str(e)
            if "500 Server Error" in error_msg:
                logger.warning(f"Encountered pruned block at height {eth_block}: {error_msg}")
                logger.info(f"Stopping collection - all blocks at height {eth_block} and below are likely pruned")
                break
            else:
                logger.error(f"Error collecting data for ETH block {eth_block}: {e}")
                continue
    
    logger.info(f"Bridge historic collection completed:")
    logger.info(f"  - Successfully collected: {successful_collections} blocks")
    logger.info(f"  - Skipped (already exist): {skipped_existing} blocks")
    logger.info(f"  - Total processed: {successful_collections + skipped_existing}/{len(block_heights)} blocks")
    
    return successful_collections


def run_single_collection(collector: UnifiedDataCollector, args):
    """Run a single unified collection cycle."""
    logger.info("Starting single unified collection cycle")
    
    processed = collector.run_unified_collection(
        hours_back=args.hours_back,
        block_interval=args.block_interval,
        max_blocks=args.max_blocks
    )
    
    logger.info(f"Collection cycle completed: {processed} blocks processed")
    return processed

def run_backfill(collector: UnifiedDataCollector, args):
    """Run backfill for incomplete data."""
    logger.info("Starting backfill for incomplete data")
    
    updated = collector.backfill_incomplete_data(max_backfill=args.max_backfill)
    
    logger.info(f"Backfill completed: {updated} snapshots updated")
    return updated

def run_monitoring_mode(collector: UnifiedDataCollector, args):
    """Run continuous monitoring mode."""
    logger.info(f"Starting monitoring mode with {args.interval} second intervals")
    logger.info("Press Ctrl+C to stop gracefully")
    
    cycles_completed = 0
    
    try:
        while not shutdown_requested:
            logger.info(f"=== MONITORING CYCLE {cycles_completed + 1} ===")
            start_time = datetime.now()
            
            try:
                # Check for shutdown before each major operation
                check_shutdown()
                
                # Run collection
                processed = run_single_collection(collector, args)
                
                check_shutdown()
                
                # Optionally run backfill periodically
                if cycles_completed % 5 == 0:  # Every 5th cycle
                    logger.info("Running periodic backfill...")
                    updated = run_backfill(collector, args)
                
                cycles_completed += 1
                
                check_shutdown()
                
                # Show summary periodically
                if cycles_completed % 3 == 0:  # Every 3rd cycle
                    summary = collector.get_data_summary()
                    logger.info(f"Collection summary: {summary}")
                
            except Exception as e:
                logger.error(f"Error in monitoring cycle: {e}")
                
            # Calculate sleep time
            elapsed = (datetime.now() - start_time).total_seconds()
            sleep_time = max(0, args.interval - elapsed)
            
            if sleep_time > 0 and not shutdown_requested:
                next_run = datetime.now().replace(microsecond=0) + \
                          timedelta(seconds=sleep_time)
                logger.info(f"Next collection cycle at: {next_run}")
                
                # Sleep in smaller increments (1 second) to be more responsive to shutdown
                slept = 0
                while slept < sleep_time and not shutdown_requested:
                    time.sleep(min(1, sleep_time - slept))
                    slept += 1
                    
    except KeyboardInterrupt:
        logger.info("Monitoring stopped by user")
    except Exception as e:
        logger.error(f"Error in monitoring mode: {e}")
        raise
    finally:
        logger.info(f"Successfully completed {cycles_completed} collection cycles")
        sys.exit(0)

def run_specific_block_collection(collector: UnifiedDataCollector, args) -> int:
    """
    Run unified data collection for a specific block height.
    
    Args:
        collector: UnifiedDataCollector instance
        args: Command line arguments containing either eth_block or layer_block
        
    Returns:
        1 if successful, 0 if failed
    """
    logger.info("Starting specific block height collection")
    
    eth_block_number = None
    eth_timestamp = None
    
    if args.eth_block:
        # User specified an Ethereum block height
        logger.info(f"Collecting data for Ethereum block {args.eth_block}")
        
        # Get Ethereum block information
        if not collector.w3:
            logger.error("Ethereum Web3 connection not available")
            return 0
            
        try:
            block = collector.w3.eth.get_block(args.eth_block)
            eth_block_number = block.get('number')
            eth_timestamp = block.get('timestamp')
            
            if eth_block_number is None or eth_timestamp is None:
                logger.error(f"Invalid block data received for block {args.eth_block}")
                return 0
            
            logger.info(f"Ethereum block {eth_block_number} timestamp: {eth_timestamp} "
                       f"({datetime.fromtimestamp(eth_timestamp)})")
                       
        except Exception as e:
            logger.error(f"Failed to get Ethereum block {args.eth_block}: {e}")
            return 0
            
    elif args.layer_block:
        # User specified a Tellor Layer block height
        logger.info(f"Collecting data for Tellor Layer block {args.layer_block}")
        
        # Get Tellor Layer block information
        layer_block_info = collector.supply_collector.get_block_info(args.layer_block)
        if not layer_block_info:
            logger.error(f"Failed to get Tellor Layer block {args.layer_block} information")
            return 0
            
        layer_height, layer_timestamp = layer_block_info
        
        logger.info(f"Tellor Layer block {layer_height} timestamp: {layer_timestamp} "
                   f"({datetime.fromtimestamp(layer_timestamp)})")
        
        # For Tellor Layer blocks, we need to find the corresponding Ethereum timestamp
        # We'll use the layer timestamp as the target for the unified collection
        eth_timestamp = layer_timestamp
        
        # Try to find the closest Ethereum block for this timestamp
        eth_block_number = collector.find_ethereum_block_for_timestamp(eth_timestamp)
        if eth_block_number is None:
            logger.warning(f"Could not find corresponding Ethereum block for timestamp {eth_timestamp}, using 0")
            eth_block_number = 0
    
    else:
        logger.error("No block height specified (use --eth-block or --layer-block)")
        return 0
    
    # Check if we already have complete data for this timestamp
    existing_snapshot = collector.db.get_unified_snapshot_by_eth_timestamp(eth_timestamp)
    if existing_snapshot and existing_snapshot.get('data_completeness_score', 0) >= 1.0:
        logger.info(f"Complete data already exists for timestamp {eth_timestamp}")
        logger.info(f"Existing snapshot: ETH block {existing_snapshot.get('eth_block_number')}, "
                   f"Layer block {existing_snapshot.get('layer_block_height')}, "
                   f"completeness: {existing_snapshot.get('data_completeness_score', 0):.2f}")
        return 1
    
    # Collect the unified snapshot
    try:
        success = collector.collect_unified_snapshot(
            eth_block_number, 
            eth_timestamp, 
            layer_block_height=args.layer_block if args.layer_block else None
        )
        
        if success:
            logger.info(f"Successfully collected unified snapshot for:")
            logger.info(f"  Ethereum block: {eth_block_number}")
            logger.info(f"  Timestamp: {eth_timestamp} ({datetime.fromtimestamp(eth_timestamp)})")
            if args.layer_block:
                logger.info(f"  Tellor Layer block: {args.layer_block}")
            return 1
        else:
            logger.error("Failed to collect unified snapshot")
            return 0
            
    except Exception as e:
        logger.error(f"Error collecting unified snapshot: {e}")
        return 0

def show_summary(collector: UnifiedDataCollector):
    """Show data collection summary."""
    print("\n" + "=" * 60)
    print("UNIFIED DATA COLLECTION SUMMARY")
    print("=" * 60)
    
    summary = collector.get_data_summary()
    
    if 'error' in summary:
        print(f"Error getting summary: {summary['error']}")
        return
    
    total = summary.get('total_snapshots', 0)
    complete = summary.get('complete_snapshots', 0)
    incomplete = summary.get('incomplete_snapshots', 0)
    rate = summary.get('completion_rate', 0)
    coverage = summary.get('coverage_hours', 0)
    
    print(f"Total Snapshots:      {total:,}")
    print(f"Complete Snapshots:   {complete:,}")
    print(f"Incomplete Snapshots: {incomplete:,}")
    print(f"Completion Rate:      {rate:.1%}")
    print(f"Time Coverage:        {coverage:.1f} hours")
    
    if summary.get('latest_eth_timestamp'):
        latest_time = datetime.fromtimestamp(summary['latest_eth_timestamp'])
        print(f"Latest Data:          {latest_time}")
        
    if summary.get('oldest_eth_timestamp'):
        oldest_time = datetime.fromtimestamp(summary['oldest_eth_timestamp'])
        print(f"Oldest Data:          {oldest_time}")
    
    print("=" * 60)

def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description='Unified Tellor Data Collector',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    # Collection parameters
    parser.add_argument('--hours-back', type=int, default=24,
                       help='Hours back to collect data for (default: 24)')
    parser.add_argument('--block-interval', type=int, default=3600,
                       help='Target interval between blocks in seconds (default: 3600)')
    parser.add_argument('--max-blocks', type=int, default=50,
                       help='Maximum blocks to process in one run (default: 50)')
    parser.add_argument('--max-backfill', type=int, default=20,
                       help='Maximum snapshots to backfill (default: 20)')
    
    # Mode selection
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument('--backfill', action='store_true',
                           help='Run backfill for incomplete data only')
    mode_group.add_argument('--summary', action='store_true',
                           help='Show data collection summary only')
    mode_group.add_argument('--monitor', action='store_true',
                           help='Run in continuous monitoring mode')
    mode_group.add_argument('--get-all-historic', action='store_true',
                           help='Collect all historic data (one sample per day back to genesis)')
    mode_group.add_argument('--bridge-historic', action='store_true',
                           help='Collect data at Ethereum blocks where bridge activity occurred')
    mode_group.add_argument('--eth-block', type=int, metavar='BLOCK_HEIGHT',
                           help='Collect data at specific Ethereum block height')
    mode_group.add_argument('--layer-block', type=int, metavar='BLOCK_HEIGHT',
                           help='Collect data at specific Tellor Layer block height')
    
    # Monitoring parameters
    parser.add_argument('--interval', type=int, default=3600,
                       help='Monitoring interval in seconds (default: 3600)')
    
    # Bridge collection parameters
    deposits_default, withdrawals_default = get_bridge_csv_paths()
    parser.add_argument('--deposits-csv', default=deposits_default,
                       help=f'Path to bridge deposits CSV file (default: {deposits_default})')
    parser.add_argument('--withdrawals-csv', default=withdrawals_default,
                       help=f'Path to bridge withdrawals CSV file (default: {withdrawals_default})')
    
    # General options
    parser.add_argument('--db-path', default='tellor_balances.db',
                       help='Database file path (default: tellor_balances.db)')
    parser.add_argument('--debug', action='store_true',
                       help='Enable debug logging')
    
    args = parser.parse_args()
    
    # Set up logging
    setup_logging(args.debug)
    global logger
    logger = logging.getLogger(__name__)
    
    # Initialize collector
    try:
        collector = UnifiedDataCollector(db_path=args.db_path)
    except Exception as e:
        logger.error(f"Failed to initialize unified collector: {e}")
        sys.exit(1)
    
    # Run based on mode
    try:
        if args.summary:
            show_summary(collector)
        elif args.backfill:
            run_backfill(collector, args)
        elif args.monitor:
            run_monitoring_mode(collector, args)
        elif args.get_all_historic:
            run_historic_collection(collector, args)
        elif args.bridge_historic:
            run_bridge_historic_collection(collector, args)
        elif args.eth_block:
            run_specific_block_collection(collector, args)
        elif args.layer_block:
            run_specific_block_collection(collector, args)
        else:
            run_single_collection(collector, args)
            
    except Exception as e:
        logger.error(f"Error running unified collection: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main() 