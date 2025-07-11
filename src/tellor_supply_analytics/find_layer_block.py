# find the block number of the Tellor Layer block that is closest to any random ethereum block

import json
import logging
import subprocess
import os
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple

# Configure logging
logger = logging.getLogger(__name__)

# Configuration from environment variables
TELLOR_LAYER_RPC_URL = os.getenv('TELLOR_LAYER_RPC_URL', 'https://node-palmito.tellorlayer.com/rpc/')

class LayerBlockFinder:
    """
    Finds the Tellor Layer block that is closest to a given Ethereum timestamp.
    
    Uses a binary search approach with layerd RPC queries to efficiently find the 
    closest matching block within a configurable tolerance.
    """
    
    def __init__(self, layerd_path: str = './layerd', tolerance_seconds: int = 300):
        """
        Initialize the layer block finder.
        
        Args:
            layerd_path: Path to the layerd binary
            tolerance_seconds: Acceptable time difference in seconds (default: 5 minutes)
        """
        self.layerd_path = layerd_path
        self.tolerance_seconds = tolerance_seconds
        self._status_cache = None  # Cache status info to avoid repeated calls
        
    def run_layerd_command(self, cmd_args: list) -> Optional[Dict]:
        """Run a layerd command and return JSON output."""
        try:
            cmd = [self.layerd_path] + cmd_args
            logger.debug(f"Running command: {' '.join(cmd)}")
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                error_msg = result.stderr.strip()
                logger.error(f"Command failed: {error_msg}")
                return None
            
            # Parse JSON output
            try:
                return json.loads(result.stdout)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON output: {e}")
                logger.debug(f"Raw output: {result.stdout}")
                return None
                
        except subprocess.TimeoutExpired:
            logger.error("Command timed out")
            return None
        except Exception as e:
            logger.error(f"Error running command: {e}")
            return None
    
    def get_status_info(self) -> Optional[Dict]:
        """
        Get status information from layerd including current and oldest block info.
        
        Returns:
            Dictionary with current_height, current_timestamp, oldest_height, oldest_timestamp
        """
        if self._status_cache:
            return self._status_cache
            
        logger.info("Getting Tellor Layer status information")
        
        cmd_args = [
            'status',
            '--output', 'json',
            '--node', TELLOR_LAYER_RPC_URL
        ]
        
        result = self.run_layerd_command(cmd_args)
        if not result:
            return None
            
        try:
            sync_info = result['sync_info']
            
            # Extract current block info
            current_height = int(sync_info['latest_block_height'])
            current_time_str = sync_info['latest_block_time']
            
            # Extract oldest block info
            oldest_height = int(sync_info.get('earliest_block_height', 1))
            oldest_time_str = sync_info.get('earliest_block_time', current_time_str)
            
            # Parse timestamps
            current_timestamp = self._parse_timestamp(current_time_str)
            oldest_timestamp = self._parse_timestamp(oldest_time_str)
            
            if current_timestamp is None or oldest_timestamp is None:
                logger.error("Failed to parse timestamps from status")
                return None
            
            status_info = {
                'current_height': current_height,
                'current_timestamp': current_timestamp,
                'oldest_height': oldest_height,
                'oldest_timestamp': oldest_timestamp
            }
            
            # Calculate average block time
            if current_height > oldest_height:
                time_diff = current_timestamp - oldest_timestamp
                block_diff = current_height - oldest_height
                avg_block_time = time_diff / block_diff
                status_info['avg_block_time'] = avg_block_time
                
                logger.info(f"Status info: current_height={current_height}, "
                           f"current_timestamp={current_timestamp}, "
                           f"oldest_height={oldest_height}, "
                           f"oldest_timestamp={oldest_timestamp}, "
                           f"avg_block_time={avg_block_time:.2f}s")
            else:
                logger.warning("Cannot calculate average block time: insufficient block range")
                status_info['avg_block_time'] = 12.0  # Default fallback
            
            self._status_cache = status_info
            return status_info
            
        except (KeyError, ValueError) as e:
            logger.error(f"Error parsing status info: {e}")
            logger.debug(f"Raw status data: {result}")
            return None
    
    def _parse_timestamp(self, time_str: str) -> Optional[int]:
        """Parse ISO timestamp string to Unix timestamp."""
        try:
            # Handle nanosecond precision timestamps by truncating to microseconds
            if '.' in time_str and 'Z' in time_str:
                date_part, fractional_part = time_str.split('.')
                fractional_part = fractional_part.rstrip('Z')
                if len(fractional_part) > 6:
                    fractional_part = fractional_part[:6]
                time_str_truncated = f"{date_part}.{fractional_part}Z"
            else:
                time_str_truncated = time_str
            
            dt = datetime.fromisoformat(time_str_truncated.replace('Z', '+00:00'))
            return int(dt.timestamp())
            
        except ValueError as e:
            logger.error(f"Error parsing timestamp '{time_str}': {e}")
            return None
    
    def get_block_timestamp(self, height: int) -> Optional[int]:
        """
        Get the timestamp for a specific block height.
        
        Args:
            height: Block height to query
            
        Returns:
            Unix timestamp of the block, or None if failed
        """
        logger.debug(f"Getting timestamp for block height: {height}")
        
        cmd_args = [
            'query', 'block',
            '--type=height', str(height),
            '--output', 'json',
            '--node', TELLOR_LAYER_RPC_URL
        ]
        
        result = self.run_layerd_command(cmd_args)
        if not result:
            return None
            
        try:
            block_time = result['header']['time']
            timestamp = self._parse_timestamp(block_time)
            
            if timestamp:
                logger.debug(f"Block {height} timestamp: {block_time} ({timestamp})")
            
            return timestamp
            
        except (KeyError, ValueError) as e:
            logger.error(f"Error parsing block timestamp for height {height}: {e}")
            return None
    
    def find_closest_block(self, target_timestamp: int, max_iterations: int = 20) -> Optional[Tuple[int, int, int]]:
        """
        Find the Tellor Layer block closest to the target Ethereum timestamp.
        
        Args:
            target_timestamp: Target Ethereum block timestamp (Unix)
            max_iterations: Maximum number of iterations before giving up
            
        Returns:
            Tuple of (block_height, block_timestamp, time_difference) or None if failed
        """
        logger.info(f"Finding closest Tellor Layer block to timestamp {target_timestamp} "
                   f"({datetime.fromtimestamp(target_timestamp, tz=timezone.utc)})")
        
        # Get status information
        status_info = self.get_status_info()
        if not status_info:
            logger.error("Failed to get status information")
            return None
        
        current_height = status_info['current_height']
        current_timestamp = status_info['current_timestamp']
        oldest_height = status_info['oldest_height']
        oldest_timestamp = status_info['oldest_timestamp']
        avg_block_time = status_info['avg_block_time']
        
        # Check if target timestamp is within available range
        if target_timestamp > current_timestamp:
            logger.warning(f"Target timestamp {target_timestamp} is in the future "
                          f"(current: {current_timestamp})")
            # Return current block as best available
            return current_height, current_timestamp, abs(target_timestamp - current_timestamp)
        
        if target_timestamp < oldest_timestamp:
            logger.warning(f"Target timestamp {target_timestamp} is before oldest available "
                          f"(oldest: {oldest_timestamp})")
            # Return oldest block as best available
            return oldest_height, oldest_timestamp, abs(target_timestamp - oldest_timestamp)
        
        # Initial guess based on average block time
        time_diff = target_timestamp - current_timestamp
        estimated_blocks_diff = int(time_diff / avg_block_time)
        initial_guess = current_height + estimated_blocks_diff
        
        # Ensure initial guess is within bounds
        initial_guess = max(oldest_height, min(current_height, initial_guess))
        
        logger.info(f"Initial guess: block {initial_guess} "
                   f"(estimated {estimated_blocks_diff} blocks from current)")
        
        # Binary search bounds
        low_height = oldest_height
        high_height = current_height
        best_match = None
        best_diff = float('inf')
        
        for iteration in range(max_iterations):
            # Use initial guess for first iteration, then binary search
            if iteration == 0:
                guess_height = initial_guess
            else:
                guess_height = (low_height + high_height) // 2
            
            # Get timestamp for this height
            guess_timestamp = self.get_block_timestamp(guess_height)
            if guess_timestamp is None:
                logger.warning(f"Failed to get timestamp for height {guess_height}, skipping")
                # Adjust bounds and continue
                if guess_height > (low_height + high_height) // 2:
                    high_height = guess_height - 1
                else:
                    low_height = guess_height + 1
                continue
            
            time_diff = abs(target_timestamp - guess_timestamp)
            
            logger.info(f"Iteration {iteration + 1}: height={guess_height}, "
                       f"timestamp={guess_timestamp}, diff={time_diff}s")
            
            # Update best match
            if time_diff < best_diff:
                best_diff = time_diff
                best_match = (guess_height, guess_timestamp, time_diff)
            
            # Check if we're within tolerance
            if time_diff <= self.tolerance_seconds:
                logger.info(f"Found block within tolerance: height={guess_height}, "
                           f"timestamp={guess_timestamp}, diff={time_diff}s")
                return guess_height, guess_timestamp, time_diff
            
            # Adjust binary search bounds
            if guess_timestamp < target_timestamp:
                low_height = guess_height + 1
            else:
                high_height = guess_height - 1
            
            # Check if search space is exhausted
            if low_height > high_height:
                logger.info("Search space exhausted")
                break
        
        if best_match:
            height, timestamp, diff = best_match
            logger.info(f"Best match found: height={height}, timestamp={timestamp}, "
                       f"diff={diff}s (tolerance was {self.tolerance_seconds}s)")
            return best_match
        else:
            logger.error("No valid block found")
            return None


