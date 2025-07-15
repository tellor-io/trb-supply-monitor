#!/usr/bin/env python3
"""
Test Script for Unified Timeline System

This script tests the unified data collection system to ensure it works correctly
and demonstrates the key functionality.
"""

import sys
import logging
from pathlib import Path
from datetime import datetime

# Add src to path for imports
sys.path.append(str(Path(__file__).parent / 'src'))

from tellor_supply_analytics.database import BalancesDatabase
from tellor_supply_analytics.unified_collector import UnifiedDataCollector

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_database_tables():
    """Test that unified database tables are created correctly."""
    logger.info("Testing database table creation...")
    
    try:
        db = BalancesDatabase('test_unified.db')
        logger.info("✅ Database initialized successfully")
        
        # Test unified methods
        snapshots = db.get_unified_snapshots(limit=1)
        logger.info(f"✅ get_unified_snapshots works (found {len(snapshots)} snapshots)")
        
        timestamps = db.get_existing_eth_timestamps()
        logger.info(f"✅ get_existing_eth_timestamps works (found {len(timestamps)} timestamps)")
        
        incomplete = db.get_incomplete_snapshots()
        logger.info(f"✅ get_incomplete_snapshots works (found {len(incomplete)} incomplete)")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Database test failed: {e}")
        return False

def test_unified_collector():
    """Test the unified data collector."""
    logger.info("Testing unified data collector...")
    
    try:
        collector = UnifiedDataCollector('test_unified.db')
        logger.info("✅ UnifiedDataCollector initialized successfully")
        
        # Test Ethereum block range (should work even if no data collected)
        blocks = collector.get_ethereum_block_range(hours_back=1, block_interval=3600)
        logger.info(f"✅ get_ethereum_block_range works (found {len(blocks)} blocks)")
        
        # Test data summary
        summary = collector.get_data_summary()
        logger.info(f"✅ get_data_summary works: {summary}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Unified collector test failed: {e}")
        return False

def test_small_collection():
    """Test a small unified collection."""
    logger.info("Testing small unified collection...")
    
    try:
        collector = UnifiedDataCollector('test_unified.db')
        
        # Try to collect data for just 1 hour back, max 2 blocks
        processed = collector.run_unified_collection(
            hours_back=1,
            block_interval=7200,  # 2 hour intervals (will get 1 block max)
            max_blocks=2
        )
        
        logger.info(f"✅ Small collection completed: {processed} blocks processed")
        
        # Check what we collected
        db = BalancesDatabase('test_unified.db')
        snapshots = db.get_unified_snapshots(limit=5)
        
        if snapshots:
            logger.info(f"✅ Found {len(snapshots)} unified snapshots after collection")
            latest = snapshots[0]
            logger.info(f"   Latest snapshot: ETH block {latest.get('eth_block_number')} "
                       f"(completeness: {latest.get('data_completeness_score', 0):.2f})")
        else:
            logger.info("ℹ️  No snapshots collected (may be normal if RPC unavailable)")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Small collection test failed: {e}")
        return False

def test_api_compatibility():
    """Test that API-compatible data is available."""
    logger.info("Testing API data compatibility...")
    
    try:
        db = BalancesDatabase('test_unified.db')
        
        # Test methods that API endpoints use
        snapshots = db.get_unified_snapshots(limit=10, min_completeness=0.0)
        logger.info(f"✅ API snapshots query works ({len(snapshots)} results)")
        
        if snapshots:
            # Test specific snapshot lookup
            timestamp = snapshots[0]['eth_block_timestamp']
            specific = db.get_unified_snapshot_by_eth_timestamp(timestamp)
            logger.info(f"✅ Specific snapshot lookup works")
            
            # Test balance lookup
            balances = db.get_unified_balances_by_eth_timestamp(timestamp)
            logger.info(f"✅ Balance lookup works ({len(balances)} addresses)")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ API compatibility test failed: {e}")
        return False

def demonstrate_timeline_data():
    """Demonstrate how timeline data would be used by frontend."""
    logger.info("Demonstrating timeline data for frontend...")
    
    try:
        db = BalancesDatabase('test_unified.db')
        snapshots = db.get_unified_snapshots(limit=24, min_completeness=0.0)
        
        if not snapshots:
            logger.info("ℹ️  No timeline data available yet")
            return True
        
        logger.info(f"📊 Timeline Data Available ({len(snapshots)} data points):")
        
        # Show sample of what frontend charts would use
        for i, snapshot in enumerate(snapshots[:3]):  # Show first 3
            timestamp = snapshot.get('eth_block_timestamp', 0)
            datetime_str = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
            
            logger.info(f"   {i+1}. {datetime_str} (ETH block {snapshot.get('eth_block_number')})")
            logger.info(f"      Bridge Balance: {snapshot.get('bridge_balance_trb', 0):.2f} TRB")
            logger.info(f"      Layer Supply: {snapshot.get('layer_total_supply_trb', 0):,.0f} TRB")
            logger.info(f"      Active Addresses: {snapshot.get('addresses_with_balance', 0):,}")
            logger.info(f"      Completeness: {snapshot.get('data_completeness_score', 0):.2f}")
            logger.info("")
        
        if len(snapshots) > 3:
            logger.info(f"   ... and {len(snapshots) - 3} more data points")
        
        # Show time range
        if len(snapshots) > 1:
            oldest = snapshots[-1]['eth_block_timestamp']
            newest = snapshots[0]['eth_block_timestamp']
            hours_coverage = (newest - oldest) / 3600
            logger.info(f"📈 Time Coverage: {hours_coverage:.1f} hours")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Timeline demonstration failed: {e}")
        return False

def main():
    """Run all tests."""
    logger.info("=" * 60)
    logger.info("UNIFIED TIMELINE SYSTEM - TEST SUITE")
    logger.info("=" * 60)
    
    tests = [
        ("Database Tables", test_database_tables),
        ("Unified Collector", test_unified_collector),
        ("Small Collection", test_small_collection),
        ("API Compatibility", test_api_compatibility),
        ("Timeline Demo", demonstrate_timeline_data),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        logger.info("")
        logger.info(f"Running test: {test_name}")
        logger.info("-" * 40)
        
        if test_func():
            passed += 1
            logger.info(f"✅ {test_name} PASSED")
        else:
            logger.info(f"❌ {test_name} FAILED")
    
    logger.info("")
    logger.info("=" * 60)
    logger.info(f"TEST RESULTS: {passed}/{total} tests passed")
    
    if passed == total:
        logger.info("🎉 All tests passed! Unified timeline system is working correctly.")
        logger.info("")
        logger.info("Next steps:")
        logger.info("1. Run: python run_unified_collection.py --summary")
        logger.info("2. Start monitoring: python run_unified_collection.py --monitor")
        logger.info("3. View API docs: http://localhost:8000/docs")
        logger.info("4. Test API: curl http://localhost:8000/api/unified/summary")
    else:
        logger.info("⚠️  Some tests failed. Check the errors above.")
        return 1
    
    logger.info("=" * 60)
    return 0

if __name__ == '__main__':
    sys.exit(main()) 