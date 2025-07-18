#!/usr/bin/env python3
"""
Find the Tellor Layer block closest to any Ethereum timestamp using binary search.

This module implements a binary search algorithm to find the Tellor Layer block
that is closest to a given target timestamp. It uses the Cosmos SDK RPC endpoints
to query block data and timestamps.

Author: Blockchain Backend Engineering Team
"""

import os
import requests
import logging
from datetime import datetime, timezone
from typing import Optional, Tuple

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv() -> bool:
        return True

# Load environment variables
load_dotenv()

# Configuration
TELLOR_LAYER_RPC_URL = os.getenv('TELLOR_LAYER_RPC_URL')

# Configure logging
logger = logging.getLogger(__name__)

class TellorLayerBlockFinder:
    """
    Find Tellor Layer blocks by timestamp using binary search.
    
    This class provides functionality to find the block height H such that:
    block_time(H) ≤ timestamp and block_time(H+1) > timestamp
    (i.e., the latest block before or at the given timestamp)
    """
    
    def __init__(self, rpc_url: str = TELLOR_LAYER_RPC_URL):
        """
        Initialize the block finder.
        
        Args:
            rpc_url: Tellor Layer RPC URL (Cosmos SDK format)
        """
        self.rpc_url = rpc_url.rstrip('/')
        self.session = requests.Session()
        self.session.headers.update({
            'Accept': 'application/json',
            'User-Agent': 'Tellor-Layer-Block-Finder/1.0'
        })
    
    def get_block_time(self, height: int) -> Optional[datetime]:
        """
        Get the timestamp of a block at a specific height.
        
        Args:
            height: Block height to query
            
        Returns:
            datetime object in UTC or None if failed
        """
        try:
            url = f"{self.rpc_url}/block?height={height}"
            logger.debug(f"Querying block {height}: {url}")
            
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            
            # Extract timestamp from block header
            time_str = data["result"]["block"]["header"]["time"]
            
            # Handle nanosecond precision timestamps by truncating to microseconds
            # Format: "2025-06-23T17:23:55.344314112Z"
            if '.' in time_str and 'Z' in time_str:
                # Split at the decimal point
                date_part, fractional_part = time_str.split('.')
                # Keep only first 6 digits (microseconds) and add Z back
                fractional_part = fractional_part.rstrip('Z')
                if len(fractional_part) > 6:
                    fractional_part = fractional_part[:6]
                time_str_truncated = f"{date_part}.{fractional_part}Z"
            else:
                time_str_truncated = time_str
            
            # Parse ISO timestamp
            block_time = datetime.fromisoformat(time_str_truncated.replace("Z", "+00:00"))
            
            logger.debug(f"Block {height} timestamp: {block_time}")
            return block_time
            
        except requests.RequestException as e:
            logger.error(f"Error querying block {height}: {e}")
            return None
        except (KeyError, ValueError) as e:
            logger.error(f"Error parsing block {height} timestamp: {e}")
            return None
    
    def get_latest_height(self) -> Optional[int]:
        """
        Get the latest block height from the Tellor Layer.
        
        Returns:
            Latest block height or None if failed
        """
        try:
            url = f"{self.rpc_url}/status"
            logger.debug(f"Querying status: {url}")
            
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            height = int(data["result"]["sync_info"]["latest_block_height"])
            
            logger.info(f"Latest Tellor Layer height: {height}")
            return height
            
        except requests.RequestException as e:
            logger.error(f"Error querying latest height: {e}")
            return None
        except (KeyError, ValueError) as e:
            logger.error(f"Error parsing latest height: {e}")
            return None
    
    def find_block_by_timestamp(self, target_time: datetime) -> Optional[int]:
        """
        Find the block height H such that block_time(H) ≤ target_time and block_time(H+1) > target_time.
        
        Uses binary search algorithm to efficiently find the correct block.
        
        Args:
            target_time: Target timestamp (should be timezone-aware)
            
        Returns:
            Block height at or before the target timestamp, or None if failed
        """
        logger.info(f"Finding Tellor Layer block for timestamp: {target_time}")
        
        # Ensure target_time is timezone-aware (UTC)
        if target_time.tzinfo is None:
            target_time = target_time.replace(tzinfo=timezone.utc)
            logger.warning("Target time was naive, assuming UTC")
        
        # Get the search range
        high = self.get_latest_height()
        if high is None:
            logger.error("Failed to get latest height")
            return None
        
        low = 1  # Genesis block
        
        logger.info(f"Searching blocks {low} to {high} for timestamp {target_time}")
        
        # Binary search
        while low <= high:
            # *** CRITICAL FIX: Check for shutdown signal during binary search ***
            try:
                from run_unified_collection import shutdown_requested
                if shutdown_requested:
                    logger.info("Shutdown requested during block search, stopping...")
                    return None
            except ImportError:
                pass  # shutdown_requested not available
                
            mid = (low + high) // 2
            logger.debug(f"Checking block {mid} (range: {low} - {high})")
            
            mid_time = self.get_block_time(mid)
            if mid_time is None:
                logger.warning(f"Failed to get time for block {mid}, skipping")
                # Try to continue search by adjusting range
                if mid == low:
                    low += 1
                elif mid == high:
                    high -= 1
                else:
                    # Split the search space
                    high = mid - 1
                continue
            
            if mid_time < target_time:
                low = mid + 1
            elif mid_time > target_time:
                high = mid - 1
            else:
                # Exact match
                logger.info(f"Found exact match: block {mid} at {mid_time}")
                return mid
        
        # Return the block before the target timestamp
        result_height = high
        
        if result_height > 0:
            result_time = self.get_block_time(result_height)
            logger.info(f"Found closest block: {result_height} at {result_time} (target: {target_time})")
            return result_height
        else:
            logger.warning(f"Target timestamp {target_time} is before genesis block")
            return None
    
    def find_block_by_unix_timestamp(self, unix_timestamp: int) -> Optional[int]:
        """
        Convenience method to find block by Unix timestamp.
        
        Args:
            unix_timestamp: Unix timestamp (seconds since epoch)
            
        Returns:
            Block height at or before the target timestamp, or None if failed
        """
        target_time = datetime.fromtimestamp(unix_timestamp, tz=timezone.utc)
        return self.find_block_by_timestamp(target_time)
    
    def get_block_info_for_timestamp(self, target_time: datetime) -> Optional[Tuple[int, datetime, int]]:
        """
        Get complete block information for a target timestamp.
        
        Args:
            target_time: Target timestamp
            
        Returns:
            Tuple of (block_height, block_time, unix_timestamp) or None if failed
        """
        block_height = self.find_block_by_timestamp(target_time)
        if block_height is None:
            return None
        
        block_time = self.get_block_time(block_height)
        if block_time is None:
            return None
        
        unix_timestamp = int(block_time.timestamp())
        return block_height, block_time, unix_timestamp


