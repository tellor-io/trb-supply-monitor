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
import sys
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple, Set
from pathlib import Path

from web3 import Web3

try:
    from .database import BalancesDatabase
    from .supply_collector import SupplyDataCollector
    from .get_active_balances import EnhancedActiveBalancesCollector
    from .find_layer_block import TellorLayerBlockFinder, find_layer_block_for_eth_timestamp
except (ImportError, ModuleNotFoundError):
    # Handle running as standalone script
    import sys
    sys.path.append(str(Path(__file__).parent.parent.parent))
    from src.tellor_supply_analytics.database import BalancesDatabase
    from src.tellor_supply_analytics.supply_collector import SupplyDataCollector
    from src.tellor_supply_analytics.get_active_balances import EnhancedActiveBalancesCollector
    from src.tellor_supply_analytics.find_layer_block import TellorLayerBlockFinder, find_layer_block_for_eth_timestamp

logger = logging.getLogger(__name__)

# Import shutdown flag from run_unified_collection
try:
    from run_unified_collection import shutdown_requested, check_shutdown
except ImportError:
    # Fallback if running standalone
    shutdown_requested = False
    def check_shutdown():
        pass

# Configuration
ETHEREUM_RPC_URL = os.getenv('ETHEREUM_RPC_URL', 'https://rpc.sepolia.org')
SEPOLIA_TRB_CONTRACT = os.getenv('SEPOLIA_TRB_CONTRACT', '0x80fc34a2f9FfE86F41580F47368289C402DEc660')
SEPOLIA_BRIDGE_CONTRACT = os.getenv('SEPOLIA_BRIDGE_CONTRACT', '0x5acb5977f35b1A91C4fE0F4386eB669E046776F2')

