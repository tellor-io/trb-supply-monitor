#!/usr/bin/env python3
"""
Tellor Supply Analytics Collector

This script collects token supply data from multiple blockchain sources:
1. Tellor Layer blockchain data using layerd CLI
2. Ethereum bridge contract balances using web3.py
3. Historical data collection going back in time

Author: Blockchain Backend Engineering Team
"""

import os
import csv
import json
import subprocess
import time
import requests
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, List, Tuple
import logging
from pathlib import Path
import pytz

from web3 import Web3
try:
    from dotenv import load_dotenv
except ImportError:
    print("Warning: python-dotenv not installed. Using environment variables directly.")
    def load_dotenv() -> bool:
        return True

try:
    from discord_webhook import DiscordWebhook, DiscordEmbed
except ImportError:
    print("Warning: discord-webhook not installed. Discord alerts will be disabled.")
    DiscordWebhook = None
    DiscordEmbed = None

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
TELLOR_LAYER_RPC_URL = os.getenv('TELLOR_LAYER_RPC_URL', 'https://node-palmito.tellorlayer.com/rpc/')
LAYER_GRPC_URL = os.getenv('LAYER_GRPC_URL', 'http://node-palmito.tellorlayer.com')
ETHEREUM_RPC_URL = os.getenv('ETHEREUM_RPC_URL', 'https://rpc.sepolia.org')
SEPOLIA_TRB_CONTRACT = os.getenv('SEPOLIA_TRB_CONTRACT', '0x80fc34a2f9FfE86F41580F47368289C402DEc660')
SEPOLIA_BRIDGE_CONTRACT = os.getenv('SEPOLIA_BRIDGE_CONTRACT', '0x5acb5977f35b1A91C4fE0F4386eB669E046776F2')
CURRENT_DATA_INTERVAL = int(os.getenv('CURRENT_DATA_INTERVAL', '300'))  # Default 5 minutes (300 seconds)
DISCORD_WEBHOOK_URL = os.getenv('DISCORD_WEBHOOK_URL', '')  # Discord webhook URL for alerts

# CSV Configuration
CSV_FILE = 'supply_data.csv'
CSV_HEADERS = [
    'eth_block_number',
    'eth_block_timestamp',
    'bridge_balance_trb',
    'layer_block_height',
    'layer_block_timestamp', 
    'layer_total_supply_trb',
    'not_bonded_tokens',
    'bonded_tokens',
    'free_floating_trb'
]

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


