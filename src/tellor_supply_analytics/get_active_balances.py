#!/usr/bin/env python3
"""
Enhanced Tellor Layer Active Balances Collector with SQLite Storage

This script collects all active addresses from Tellor Layer and their corresponding
balances, storing the data in both CSV and SQLite database for historical tracking.

Author: Blockchain Backend Engineering Team
"""

import os
import csv
import json
import requests
import time
import logging
import subprocess
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from pathlib import Path

# Web3 imports for bridge balance
from web3 import Web3
try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv() -> bool:
        return True

# Local imports
from .database import BalancesDatabase

# Load environment variables
load_dotenv()

# Import configuration from supply_collector if needed
try:
    from .supply_collector import LAYER_GRPC_URL, logger, TELLOR_LAYER_RPC_URL
except ImportError:
    # Fallback configuration if import fails
    LAYER_GRPC_URL = os.getenv('LAYER_GRPC_URL')
    TELLOR_LAYER_RPC_URL = os.getenv('TELLOR_LAYER_RPC_URL')
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger(__name__)

# Ensure LAYER_GRPC_URL is not None and properly configured
if not LAYER_GRPC_URL:
    LAYER_GRPC_URL = os.getenv('LAYER_GRPC_URL')
    logger.warning(f"LAYER_GRPC_URL was None, using fallback: {LAYER_GRPC_URL}")

if not TELLOR_LAYER_RPC_URL:
    TELLOR_LAYER_RPC_URL = os.getenv('TELLOR_LAYER_RPC_URL')
    logger.warning(f"TELLOR_LAYER_RPC_URL was None, using fallback: {TELLOR_LAYER_RPC_URL}")

# Validate URLs
if not LAYER_GRPC_URL.startswith(('http://', 'https://')):
    raise ValueError(f"Invalid LAYER_GRPC_URL: {LAYER_GRPC_URL}")
if not TELLOR_LAYER_RPC_URL.startswith(('http://', 'https://')):
    raise ValueError(f"Invalid TELLOR_LAYER_RPC_URL: {TELLOR_LAYER_RPC_URL}")

logger.info(f"Using Tellor Layer GRPC URL: {LAYER_GRPC_URL}")
logger.info(f"Using Tellor Layer RPC URL: {TELLOR_LAYER_RPC_URL}")

# Configuration
CSV_FILE = 'active_addresses.csv'
CSV_HEADERS = ['address', 'account_type', 'loya_balance', 'loya_balance_trb', 'last_updated']
REQUEST_TIMEOUT = 30
REQUEST_DELAY = 0.1  # Delay between requests to avoid overwhelming the API

# Ethereum/Bridge Configuration
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


