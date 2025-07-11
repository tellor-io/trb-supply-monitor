#!/usr/bin/env python3
"""
Unified Data Collector for Tellor Supply Analytics

This module provides a unified data collection system that uses Ethereum block timestamps
as the primary timeline. All data (supply, balances, bridge data) is collected and stored
for specific Ethereum blocks to ensure temporal consistency across all metrics.

Design Goals:
- Use Ethereum block timestamp as the ruler by which everything is measured
- Ensure that for any unique Ethereum block timestamp, all data columns are populated
- Support historical backfill and real-time collection
- Track data completeness and support incremental updates
"""

import os
import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple, Set
from pathlib import Path

from web3 import Web3

try:
    from .database import BalancesDatabase
    from .supply_collector import SupplyDataCollector
    from .get_active_balances import EnhancedActiveBalancesCollector
except (ImportError, ModuleNotFoundError):
    # Handle running as standalone script
    import sys
    sys.path.append(str(Path(__file__).parent.parent.parent))
    from src.tellor_supply_analytics.database import BalancesDatabase
    from src.tellor_supply_analytics.supply_collector import SupplyDataCollector
    from src.tellor_supply_analytics.get_active_balances import EnhancedActiveBalancesCollector

logger = logging.getLogger(__name__)

# Configuration
ETHEREUM_RPC_URL = os.getenv('ETHEREUM_RPC_URL', 'https://rpc.sepolia.org')
SEPOLIA_TRB_CONTRACT = os.getenv('SEPOLIA_TRB_CONTRACT', '0x80fc34a2f9FfE86F41580F47368289C402DEc660')
SEPOLIA_BRIDGE_CONTRACT = os.getenv('SEPOLIA_BRIDGE_CONTRACT', '0x5acb5977f35b1A91C4fE0F4386eB669E046776F2')

# ERC20 ABI for balanceOf function
ERC20_ABI = [
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function"
    }
]