class SupplyDataCollector:
    """Collects token supply data from multiple blockchain sources."""
    
    def __init__(self):
        """Initialize the supply data collector."""
        self.layerd_path = './layerd'
        self.csv_file = CSV_FILE
        self.initialize_csv()
        
        # Initialize Web3 connection
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
        
        # Track last daily alert time
        self.last_daily_alert = None
    
    def initialize_csv(self):
        """Initialize CSV file with headers if it doesn't exist."""
        if not Path(self.csv_file).exists():
            with open(self.csv_file, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(CSV_HEADERS)
            logger.info(f"Created CSV file: {self.csv_file}")
        else:
            logger.info(f"CSV file already exists: {self.csv_file}")
    
    def run_layerd_command(self, cmd_args: List[str]) -> Optional[Dict]:
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
                if "rpc error: code = InvalidArgument" in error_msg:
                    logger.warning(f"RPC InvalidArgument error: {error_msg}")
                    return None
                else:
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
    
    def get_current_height(self) -> Optional[int]:
        """
        Get the current block height from Tellor Layer using layerd status.
        
        Returns:
            Current block height or None if failed
        """
        logger.info("Getting current block height from Tellor Layer")
        
        cmd_args = [
            'status',
            '--output', 'json',
            '--node', TELLOR_LAYER_RPC_URL
        ]
        
        result = self.run_layerd_command(cmd_args)
        if not result:
            return None
            
        try:
            # Extract latest block height from sync_info
            latest_height = result['sync_info']['latest_block_height']
            height = int(latest_height)
            
            logger.info(f"Current Tellor Layer height: {height}")
            return height
            
        except (KeyError, ValueError) as e:
            logger.error(f"Error parsing current height: {e}")
            logger.debug(f"Raw status data: {result}")
            return None

    def get_block_info(self, height: int) -> Optional[Tuple[str, int]]:
        """
        Goal 1: Get block information for a specific height.
        
        Returns:
            Tuple of (timestamp_str, timestamp_unix) or None if failed
        """
        logger.info(f"Getting block info for height: {height}")
        
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
            # Extract timestamp from block data
            block_time = result['header']['time']
            
            # Handle nanosecond precision timestamps by truncating to microseconds
            # Format: "2025-06-23T17:23:55.344314112Z"
            if '.' in block_time and 'Z' in block_time:
                # Split at the decimal point
                date_part, fractional_part = block_time.split('.')
                # Keep only first 6 digits (microseconds) and add Z back
                fractional_part = fractional_part.rstrip('Z')
                if len(fractional_part) > 6:
                    fractional_part = fractional_part[:6]
                block_time_truncated = f"{date_part}.{fractional_part}Z"
            else:
                block_time_truncated = block_time
            
            # Parse ISO timestamp and convert to Unix timestamp
            dt = datetime.fromisoformat(block_time_truncated.replace('Z', '+00:00'))
            timestamp_unix = int(dt.timestamp())
            
            logger.info(f"Block {height} timestamp: {block_time} ({timestamp_unix})")
            return block_time, timestamp_unix
            
        except (KeyError, ValueError) as e:
            logger.error(f"Error parsing block timestamp: {e}")
            logger.debug(f"Raw block data: {result}")
            return None
    
    def get_total_supply(self, height: int) -> Optional[int]:
        """
        Goal 2: Get total supply at a specific height.
        
        Returns:
            Total supply amount in loya or None if failed
        """
        logger.info(f"Getting total supply at height: {height}")
        
        cmd_args = [
            'query', 'bank', 'total-supply',
            '--height', str(height),
            '--output', 'json',
            '--node', TELLOR_LAYER_RPC_URL
        ]
        
        result = self.run_layerd_command(cmd_args)
        if not result:
            return None
            
        try:
            # Find loya denomination in supply
            for supply_item in result.get('supply', []):
                if supply_item.get('denom') == 'loya':
                    amount = int(supply_item['amount'])
                    logger.info(f"Total supply at height {height}: {amount} loya")
                    return amount
            
            logger.warning(f"No loya supply found at height {height}")
            return None
            
        except (KeyError, ValueError) as e:
            logger.error(f"Error parsing total supply: {e}")
            return None
    
    def get_staking_pool(self, height: Optional[int] = None) -> Optional[Tuple[float, float]]:
        """
        Get staking pool data (bonded and not bonded tokens) at a specific height.
        
        Args:
            height: Block height for historical data, or None for current
            
        Returns:
            Tuple of (not_bonded_tokens, bonded_tokens) in TRB units or None if failed
        """
        try:
            url = f"{LAYER_GRPC_URL}:1317/cosmos/staking/v1beta1/pool"
            headers = {}
            
            if height is not None:
                headers["x-cosmos-block-height"] = str(height)
                logger.info(f"Getting staking pool data at height: {height}")
            else:
                logger.info("Getting current staking pool data")
            
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            
            # Extract bonded and not bonded tokens
            pool = data.get('pool', {})
            not_bonded_tokens = int(pool.get('not_bonded_tokens', 0)) / 10 ** 6
            bonded_tokens = int(pool.get('bonded_tokens', 0)) / 10 ** 6
            
            logger.info(f"Staking pool data - Bonded: {bonded_tokens}, Not Bonded: {not_bonded_tokens}")
            return not_bonded_tokens, bonded_tokens
            
        except requests.RequestException as e:
            logger.error(f"Error querying staking pool: {e}")
            return None
        except (KeyError, ValueError, json.JSONDecodeError) as e:
            logger.error(f"Error parsing staking pool data: {e}")
            return None
    
    def get_bridge_balance(self, block_number: Optional[int] = None) -> Optional[Tuple[int, int, str, float]]:
        """
        Goal 3: Get TRB balance in bridge contract at specific block.
        
        Args:
            block_number: Ethereum block number, or None for latest
            
        Returns:
            Tuple of (block_number, timestamp, datetime_str, balance_trb) or None if failed
        """
        if not self.w3 or not self.trb_contract:
            logger.error("Web3 or TRB contract not initialized")
            return None
            
        try:
            # Get block info
            if block_number is None:
                block = self.w3.eth.get_block('latest')
                block_number = int(block.get('number', 0))
            else:
                block = self.w3.eth.get_block(block_number)
            
            timestamp = int(block.get('timestamp', 0))
            datetime_str = datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()
            
            # Get bridge balance
            balance = self.trb_contract.functions.balanceOf(
                Web3.to_checksum_address(SEPOLIA_BRIDGE_CONTRACT)
            ).call(block_identifier=block_number)
            
            # Convert from wei to TRB (18 decimals)
            balance_trb = balance / (10 ** 18)
            
            logger.info(f"Bridge balance at block {block_number}: {balance_trb} TRB")
            return block_number, timestamp, datetime_str, balance_trb
            
        except Exception as e:
            logger.error(f"Error getting bridge balance: {e}")
            return None
    
    def collect_current_data(self) -> Optional[Dict]:
        """Collect current supply data from all sources."""
        logger.info("Collecting current supply data...")
        
        # Get current Ethereum block info (optional, fallback if unavailable)
        eth_data = self.get_bridge_balance()
        if eth_data:
            eth_block, eth_timestamp, eth_datetime, bridge_balance = eth_data
        else:
            logger.warning("Failed to get Ethereum data, using placeholder values")
            # Use placeholder values if Ethereum RPC is unavailable
            import time
            eth_block = 0
            eth_timestamp = int(time.time())
            eth_datetime = datetime.fromtimestamp(eth_timestamp, tz=timezone.utc).isoformat()
            bridge_balance = 0.0
        
        # Get current Tellor Layer block height from the layerd CLI
        current_height = self.get_current_height()
        if current_height is None:
            logger.error("Failed to get current height from Tellor Layer")
            return None
        
        # Try to find a valid height by going backwards
        layer_block_time = None
        layer_supply = None
        
        for height in range(current_height, current_height - 10000, -100):
            block_info = self.get_block_info(height)
            if block_info:
                layer_block_time = block_info[1]  # Unix timestamp
                layer_supply = self.get_total_supply(height)
                if layer_supply is not None:
                    current_height = height
                    break
        
        if layer_block_time is None or layer_supply is None:
            logger.error("Failed to get Tellor Layer data")
            return None
        
        # Convert supply from loya to TRB (assuming 18 decimals)
        layer_supply_trb = layer_supply / (10 ** 6)
        
        # Get current staking pool data
        staking_pool_data = self.get_staking_pool()
        if staking_pool_data:
            not_bonded_tokens, bonded_tokens = staking_pool_data
        else:
            logger.warning("Failed to get staking pool data, using placeholder values")
            not_bonded_tokens = 0
            bonded_tokens = 0
        
        # Calculate free floating TRB
        # Staking pool values are already in TRB units
        free_floating_trb = layer_supply_trb - not_bonded_tokens - bonded_tokens
        
        data = {
            'eth_block_number': eth_block,
            'eth_block_timestamp': eth_timestamp,
            'bridge_balance_trb': bridge_balance,
            'layer_block_height': current_height,
            'layer_block_timestamp': layer_block_time,
            'layer_total_supply_trb': layer_supply_trb,
            'not_bonded_tokens': not_bonded_tokens,
            'bonded_tokens': bonded_tokens,
            'free_floating_trb': free_floating_trb
        }
        
        logger.info(f"Collected data: {data}")
        return data
    
    def get_existing_timestamps(self) -> List[int]:
        """Get all existing layer block timestamps from CSV file."""
        timestamps = []
        try:
            if not Path(self.csv_file).exists():
                return timestamps
                
            with open(self.csv_file, 'r', newline='') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if 'layer_block_timestamp' in row and row['layer_block_timestamp']:
                        try:
                            timestamp = int(row['layer_block_timestamp'])
                            timestamps.append(timestamp)
                        except (ValueError, TypeError):
                            continue
            logger.info(f"Found {len(timestamps)} existing timestamps in CSV")
        except Exception as e:
            logger.error(f"Error reading existing timestamps: {e}")
        
        return timestamps

    def save_to_csv(self, data: Dict):
        """Save data to CSV file."""
        try:
            with open(self.csv_file, 'a', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
                writer.writerow(data)
            logger.info(f"Data saved to {self.csv_file}")
        except Exception as e:
            logger.error(f"Error saving to CSV: {e}")
    
    def get_last_csv_row(self) -> Optional[Dict]:
        """Get the last row from the CSV file."""
        try:
            if not Path(self.csv_file).exists():
                return None
                
            with open(self.csv_file, 'r', newline='') as f:
                reader = csv.DictReader(f)
                last_row = None
                for row in reader:
                    last_row = row
                return last_row
        except Exception as e:
            logger.error(f"Error reading last CSV row: {e}")
            return None
    
    def send_discord_alert(self, title: str, description: str, color: int = 0x00FF00):
        """Send a Discord webhook alert."""
        if not DISCORD_WEBHOOK_URL or not DiscordWebhook or not DiscordEmbed:
            logger.warning("Discord webhook not configured or discord-webhook not installed")
            return False
            
        try:
            webhook = DiscordWebhook(url=DISCORD_WEBHOOK_URL)
            embed = DiscordEmbed(title=title, description=description, color=color)
            embed.set_timestamp()
            webhook.add_embed(embed)
            
            response = webhook.execute()
            if response.status_code == 200:
                logger.info(f"Discord alert sent: {title}")
                return True
            else:
                logger.error(f"Failed to send Discord alert: {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"Error sending Discord alert: {e}")
            return False
    
    def check_bonded_tokens_alert(self, current_data: Dict, previous_data: Optional[Dict]):
        """Check for bonded tokens changes and send alerts if needed."""
        if not previous_data:
            logger.info("No previous data available for comparison")
            return
            
        try:
            current_bonded = int(current_data.get('bonded_tokens', 0))
            previous_bonded = int(previous_data.get('bonded_tokens', 0))
            
            if current_bonded > previous_bonded:
                # Calculate percentage increase
                increase = current_bonded - previous_bonded
                percentage_increase = (increase / previous_bonded) * 100 if previous_bonded > 0 else 0
                
                # Format the increase alert message
                title = "🚀 Bonded Tokens Increased!"
                description = (
                    f"**Previous Bonded Tokens:** {previous_bonded:,}\n"
                    f"**Current Bonded Tokens:** {current_bonded:,}\n"
                    f"**Increase:** {increase:,} (+{percentage_increase:.2f}%)\n\n"
                    f"**Block Height:** {current_data.get('layer_block_height', 'N/A')}\n"
                    f"**Timestamp:** <t:{current_data.get('layer_block_timestamp', 0)}:F>"
                )
                
                self.send_discord_alert(title, description, color=0x00FF00)  # Green color
                logger.info(f"Bonded tokens increased by {percentage_increase:.2f}%: {previous_bonded:,} -> {current_bonded:,}")
                
            elif current_bonded < previous_bonded:
                # Calculate percentage decrease
                decrease = previous_bonded - current_bonded
                percentage_decrease = (decrease / previous_bonded) * 100 if previous_bonded > 0 else 0
                
                # Format the decrease alert message
                title = "📉 Bonded Tokens Decreased!"
                description = (
                    f"**Previous Bonded Tokens:** {previous_bonded:,}\n"
                    f"**Current Bonded Tokens:** {current_bonded:,}\n"
                    f"**Decrease:** {decrease:,} (-{percentage_decrease:.2f}%)\n\n"
                    f"**Block Height:** {current_data.get('layer_block_height', 'N/A')}\n"
                    f"**Timestamp:** <t:{current_data.get('layer_block_timestamp', 0)}:F>"
                )
                
                self.send_discord_alert(title, description, color=0xFF0000)  # Red color
                logger.info(f"Bonded tokens decreased by {percentage_decrease:.2f}%: {previous_bonded:,} -> {current_bonded:,}")
                
            else:
                logger.debug(f"No bonded tokens change detected: {previous_bonded:,} -> {current_bonded:,}")
                
        except (ValueError, TypeError) as e:
            logger.error(f"Error checking bonded tokens alert: {e}")
    
    def is_daily_alert_time(self) -> bool:
        """Check if it's time for the daily alert (9:00 AM Eastern)."""
        try:
            # Get current time in Eastern timezone
            eastern = pytz.timezone('US/Eastern')
            now_eastern = datetime.now(eastern)
            
            # Check if it's 9:00 AM hour (between 9:00 and 9:59)
            if now_eastern.hour != 9:
                return False
            
            # Check if we already sent an alert today
            if self.last_daily_alert:
                last_alert_date = self.last_daily_alert.date()
                current_date = now_eastern.date()
                
                # If we already sent an alert today, don't send another
                if last_alert_date == current_date:
                    return False
            
            logger.info(f"Daily alert time reached: {now_eastern.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            return True
            
        except Exception as e:
            logger.error(f"Error checking daily alert time: {e}")
            return False
    
    def get_data_24_hours_ago(self, current_timestamp: int) -> Optional[Dict]:
        """Get data from approximately 24 hours ago."""
        try:
            # Calculate target timestamp (24 hours ago)
            target_timestamp = current_timestamp - 86400
            
            # Read CSV file and find the closest data point to 24 hours ago
            if not Path(self.csv_file).exists():
                logger.warning("CSV file does not exist for historical comparison")
                return None
            
            closest_data = None
            min_time_diff = float('inf')
            
            with open(self.csv_file, 'r', newline='') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        row_timestamp = int(row.get('layer_block_timestamp', 0))
                        time_diff = abs(row_timestamp - target_timestamp)
                        
                        # Find the closest timestamp to 24 hours ago
                        if time_diff < min_time_diff:
                            min_time_diff = time_diff
                            closest_data = row.copy()
                            
                    except (ValueError, TypeError):
                        continue
            
            if closest_data:
                # Convert string values to appropriate types
                try:
                    closest_data['layer_total_supply_trb'] = float(closest_data.get('layer_total_supply_trb', 0))
                    closest_data['bridge_balance_trb'] = float(closest_data.get('bridge_balance_trb', 0))
                    closest_data['not_bonded_tokens'] = int(closest_data.get('not_bonded_tokens', 0))
                    closest_data['bonded_tokens'] = int(closest_data.get('bonded_tokens', 0))
                    closest_data['layer_block_timestamp'] = int(closest_data.get('layer_block_timestamp', 0))
                    closest_data['layer_block_height'] = int(closest_data.get('layer_block_height', 0))
                    closest_data['free_floating_trb'] = float(closest_data.get('free_floating_trb', 0))
                    print(f"closest_data: {closest_data}")
                    
                    hours_diff = min_time_diff / 3600  # Convert seconds to hours
                    logger.info(f"Found data from {hours_diff:.1f} hours ago for 24h comparison")
                    return closest_data
                    
                except (ValueError, TypeError) as e:
                    logger.error(f"Error converting historical data types: {e}")
                    return None
            else:
                logger.warning("No historical data found for 24h comparison")
                return None
                
        except Exception as e:
            logger.error(f"Error getting 24-hour historical data: {e}")
            return None
    
    def calculate_percentage_change(self, current: float, previous: float) -> float:
        """Calculate percentage change between two values."""
        if previous == 0:
            return 0.0 if current == 0 else 100.0
        return ((current - previous) / previous) * 100
    
    def format_percentage_change(self, change: float) -> str:
        """Format percentage change with appropriate emoji and color indicators."""
        if change > 0:
            return f"📈 +{change:.2f}%"
        elif change < 0:
            return f"📉 {change:.2f}%"
        else:
            return f"➡️ {change:.2f}%"
    
    def send_daily_summary_alert(self, current_data: Dict, historical_data: Optional[Dict]):
        """Send daily summary Discord alert with 24-hour comparison."""
        try:
            # Get current time in Eastern timezone for display
            eastern = pytz.timezone('US/Eastern')
            now_eastern = datetime.now(eastern)
            
            title = f"📊 Daily Tellor Supply Report - {now_eastern.strftime('%B %d, %Y')}"
            
            # Format current data
            current_supply = current_data.get('layer_total_supply_trb', 0)
            current_bridge = current_data.get('bridge_balance_trb', 0)
            current_bonded = current_data.get('bonded_tokens', 0)
            current_not_bonded = current_data.get('not_bonded_tokens', 0)
            current_free_floating = current_data.get('free_floating_trb', 0)
            current_timestamp = current_data.get('layer_block_timestamp', 0)
            current_height = current_data.get('layer_block_height', 0)
            
            description = f"**📅 Report Time:** {now_eastern.strftime('%I:%M %p %Z')}\n\n"
            
            # Current data section
            description += "**📊 Current Data:**\n"
            description += f"• **Layer Total Supply:** {current_supply:,.2f} TRB\n"
            description += f"• **Bridge Balance:** {current_bridge:,.2f} TRB\n"
            description += f"• **Free Floating TRB:** {current_free_floating:,.2f} TRB\n"
            description += f"• **Bonded Tokens:** {current_bonded:,}\n"
            description += f"• **Not Bonded Tokens:** {current_not_bonded:,}\n"
            description += f"• **Block Height:** {current_height:,}\n"
            description += f"• **Timestamp:** <t:{current_timestamp}:F>\n\n"
            
            # 24-hour comparison section
            if historical_data:
                hist_supply = historical_data.get('layer_total_supply_trb', 0)
                hist_bridge = historical_data.get('bridge_balance_trb', 0)
                hist_bonded = historical_data.get('bonded_tokens', 0)
                hist_not_bonded = historical_data.get('not_bonded_tokens', 0)
                hist_free_floating = historical_data.get('free_floating_trb', 0)
                hist_timestamp = historical_data.get('layer_block_timestamp', 0)
                hist_height = historical_data.get('layer_block_height', 0)
                
                # Calculate percentage changes
                supply_change = self.calculate_percentage_change(current_supply, hist_supply)
                bridge_change = self.calculate_percentage_change(current_bridge, hist_bridge)
                bonded_change = self.calculate_percentage_change(current_bonded, hist_bonded)
                not_bonded_change = self.calculate_percentage_change(current_not_bonded, hist_not_bonded)
                free_floating_change = self.calculate_percentage_change(current_free_floating, hist_free_floating)
                
                # Calculate average block time
                try:
                    block_diff = (current_height - hist_height)
                    time_diff = (current_timestamp - hist_timestamp)
                    average_block_time = time_diff / block_diff
                    logger.info(f"Average block time: {average_block_time:.2f} seconds")
                except Exception as e:
                    logger.error(f"Error calculating average block time: {e}")
                    average_block_time = 0

                
                description += "**📈 24-Hour Changes:**\n"
                description += f"• **Total Supply:** {self.format_percentage_change(supply_change)}\n"
                description += f"• **Bridge Balance:** {self.format_percentage_change(bridge_change)}\n"
                description += f"• **Free Floating TRB:** {self.format_percentage_change(free_floating_change)}\n"
                description += f"• **Bonded Tokens:** {self.format_percentage_change(bonded_change)}\n"
                description += f"• **Not Bonded Tokens:** {self.format_percentage_change(not_bonded_change)}\n"
                description += f"• **Average Block Time:** {average_block_time:.2f} seconds\n\n"
                
                description += "**📋 24 Hours Ago:**\n"
                description += f"• **Block Height:** {hist_height:,}\n"
                description += f"• **Total Supply:** {hist_supply:,.2f} TRB\n"
                description += f"• **Bridge Balance:** {hist_bridge:,.2f} TRB\n"
                description += f"• **Free Floating TRB:** {hist_free_floating:,.2f} TRB\n"
                description += f"• **Bonded Tokens:** {hist_bonded:,}\n"
                description += f"• **Not Bonded Tokens:** {hist_not_bonded:,}\n"
                description += f"• **Timestamp:** <t:{hist_timestamp}:F>\n"
            else:
                description += "**⚠️ 24-Hour Comparison:** No historical data available\n"
            
            # Send the alert with blue color for daily reports
            success = self.send_discord_alert(title, description, color=0x0066CC)
            
            if success:
                # Update last daily alert time
                self.last_daily_alert = now_eastern
                logger.info("Daily summary alert sent successfully")
            else:
                logger.error("Failed to send daily summary alert")
                
        except Exception as e:
            logger.error(f"Error sending daily summary alert: {e}")
    
    def collect_historical_data(self, start_height: int, step: int = 16000):
        """
        Goal 4: Collect historical supply data going back in time.
        
        Args:
            start_height: Starting block height
            step: Step size to go back in time
        """
        logger.info(f"Starting historical data collection from height {start_height}")
        
        # Get existing timestamps to avoid collecting duplicate data
        existing_timestamps = set(self.get_existing_timestamps())
        logger.info(f"Found {len(existing_timestamps)} existing timestamps to avoid duplicating")
        
        current_height = start_height
        successful_collections = 0
        consecutive_existing_count = 0  # Track consecutive existing timestamps
        
        while True:
            logger.info(f"Processing height: {current_height}")
            
            # Get block info
            block_info = self.get_block_info(current_height)
            if not block_info:
                logger.warning(f"Failed to get block info for height {current_height}, trying next...")
                current_height -= step
                continue
            
            # Check if this timestamp is already collected (with some tolerance for time differences)
            layer_timestamp = block_info[1]
            
            # Check if we already have this exact timestamp or within a 60-second window
            timestamp_exists = False
            for existing_ts in existing_timestamps:
                if abs(layer_timestamp - existing_ts) <= 60:  # 60 second tolerance
                    timestamp_exists = True
                    break
            
            if timestamp_exists:
                consecutive_existing_count += 1
                logger.info(f"Timestamp {layer_timestamp} already exists in data (within 60s tolerance). Skipping. ({consecutive_existing_count} consecutive)")
                
                # If we've encountered 3 consecutive existing timestamps, stop collection
                if consecutive_existing_count >= 3:
                    logger.info("Encountered 3 consecutive existing timestamps. Stopping historical collection.")
                    break
                    
                current_height -= step
                continue
            else:
                # Reset counter when we find new data
                consecutive_existing_count = 0
            
            # Get total supply
            layer_supply = self.get_total_supply(current_height)
            if layer_supply is None:
                logger.warning(f"Failed to get supply for height {current_height}, trying next...")
                current_height -= step
                continue
            
            # Try to get corresponding Ethereum data (approximate by time)
            # layer_timestamp already extracted above for timestamp check
            
            # For historical data, we'll use the layer timestamp as reference
            # In a production system, you might want to find the closest Ethereum block
            eth_data = self.get_bridge_balance()  # Current for now
            if not eth_data:
                logger.warning("Failed to get Ethereum data, skipping...")
                current_height -= step
                continue
            
            eth_block, eth_timestamp, eth_datetime, bridge_balance = eth_data
            layer_supply_trb = layer_supply / (10 ** 6)
            
            # Get historical staking pool data
            staking_pool_data = self.get_staking_pool(current_height)
            if staking_pool_data:
                not_bonded_tokens, bonded_tokens = staking_pool_data
            else:
                logger.warning(f"Failed to get staking pool data for height {current_height}, using placeholder values")
                not_bonded_tokens = 0
                bonded_tokens = 0
            
            # Calculate free floating TRB
            # Staking pool values are already in TRB units
            free_floating_trb = layer_supply_trb - not_bonded_tokens - bonded_tokens
            
            data = {
                'eth_block_number': eth_block,
                'eth_block_timestamp': eth_timestamp,
                'bridge_balance_trb': bridge_balance,
                'layer_block_height': current_height,
                'layer_block_timestamp': layer_timestamp,
                'layer_total_supply_trb': layer_supply_trb,
                'not_bonded_tokens': not_bonded_tokens,
                'bonded_tokens': bonded_tokens,
                'free_floating_trb': free_floating_trb
            }
            
            self.save_to_csv(data)
            successful_collections += 1
            
            logger.info(f"Successfully collected data for height {current_height}")
            logger.info(f"Sleeping for 1 second")
            time.sleep(1)
            
            # Move to next height
            current_height -= step
            
            # Small delay to avoid overwhelming the RPC
            time.sleep(0.5)
            
            # Stop if we've been going for too long or hit very old blocks
            if current_height <= 0 or successful_collections >= 100:
                logger.info(f"Stopping historical collection after {successful_collections} successful collections")
                break
    
    def run(self, collect_historical: bool = False, monitor: bool = False, test_daily_alert: bool = False):
        """Main execution method."""
        logger.info("Starting Tellor Supply Analytics Collection")
        
        if test_daily_alert:
            logger.info("Testing daily alert functionality...")
            current_data = self.collect_current_data()
            if current_data:
                current_timestamp = current_data.get('layer_block_timestamp', 0)
                historical_data = self.get_data_24_hours_ago(current_timestamp)
                self.send_daily_summary_alert(current_data, historical_data)
                logger.info("Daily alert test completed")
            else:
                logger.error("Failed to collect current data for daily alert test")
            return
        
        if monitor:
            logger.info(f"Starting monitoring mode with {CURRENT_DATA_INTERVAL} second intervals")
            self._run_monitor()
            return
        
        # Collect current data
        previous_data = self.get_last_csv_row()
        current_data = self.collect_current_data()
        if current_data:
            # Check for alerts before saving new data
            self.check_bonded_tokens_alert(current_data, previous_data)
            
            self.save_to_csv(current_data)
            logger.info("Current data collection completed successfully")
        else:
            logger.error("Failed to collect current data")
            return
        
        # Optionally collect historical data
        if collect_historical:
            logger.info("Starting historical data collection...")
            # Start from a reasonable height and go backwards
            start_height = current_data['layer_block_height'] - 1000
            self.collect_historical_data(start_height)
    
    def _run_monitor(self):
        """Run continuous monitoring mode."""
        logger.info("Entering monitoring mode - press Ctrl+C to stop")
        
        try:
            while True:
                logger.info("Collecting current data...")
                
                # Get previous data for comparison
                previous_data = self.get_last_csv_row()
                
                current_data = self.collect_current_data()
                
                if current_data:
                    # Check for alerts before saving new data
                    self.check_bonded_tokens_alert(current_data, previous_data)
                    
                    # Check if it's time for daily alert
                    if self.is_daily_alert_time():
                        logger.info("Sending daily summary alert...")
                        current_timestamp = current_data.get('layer_block_timestamp', 0)
                        historical_data = self.get_data_24_hours_ago(current_timestamp)
                        self.send_daily_summary_alert(current_data, historical_data)
                    
                    self.save_to_csv(current_data)
                    logger.info("Current data collection completed successfully")
                    logger.info(f"Next collection in {CURRENT_DATA_INTERVAL} seconds")
                else:
                    logger.error("Failed to collect current data")
                    logger.info(f"Retrying in {CURRENT_DATA_INTERVAL} seconds")
                
                # Sleep for the configured interval
                time.sleep(CURRENT_DATA_INTERVAL)
                
        except KeyboardInterrupt:
            logger.info("Monitoring stopped by user")
        except Exception as e:
            logger.error(f"Error in monitoring mode: {e}")
            raise


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Tellor Supply Analytics Collector')
    parser.add_argument(
        '--historical',
        action='store_true',
        help='Collect historical data in addition to current data'
    )
    parser.add_argument(
        '--monitor',
        action='store_true',
        help='Run in monitoring mode - continuously collect current data at set intervals'
    )
    parser.add_argument(
        '--test-daily-alert',
        action='store_true',
        help='Test the daily alert functionality by sending it immediately'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug logging'
    )
    
    args = parser.parse_args()
    
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    
    collector = SupplyDataCollector()
    collector.run(
        collect_historical=args.historical, 
        monitor=args.monitor,
        test_daily_alert=args.test_daily_alert
    )


if __name__ == '__main__':
    main() 