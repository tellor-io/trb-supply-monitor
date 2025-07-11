#!/usr/bin/env python3
"""
Tellor Layer Balance Analytics Application

Main application that runs both the web dashboard and periodic balance collection
with configurable intervals.

Usage:
    python app.py                           # Web server only
    python app.py --collect-interval 3600  # Web server + hourly collection
    python app.py --collect-interval 1800  # Web server + 30-minute collection
    python app.py --collect-only --interval 3600  # Collection only (no web server)
"""

import asyncio
import argparse
import logging
import signal
import sys
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse

# Local imports
from src.tellor_supply_analytics.database import BalancesDatabase
from src.tellor_supply_analytics.get_active_balances import EnhancedActiveBalancesCollector

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('logs/app.log') if Path('logs').exists() else logging.NullHandler()
    ]
)
logger = logging.getLogger(__name__)

# Global variables for managing the application
app_shutdown = False
collection_thread = None
collection_service = None
collection_interval = None


class BalanceCollectionService:
    """Service for periodic balance collection."""
    
    def __init__(self, interval_seconds: int, db_path: str = 'tellor_balances.db'):
        self.interval_seconds = interval_seconds
        self.db_path = db_path
        self.running = False
        self.last_collection = None
        
    def start(self):
        """Start the collection service."""
        self.running = True
        logger.info(f"Starting balance collection service with {self.interval_seconds}s interval")
        
        while self.running and not app_shutdown:
            try:
                logger.info("=== STARTING PERIODIC BALANCE COLLECTION ===")
                start_time = datetime.now()
                
                # Run collection
                collector = EnhancedActiveBalancesCollector(db_path=self.db_path)
                success = collector.run()
                
                if success:
                    self.last_collection = start_time
                    summary = collector.get_latest_summary()
                    
                    logger.info("=== COLLECTION COMPLETED SUCCESSFULLY ===")
                    logger.info(f"Collection time: {summary.get('run_time')}")
                    logger.info(f"Total addresses: {summary.get('total_addresses')}")
                    logger.info(f"Addresses with balance: {summary.get('addresses_with_balance')}")
                    logger.info(f"Total TRB balance: {summary.get('total_trb_balance', 0):,.6f}")
                else:
                    logger.error("Collection failed")
                
                # Calculate next collection time
                elapsed = (datetime.now() - start_time).total_seconds()
                sleep_time = max(0, self.interval_seconds - elapsed)
                
                next_collection = datetime.now() + timedelta(seconds=sleep_time)
                logger.info(f"Next collection scheduled for: {next_collection.strftime('%Y-%m-%d %H:%M:%S')}")
                
                # Sleep until next collection
                for _ in range(int(sleep_time)):
                    if app_shutdown or not self.running:
                        break
                    time.sleep(1)
                    
            except Exception as e:
                logger.error(f"Error in collection service: {e}")
                # Sleep for a shorter time on error before retrying
                for _ in range(60):  # 1 minute
                    if app_shutdown or not self.running:
                        break
                    time.sleep(1)
    
    def stop(self):
        """Stop the collection service."""
        self.running = False
        logger.info("Stopping balance collection service")


# Initialize FastAPI app
app = FastAPI(
    title="Tellor Layer Balance Analytics",
    description="Real-time monitoring of Tellor Layer active balances",
    version="1.0.0"
)

# Initialize database
db = BalancesDatabase()

# Mount static files
try:
    app.mount("/static", StaticFiles(directory="static"), name="static")
except RuntimeError:
    logger.warning("Static directory not found, creating basic structure")
    Path("static/css").mkdir(parents=True, exist_ok=True)
    Path("static/js").mkdir(parents=True, exist_ok=True)


