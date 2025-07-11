#!/usr/bin/env python3
"""
Runner script for Unified Tellor Data Collection

This script runs the unified data collection system that uses Ethereum block timestamps
as the primary timeline for all data collection activities.

Usage Examples:
    # Collect data for the last 24 hours
    python run_unified_collection.py

    # Collect data for the last 48 hours with 2-hour intervals
    python run_unified_collection.py --hours-back 48 --block-interval 7200

    # Run backfill for incomplete data
    python run_unified_collection.py --backfill

    # Show data collection summary
    python run_unified_collection.py --summary

    # Continuous monitoring mode (collect every hour)
    python run_unified_collection.py --monitor --interval 3600
"""

import argparse
import logging
import time
import signal
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add src to path for imports
sys.path.append(str(Path(__file__).parent / 'src'))

from tellor_supply_analytics.unified_collector import UnifiedDataCollector

# Global flag for graceful shutdown
shutdown_requested = False

def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    global shutdown_requested
    logger.info(f"Received signal {signum}, shutting down gracefully...")
    shutdown_requested = True

def setup_logging(debug: bool = False):
    """Set up logging configuration."""
    level = logging.DEBUG if debug else logging.INFO
    
    # Create logs directory if it doesn't exist
    logs_dir = Path('logs')
    logs_dir.mkdir(exist_ok=True)
    
    # Configure logging
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(logs_dir / 'unified_collection.log')
        ]
    )

def run_single_collection(collector: UnifiedDataCollector, args):
    """Run a single unified collection cycle."""
    logger.info("Starting single unified collection cycle")
    
    processed = collector.run_unified_collection(
        hours_back=args.hours_back,
        block_interval=args.block_interval,
        max_blocks=args.max_blocks
    )
    
    logger.info(f"Collection cycle completed: {processed} blocks processed")
    return processed

def run_backfill(collector: UnifiedDataCollector, args):
    """Run backfill for incomplete data."""
    logger.info("Starting backfill for incomplete data")
    
    updated = collector.backfill_incomplete_data(max_backfill=args.max_backfill)
    
    logger.info(f"Backfill completed: {updated} snapshots updated")
    return updated

def run_monitoring_mode(collector: UnifiedDataCollector, args):
    """Run continuous monitoring mode."""
    logger.info(f"Starting monitoring mode with {args.interval} second intervals")
    logger.info("Press Ctrl+C to stop gracefully")
    
    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    cycles_completed = 0
    
    try:
        while not shutdown_requested:
            logger.info(f"=== MONITORING CYCLE {cycles_completed + 1} ===")
            start_time = datetime.now()
            
            try:
                # Run collection
                processed = run_single_collection(collector, args)
                
                # Optionally run backfill periodically
                if cycles_completed % 5 == 0:  # Every 5th cycle
                    logger.info("Running periodic backfill...")
                    updated = run_backfill(collector, args)
                
                cycles_completed += 1
                
                # Show summary periodically
                if cycles_completed % 3 == 0:  # Every 3rd cycle
                    summary = collector.get_data_summary()
                    logger.info(f"Collection summary: {summary}")
                
            except Exception as e:
                logger.error(f"Error in monitoring cycle: {e}")
                
            # Calculate sleep time
            elapsed = (datetime.now() - start_time).total_seconds()
            sleep_time = max(0, args.interval - elapsed)
            
            if sleep_time > 0 and not shutdown_requested:
                next_run = datetime.now().replace(microsecond=0) + \
                          timedelta(seconds=sleep_time)
                logger.info(f"Next collection cycle at: {next_run}")
                
                # Sleep in small increments to check for shutdown
                slept = 0
                while slept < sleep_time and not shutdown_requested:
                    time.sleep(min(5, sleep_time - slept))
                    slept += 5
                    
    except KeyboardInterrupt:
        logger.info("Monitoring stopped by user")
    except Exception as e:
        logger.error(f"Error in monitoring mode: {e}")
        raise
    
    logger.info(f"Monitoring completed after {cycles_completed} cycles")

def show_summary(collector: UnifiedDataCollector):
    """Show data collection summary."""
    print("\n" + "=" * 60)
    print("UNIFIED DATA COLLECTION SUMMARY")
    print("=" * 60)
    
    summary = collector.get_data_summary()
    
    if 'error' in summary:
        print(f"Error getting summary: {summary['error']}")
        return
    
    total = summary.get('total_snapshots', 0)
    complete = summary.get('complete_snapshots', 0)
    incomplete = summary.get('incomplete_snapshots', 0)
    rate = summary.get('completion_rate', 0)
    coverage = summary.get('coverage_hours', 0)
    
    print(f"Total Snapshots:      {total:,}")
    print(f"Complete Snapshots:   {complete:,}")
    print(f"Incomplete Snapshots: {incomplete:,}")
    print(f"Completion Rate:      {rate:.1%}")
    print(f"Time Coverage:        {coverage:.1f} hours")
    
    if summary.get('latest_eth_timestamp'):
        latest_time = datetime.fromtimestamp(summary['latest_eth_timestamp'])
        print(f"Latest Data:          {latest_time}")
        
    if summary.get('oldest_eth_timestamp'):
        oldest_time = datetime.fromtimestamp(summary['oldest_eth_timestamp'])
        print(f"Oldest Data:          {oldest_time}")
    
    print("=" * 60)

def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description='Unified Tellor Data Collector',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    # Collection parameters
    parser.add_argument('--hours-back', type=int, default=24,
                       help='Hours back to collect data for (default: 24)')
    parser.add_argument('--block-interval', type=int, default=3600,
                       help='Target interval between blocks in seconds (default: 3600)')
    parser.add_argument('--max-blocks', type=int, default=50,
                       help='Maximum blocks to process in one run (default: 50)')
    parser.add_argument('--max-backfill', type=int, default=20,
                       help='Maximum snapshots to backfill (default: 20)')
    
    # Mode selection
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument('--backfill', action='store_true',
                           help='Run backfill for incomplete data only')
    mode_group.add_argument('--summary', action='store_true',
                           help='Show data collection summary only')
    mode_group.add_argument('--monitor', action='store_true',
                           help='Run in continuous monitoring mode')
    
    # Monitoring parameters
    parser.add_argument('--interval', type=int, default=3600,
                       help='Monitoring interval in seconds (default: 3600)')
    
    # General options
    parser.add_argument('--db-path', default='tellor_balances.db',
                       help='Database file path (default: tellor_balances.db)')
    parser.add_argument('--debug', action='store_true',
                       help='Enable debug logging')
    
    args = parser.parse_args()
    
    # Set up logging
    setup_logging(args.debug)
    global logger
    logger = logging.getLogger(__name__)
    
    # Initialize collector
    try:
        collector = UnifiedDataCollector(db_path=args.db_path)
    except Exception as e:
        logger.error(f"Failed to initialize unified collector: {e}")
        sys.exit(1)
    
    # Run based on mode
    try:
        if args.summary:
            show_summary(collector)
        elif args.backfill:
            run_backfill(collector, args)
        elif args.monitor:
            run_monitoring_mode(collector, args)
        else:
            run_single_collection(collector, args)
            
    except Exception as e:
        logger.error(f"Error running unified collection: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main() 