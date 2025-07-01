#!/usr/bin/env python3
"""
Tellor Layer Active Balances Collector

This script collects all active addresses from Tellor Layer and their corresponding
balances, storing the data in a CSV file.

Author: Blockchain Backend Engineering Team
"""

import os
import csv
import json
import requests
import time
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from pathlib import Path

# Import configuration from supply_collector if needed
try:
    from .supply_collector import LAYER_GRPC_URL, logger
except ImportError:
    # Fallback configuration if import fails
    LAYER_GRPC_URL = os.getenv('LAYER_GRPC_URL', 'http://node-palmito.tellorlayer.com')
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger(__name__)

# Configuration
CSV_FILE = 'active_addresses.csv'
CSV_HEADERS = ['address', 'account_type', 'loya_balance', 'loya_balance_trb', 'last_updated']
REQUEST_TIMEOUT = 30
REQUEST_DELAY = 0.1  # Delay between requests to avoid overwhelming the API


class ActiveBalancesCollector:
    """Collects active addresses and their balances from Tellor Layer."""
    
    def __init__(self):
        """Initialize the active balances collector."""
        self.csv_file = CSV_FILE
        self.base_url = LAYER_GRPC_URL.rstrip('/')
        self.accounts_endpoint = f"{self.base_url}:1317/cosmos/auth/v1beta1/accounts"
        self.balance_endpoint_template = f"{self.base_url}:1317/cosmos/bank/v1beta1/balances/{{}}"
        self.session = requests.Session()
        
        # Set up session headers
        self.session.headers.update({
            'Accept': 'application/json',
            'User-Agent': 'Tellor-Supply-Analytics/1.0'
        })
        
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
    
    def get_address_balance(self, address: str) -> Tuple[int, float]:
        """
        Get the loya balance for a specific address.
        
        Args:
            address: The address to query
            
        Returns:
            Tuple of (loya_balance, loya_balance_trb)
        """
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
    
    def save_addresses_with_balances(self, addresses: List[Tuple[str, str]]):
        """
        Save addresses with their balances to CSV file.
        
        Args:
            addresses: List of tuples (address, account_type)
        """
        logger.info(f"Fetching balances for {len(addresses)} addresses...")
        
        timestamp = datetime.now(timezone.utc).isoformat()
        
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
        
        # Process addresses
        new_addresses = 0
        updated_addresses = 0
        
        with open(self.csv_file, 'a', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
            
            for i, (address, account_type) in enumerate(addresses, 1):
                if i % 10 == 0:
                    logger.info(f"Processed {i}/{len(addresses)} addresses...")
                
                # Get balance for this address
                loya_balance, loya_balance_trb = self.get_address_balance(address)
                
                # Prepare row data
                row_data = {
                    'address': address,
                    'account_type': account_type,
                    'loya_balance': loya_balance,
                    'loya_balance_trb': loya_balance_trb,
                    'last_updated': timestamp
                }
                
                if address not in existing_addresses:
                    writer.writerow(row_data)
                    new_addresses += 1
                else:
                    updated_addresses += 1
                
                # Small delay between balance requests
                time.sleep(REQUEST_DELAY)
        
        logger.info(f"Saved {new_addresses} new addresses, skipped {updated_addresses} existing addresses")
    
    def update_existing_balances(self):
        """Update balances for all existing addresses in the CSV file."""
        if not Path(self.csv_file).exists():
            logger.error("CSV file does not exist. Run collect_addresses first.")
            return
        
        logger.info("Updating balances for existing addresses...")
        
        # Read existing data
        existing_data = []
        with open(self.csv_file, 'r', newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                existing_data.append(row)
        
        if not existing_data:
            logger.warning("No existing data found in CSV file")
            return
        
        timestamp = datetime.now(timezone.utc).isoformat()
        
        # Update balances
        logger.info(f"Updating balances for {len(existing_data)} addresses...")
        
        for i, row in enumerate(existing_data, 1):
            if i % 10 == 0:
                logger.info(f"Updated {i}/{len(existing_data)} addresses...")
            
            address = row.get('address', '')
            if address:
                loya_balance, loya_balance_trb = self.get_address_balance(address)
                row['loya_balance'] = loya_balance
                row['loya_balance_trb'] = loya_balance_trb
                row['last_updated'] = timestamp
                
                # Small delay between requests
                time.sleep(REQUEST_DELAY)
        
        # Write updated data back to CSV
        with open(self.csv_file, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
            writer.writeheader()
            writer.writerows(existing_data)
        
        logger.info("Finished updating all balances")
    
    def get_balance_summary(self) -> Dict:
        """Get a summary of balances from the CSV file."""
        if not Path(self.csv_file).exists():
            logger.error("CSV file does not exist")
            return {}
        
        total_addresses = 0
        total_loya_balance = 0
        total_trb_balance = 0.0
        account_type_counts = {}
        non_zero_balances = 0
        
        with open(self.csv_file, 'r', newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                total_addresses += 1
                
                # Parse balance
                try:
                    loya_balance = int(row.get('loya_balance', 0))
                    trb_balance = float(row.get('loya_balance_trb', 0.0))
                    
                    total_loya_balance += loya_balance
                    total_trb_balance += trb_balance
                    
                    if loya_balance > 0:
                        non_zero_balances += 1
                        
                except (ValueError, TypeError):
                    continue
                
                # Count account types
                account_type = row.get('account_type', 'unknown')
                account_type_counts[account_type] = account_type_counts.get(account_type, 0) + 1
        
        summary = {
            'total_addresses': total_addresses,
            'addresses_with_balance': non_zero_balances,
            'total_loya_balance': total_loya_balance,
            'total_trb_balance': total_trb_balance,
            'account_type_breakdown': account_type_counts
        }
        
        return summary
    
    def run(self, update_only: bool = False):
        """
        Main execution method.
        
        Args:
            update_only: If True, only update existing balances without fetching new addresses
        """
        logger.info("Starting Active Balances Collection")
        
        if update_only:
            self.update_existing_balances()
        else:
            # Get all accounts
            accounts = self.get_all_accounts()
            if not accounts:
                logger.error("Failed to retrieve accounts")
                return
            
            # Extract addresses
            addresses = self.extract_addresses(accounts)
            if not addresses:
                logger.error("No addresses found")
                return
            
            # Save addresses with balances
            self.save_addresses_with_balances(addresses)
        
        # Print summary
        summary = self.get_balance_summary()
        if summary:
            logger.info("=== BALANCE SUMMARY ===")
            logger.info(f"Total addresses: {summary['total_addresses']}")
            logger.info(f"Addresses with balance: {summary['addresses_with_balance']}")
            logger.info(f"Total balance: {summary['total_loya_balance']:,} loya ({summary['total_trb_balance']:,.6f} TRB)")
            logger.info("Account type breakdown:")
            for account_type, count in summary['account_type_breakdown'].items():
                logger.info(f"  {account_type}: {count}")
        
        logger.info(f"Results saved to: {self.csv_file}")


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Tellor Layer Active Balances Collector')
    parser.add_argument(
        '--update-only',
        action='store_true',
        help='Update balances for existing addresses only (skip fetching new addresses)'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug logging'
    )
    
    args = parser.parse_args()
    
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    
    collector = ActiveBalancesCollector()
    collector.run(update_only=args.update_only)


if __name__ == '__main__':
    main()