class UnifiedDataCollector:
    """
    Unified data collector that uses Ethereum block timestamps as the primary timeline.
    
    This collector coordinates all data collection activities to ensure that for any given
    Ethereum block timestamp, we have complete data across all metrics:
    - Bridge balances (from Ethereum)
    - Supply data (from Tellor Layer)
    - Active balance data (from Tellor Layer)
    - Staking data (from Tellor Layer)
    """
    
    def __init__(self, db_path: str = 'tellor_balances.db'):
        """
        Initialize the unified data collector.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db = BalancesDatabase(db_path)
        
        # Initialize Web3 connection for Ethereum data
        try:
            self.w3 = Web3(Web3.HTTPProvider(ETHEREUM_RPC_URL))
            if not self.w3.is_connected():
                logger.warning(f"Failed to connect to Ethereum RPC: {ETHEREUM_RPC_URL}")
                self.w3 = None
            else:
                logger.info(f"Connected to Ethereum RPC: {ETHEREUM_RPC_URL}")
        except Exception as e:
            logger.error(f"Error connecting to Ethereum RPC: {e}")
            self.w3 = None
            
        # Initialize TRB contract
        if self.w3:
            try:
                self.trb_contract = self.w3.eth.contract(
                    address=Web3.to_checksum_address(SEPOLIA_TRB_CONTRACT),
                    abi=ERC20_ABI
                )
                logger.info(f"Initialized TRB contract: {SEPOLIA_TRB_CONTRACT}")
            except Exception as e:
                logger.error(f"Error initializing TRB contract: {e}")
                self.trb_contract = None
        else:
            self.trb_contract = None
        
        # Initialize component collectors
        self.supply_collector = SupplyDataCollector(db_path=db_path, use_csv=False)
        self.balance_collector = EnhancedActiveBalancesCollector(db_path=db_path, use_csv=False)
        
        logger.info("Unified data collector initialized")
    
    def get_ethereum_block_range(self, 
                                hours_back: int = 24, 
                                block_interval: int = 300) -> List[Tuple[int, int]]:
        """
        Generate a list of Ethereum blocks to collect data for.
        
        Args:
            hours_back: How many hours back to collect data for
            block_interval: Approximate seconds between blocks to target
            
        Returns:
            List of (block_number, block_timestamp) tuples
        """
        if not self.w3:
            logger.error("Web3 not available, cannot get Ethereum block range")
            return []
        
        try:
            # Get current block
            current_block = self.w3.eth.get_block('latest')
            current_block_number = int(current_block['number'])
            current_timestamp = int(current_block['timestamp'])
            
            # Calculate target timestamp range
            target_start_timestamp = current_timestamp - (hours_back * 3600)
            
            # Get existing timestamps to avoid duplicating work
            existing_timestamps = set(self.db.get_existing_eth_timestamps())
            
            # Estimate blocks per hour (assume ~12 second average block time)
            blocks_per_hour = 3600 // 12
            estimated_blocks_back = hours_back * blocks_per_hour
            
            blocks_to_check = []
            
            # Work backwards from current block
            for i in range(0, estimated_blocks_back, block_interval // 12):  # Convert seconds to blocks
                block_number = current_block_number - i
                if block_number <= 0:
                    break
                    
                try:
                    block = self.w3.eth.get_block(block_number)
                    block_timestamp = int(block['timestamp'])
                    
                    # Stop if we've gone back far enough
                    if block_timestamp < target_start_timestamp:
                        break
                    
                    # Skip if we already have this timestamp (within 60 seconds)
                    skip_block = False
                    for existing_ts in existing_timestamps:
                        if abs(block_timestamp - existing_ts) <= 60:
                            skip_block = True
                            break
                    
                    if not skip_block:
                        blocks_to_check.append((block_number, block_timestamp))
                    
                except Exception as e:
                    logger.warning(f"Error getting block {block_number}: {e}")
                    continue
            
            logger.info(f"Found {len(blocks_to_check)} Ethereum blocks to process")
            return blocks_to_check
            
        except Exception as e:
            logger.error(f"Error getting Ethereum block range: {e}")
            return []
    
    def collect_bridge_data_for_block(self, block_number: int, block_timestamp: int) -> Optional[float]:
        """
        Collect bridge balance data for a specific Ethereum block.
        
        Args:
            block_number: Ethereum block number
            block_timestamp: Ethereum block timestamp
            
        Returns:
            Bridge balance in TRB, or None if failed
        """
        if not self.w3 or not self.trb_contract:
            logger.error("Web3 or TRB contract not initialized")
            return None
            
        try:
            # Get bridge balance at specific block
            balance = self.trb_contract.functions.balanceOf(
                Web3.to_checksum_address(SEPOLIA_BRIDGE_CONTRACT)
            ).call(block_identifier=block_number)
            
            # Convert from wei to TRB (18 decimals)
            balance_trb = balance / (10 ** 18)
            
            logger.info(f"Bridge balance at ETH block {block_number}: {balance_trb:.6f} TRB")
            return balance_trb
            
        except Exception as e:
            logger.error(f"Error getting bridge balance for block {block_number}: {e}")
            return None
    
    def find_corresponding_layer_data(self, eth_timestamp: int, tolerance_hours: int = 2) -> Optional[Dict]:
        """
        Find Tellor Layer data that corresponds to an Ethereum timestamp.
        
        Args:
            eth_timestamp: Ethereum block timestamp
            tolerance_hours: How many hours tolerance for finding matching layer data
            
        Returns:
            Dictionary containing layer data, or None if not found
        """
        # Try to collect current layer data that's close to the Ethereum timestamp
        target_time = datetime.fromtimestamp(eth_timestamp, tz=timezone.utc)
        current_time = datetime.now(timezone.utc)
        
        # If the Ethereum timestamp is recent (within tolerance), get current layer data
        time_diff = abs((current_time - target_time).total_seconds())
        if time_diff <= tolerance_hours * 3600:
            logger.info(f"ETH timestamp {eth_timestamp} is recent, collecting current layer data")
            return self.supply_collector.collect_current_data()
        
        # For historical data, we'd need to implement layer block number lookup by timestamp
        # For now, log that we need historical layer data and return None
        logger.warning(f"ETH timestamp {eth_timestamp} is historical ({target_time}), "
                      f"historical layer data collection not yet implemented")
        return None
    
    def collect_balance_data_for_timestamp(self, eth_timestamp: int) -> Optional[List[Tuple[str, str, int, float]]]:
        """
        Collect balance data that corresponds to an Ethereum timestamp.
        
        Args:
            eth_timestamp: Ethereum block timestamp
            
        Returns:
            List of balance tuples, or None if collection failed
        """
        target_time = datetime.fromtimestamp(eth_timestamp, tz=timezone.utc)
        current_time = datetime.now(timezone.utc)
        
        # If the timestamp is recent (within 2 hours), collect current balances
        time_diff = abs((current_time - target_time).total_seconds())
        if time_diff <= 2 * 3600:
            logger.info(f"Collecting current balance data for recent ETH timestamp {eth_timestamp}")
            
            # Get active addresses
            addresses = self.balance_collector.get_all_addresses()
            if not addresses:
                logger.error("Failed to get active addresses")
                return None
            
            # Collect balances
            addresses_with_balances = []
            for i, (address, account_type) in enumerate(addresses, 1):
                if i % 100 == 0:
                    logger.info(f"Collected balances for {i}/{len(addresses)} addresses...")
                
                loya_balance, loya_balance_trb = self.balance_collector.get_address_balance(address)
                addresses_with_balances.append((address, account_type, loya_balance, loya_balance_trb))
                
                # Small delay to avoid overwhelming the RPC
                time.sleep(0.01)
            
            logger.info(f"Collected balances for {len(addresses_with_balances)} addresses")
            return addresses_with_balances
        
        # For historical balance data, we'd need to implement historical balance collection
        logger.warning(f"ETH timestamp {eth_timestamp} is historical, "
                      f"historical balance collection not yet implemented")
        return None
    
    def collect_unified_snapshot(self, eth_block_number: int, eth_timestamp: int) -> bool:
        """
        Collect a complete unified snapshot for a specific Ethereum block.
        
        Args:
            eth_block_number: Ethereum block number
            eth_timestamp: Ethereum block timestamp
            
        Returns:
            True if collection was successful, False otherwise
        """
        logger.info(f"Collecting unified snapshot for ETH block {eth_block_number} "
                   f"(timestamp {eth_timestamp})")
        
        # Check if we already have complete data for this timestamp
        existing_snapshot = self.db.get_unified_snapshot_by_eth_timestamp(eth_timestamp)
        if existing_snapshot and existing_snapshot.get('data_completeness_score', 0) >= 1.0:
            logger.info(f"Complete data already exists for ETH timestamp {eth_timestamp}")
            return True
        
        # Collect bridge data
        logger.info("Collecting bridge balance data...")
        bridge_balance = self.collect_bridge_data_for_block(eth_block_number, eth_timestamp)
        
        # Collect layer supply data
        logger.info("Collecting layer supply data...")
        supply_data = self.find_corresponding_layer_data(eth_timestamp)
        
        # Collect balance data
        logger.info("Collecting balance data...")
        balance_data = self.collect_balance_data_for_timestamp(eth_timestamp)
        
        # Save unified snapshot
        try:
            snapshot_id = self.db.save_unified_snapshot(
                eth_block_number=eth_block_number,
                eth_block_timestamp=eth_timestamp,
                supply_data=supply_data,
                balance_data=balance_data,
                bridge_balance_trb=bridge_balance
            )
            
            logger.info(f"Saved unified snapshot {snapshot_id} for ETH block {eth_block_number}")
            return True
            
        except Exception as e:
            logger.error(f"Error saving unified snapshot: {e}")
            return False
    
    def run_unified_collection(self, 
                             hours_back: int = 24, 
                             block_interval: int = 3600,
                             max_blocks: int = 50) -> int:
        """
        Run unified data collection for a range of Ethereum blocks.
        
        Args:
            hours_back: How many hours back to collect data for
            block_interval: Target interval between blocks (in seconds)
            max_blocks: Maximum number of blocks to process in one run
            
        Returns:
            Number of blocks successfully processed
        """
        logger.info(f"Starting unified collection for last {hours_back} hours")
        
        # Get target Ethereum blocks
        blocks_to_process = self.get_ethereum_block_range(hours_back, block_interval)
        
        if not blocks_to_process:
            logger.warning("No Ethereum blocks to process")
            return 0
        
        # Limit the number of blocks to process
        if len(blocks_to_process) > max_blocks:
            logger.info(f"Limiting processing to {max_blocks} most recent blocks")
            blocks_to_process = blocks_to_process[:max_blocks]
        
        successful_collections = 0
        
        for i, (block_number, block_timestamp) in enumerate(blocks_to_process, 1):
            logger.info(f"Processing block {i}/{len(blocks_to_process)}: "
                       f"ETH block {block_number} (timestamp {block_timestamp})")
            
            try:
                if self.collect_unified_snapshot(block_number, block_timestamp):
                    successful_collections += 1
                else:
                    logger.warning(f"Failed to collect data for ETH block {block_number}")
                
                # Add delay between collections to avoid overwhelming RPCs
                if i < len(blocks_to_process):
                    time.sleep(2)
                    
            except Exception as e:
                logger.error(f"Error processing ETH block {block_number}: {e}")
                continue
        
        logger.info(f"Unified collection completed: {successful_collections}/{len(blocks_to_process)} blocks processed")
        return successful_collections
    
    def backfill_incomplete_data(self, max_backfill: int = 20) -> int:
        """
        Backfill missing data for existing snapshots with incomplete data.
        
        Args:
            max_backfill: Maximum number of snapshots to backfill
            
        Returns:
            Number of snapshots that were updated
        """
        logger.info("Starting backfill of incomplete data")
        
        # Get snapshots with incomplete data
        incomplete_snapshots = self.db.get_incomplete_snapshots(min_completeness=1.0)
        
        if not incomplete_snapshots:
            logger.info("No incomplete snapshots found")
            return 0
        
        logger.info(f"Found {len(incomplete_snapshots)} incomplete snapshots")
        
        # Limit backfill to avoid overwhelming the system
        if len(incomplete_snapshots) > max_backfill:
            incomplete_snapshots = incomplete_snapshots[:max_backfill]
            logger.info(f"Limiting backfill to {max_backfill} snapshots")
        
        updated_count = 0
        
        for snapshot in incomplete_snapshots:
            eth_block_number = snapshot['eth_block_number']
            eth_timestamp = snapshot['eth_block_timestamp']
            current_score = snapshot.get('data_completeness_score', 0)
            
            logger.info(f"Backfilling data for ETH block {eth_block_number} "
                       f"(current completeness: {current_score:.2f})")
            
            try:
                # Attempt to collect missing data
                if self.collect_unified_snapshot(eth_block_number, eth_timestamp):
                    updated_count += 1
                    
            except Exception as e:
                logger.error(f"Error backfilling ETH block {eth_block_number}: {e}")
                continue
        
        logger.info(f"Backfill completed: {updated_count}/{len(incomplete_snapshots)} snapshots updated")
        return updated_count
    
    def get_data_summary(self) -> Dict:
        """Get a summary of unified data collection status."""
        try:
            snapshots = self.db.get_unified_snapshots(limit=1000)
            
            if not snapshots:
                return {"total_snapshots": 0, "complete_snapshots": 0, "incomplete_snapshots": 0}
            
            total_snapshots = len(snapshots)
            complete_snapshots = sum(1 for s in snapshots if s.get('data_completeness_score', 0) >= 1.0)
            incomplete_snapshots = total_snapshots - complete_snapshots
            
            latest_snapshot = snapshots[0] if snapshots else None
            oldest_snapshot = snapshots[-1] if snapshots else None
            
            return {
                "total_snapshots": total_snapshots,
                "complete_snapshots": complete_snapshots,
                "incomplete_snapshots": incomplete_snapshots,
                "completion_rate": complete_snapshots / total_snapshots if total_snapshots > 0 else 0,
                "latest_eth_timestamp": latest_snapshot.get('eth_block_timestamp') if latest_snapshot else None,
                "oldest_eth_timestamp": oldest_snapshot.get('eth_block_timestamp') if oldest_snapshot else None,
                "coverage_hours": (latest_snapshot.get('eth_block_timestamp', 0) - oldest_snapshot.get('eth_block_timestamp', 0)) / 3600 if latest_snapshot and oldest_snapshot else 0
            }
            
        except Exception as e:
            logger.error(f"Error getting data summary: {e}")
            return {"error": str(e)}


def main():
    """Main function for running unified data collection."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Unified Tellor Data Collector')
    parser.add_argument('--hours-back', type=int, default=24, help='Hours back to collect data for')
    parser.add_argument('--block-interval', type=int, default=3600, help='Target interval between blocks (seconds)')
    parser.add_argument('--max-blocks', type=int, default=50, help='Maximum blocks to process in one run')
    parser.add_argument('--backfill', action='store_true', help='Run backfill for incomplete data')
    parser.add_argument('--summary', action='store_true', help='Show data collection summary')
    parser.add_argument('--db-path', default='tellor_balances.db', help='Database file path')
    
    args = parser.parse_args()
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    collector = UnifiedDataCollector(db_path=args.db_path)
    
    if args.summary:
        summary = collector.get_data_summary()
        print("\n=== UNIFIED DATA COLLECTION SUMMARY ===")
        for key, value in summary.items():
            print(f"{key}: {value}")
        return
    
    if args.backfill:
        logger.info("Running backfill mode")
        updated = collector.backfill_incomplete_data()
        logger.info(f"Backfill completed: {updated} snapshots updated")
    else:
        logger.info("Running unified collection")
        processed = collector.run_unified_collection(
            hours_back=args.hours_back,
            block_interval=args.block_interval,
            max_blocks=args.max_blocks
        )
        logger.info(f"Collection completed: {processed} blocks processed")


if __name__ == '__main__':
    main() 