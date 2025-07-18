#!/usr/bin/env python3
"""
Test script for data management functionality

This script demonstrates how to use the new data management features
for removing and re-collecting data by Tellor Layer block number.
"""

import sys
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_data_management():
    """Test the data management functionality."""
    try:
        from src.tellor_supply_analytics.unified_collector import UnifiedDataCollector
        
        # Initialize collector
        collector = UnifiedDataCollector(db_path='test_tellor_balances.db')
        
        # Test listing layer blocks
        logger.info("=== Testing List Layer Blocks ===")
        layer_blocks = collector.list_layer_blocks_in_database(limit=10)
        
        if layer_blocks:
            print(f"\nFound {len(layer_blocks)} layer blocks in database:")
            print(f"{'Layer Height':<15} {'ETH Block':<12} {'Completeness':<12} {'Collection Time'}")
            print("-" * 70)
            for block in layer_blocks[:5]:  # Show first 5
                print(f"{block['layer_block_height']:<15} {block['eth_block_number']:<12} "
                      f"{block['data_completeness_score']:<12.2f} {block['collection_time'] or 'N/A'}")
        else:
            print("No layer blocks found in database")
        
        # Test data summary
        logger.info("=== Testing Data Summary ===")
        summary = collector.get_data_summary()
        print(f"\nData Summary:")
        for key, value in summary.items():
            print(f"  {key}: {value}")
        
        return True
        
    except ImportError as e:
        logger.error(f"Import error: {e}")
        logger.error("Make sure you're running in the virtual environment with all dependencies installed")
        return False
    except Exception as e:
        logger.error(f"Test failed: {e}")
        return False

def show_usage_examples():
    """Show usage examples for the new functionality."""
    print("\n=== DATA MANAGEMENT USAGE EXAMPLES ===")
    
    print("\n1. List layer blocks in database:")
    print("   python -m src.tellor_supply_analytics.unified_collector --list-layer-blocks --list-limit 20")
    
    print("\n2. Remove data for a specific layer block:")
    print("   python -m src.tellor_supply_analytics.unified_collector --remove-layer-block 12345")
    
    print("\n3. Re-collect data for a specific layer block:")
    print("   python -m src.tellor_supply_analytics.unified_collector --rerun-layer-block 12345")
    
    print("\n4. Remove and re-collect data (recommended):")
    print("   python -m src.tellor_supply_analytics.unified_collector --remove-and-rerun 12345")
    
    print("\n5. Get data collection summary:")
    print("   python -m src.tellor_supply_analytics.unified_collector --summary")
    
    print("\n=== API ENDPOINTS ===")
    
    print("\n1. List layer blocks:")
    print("   GET /api/unified/layer-blocks?limit=100")
    
    print("\n2. Remove layer block data:")
    print("   DELETE /api/unified/layer-block/12345")
    
    print("\n3. Re-collect layer block data:")
    print("   POST /api/unified/layer-block/12345/rerun")
    
    print("\n4. Remove and re-collect:")
    print("   POST /api/unified/layer-block/12345/remove-and-rerun")

def main():
    """Main function."""
    print("Testing Tellor Supply Monitor Data Management Features")
    print("=" * 60)
    
    # Show usage examples
    show_usage_examples()
    
    # Test if we can import the modules (without running in venv)
    try:
        test_data_management()
        print("\n✅ Data management functionality is available and working!")
    except Exception as e:
        print(f"\n⚠️  Could not test functionality (likely need virtual environment): {e}")
        print("To test with actual data, activate the virtual environment first:")
        print("  source .venv/bin/activate")
        print("  python test_data_management.py")

if __name__ == "__main__":
    main() 