class EnhancedActiveBalancesCollector:
    """Enhanced collector with SQLite database storage for historical tracking."""
    
    def __init__(self, db_path: str = 'tellor_balances.db', use_csv: bool = True):
        """
        Initialize the enhanced active balances collector.
        
        Args:
            db_path: Path to SQLite database file
            use_csv: Whether to also maintain CSV file for backward compatibility
        """
        self.csv_file = CSV_FILE
        self.use_csv = use_csv
        self.base_url = LAYER_GRPC_URL.rstrip('/')
        self.accounts_endpoint = f"{self.base_url}/cosmos/auth/v1beta1/accounts"
        self.balance_endpoint_template = f"{self.base_url}/cosmos/bank/v1beta1/balances/{{}}"
        self.session = requests.Session()
        self.layerd_path = './layerd'
        
        # Initialize database
        self.db = BalancesDatabase(db_path)
        
        # Set up session headers
        self.session.headers.update({
            'Accept': 'application/json',
            'User-Agent': 'Tellor-Supply-Analytics/1.0'
        })
        
        # Initialize Web3 connection for bridge balance
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
        
        if self.use_csv:
            self.initialize_csv()
    
    def initialize_csv(self):
        """Initialize CSV file with headers if it doesn't exist."""
        if not Path(self.csv_file).exists():
            with open(self.csv_file, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(CSV_HEADERS)
            logger.info(f"Created CSV file: {self.csv_file}")
        else:
            logger.info(f"CSV file already exists: {self.csv_file}")
    
    def get_all_accounts(self) -> List[Dict]:
        """
        Get all accounts from Tellor Layer using pagination if necessary.
        
        Returns:
            List of account dictionaries
        """
        logger.info("Fetching all accounts from Tellor Layer...")
        
        all_accounts = []
        next_key = None
        page_count = 0
        
        while True:
            page_count += 1
            logger.info(f"Fetching accounts page {page_count}...")
            
            try:
                # Prepare request parameters
                params = {}
                if next_key:
                    params['pagination.key'] = next_key
                
                # Make the request
                response = self.session.get(
                    self.accounts_endpoint,
                    params=params,
                    timeout=REQUEST_TIMEOUT
                )
                response.raise_for_status()
                
                data = response.json()
                
                # Extract accounts from response
                accounts = data.get('accounts', [])
                all_accounts.extend(accounts)
                
                logger.info(f"Retrieved {len(accounts)} accounts on page {page_count}")
                
                # Check if there are more pages
                pagination = data.get('pagination', {})
                next_key = pagination.get('next_key')
                
                if not next_key:
                    break
                
                # Small delay between requests
                time.sleep(REQUEST_DELAY)
                
            except requests.RequestException as e:
                logger.error(f"Error fetching accounts page {page_count}: {e}")
                break
            except json.JSONDecodeError as e:
                logger.error(f"Error parsing JSON response on page {page_count}: {e}")
                break
        
        logger.info(f"Total accounts retrieved: {len(all_accounts)} across {page_count} pages")
        return all_accounts
    
    def extract_addresses(self, accounts: List[Dict]) -> List[Tuple[str, str]]:
        """
        Extract unique addresses from accounts data.
        
        Args:
            accounts: List of account dictionaries
            
        Returns:
            List of tuples (address, account_type)
        """
        logger.info("Extracting addresses from accounts...")
        
        addresses = []
        seen_addresses = set()
        
        for account in accounts:
            try:
                # Handle different account types
                account_type = account.get('@type', 'unknown')
                
                if account_type == '/cosmos.auth.v1beta1.BaseAccount':
                    address = account.get('address')
                    type_name = 'BaseAccount'
                elif account_type == '/cosmos.auth.v1beta1.ModuleAccount':
                    # Module accounts have address in base_account
                    base_account = account.get('base_account', {})
                    address = base_account.get('address')
                    module_name = account.get('name', 'unknown')
                    type_name = f'ModuleAccount({module_name})'
                else:
                    # Handle other account types
                    address = account.get('address')
                    if not address and 'base_account' in account:
                        address = account['base_account'].get('address')
                    type_name = account_type.split('.')[-1] if '.' in account_type else account_type
                
                if address and address not in seen_addresses:
                    addresses.append((address, type_name))
                    seen_addresses.add(address)
                    
            except Exception as e:
                logger.warning(f"Error processing account: {e}")
                logger.debug(f"Account data: {account}")
                continue
        
        logger.info(f"Extracted {len(addresses)} unique addresses")
        return addresses
    
    def get_all_addresses(self) -> List[Tuple[str, str]]:
        """
        Get all addresses from Tellor Layer.
        
        This is a convenience method that combines get_all_accounts() and extract_addresses().
        
        Returns:
            List of tuples (address, account_type)
        """
        accounts = self.get_all_accounts()
        if not accounts:
            return []
        
        return self.extract_addresses(accounts)
    
    def collect_balances_at_height(self, addresses: List[Tuple[str, str]], height: int) -> List[Tuple[str, str, int, float]]:
        """
        Collect balances for all addresses at a specific block height.
        
        Args:
            addresses: List of tuples (address, account_type)
            height: Block height to query at
            
        Returns:
            List of tuples (address, account_type, loya_balance, loya_balance_trb)
        """
        logger.info(f"Collecting balances for {len(addresses)} addresses at height {height}")
        
        addresses_with_balances = []
        
        for i, (address, account_type) in enumerate(addresses, 1):
            if i % 10 == 0:
                logger.info(f"Processed {i}/{len(addresses)} addresses at height {height}...")
            
            # Get historical balance for this address at the specified height
            loya_balance, loya_balance_trb = self.get_address_balance_at_height(address, height)
            addresses_with_balances.append((address, account_type, loya_balance, loya_balance_trb))
            
            # Small delay between balance requests to avoid overwhelming the RPC
            time.sleep(REQUEST_DELAY)
        
        logger.info(f"Collected historical balances for {len(addresses_with_balances)} addresses at height {height}")
        return addresses_with_balances
    
    def get_address_balance(self, address: str, height: Optional[int] = None) -> Tuple[int, float]:
        """
        Get the loya balance for a specific address at a specific height.
        
        Args:
            address: The address to query
            height: Block height to query (None for current)
            
        Returns:
            Tuple of (loya_balance, loya_balance_trb)
        """
        # For historical queries, use layerd CLI
        if height is not None:
            return self.get_address_balance_at_height(address, height)
        
        # For current queries, use REST API (faster)
        try:
            url = self.balance_endpoint_template.format(address)
            
            response = self.session.get(url, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            
            data = response.json()
            balances = data.get('balances', [])
            
            # Find loya balance
            loya_balance = 0
            for balance in balances:
                if balance.get('denom') == 'loya':
                    loya_balance = int(balance.get('amount', 0))
                    break
            
            # Convert loya to TRB (assuming 6 decimal places)
            loya_balance_trb = loya_balance / (10 ** 6)
            
            return loya_balance, loya_balance_trb
            
        except requests.RequestException as e:
            logger.warning(f"Error fetching balance for {address}: {e}")
            return 0, 0.0
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Error parsing balance response for {address}: {e}")
            return 0, 0.0
    
    def get_address_balance_at_height(self, address: str, height: int) -> Tuple[int, float]:
        """
        Get the loya balance for a specific address at a specific block height.
        
        Args:
            address: The address to query
            height: Block height to query
            
        Returns:
            Tuple of (loya_balance, loya_balance_trb)
        """
        try:
            cmd_args = [
                'query', 'bank', 'balances', address,
                '--height', str(height),
                '--output', 'json',
                '--node', TELLOR_LAYER_RPC_URL
            ]
            
            result = self.run_layerd_command(cmd_args)
            if not result:
                logger.debug(f"No balance data for {address} at height {height} (address likely didn't exist yet)")
                return 0, 0.0
            
            balances = result.get('balances', [])
            
            # Find loya balance
            loya_balance = 0
            for balance in balances:
                if balance.get('denom') == 'loya':
                    loya_balance = int(balance.get('amount', 0))
                    break
            
            # Convert loya to TRB (assuming 6 decimal places)
            loya_balance_trb = loya_balance / (10 ** 6)
            
            return loya_balance, loya_balance_trb
            
        except Exception as e:
            logger.debug(f"Error fetching balance for {address} at height {height}: {e}")
            return 0, 0.0
    
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
                    # This is expected when querying addresses that didn't exist at historical heights
                    logger.debug(f"RPC InvalidArgument error (address likely didn't exist at this height): {error_msg}")
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
        """Get the current block height from Tellor Layer using layerd status."""
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
            return None
    
    def get_bridge_balance(self) -> Optional[float]:
        """Get TRB balance in bridge contract."""
        if not self.w3 or not self.trb_contract:
            logger.warning("Web3 or TRB contract not initialized, returning 0 for bridge balance")
            return 0.0
            
        try:
            # Get bridge balance
            balance = self.trb_contract.functions.balanceOf(
                Web3.to_checksum_address(SEPOLIA_BRIDGE_CONTRACT)
            ).call()
            
            # Convert from wei to TRB (18 decimals)
            balance_trb = balance / (10 ** 18)
            
            logger.info(f"Bridge balance: {balance_trb:.6f} TRB")
            return balance_trb
            
        except Exception as e:
            logger.error(f"Error getting bridge balance: {e}")
            return 0.0
    
    def calculate_free_floating_trb(self, addresses_with_balances: List[Tuple[str, str, int, float]]) -> float:
        """
        Calculate free floating TRB from active addresses data.
        Free floating TRB = Total supply - Total ModuleAccount balances
        
        Args:
            addresses_with_balances: List of tuples (address, account_type, loya_balance, loya_balance_trb)
            
        Returns:
            Free floating TRB amount
        """
        # Calculate total TRB supply from all addresses
        total_supply_trb = sum(trb for _, _, _, trb in addresses_with_balances)
        
        # Calculate total ModuleAccount balances
        module_account_balances_trb = sum(
            trb for _, account_type, _, trb in addresses_with_balances 
            if account_type.startswith('ModuleAccount')
        )
        
        # Free floating = Total supply - ModuleAccount balances
        free_floating_trb = total_supply_trb - module_account_balances_trb
        
        logger.info(f"Free floating TRB calculation:")
        logger.info(f"  Total supply: {total_supply_trb:.6f} TRB")
        logger.info(f"  ModuleAccount balances: {module_account_balances_trb:.6f} TRB")
        logger.info(f"  Free floating: {free_floating_trb:.6f} TRB")
        
        return free_floating_trb
    
    def collect_and_save_balances(self, addresses: List[Tuple[str, str]]):
        """
        Collect balances for all addresses and save to both CSV and database.
        
        Args:
            addresses: List of tuples (address, account_type)
        """
        logger.info(f"Fetching balances for {len(addresses)} addresses...")
        
        timestamp = datetime.now(timezone.utc).isoformat()
        addresses_with_balances = []
        
        # Collect all balances
        for i, (address, account_type) in enumerate(addresses, 1):
            if i % 10 == 0:
                logger.info(f"Processed {i}/{len(addresses)} addresses...")
            
            # Get balance for this address
            loya_balance, loya_balance_trb = self.get_address_balance(address)
            
            addresses_with_balances.append((address, account_type, loya_balance, loya_balance_trb))
            
            # Small delay between balance requests
            time.sleep(REQUEST_DELAY)
        
        # Collect additional data
        logger.info("Collecting additional blockchain data...")
        
        # Get current block height
        current_height = self.get_current_height()
        if current_height is None:
            logger.warning("Failed to get current block height, using 0")
            current_height = 0
        
        # Get bridge balance
        bridge_balance = self.get_bridge_balance()
        if bridge_balance is None:
            bridge_balance = 0.0
        
        # Calculate free floating TRB
        free_floating_trb = self.calculate_free_floating_trb(addresses_with_balances)
        
        # Save to database with additional data
        self.db.save_snapshot(
            addresses_with_balances, 
            bridge_balance_trb=bridge_balance,
            layer_block_height=current_height,
            free_floating_trb=free_floating_trb
        )
        logger.info(f"Saved {len(addresses_with_balances)} addresses to database with additional data")
        
        # Save to CSV if enabled
        if self.use_csv:
            self.save_to_csv(addresses_with_balances, timestamp)
    
    def save_to_csv(self, addresses_with_balances: List[Tuple[str, str, int, float]], timestamp: str):
        """Save data to CSV file for backward compatibility."""
        # Read existing addresses to avoid duplicates
        existing_addresses = set()
        if Path(self.csv_file).exists():
            try:
                with open(self.csv_file, 'r', newline='') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        existing_addresses.add(row.get('address', ''))
            except Exception as e:
                logger.warning(f"Error reading existing CSV file: {e}")
        
        # Write new data
        new_addresses = 0
        with open(self.csv_file, 'a', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
            
            for address, account_type, loya_balance, loya_balance_trb in addresses_with_balances:
                if address not in existing_addresses:
                    writer.writerow({
                        'address': address,
                        'account_type': account_type,
                        'loya_balance': loya_balance,
                        'loya_balance_trb': loya_balance_trb,
                        'last_updated': timestamp
                    })
                    new_addresses += 1
        
        logger.info(f"Saved {new_addresses} new addresses to CSV")
    
    def get_latest_summary(self) -> Dict:
        """Get summary of the latest collection from database."""
        return self.db.get_latest_snapshot()
    
    def get_history(self, limit: int = 100) -> List[Dict]:
        """Get collection history from database."""
        return self.db.get_snapshots_history(limit)
    
    def run(self):
        """Main execution method - collect all balances and store them."""
        logger.info("Starting Enhanced Active Balances Collection")
        
        try:
            # Get all accounts
            accounts = self.get_all_accounts()
            if not accounts:
                logger.error("Failed to retrieve accounts")
                return False
            
            # Extract addresses
            addresses = self.extract_addresses(accounts)
            if not addresses:
                logger.error("No addresses found")
                return False
            
            # Collect and save balances
            self.collect_and_save_balances(addresses)
            
            # Print summary
            summary = self.get_latest_summary()
            if summary:
                logger.info("=== COLLECTION SUMMARY ===")
                logger.info(f"Collection time: {summary.get('run_time')}")
                logger.info(f"Block height: {summary.get('layer_block_height', 0):,}")
                logger.info(f"Total addresses: {summary.get('total_addresses')}")
                logger.info(f"Addresses with balance: {summary.get('addresses_with_balance')}")
                logger.info(f"Total balance: {summary.get('total_loya_balance'):,} loya ({summary.get('total_trb_balance'):,.6f} TRB)")
                logger.info(f"Bridge balance: {summary.get('bridge_balance_trb', 0):,.6f} TRB")
                logger.info(f"Free floating TRB: {summary.get('free_floating_trb', 0):,.6f} TRB")
            
            return True
            
        except Exception as e:
            logger.error(f"Collection failed: {e}")
            return False


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Enhanced Tellor Layer Active Balances Collector')
    parser.add_argument(
        '--db-path',
        default='tellor_balances.db',
        help='Path to SQLite database file'
    )
    parser.add_argument(
        '--no-csv',
        action='store_true',
        help='Disable CSV output (database only)'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug logging'
    )
    
    args = parser.parse_args()
    
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    
    collector = EnhancedActiveBalancesCollector(
        db_path=args.db_path,
        use_csv=not args.no_csv
    )
    
    success = collector.run()
    exit(0 if success else 1)


if __name__ == '__main__':
    main()