@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the main dashboard HTML page."""
    html_file = Path("templates/dashboard.html")
    if html_file.exists():
        return FileResponse("templates/dashboard.html")
    else:
        return HTMLResponse("""
        <html>
            <head><title>Tellor Balance Dashboard</title></head>
            <body style="font-family: Arial, sans-serif; margin: 40px;">
                <h1>Tellor Layer Balance Dashboard</h1>
                <p>Dashboard is initializing... Please ensure templates/dashboard.html exists.</p>
                <p><a href="/docs" style="color: #007bff;">View API Documentation</a></p>
                <h2>Quick Start:</h2>
                <ol>
                    <li>Ensure all files are in place (run setup.sh if needed)</li>
                    <li>Trigger a collection: <code>curl -X POST http://localhost:8000/api/collect</code></li>
                    <li>Refresh this page to see the dashboard</li>
                </ol>
            </body>
        </html>
        """)


@app.get("/api/summary")
async def get_summary():
    """Get summary of latest balance collection."""
    try:
        summary = db.get_latest_snapshot()
        if not summary:
            return {
                "message": "No balance data found. Run a collection first.",
                "total_addresses": 0,
                "addresses_with_balance": 0,
                "total_trb_balance": 0,
                "run_time": None
            }
        return summary
    except Exception as e:
        logger.error(f"Error getting summary: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/balances")
async def get_balances(
    limit: int = Query(100, description="Number of addresses to return", ge=1, le=1000),
    offset: int = Query(0, description="Offset for pagination", ge=0),
    search: Optional[str] = Query(None, description="Search addresses")
):
    """Get latest balances for all addresses with pagination and search."""
    try:
        if search:
            balances = db.search_addresses(search, limit)
        else:
            balances = db.get_latest_balances(limit, offset)
        
        return {
            "balances": balances,
            "limit": limit,
            "offset": offset,
            "search": search,
            "count": len(balances)
        }
    except Exception as e:
        logger.error(f"Error getting balances: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/address/{address}/history")
async def get_address_history(
    address: str,
    limit: int = Query(50, description="Number of historical records", ge=1, le=100)
):
    """Get balance history for a specific address."""
    try:
        history = db.get_address_history(address, limit)
        return {
            "address": address,
            "history": history,
            "count": len(history)
        }
    except Exception as e:
        logger.error(f"Error getting address history: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/account-types")
async def get_account_types_summary():
    """Get summary statistics by account type."""
    try:
        summary = db.get_account_type_summary()
        return {"account_types": summary}
    except Exception as e:
        logger.error(f"Error getting account types summary: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/history")
async def get_collection_history(
    limit: int = Query(100, description="Number of collection runs", ge=1, le=500)
):
    """Get history of balance collection runs."""
    try:
        history = db.get_snapshots_history(limit)
        return {"history": history}
    except Exception as e:
        logger.error(f"Error getting collection history: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/api/collect")
async def trigger_collection():
    """Trigger a new balance collection (for manual runs)."""
    try:
        logger.info("Manual collection triggered via API")
        collector = EnhancedActiveBalancesCollector()
        success = collector.run()
        
        if success:
            summary = db.get_latest_snapshot()
            return {
                "status": "success",
                "message": "Balance collection completed successfully",
                "summary": summary
            }
        else:
            raise HTTPException(status_code=500, detail="Collection failed")
            
    except Exception as e:
        logger.error(f"Error during collection: {e}")
        raise HTTPException(status_code=500, detail="Collection failed")


@app.get("/api/status")
async def get_api_status():
    """Get API and database status."""
    try:
        latest = db.get_latest_snapshot()
        
        # Get collection service status
        global collection_thread, collection_service
        collection_status = {
            "enabled": collection_thread is not None and collection_thread.is_alive(),
            "interval_seconds": collection_interval,
            "next_collection": None
        }
        
        if collection_service and collection_service.last_collection and collection_interval:
            next_coll = collection_service.last_collection + timedelta(seconds=collection_interval)
            collection_status["next_collection"] = next_coll.isoformat()
        
        return {
            "status": "healthy",
            "database_connected": True,
            "latest_collection": latest.get('run_time') if latest else None,
            "total_addresses": latest.get('total_addresses', 0) if latest else 0,
            "collection_service": collection_status
        }
    except Exception as e:
        logger.error(f"Error getting status: {e}")
        return {
            "status": "error",
            "database_connected": False,
            "error": str(e)
        }


def signal_handler(signum, frame):
    """Handle shutdown signals."""
    global app_shutdown, collection_thread
    logger.info(f"Received signal {signum}, shutting down...")
    app_shutdown = True
    
    if collection_thread and collection_thread.is_alive():
        logger.info("Stopping collection service...")
        collection_thread.join(timeout=5)
    
    sys.exit(0)


def run_collection_service(interval_seconds: int):
    """Run the collection service in a separate thread."""
    global collection_service
    collection_service = BalanceCollectionService(interval_seconds)
    collection_service.start()


def main():
    """Main entry point."""
    global app_shutdown, collection_thread, collection_interval
    
    parser = argparse.ArgumentParser(description='Tellor Layer Balance Analytics Application')
    parser.add_argument(
        '--collect-interval',
        type=int,
        help='Enable periodic collection with interval in seconds (e.g., 3600 for hourly)'
    )
    parser.add_argument(
        '--collect-only',
        action='store_true',
        help='Run collection only (no web server)'
    )
    parser.add_argument(
        '--interval',
        type=int,
        default=3600,
        help='Collection interval in seconds (default: 3600 = 1 hour)'
    )
    parser.add_argument(
        '--host',
        default='0.0.0.0',
        help='Host to bind the web server (default: 0.0.0.0)'
    )
    parser.add_argument(
        '--port',
        type=int,
        default=8000,
        help='Port for the web server (default: 8000)'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug logging'
    )
    
    args = parser.parse_args()
    
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Create necessary directories
    Path("logs").mkdir(exist_ok=True)
    Path("templates").mkdir(exist_ok=True)
    Path("static/css").mkdir(parents=True, exist_ok=True)
    Path("static/js").mkdir(parents=True, exist_ok=True)
    
    # Determine collection interval
    if args.collect_interval:
        collection_interval = args.collect_interval
    elif args.collect_only:
        collection_interval = args.interval
    
    # Start collection service if requested
    if collection_interval:
        logger.info(f"Starting collection service with {collection_interval}s interval")
        collection_thread = threading.Thread(
            target=run_collection_service,
            args=(collection_interval,),
            daemon=True
        )
        collection_thread.start()
    
    # Run collection-only mode
    if args.collect_only:
        logger.info("Running in collection-only mode")
        try:
            while not app_shutdown:
                time.sleep(1)
        except KeyboardInterrupt:
            signal_handler(signal.SIGINT, None)
        return
    
    # Start web server
    logger.info(f"Starting Tellor Balance Analytics web server on {args.host}:{args.port}")
    
    if collection_interval:
        logger.info(f"Periodic collection enabled with {collection_interval}s interval")
        logger.info("Collection will start automatically in the background")
    else:
        logger.info("No automatic collection enabled. Use --collect-interval to enable.")
        logger.info("You can trigger collections manually via the web interface or API")
    
    logger.info(f"Dashboard will be available at: http://{args.host}:{args.port}")
    logger.info(f"API documentation at: http://{args.host}:{args.port}/docs")
    
    try:
        uvicorn.run(
            "app:app",
            host=args.host,
            port=args.port,
            reload=False,
            log_level="info" if not args.debug else "debug"
        )
    except Exception as e:
        logger.error(f"Failed to start web server: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main() 