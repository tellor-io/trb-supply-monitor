#!/usr/bin/env python3
"""
Hourly Balance Collection Scheduler

This script runs the balance collection every hour and can be used with
cron or systemd timer for automated execution.
"""

import sys
import logging
import traceback
from datetime import datetime
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from tellor_supply_analytics.get_active_balances import EnhancedActiveBalancesCollector
from tellor_supply_analytics.database import BalancesDatabase

# Configure logging with file output
log_file = Path('logs/scheduler.log')
log_file.parent.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def run_collection():
    """Run a single balance collection."""
    try:
        logger.info("=== STARTING SCHEDULED BALANCE COLLECTION ===")
        
        # Initialize collector
        collector = EnhancedActiveBalancesCollector()
        
        # Run collection
        success = collector.run()
        
        if success:
            # Get summary of what was collected
            summary = collector.get_latest_summary()
            
            logger.info("=== COLLECTION COMPLETED SUCCESSFULLY ===")
            logger.info(f"Collection time: {summary.get('run_time')}")
            logger.info(f"Total addresses: {summary.get('total_addresses')}")
            logger.info(f"Addresses with balance: {summary.get('addresses_with_balance')}")
            logger.info(f"Total TRB balance: {summary.get('total_trb_balance', 0):,.6f}")
            
            return True
        else:
            logger.error("Collection failed")
            return False
            
    except Exception as e:
        logger.error(f"Collection error: {e}")
        logger.error(traceback.format_exc())
        return False


if __name__ == '__main__':
    # Run collection
    success = run_collection()
    
    if success:
        logger.info("Scheduled collection completed successfully")
        sys.exit(0)
    else:
        logger.error("Scheduled collection failed")
        sys.exit(1)