# Bridge CSV configuration with environment variable support
BRIDGE_DEPOSITS_CSV_PATH = os.getenv('BRIDGE_DEPOSITS_CSV_PATH', 'example_bridge_deposits.csv')
BRIDGE_WITHDRAWALS_CSV_PATH = os.getenv('BRIDGE_WITHDRAWALS_CSV_PATH', 'example_bridge_withdrawals.csv')

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
    
    def find_ethereum_block_for_timestamp(self, target_timestamp: int) -> Optional[int]:
        """
        Find the Ethereum block number for a given timestamp using binary search.
        
        Args:
            target_timestamp: Unix timestamp to find block for
            
        Returns:
            Ethereum block number at or before the target timestamp, or None if failed
        """
        if not self.w3:
            logger.warning("Web3 not available, cannot find Ethereum block for timestamp")
            return None
            
        try:
            # Get current block as upper bound
            current_block = self.w3.eth.get_block('latest')
            high = int(current_block.get('number', 0))
            current_timestamp = int(current_block.get('timestamp', 0))
            
            # If target timestamp is in the future, return None
            if target_timestamp > current_timestamp:
                logger.warning(f"Target timestamp {target_timestamp} is in the future")
                return None
            
            # Start binary search
            low = 1  # Genesis block
            
            logger.info(f"Searching Ethereum blocks {low} to {high} for timestamp {target_timestamp}")
            
            while low <= high:
                mid = (low + high) // 2
                
                try:
                    block = self.w3.eth.get_block(mid)
                    block_timestamp = int(block.get('timestamp', 0))
                    
                    if block_timestamp < target_timestamp:
                        low = mid + 1
                    elif block_timestamp > target_timestamp:
                        high = mid - 1
                    else:
                        # Exact match
                        logger.info(f"Found exact Ethereum block match: {mid} at timestamp {block_timestamp}")
                        return mid
                        
                except Exception as e:
                    logger.warning(f"Error getting Ethereum block {mid}: {e}")
                    # Adjust search range and continue
                    if mid == low:
                        low += 1
                    elif mid == high:
                        high -= 1
                    else:
                        high = mid - 1
                    continue
            
            # Return the block at or before the target timestamp
            if high > 0:
                try:
                    result_block = self.w3.eth.get_block(high)
                    result_timestamp = int(result_block.get('timestamp', 0))
                    logger.info(f"Found closest Ethereum block: {high} at timestamp {result_timestamp} (target: {target_timestamp})")
                    return high
                except Exception as e:
                    logger.warning(f"Error verifying result block {high}: {e}")
                    return high  # Return anyway, it's our best estimate
            else:
                logger.warning(f"Target timestamp {target_timestamp} is before genesis block")
                return None
                
        except Exception as e:
            logger.error(f"Error finding Ethereum block for timestamp {target_timestamp}: {e}")
            return None

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
            current_block_number = int(current_block.get('number', 0))
            current_timestamp = int(current_block.get('timestamp', 0))
            
            # Get the latest block from our database to compare timestamps
            latest_db_snapshots = self.db.get_unified_snapshots(limit=1)
            if latest_db_snapshots:
                latest_db_timestamp = latest_db_snapshots[0].get('eth_block_timestamp', 0)
                
                # If the "current" block from RPC is older than our latest DB entry,
                # we're likely connected to an archive node with old data
                if current_timestamp < latest_db_timestamp:
                    logger.warning(
                        f"Current RPC block timestamp ({current_timestamp}) is older than latest DB "
                        f"timestamp ({latest_db_timestamp}). This appears to be an archive node "
                        "with historical data. Skipping collection to prevent data inconsistency."
                    )
                    return []
            
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
                    block_timestamp = int(block.get('timestamp', 0))
                    
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
            
            # Sort blocks by timestamp to ensure chronological order
            blocks_to_check.sort(key=lambda x: x[1])
            
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
    
    def calculate_historical_bridge_balance(self, target_timestamp: int, 
                                          deposits_csv: Optional[str] = None,
                                          withdrawals_csv: Optional[str] = None) -> Optional[float]:
        """
        Calculate historical bridge balance from CSV files up to a specific timestamp.
        
        Args:
            target_timestamp: Unix timestamp to calculate balance up to
            deposits_csv: Path to bridge deposits CSV file (uses env var if None)
            withdrawals_csv: Path to bridge withdrawals CSV file (uses env var if None)
            
        Returns:
            Bridge balance in TRB, or None if calculation failed
        """
        import csv
        from datetime import datetime, timezone
        from pathlib import Path
        
        # Use environment variables if paths not provided
        if deposits_csv is None:
            deposits_csv = BRIDGE_DEPOSITS_CSV_PATH
        if withdrawals_csv is None:
            withdrawals_csv = BRIDGE_WITHDRAWALS_CSV_PATH
        
        try:
            total_deposits = 0.0
            total_withdrawals = 0.0
            
            # Process deposits CSV
            deposits_file = Path(deposits_csv)
            if deposits_file.exists():
                logger.info(f"Processing deposits from {deposits_file}")
                with open(deposits_file, 'r') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        # Parse timestamp
                        timestamp_str = row.get('Timestamp', '')
                        if not timestamp_str:
                            continue
                            
                        try:
                            # Parse timestamp (format: "2025-06-20 13:24:27")
                            deposit_time = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                            deposit_time = deposit_time.replace(tzinfo=timezone.utc)
                            deposit_timestamp = int(deposit_time.timestamp())
                            
                            # Only include deposits up to target timestamp
                            if deposit_timestamp <= target_timestamp:
                                amount_wei = int(row.get('Amount', 0))
                                amount_trb = amount_wei / (10 ** 18)  # Convert from wei to TRB
                                total_deposits += amount_trb
                        except (ValueError, TypeError) as e:
                            logger.warning(f"Error parsing deposit row: {e}")
                            continue
                            
                logger.info(f"Total deposits up to timestamp {target_timestamp}: {total_deposits:.6f} TRB")
            else:
                logger.warning(f"Deposits file not found: {deposits_file}")
            
            # Process withdrawals CSV
            withdrawals_file = Path(withdrawals_csv)
            if withdrawals_file.exists():
                logger.info(f"Processing withdrawals from {withdrawals_file}")
                # Note: Withdrawals CSV doesn't have timestamps in the example
                # For now, we'll assume all withdrawals happened before the target timestamp
                # In a real implementation, you'd need timestamp data for withdrawals too
                with open(withdrawals_file, 'r') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        try:
                            # Amount appears to be in microTRB (6 decimals)
                            amount_micro_trb = int(row.get('Amount', 0))
                            amount_trb = amount_micro_trb / (10 ** 6)  # Convert from microTRB to TRB
                            total_withdrawals += amount_trb
                        except (ValueError, TypeError) as e:
                            logger.warning(f"Error parsing withdrawal row: {e}")
                            continue
                            
                logger.info(f"Total withdrawals: {total_withdrawals:.6f} TRB")
            else:
                logger.warning(f"Withdrawals file not found: {withdrawals_file}")
            
            # Calculate net bridge balance (deposits - withdrawals)
            bridge_balance = total_deposits - total_withdrawals
            
            logger.info(f"Historical bridge balance calculated: {bridge_balance:.6f} TRB "
                       f"(deposits: {total_deposits:.6f}, withdrawals: {total_withdrawals:.6f})")
            
            return bridge_balance
            
        except Exception as e:
            logger.error(f"Error calculating historical bridge balance: {e}")
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
        # For historical data, use the block finder to get corresponding Tellor Layer data
        logger.info(f"Finding corresponding Tellor Layer block for ETH timestamp {eth_timestamp}...")
        
        try:
            # Find the corresponding Tellor Layer block for this Ethereum timestamp
            layer_block_info = find_layer_block_for_eth_timestamp(eth_timestamp)
            if layer_block_info is None:
                logger.warning(f"Could not find corresponding Tellor Layer block for ETH timestamp {eth_timestamp}")
                return None
            
            layer_height, layer_time, layer_timestamp = layer_block_info
            
            # Verify that the timestamps are within tolerance
            time_diff_minutes = abs(eth_timestamp - layer_timestamp) / 60
            if time_diff_minutes > tolerance_hours * 60:
                logger.warning(f"Found Tellor Layer block {layer_height} but timestamps differ by {time_diff_minutes:.2f} minutes "
                             f"(max allowed: {tolerance_hours * 60} minutes)")
                return None
            
            logger.info(f"Found Tellor Layer block {layer_height} at {layer_time} for ETH timestamp {eth_timestamp}")
            
            # Now collect historical layer data at that specific block height
            historical_data = self.collect_historical_layer_data(layer_height, layer_timestamp, eth_timestamp)
            
            if historical_data:
                logger.info(f"Successfully collected historical Tellor Layer data for block {layer_height}")
                return historical_data
            else:
                logger.warning(f"Failed to collect historical data for Tellor Layer block {layer_height}")
                return None
                
        except Exception as e:
            logger.error(f"Error finding corresponding layer data for ETH timestamp {eth_timestamp}: {e}")
            return None
    
    def collect_historical_layer_data(self, layer_height: int, layer_timestamp: int, eth_timestamp: int) -> Optional[Dict]:
        """
        Collect historical Tellor Layer supply data for a specific block height.
        
        Args:
            layer_height: Tellor Layer block height
            layer_timestamp: Tellor Layer block timestamp
            eth_timestamp: Original Ethereum timestamp for reference
            
        Returns:
            Dictionary containing historical layer data, or None if failed
        """
        try:
            # Get total supply at the specific height
            layer_supply = self.supply_collector.get_total_supply(layer_height)
            if layer_supply is None:
                logger.error(f"Failed to get total supply for layer height {layer_height}")
                return None
            
            # Convert supply from loya to TRB
            layer_supply_trb = layer_supply / (10 ** 6)
            
            # Get staking pool data at the specific height
            staking_pool_data = self.supply_collector.get_staking_pool(layer_height)
            if staking_pool_data:
                not_bonded_tokens, bonded_tokens = staking_pool_data
            else:
                logger.warning(f"Failed to get staking pool data for height {layer_height}, using placeholder values")
                not_bonded_tokens = 0
                bonded_tokens = 0
            
            # Calculate free floating TRB
            free_floating_trb = layer_supply_trb - not_bonded_tokens - bonded_tokens
            
            # Find the corresponding Ethereum block number for this timestamp
            eth_block_number = self.find_ethereum_block_for_timestamp(eth_timestamp)
            if eth_block_number is None:
                logger.warning(f"Could not find Ethereum block for timestamp {eth_timestamp}, using 0")
                eth_block_number = 0
            
            # Create historical data structure similar to current data
            historical_data = {
                'eth_block_number': eth_block_number,  # Now using actual ETH block mapping
                'eth_block_timestamp': eth_timestamp,
                'bridge_balance_trb': 0.0,
                'layer_block_height': layer_height,
                'layer_block_timestamp': layer_timestamp,
                'layer_total_supply_trb': layer_supply_trb,
                'not_bonded_tokens': not_bonded_tokens,
                'bonded_tokens': bonded_tokens,
                'free_floating_trb': free_floating_trb
            }
            
            logger.info(f"Collected historical layer data for height {layer_height}: "
                       f"supply={layer_supply_trb:.2f} TRB, "
                       f"bonded={bonded_tokens:.2f}, "
                       f"not_bonded={not_bonded_tokens:.2f}")
            
            return historical_data
            
        except Exception as e:
            logger.error(f"Error collecting historical layer data for height {layer_height}: {e}")
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
        
        # Calculate time difference
        time_diff = abs((current_time - target_time).total_seconds())
        
        # Get active addresses first
        addresses = self.balance_collector.get_all_addresses()
        if not addresses:
            logger.error("Failed to get active addresses")
            return None
        
        # For recent timestamps (within 2 hours), collect current balances
        if time_diff <= 2 * 3600:
            logger.info(f"Collecting current balance data for recent ETH timestamp {eth_timestamp}")
            
            # Collect current balances
            addresses_with_balances = []
            for i, (address, account_type) in enumerate(addresses, 1):
                if i % 100 == 0:
                    logger.info(f"Collected balances for {i}/{len(addresses)} addresses...")
                
                loya_balance, loya_balance_trb = self.balance_collector.get_address_balance(address)
                addresses_with_balances.append((address, account_type, loya_balance, loya_balance_trb))
                
                # Small delay to avoid overwhelming the RPC
                time.sleep(0.01)
            
            logger.info(f"Collected current balances for {len(addresses_with_balances)} addresses")
            return addresses_with_balances
        
        # For historical timestamps, find the corresponding Tellor Layer block and query balances at that height
        logger.info(f"ETH timestamp {eth_timestamp} is historical ({target_time}), "
                   f"finding corresponding Tellor Layer block for balance collection...")
        
        try:
            # Find the corresponding Tellor Layer block for this Ethereum timestamp
            layer_block_info = find_layer_block_for_eth_timestamp(eth_timestamp)
            if layer_block_info is None:
                logger.warning(f"Could not find corresponding Tellor Layer block for ETH timestamp {eth_timestamp}")
                return None
            
            layer_height, layer_time, layer_timestamp = layer_block_info
            logger.info(f"Found Tellor Layer block {layer_height} at {layer_time} for balance collection")
            
            # Collect historical balances at the specific height
            addresses_with_balances = self.balance_collector.collect_balances_at_height(addresses, layer_height)
            
            logger.info(f"Collected historical balances for {len(addresses_with_balances)} addresses at height {layer_height}")
            return addresses_with_balances
            
        except Exception as e:
            logger.error(f"Error collecting historical balance data for ETH timestamp {eth_timestamp}: {e}")
            return None
    

    
    def collect_unified_snapshot(self, eth_block_number: int, eth_timestamp: int, layer_block_height: Optional[int] = None) -> bool:
        """
        Collect a complete unified snapshot for a specific Ethereum block.
        
        Args:
            eth_block_number: Ethereum block number
            eth_timestamp: Ethereum block timestamp
            layer_block_height: Optional specific Tellor Layer block height to use
            
        Returns:
            True if collection was successful, False otherwise
        """
        logger.info(f"Collecting unified snapshot for ETH block {eth_block_number} "
                   f"(timestamp {eth_timestamp})")
        if layer_block_height:
            logger.info(f"Using specified Tellor Layer block height: {layer_block_height}")
        
        # Check if we already have complete data for this timestamp
        existing_snapshot = self.db.get_unified_snapshot_by_eth_timestamp(eth_timestamp)
        if existing_snapshot and existing_snapshot.get('data_completeness_score', 0) >= 1.0:
            logger.info(f"Complete data already exists for ETH timestamp {eth_timestamp}")
            return True
        
        # Find the corresponding Ethereum block number if not provided
        if eth_block_number <= 0:
            found_block = self.find_ethereum_block_for_timestamp(eth_timestamp)
            if found_block is None:
                logger.error(f"Could not find Ethereum block for timestamp {eth_timestamp}")
                return False
            eth_block_number = found_block

        # *** CRITICAL FIX: Resolve Tellor Layer block height ONCE for timestamp consistency ***
        resolved_layer_height: int
        resolved_layer_timestamp: int
        
        if layer_block_height is None:
            # Find the corresponding Tellor Layer block for this Ethereum timestamp
            logger.info(f"Resolving Tellor Layer block for ETH timestamp {eth_timestamp}...")
            layer_block_info = find_layer_block_for_eth_timestamp(eth_timestamp)
            if layer_block_info is None:
                logger.error("Could not find corresponding Tellor Layer block, skipping snapshot")
                return False
            
            resolved_layer_height, layer_time, resolved_layer_timestamp = layer_block_info
            logger.info(f"Resolved to Tellor Layer block {resolved_layer_height} at {layer_time}")
        else:
            resolved_layer_height = layer_block_height
            # Get the timestamp for the specified layer block height
            block_info = self.supply_collector.get_block_info(layer_block_height)
            if block_info:
                resolved_layer_timestamp = block_info[1]
                logger.info(f"Using specified Tellor Layer block {layer_block_height} with timestamp {resolved_layer_timestamp}")
            else:
                logger.warning(f"Could not get timestamp for specified layer block {layer_block_height}, using ETH timestamp")
                resolved_layer_timestamp = eth_timestamp
        
        # Collect bridge data
        logger.info("Collecting bridge balance data...")
        bridge_balance = self.collect_bridge_data_for_block(eth_block_number, eth_timestamp)
        if bridge_balance is None:
            # For historical data, calculate bridge balance from CSV files
            bridge_balance = self.calculate_historical_bridge_balance(eth_timestamp)
            if bridge_balance is None:
                logger.error("Failed to calculate historical bridge balance from CSV files")
                bridge_balance = 0.0
        
        # Collect layer supply data using the resolved layer height
        logger.info(f"Collecting layer supply data at Tellor Layer block height {resolved_layer_height}...")
        supply_data = self.collect_historical_layer_data(resolved_layer_height, resolved_layer_timestamp, eth_timestamp)
        
        # If we couldn't collect layer supply data, skip this snapshot
        if supply_data is None:
            logger.error("Could not collect Tellor Layer supply data, skipping snapshot")
            return False
        
        # Collect balance data using the SAME resolved layer height
        logger.info(f"Collecting balance data at Tellor Layer block height {resolved_layer_height}...")
        
        # Get active addresses first
        addresses = self.balance_collector.get_all_addresses()
        if not addresses:
            logger.error("Failed to get active addresses")
            balance_data = None
        else:
            # Always collect balances at the resolved layer height for consistency
            balance_data = self.balance_collector.collect_balances_at_height(addresses, resolved_layer_height)
        
        # Save unified snapshot
        try:
            snapshot_id = self.db.save_unified_snapshot(
                eth_block_number=eth_block_number,
                eth_block_timestamp=eth_timestamp,
                supply_data=supply_data,
                balance_data=balance_data,
                bridge_balance_trb=bridge_balance
            )
            
            logger.info(f"Saved unified snapshot {snapshot_id} for ETH block {eth_block_number} using Tellor Layer block {resolved_layer_height}")
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
        
        try:
            for i, (block_number, block_timestamp) in enumerate(blocks_to_process, 1):
                # Check for shutdown request
                if shutdown_requested:
                    logger.info("Shutdown requested, stopping collection...")
                    break
                    
                logger.info(f"Processing block {i}/{len(blocks_to_process)}: "
                           f"ETH block {block_number} (timestamp {block_timestamp})")
                
                try:
                    if self.collect_unified_snapshot(block_number, block_timestamp):
                        successful_collections += 1
                    else:
                        logger.warning(f"Failed to collect data for ETH block {block_number}")
                    
                    # Add delay between collections to avoid overwhelming RPCs
                    if i < len(blocks_to_process) and not shutdown_requested:
                        time.sleep(2)
                        
                except Exception as e:
                    logger.error(f"Error processing ETH block {block_number}: {e}")
                    continue
                    
        except KeyboardInterrupt:
            logger.info("\nCollection interrupted by user. Saving progress...")
        except Exception as e:
            logger.error(f"Error in unified collection: {e}")
        finally:
            if successful_collections > 0:
                logger.info(f"Successfully collected data for {successful_collections} blocks")
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
        
        try:
            for snapshot in incomplete_snapshots:
                # Check for shutdown request
                if shutdown_requested:
                    logger.info("Shutdown requested, stopping backfill...")
                    break
                    
                eth_block_number = snapshot.get('eth_block_number', 0)
                eth_timestamp = snapshot.get('eth_block_timestamp', 0)
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
                    
        except KeyboardInterrupt:
            logger.info("\nBackfill interrupted by user. Saving progress...")
        except Exception as e:
            logger.error(f"Error in backfill: {e}")
        finally:
            if updated_count > 0:
                logger.info(f"Successfully updated {updated_count} snapshots")
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

    def cleanup_mismatched_timestamps(self, max_time_diff_minutes: int = 5) -> int:
        """
        Remove unified snapshots where Ethereum and Tellor Layer timestamps are too far apart.
        
        Args:
            max_time_diff_minutes: Maximum allowed difference between timestamps in minutes
            
        Returns:
            Number of rows removed
        """
        logger.info(f"Cleaning up snapshots with mismatched timestamps (max diff: {max_time_diff_minutes} minutes)")
        
        try:
            # Get all snapshots
            snapshots = self.db.get_unified_snapshots()
            if not snapshots:
                logger.info("No snapshots found to clean up")
                return 0
            
            rows_to_remove = []
            for snapshot in snapshots:
                eth_timestamp = snapshot.get('eth_block_timestamp', 0)
                layer_timestamp = snapshot.get('layer_block_timestamp', 0)
                
                # Skip if either timestamp is missing
                if not eth_timestamp or not layer_timestamp:
                    continue
                
                # Calculate time difference in minutes
                time_diff_minutes = abs(eth_timestamp - layer_timestamp) / 60
                
                if time_diff_minutes > max_time_diff_minutes:
                    logger.info(f"Found mismatched snapshot: ETH timestamp={eth_timestamp}, "
                              f"Layer timestamp={layer_timestamp}, diff={time_diff_minutes:.2f} minutes")
                    rows_to_remove.append(snapshot['id'])
            
            if not rows_to_remove:
                logger.info("No mismatched snapshots found")
                return 0
            
            # Remove the mismatched snapshots
            for snapshot_id in rows_to_remove:
                self.db.delete_unified_snapshot(snapshot_id)
            
            logger.info(f"Removed {len(rows_to_remove)} snapshots with mismatched timestamps")
            return len(rows_to_remove)
            
        except Exception as e:
            logger.error(f"Error cleaning up mismatched timestamps: {e}")
            return 0

    def remove_data_by_layer_block(self, layer_block_height: int) -> bool:
        """
        Remove all data associated with a specific Tellor Layer block height.
        
        Args:
            layer_block_height: Tellor Layer block height to remove data for
            
        Returns:
            True if data was removed successfully, False otherwise
        """
        logger.info(f"Removing all data for Tellor Layer block height {layer_block_height}")
        
        try:
            # Find all snapshots with this layer block height
            snapshots = self.db.get_unified_snapshots()
            snapshots_to_remove = [
                s for s in snapshots 
                if s.get('layer_block_height') == layer_block_height
            ]
            
            if not snapshots_to_remove:
                logger.info(f"No snapshots found for Tellor Layer block height {layer_block_height} - already clean")
                return True
            
            logger.info(f"Found {len(snapshots_to_remove)} snapshots to remove for layer block {layer_block_height}")
            
            # Remove each snapshot and its associated data
            removed_count = 0
            for snapshot in snapshots_to_remove:
                snapshot_id = snapshot.get('id')
                eth_timestamp = snapshot.get('eth_block_timestamp')
                
                logger.info(f"Removing snapshot {snapshot_id} (ETH timestamp: {eth_timestamp})")
                
                # Remove the unified snapshot (this should cascade to remove balances)
                if snapshot_id and self.db.delete_unified_snapshot(snapshot_id):
                    removed_count += 1
                else:
                    logger.warning(f"Failed to remove snapshot {snapshot_id}")
            
            if removed_count > 0:
                logger.info(f"Successfully removed {removed_count} snapshots for layer block {layer_block_height}")
                return True
            else:
                logger.error(f"Failed to remove any snapshots for layer block {layer_block_height}")
                return False
                
        except Exception as e:
            logger.error(f"Error removing data for layer block {layer_block_height}: {e}")
            return False

    def rerun_collection_for_layer_block(self, layer_block_height: int) -> bool:
        """
        Re-collect all data for a specific Tellor Layer block height.
        
        Args:
            layer_block_height: Tellor Layer block height to re-collect data for
            
        Returns:
            True if collection was successful, False otherwise
        """
        logger.info(f"Re-collecting data for Tellor Layer block height {layer_block_height}")
        
        try:
            # Get block info for the specified layer height
            block_info = self.supply_collector.get_block_info(layer_block_height)
            if not block_info:
                logger.error(f"Could not get block info for layer height {layer_block_height}")
                return False
            
            block_time_str, layer_timestamp = block_info
            logger.info(f"Found layer block {layer_block_height} at timestamp {layer_timestamp} ({block_time_str})")
            
            # Find the corresponding Ethereum timestamp for this layer block
            # We'll use the layer timestamp to find the closest Ethereum block
            eth_block_number = self.find_ethereum_block_for_timestamp(layer_timestamp)
            if eth_block_number is None:
                logger.error(f"Could not find corresponding Ethereum block for layer timestamp {layer_timestamp}")
                return False
            
            logger.info(f"Found corresponding Ethereum block {eth_block_number} for layer timestamp {layer_timestamp}")
            
            # Collect unified snapshot using the specific layer block height
            success = self.collect_unified_snapshot(
                eth_block_number=eth_block_number,
                eth_timestamp=layer_timestamp,  # Use layer timestamp as the eth timestamp
                layer_block_height=layer_block_height
            )
            
            if success:
                logger.info(f"Successfully re-collected data for layer block {layer_block_height}")
                return True
            else:
                logger.error(f"Failed to re-collect data for layer block {layer_block_height}")
                return False
                
        except Exception as e:
            logger.error(f"Error re-collecting data for layer block {layer_block_height}: {e}")
            return False

    def remove_and_rerun_layer_block(self, layer_block_height: int) -> bool:
        """
        Remove existing data for a Tellor Layer block and re-collect it.
        
        Args:
            layer_block_height: Tellor Layer block height to remove and re-collect
            
        Returns:
            True if both removal and re-collection were successful, False otherwise
        """
        logger.info(f"Removing and re-running collection for Tellor Layer block {layer_block_height}")
        
        # First, remove existing data
        if not self.remove_data_by_layer_block(layer_block_height):
            logger.error(f"Failed to remove existing data for layer block {layer_block_height}")
            return False
        
        # Wait a moment for database operations to complete
        time.sleep(1)
        
        # Then, re-collect the data
        if not self.rerun_collection_for_layer_block(layer_block_height):
            logger.error(f"Failed to re-collect data for layer block {layer_block_height}")
            return False
        
        logger.info(f"Successfully removed and re-collected data for layer block {layer_block_height}")
        return True

    def list_layer_blocks_in_database(self, limit: int = 100) -> List[Dict]:
        """
        List Tellor Layer blocks that have data in the database.
        
        Args:
            limit: Maximum number of blocks to return
            
        Returns:
            List of dictionaries with layer block information
        """
        try:
            snapshots = self.db.get_unified_snapshots(limit=limit)
            
            layer_blocks = []
            for snapshot in snapshots:
                layer_height = snapshot.get('layer_block_height')
                if layer_height:
                    layer_blocks.append({
                        'layer_block_height': layer_height,
                        'layer_block_timestamp': snapshot.get('layer_block_timestamp'),
                        'eth_block_number': snapshot.get('eth_block_number'),
                        'eth_block_timestamp': snapshot.get('eth_block_timestamp'),
                        'data_completeness_score': snapshot.get('data_completeness_score', 0),
                        'snapshot_id': snapshot.get('id'),
                        'collection_time': snapshot.get('collection_time')
                    })
            
            # Sort by layer block height (descending)
            layer_blocks.sort(key=lambda x: x['layer_block_height'], reverse=True)
            
            return layer_blocks
            
        except Exception as e:
            logger.error(f"Error listing layer blocks in database: {e}")
            return []

    def remove_data_by_layer_block_range(self, start_block: int, end_block: int, confirm: bool = True) -> bool:
        """
        Remove all data for Tellor Layer blocks within a specified range.
        
        Args:
            start_block: Starting Tellor Layer block height (inclusive)
            end_block: Ending Tellor Layer block height (inclusive)
            confirm: Whether to ask for user confirmation before deletion
            
        Returns:
            True if data was removed successfully, False otherwise
        """
        logger.info(f"Finding snapshots for Tellor Layer block range {start_block}-{end_block}")
        
        try:
            # Query database directly for snapshots in the range (bypassing the limit in get_unified_snapshots)
            import sqlite3
            
            snapshots_to_remove = []
            with sqlite3.connect(self.db.db_path) as conn:
                cursor = conn.execute('''
                    SELECT * FROM unified_snapshots 
                    WHERE layer_block_height >= ? AND layer_block_height <= ?
                    AND layer_block_height IS NOT NULL
                    ORDER BY layer_block_height ASC
                ''', (start_block, end_block))
                
                columns = [desc[0] for desc in cursor.description]
                snapshots_to_remove = [dict(zip(columns, row)) for row in cursor.fetchall()]
            
            if not snapshots_to_remove:
                logger.info(f"No snapshots found for Tellor Layer block range {start_block}-{end_block}")
                return True
            
            # Sort by layer block height for better display
            snapshots_to_remove.sort(key=lambda x: x.get('layer_block_height', 0))
            
            # Display snapshots that will be removed
            print(f"\n=== SNAPSHOTS TO BE REMOVED FOR LAYER BLOCK RANGE {start_block}-{end_block} ===")
            print(f"Found {len(snapshots_to_remove)} snapshots to remove:")
            print(f"{'Snapshot ID':<12} {'Layer Height':<15} {'Layer Timestamp':<15} {'ETH Block':<12} {'ETH Timestamp':<15} {'Completeness':<12}")
            print("-" * 105)
            
            for snapshot in snapshots_to_remove:
                layer_dt = datetime.fromtimestamp(snapshot.get('layer_block_timestamp', 0)).strftime('%Y-%m-%d %H:%M') if snapshot.get('layer_block_timestamp') else "N/A"
                eth_dt = datetime.fromtimestamp(snapshot.get('eth_block_timestamp', 0)).strftime('%Y-%m-%d %H:%M') if snapshot.get('eth_block_timestamp') else "N/A"
                
                print(f"{snapshot.get('id', 'N/A'):<12} "
                      f"{snapshot.get('layer_block_height', 'N/A'):<15} "
                      f"{layer_dt:<15} "
                      f"{snapshot.get('eth_block_number', 'N/A'):<12} "
                      f"{eth_dt:<15} "
                      f"{snapshot.get('data_completeness_score', 0):<12.2f}")
            
            print(f"\nTotal snapshots to remove: {len(snapshots_to_remove)}")
            
            # Ask for confirmation if required
            if confirm:
                response = input(f"\nAre you sure you want to remove these {len(snapshots_to_remove)} snapshots? (y/N): ").strip().lower()
                if response not in ['y', 'yes']:
                    logger.info("Operation cancelled by user")
                    return False
            
            # Remove the snapshots
            logger.info(f"Removing {len(snapshots_to_remove)} snapshots...")
            removed_count = 0
            
            for snapshot in snapshots_to_remove:
                snapshot_id = snapshot.get('id')
                layer_height = snapshot.get('layer_block_height')
                
                if snapshot_id and self.db.delete_unified_snapshot(snapshot_id):
                    removed_count += 1
                    if removed_count % 10 == 0:
                        logger.info(f"Removed {removed_count}/{len(snapshots_to_remove)} snapshots...")
                else:
                    logger.warning(f"Failed to remove snapshot {snapshot_id} for layer block {layer_height}")
            
            if removed_count > 0:
                logger.info(f"Successfully removed {removed_count} snapshots for layer block range {start_block}-{end_block}")
                return True
            else:
                logger.error(f"Failed to remove any snapshots for layer block range {start_block}-{end_block}")
                return False
                
        except Exception as e:
            logger.error(f"Error removing data for layer block range {start_block}-{end_block}: {e}")
            return False

    def parse_layer_block_range(self, range_str: str) -> Tuple[int, int]:
        """
        Parse a layer block range string in format "start-end".
        
        Args:
            range_str: Range string like "1554392-1791109"
            
        Returns:
            Tuple of (start_block, end_block)
            
        Raises:
            ValueError: If the range format is invalid
        """
        try:
            if '-' not in range_str:
                raise ValueError("Range must contain a hyphen (-)")
            
            parts = range_str.split('-')
            if len(parts) != 2:
                raise ValueError("Range must be in format 'start-end'")
            
            start_block = int(parts[0].strip())
            end_block = int(parts[1].strip())
            
            if start_block < 0 or end_block < 0:
                raise ValueError("Block numbers must be positive")
            
            if start_block > end_block:
                raise ValueError("Start block must be less than or equal to end block")
            
            return start_block, end_block
            
        except ValueError as e:
            raise ValueError(f"Invalid range format '{range_str}': {e}")