def find_layer_block_for_eth_timestamp(eth_timestamp: int, 
                                      tolerance_seconds: int = 300) -> Optional[Tuple[int, int, int]]:
    """
    Convenience function to find the closest Tellor Layer block for an Ethereum timestamp.
    
    Args:
        eth_timestamp: Ethereum block timestamp (Unix)
        tolerance_seconds: Acceptable time difference in seconds (default: 5 minutes)
        
    Returns:
        Tuple of (layer_block_height, layer_timestamp, time_difference) or None if failed
    """
    finder = LayerBlockFinder(tolerance_seconds=tolerance_seconds)
    return finder.find_closest_block(eth_timestamp)


if __name__ == "__main__":
    import argparse
    
    # Configure logging for CLI usage
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    parser = argparse.ArgumentParser(description='Find Tellor Layer block closest to Ethereum timestamp')
    parser.add_argument('eth_timestamp', type=int, help='Ethereum block timestamp (Unix)')
    parser.add_argument('--tolerance', type=int, default=300, 
                       help='Tolerance in seconds (default: 300)')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    
    args = parser.parse_args()
    
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    
    result = find_layer_block_for_eth_timestamp(args.eth_timestamp, args.tolerance)
    
    if result:
        height, timestamp, diff = result
        eth_dt = datetime.fromtimestamp(args.eth_timestamp, tz=timezone.utc)
        layer_dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        
        print(f"\n=== RESULT ===")
        print(f"Ethereum timestamp: {args.eth_timestamp} ({eth_dt})")
        print(f"Closest Layer block: {height}")
        print(f"Layer timestamp: {timestamp} ({layer_dt})")
        print(f"Time difference: {diff} seconds")
        print(f"Within tolerance: {'✓' if diff <= args.tolerance else '✗'}")
    else:
        print("Failed to find matching block")
        exit(1)

