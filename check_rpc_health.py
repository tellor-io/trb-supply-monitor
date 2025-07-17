#!/usr/bin/env python3
"""
Standalone RPC Health Check Script for Tellor Supply Monitor

This script checks the health of all required RPC endpoints and provides
detailed diagnostic information. Run this script to verify your RPC
configuration before starting the main application.

Usage:
    python check_rpc_health.py
    python check_rpc_health.py --verbose
"""

import os
import sys
import argparse
import logging
import requests
import subprocess
import json
from pathlib import Path
from web3 import Web3

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Configuration from environment
TELLOR_LAYER_RPC_URL = os.getenv('TELLOR_LAYER_RPC_URL')
LAYER_GRPC_URL = os.getenv('LAYER_GRPC_URL')
ETHEREUM_RPC_URL = os.getenv('ETHEREUM_RPC_URL')

def setup_logging(verbose: bool = False):
    """Set up logging configuration."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    return logging.getLogger(__name__)

def check_tellor_layer_rpc(logger) -> tuple:
    """
    Check if Tellor Layer RPC is responding.
    
    Returns:
        (success: bool, info: dict)
    """
    logger.info(f"🔍 Checking Tellor Layer RPC: {TELLOR_LAYER_RPC_URL}")
    
    info = {
        'url': TELLOR_LAYER_RPC_URL,
        'layerd_available': False,
        'direct_rpc_available': False,
        'latest_height': None,
        'earliest_height': None,
        'error': None
    }
    
    try:
        # Try using layerd status command if available
        layerd_path = './layerd'
        if Path(layerd_path).exists():
            logger.debug("Found layerd binary, testing command...")
            try:
                result = subprocess.run(
                    [layerd_path, 'status', '--output', 'json', '--node', TELLOR_LAYER_RPC_URL],
                    capture_output=True,
                    text=True,
                    timeout=15
                )
                
                if result.returncode == 0:
                    status_data = json.loads(result.stdout)
                    sync_info = status_data.get('sync_info', {})
                    info['latest_height'] = sync_info.get('latest_block_height')
                    info['earliest_height'] = sync_info.get('earliest_block_height')
                    info['layerd_available'] = True
                    logger.info(f"✅ layerd command successful - Latest: {info['latest_height']}, Earliest: {info['earliest_height']}")
                    return True, info
                else:
                    logger.warning(f"⚠️  layerd command failed: {result.stderr}")
                    info['error'] = f"layerd failed: {result.stderr}"
            except Exception as e:
                logger.warning(f"⚠️  layerd command error: {e}")
                info['error'] = f"layerd error: {e}"
        else:
            logger.debug("layerd binary not found, trying direct RPC...")
        
        # Fallback: Try direct RPC call
        logger.debug("Testing direct RPC call...")
        response = requests.post(
            TELLOR_LAYER_RPC_URL,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "status",
                "params": []
            },
            timeout=15
        )
        
        if response.status_code == 200:
            data = response.json()
            if 'result' in data:
                sync_info = data['result'].get('sync_info', {})
                info['latest_height'] = sync_info.get('latest_block_height')
                info['earliest_height'] = sync_info.get('earliest_block_height')
                info['direct_rpc_available'] = True
                logger.info(f"✅ Direct RPC successful - Latest: {info['latest_height']}, Earliest: {info['earliest_height']}")
                return True, info
        
        error_msg = f"RPC not responding properly. Status: {response.status_code}"
        logger.error(f"❌ {error_msg}")
        info['error'] = error_msg
        return False, info
        
    except requests.RequestException as e:
        error_msg = f"Connection failed: {e}"
        logger.error(f"❌ {error_msg}")
        info['error'] = error_msg
        return False, info
    except Exception as e:
        error_msg = f"Unexpected error: {e}"
        logger.error(f"❌ {error_msg}")
        info['error'] = error_msg
        return False, info

def check_ethereum_rpc(logger) -> tuple:
    """
    Check if Ethereum RPC is responding.
    
    Returns:
        (success: bool, info: dict)
    """
    logger.info(f"🔍 Checking Ethereum RPC: {ETHEREUM_RPC_URL}")
    
    info = {
        'url': ETHEREUM_RPC_URL,
        'connected': False,
        'latest_block': None,
        'chain_id': None,
        'client_version': None,
        'error': None
    }
    
    try:
        w3 = Web3(Web3.HTTPProvider(ETHEREUM_RPC_URL))
        
        if not w3.is_connected():
            error_msg = "Connection failed"
            logger.error(f"❌ {error_msg}")
            info['error'] = error_msg
            return False, info
        
        info['connected'] = True
        
        # Get additional info
        try:
            info['chain_id'] = w3.eth.chain_id
            info['client_version'] = w3.client_version
        except Exception as e:
            logger.debug(f"Could not get chain info: {e}")
        
        # Try to get the latest block
        latest_block = w3.eth.get_block('latest')
        info['latest_block'] = latest_block.get('number')
        
        if info['latest_block']:
            logger.info(f"✅ Ethereum RPC responding - Block: {info['latest_block']}, Chain ID: {info['chain_id']}")
            return True, info
        else:
            error_msg = "Could not get block number"
            logger.error(f"❌ {error_msg}")
            info['error'] = error_msg
            return False, info
            
    except Exception as e:
        error_msg = f"Connection error: {e}"
        logger.error(f"❌ {error_msg}")
        info['error'] = error_msg
        return False, info

def check_tellor_layer_grpc(logger) -> tuple:
    """
    Check if Tellor Layer GRPC endpoint is responding.
    
    Returns:
        (success: bool, info: dict)
    """
    logger.info(f"🔍 Checking Tellor Layer GRPC: {LAYER_GRPC_URL}")
    
    info = {
        'url': LAYER_GRPC_URL,
        'node_info_available': False,
        'accounts_available': False,
        'network': None,
        'version': None,
        'error': None
    }
    
    try:
        # Test node info endpoint
        logger.debug("Testing node info endpoint...")
        response = requests.get(
            f"{LAYER_GRPC_URL.rstrip('/')}/cosmos/base/tendermint/v1beta1/node_info",
            timeout=15
        )
        
        if response.status_code == 200:
            data = response.json()
            node_info = data.get('default_node_info', {})
            if node_info:
                info['network'] = node_info.get('network', 'unknown')
                info['version'] = node_info.get('version', 'unknown')
                info['node_info_available'] = True
                logger.debug(f"Node info available - Network: {info['network']}, Version: {info['version']}")
        
        # Test accounts endpoint
        logger.debug("Testing accounts endpoint...")
        response = requests.get(
            f"{LAYER_GRPC_URL.rstrip('/')}/cosmos/auth/v1beta1/accounts?pagination.limit=1",
            timeout=15
        )
        
        if response.status_code == 200:
            data = response.json()
            accounts = data.get('accounts', [])
            if accounts:
                info['accounts_available'] = True
                logger.debug("Accounts endpoint responding")
        
        if info['node_info_available'] or info['accounts_available']:
            logger.info(f"✅ Tellor Layer GRPC responding - Network: {info['network']}, Version: {info['version']}")
            return True, info
        else:
            error_msg = "No endpoints responding properly"
            logger.error(f"❌ {error_msg}")
            info['error'] = error_msg
            return False, info
        
    except requests.RequestException as e:
        error_msg = f"Connection failed: {e}"
        logger.error(f"❌ {error_msg}")
        info['error'] = error_msg
        return False, info
    except Exception as e:
        error_msg = f"Unexpected error: {e}"
        logger.error(f"❌ {error_msg}")
        info['error'] = error_msg
        return False, info

def print_summary(results):
    """Print a summary of all health check results."""
    print("\n" + "="*60)
    print("RPC HEALTH CHECK SUMMARY")
    print("="*60)
    
    total_checks = len(results)
    passed_checks = sum(1 for success, _ in results.values() if success)
    
    for name, (success, info) in results.items():
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{name:20} | {status} | {info['url']}")
        
        if not success and info.get('error'):
            print(f"{'':20} | Error: {info['error']}")
    
    print("="*60)
    print(f"TOTAL: {passed_checks}/{total_checks} checks passed")
    
    if passed_checks == total_checks:
        print("🎉 All RPC endpoints are healthy!")
        return True
    elif passed_checks >= 2:  # At least the critical ones
        print("⚠️  Some non-critical endpoints have issues, but system should work")
        return True
    else:
        print("❌ Critical RPC endpoints are failing. System will not work properly.")
        return False

def main():
    parser = argparse.ArgumentParser(description='Check RPC health for Tellor Supply Monitor')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose logging')
    args = parser.parse_args()
    
    logger = setup_logging(args.verbose)
    
    print("🔧 Starting RPC Health Checks...")
    print(f"Environment:")
    print(f"  TELLOR_LAYER_RPC_URL: {TELLOR_LAYER_RPC_URL}")
    print(f"  LAYER_GRPC_URL: {LAYER_GRPC_URL}")
    print(f"  ETHEREUM_RPC_URL: {ETHEREUM_RPC_URL}")
    print()
    
    results = {}
    
    # Check all RPCs
    results['Tellor Layer RPC'] = check_tellor_layer_rpc(logger)
    results['Ethereum RPC'] = check_ethereum_rpc(logger)
    results['Tellor Layer GRPC'] = check_tellor_layer_grpc(logger)
    
    # Print summary
    success = print_summary(results)
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)

if __name__ == '__main__':
    main() 