def main():
    """Main function for running unified data collection."""
    import argparse
    import signal
    import sys
    
    def signal_handler(signum, frame):
        """Handle interrupt signals gracefully."""
        logger.info("\nReceived interrupt signal. Shutting down gracefully...")
        sys.exit(0)
    
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)   # Ctrl+C
    signal.signal(signal.SIGTERM, signal_handler)  # Termination request
    
    parser = argparse.ArgumentParser(description='Unified Tellor Data Collector')
    parser.add_argument('--hours-back', type=int, default=24, help='Hours back to collect data for')
    parser.add_argument('--block-interval', type=int, default=3600, help='Target interval between blocks (seconds)')
    parser.add_argument('--max-blocks', type=int, default=50, help='Maximum blocks to process in one run')
    parser.add_argument('--backfill', action='store_true', help='Run backfill for incomplete data')
    parser.add_argument('--summary', action='store_true', help='Show data collection summary')
    parser.add_argument('--cleanup', action='store_true', help='Clean up snapshots with mismatched timestamps')
    parser.add_argument('--max-time-diff', type=int, default=5, help='Maximum allowed time difference in minutes for cleanup')
    parser.add_argument('--remove-layer-block', type=int, help='Remove data for specific Tellor Layer block height')
    parser.add_argument('--rerun-layer-block', type=int, help='Re-collect data for specific Tellor Layer block height')
    parser.add_argument('--remove-and-rerun', type=int, help='Remove and re-collect data for specific Tellor Layer block height')
    parser.add_argument('--remove-range', type=str, help='Remove data for range of Tellor Layer blocks (format: start-end, e.g., 1554392-1791109)')
    parser.add_argument('--list-layer-blocks', action='store_true', help='List Tellor Layer blocks in database')
    parser.add_argument('--list-limit', type=int, default=50, help='Limit for listing layer blocks')
    parser.add_argument('--db-path', default='tellor_balances.db', help='Database file path')
    
    args = parser.parse_args()
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    try:
        collector = UnifiedDataCollector(db_path=args.db_path)
        
        if args.summary:
            summary = collector.get_data_summary()
            print("\n=== UNIFIED DATA COLLECTION SUMMARY ===")
            for key, value in summary.items():
                print(f"{key}: {value}")
            return
        
        if args.list_layer_blocks:
            logger.info("Listing Tellor Layer blocks in database")
            layer_blocks = collector.list_layer_blocks_in_database(limit=args.list_limit)
            if layer_blocks:
                print(f"\n=== TELLOR LAYER BLOCKS IN DATABASE (latest {len(layer_blocks)}) ===")
                print(f"{'Layer Height':<15} {'Layer Timestamp':<12} {'ETH Block':<12} {'ETH Timestamp':<12} {'Completeness':<12} {'Collection Time'}")
                print("-" * 100)
                for block in layer_blocks:
                    layer_dt = datetime.fromtimestamp(block['layer_block_timestamp']) if block['layer_block_timestamp'] else "N/A"
                    eth_dt = datetime.fromtimestamp(block['eth_block_timestamp']) if block['eth_block_timestamp'] else "N/A"
                    print(f"{block['layer_block_height']:<15} {block['layer_block_timestamp']:<12} "
                          f"{block['eth_block_number']:<12} {block['eth_block_timestamp']:<12} "
                          f"{block['data_completeness_score']:<12.2f} {block['collection_time'] or 'N/A'}")
            else:
                print("No Tellor Layer blocks found in database")
            return
        
        if args.remove_range:
            try:
                start_block, end_block = collector.parse_layer_block_range(args.remove_range)
                logger.info(f"Removing data for Tellor Layer block range {start_block}-{end_block}")
                success = collector.remove_data_by_layer_block_range(start_block, end_block)
                if success:
                    logger.info(f"Successfully removed data for layer block range {start_block}-{end_block}")
                else:
                    logger.error(f"Failed to remove data for layer block range {start_block}-{end_block}")
            except ValueError as e:
                logger.error(f"Invalid range format: {e}")
                sys.exit(1)
            return
        
        if args.remove_layer_block:
            logger.info(f"Removing data for Tellor Layer block {args.remove_layer_block}")
            success = collector.remove_data_by_layer_block(args.remove_layer_block)
            if success:
                logger.info(f"Successfully removed data for layer block {args.remove_layer_block}")
            else:
                logger.error(f"Failed to remove data for layer block {args.remove_layer_block}")
            return
        
        if args.rerun_layer_block:
            logger.info(f"Re-running collection for Tellor Layer block {args.rerun_layer_block}")
            success = collector.rerun_collection_for_layer_block(args.rerun_layer_block)
            if success:
                logger.info(f"Successfully re-collected data for layer block {args.rerun_layer_block}")
            else:
                logger.error(f"Failed to re-collect data for layer block {args.rerun_layer_block}")
            return
        
        if args.remove_and_rerun:
            logger.info(f"Removing and re-running collection for Tellor Layer block {args.remove_and_rerun}")
            success = collector.remove_and_rerun_layer_block(args.remove_and_rerun)
            if success:
                logger.info(f"Successfully removed and re-collected data for layer block {args.remove_and_rerun}")
            else:
                logger.error(f"Failed to remove and re-collect data for layer block {args.remove_and_rerun}")
            return
        
        if args.cleanup:
            logger.info("Running cleanup mode")
            removed = collector.cleanup_mismatched_timestamps(max_time_diff_minutes=args.max_time_diff)
            logger.info(f"Cleanup completed: {removed} snapshots removed")
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
            
    except KeyboardInterrupt:
        logger.info("\nReceived keyboard interrupt. Shutting down gracefully...")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main() 