# Convenience functions for backward compatibility and easy import
def find_layer_block_by_timestamp(target_time: datetime, rpc_url: str = TELLOR_LAYER_RPC_URL) -> Optional[int]:
    """
    Find the Tellor Layer block closest to a target timestamp.
    
    Args:
        target_time: Target timestamp (datetime object)
        rpc_url: Tellor Layer RPC URL
        
    Returns:
        Block height or None if failed
    """
    finder = TellorLayerBlockFinder(rpc_url)
    return finder.find_block_by_timestamp(target_time)


def find_layer_block_by_unix_timestamp(unix_timestamp: int, rpc_url: str = TELLOR_LAYER_RPC_URL) -> Optional[int]:
    """
    Find the Tellor Layer block closest to a Unix timestamp.
    
    Args:
        unix_timestamp: Unix timestamp (seconds since epoch)
        rpc_url: Tellor Layer RPC URL
        
    Returns:
        Block height or None if failed
    """
    finder = TellorLayerBlockFinder(rpc_url)
    return finder.find_block_by_unix_timestamp(unix_timestamp)


def find_layer_block_for_eth_timestamp(eth_timestamp: int, rpc_url: str = TELLOR_LAYER_RPC_URL) -> Optional[Tuple[int, datetime, int]]:
    """
    Find Tellor Layer block information for an Ethereum timestamp.
    
    This is the main function to resolve the historical data collection warning.
    
    Args:
        eth_timestamp: Ethereum block timestamp (Unix timestamp)
        rpc_url: Tellor Layer RPC URL
        
    Returns:
        Tuple of (layer_height, layer_time, layer_timestamp) or None if failed
    """
    logger.info(f"Finding Tellor Layer block for Ethereum timestamp: {eth_timestamp}")
    
    finder = TellorLayerBlockFinder(rpc_url)
    target_time = datetime.fromtimestamp(eth_timestamp, tz=timezone.utc)
    
    return finder.get_block_info_for_timestamp(target_time)


# Example usage
if __name__ == "__main__":
    # Example: Find block for a specific timestamp
    target_timestamp = datetime(2025, 7, 10, 18, 33, 36, tzinfo=timezone.utc)  # From the warning message
    
    print(f"Finding Tellor Layer block for timestamp: {target_timestamp}")
    
    finder = TellorLayerBlockFinder()
    
    # Test getting latest height
    latest = finder.get_latest_height()
    print(f"Latest height: {latest}")
    
    # Test finding block by timestamp
    block_height = finder.find_block_by_timestamp(target_timestamp)
    if block_height:
        print(f"Found block: {block_height}")
        
        # Get the actual block time for verification
        block_time = finder.get_block_time(block_height)
        print(f"Block time: {block_time}")
    else:
        print("Failed to find block")

