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
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.templating import Jinja2Templates

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
root_path = ""  # Global variable to store the root path


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

# Initialize Jinja2 templates
templates = Jinja2Templates(directory="templates")

# Mount static files
try:
    app.mount("/static", StaticFiles(directory="static"), name="static")
except RuntimeError:
    logger.warning("Static directory not found, creating basic structure")
    Path("static/css").mkdir(parents=True, exist_ok=True)
    Path("static/js").mkdir(parents=True, exist_ok=True)


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """Serve the main dashboard HTML page."""
    html_file = Path("templates/dashboard.html")
    if html_file.exists():
        return templates.TemplateResponse("dashboard.html", {
            "request": request,
            "root_path": request.scope.get("root_path", "")
        })
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
                    <li>Trigger a collection: <code>curl -X POST http://localhost:8001/api/collect</code></li>
                    <li>Refresh this page to see the dashboard</li>
                </ol>
            </body>
        </html>
        """)


@app.get("/analytics/block-time", response_class=HTMLResponse)
async def block_time_analytics(request: Request):
    """Serve the block time analytics HTML page."""
    html_file = Path("templates/block-time-analytics.html")
    if html_file.exists():
        return templates.TemplateResponse("block-time-analytics.html", {
            "request": request,
            "root_path": request.scope.get("root_path", "")
        })
    else:
        return HTMLResponse("""
        <html>
            <head><title>Block Time Analytics</title></head>
            <body style="font-family: Arial, sans-serif; margin: 40px;">
                <h1>Block Time Analytics</h1>
                <p>Block time analytics page is initializing... Please ensure templates/block-time-analytics.html exists.</p>
                <p><a href="/" style="color: #007bff;">Back to Dashboard</a></p>
            </body>
        </html>
        """)


@app.get("/api/summary")
async def get_summary():
    """Get summary of latest balance collection."""
    try:
        # First try to get legacy collection run data
        summary = db.get_latest_snapshot()
        if summary:
            return summary
        
        # If no legacy data, get latest unified snapshot data
        unified_snapshots = db.get_unified_snapshots(limit=1, min_completeness=0.0)
        if unified_snapshots:
            unified = unified_snapshots[0]
            # Convert unified snapshot to legacy format for frontend compatibility
            return {
                "id": unified.get('id'),
                "run_time": unified.get('collection_time'),
                "total_addresses": unified.get('total_addresses', 0),
                "addresses_with_balance": unified.get('addresses_with_balance', 0),
                "total_loya_balance": unified.get('total_loya_balance', 0),
                "total_trb_balance": unified.get('total_trb_balance', 0),
                "bridge_balance_trb": unified.get('bridge_balance_trb', 0),
                "layer_block_height": unified.get('layer_block_height', 0),
                "free_floating_trb": unified.get('free_floating_trb', 0),
                "status": "completed",
                "created_at": unified.get('created_at')
            }
        
        # If no data at all, return default structure
        return {
            "message": "No balance data found. Run a collection first.",
            "total_addresses": 0,
            "addresses_with_balance": 0,
            "total_trb_balance": 0,
            "run_time": None
        }
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
        
        # If no legacy balance data, try to get from unified snapshots
        if not balances:
            unified_snapshots = db.get_unified_snapshots(limit=1, min_completeness=0.0)
            if unified_snapshots:
                latest_unified = unified_snapshots[0]
                eth_timestamp = latest_unified.get('eth_block_timestamp')
                if eth_timestamp:
                    balances = db.get_unified_balances_by_eth_timestamp(eth_timestamp)
                    # Convert unified balance format to legacy format for frontend compatibility
                    balances = [
                        {
                            "id": balance.get('id'),
                            "snapshot_time": latest_unified.get('collection_time'),
                            "address": balance.get('address'),
                            "account_type": balance.get('account_type'),
                            "loya_balance": balance.get('loya_balance', 0),
                            "loya_balance_trb": balance.get('loya_balance_trb', 0),
                            "created_at": balance.get('created_at')
                        }
                        for balance in balances[:limit]
                    ]
        
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
        # Try legacy data first
        latest = db.get_latest_snapshot()
        
        # If no legacy data, use unified data
        if not latest:
            unified_snapshots = db.get_unified_snapshots(limit=1, min_completeness=0.0)
            if unified_snapshots:
                latest = unified_snapshots[0]
                # Convert to legacy format for status display
                latest = {
                    "run_time": latest.get('collection_time'),
                    "total_addresses": latest.get('total_addresses', 0)
                }
        
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


# ================================
# UNIFIED TIMELINE ENDPOINTS
# ================================

@app.get("/api/unified/snapshots")
async def get_unified_snapshots(
    limit: int = Query(100, description="Number of snapshots to return", ge=1, le=1000),
    min_completeness: float = Query(0.0, description="Minimum completeness score (0-1)", ge=0.0, le=1.0)
):
    """Get unified snapshots ordered by Ethereum block timestamp."""
    try:
        snapshots = db.get_unified_snapshots(limit=limit, min_completeness=min_completeness)
        
        return {
            "snapshots": snapshots,
            "count": len(snapshots),
            "limit": limit,
            "min_completeness": min_completeness
        }
    except Exception as e:
        logger.error(f"Error getting unified snapshots: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/unified/snapshot/{eth_timestamp}")
async def get_unified_snapshot_by_timestamp(eth_timestamp: int):
    """Get a specific unified snapshot by Ethereum block timestamp."""
    try:
        snapshot = db.get_unified_snapshot_by_eth_timestamp(eth_timestamp)
        if not snapshot:
            raise HTTPException(status_code=404, detail="Snapshot not found for this timestamp")
        
        return snapshot
    except Exception as e:
        logger.error(f"Error getting unified snapshot: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/unified/balances/{eth_timestamp}")
async def get_unified_balances_by_timestamp(
    eth_timestamp: int,
    limit: int = Query(1000, description="Number of addresses to return", ge=1, le=5000)
):
    """Get all balance records for a specific Ethereum block timestamp."""
    try:
        balances = db.get_unified_balances_by_eth_timestamp(eth_timestamp)
        
        if not balances:
            raise HTTPException(status_code=404, detail="No balance data found for this timestamp")
        
        # Apply limit
        if len(balances) > limit:
            balances = balances[:limit]
        
        return {
            "eth_timestamp": eth_timestamp,
            "eth_datetime": datetime.fromtimestamp(eth_timestamp).isoformat(),
            "balances": balances,
            "count": len(balances),
            "limit": limit
        }
    except Exception as e:
        logger.error(f"Error getting unified balances: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/unified/timeline")
async def get_unified_timeline(
    hours_back: int = Query(24, description="Hours of data to include", ge=1, le=8760),
    min_completeness: float = Query(0.5, description="Minimum completeness score", ge=0.0, le=1.0)
):
    """Get timeline data for charts - optimized for frontend visualization."""
    try:
        # Calculate limit based on hours_back (assume one data point per hour max)
        limit = hours_back * 2  # Allow for denser data
        
        snapshots = db.get_unified_snapshots(limit=limit, min_completeness=min_completeness)
        
        if not snapshots:
            return {
                "timeline": [],
                "count": 0,
                "hours_back": hours_back,
                "min_completeness": min_completeness
            }
        
        # Filter by time range
        current_time = datetime.now().timestamp()
        cutoff_time = current_time - (hours_back * 3600)
        
        filtered_snapshots = [
            s for s in snapshots 
            if s.get('eth_block_timestamp', 0) >= cutoff_time
        ]
        
        # Transform for frontend charts
        timeline_data = []
        for snapshot in filtered_snapshots:
            timeline_data.append({
                'timestamp': snapshot.get('eth_block_timestamp'),
                'datetime': snapshot.get('eth_block_datetime'),
                'eth_block_number': snapshot.get('eth_block_number'),
                'layer_block_height': snapshot.get('layer_block_height', 0),
                'bridge_balance_trb': snapshot.get('bridge_balance_trb', 0),
                'layer_total_supply_trb': snapshot.get('layer_total_supply_trb', 0),
                'bonded_tokens': snapshot.get('bonded_tokens', 0),
                'not_bonded_tokens': snapshot.get('not_bonded_tokens', 0),
                'total_reporter_power': snapshot.get('total_reporter_power', 0),
                'free_floating_trb': snapshot.get('free_floating_trb', 0),
                'total_addresses': snapshot.get('total_addresses', 0),
                'addresses_with_balance': snapshot.get('addresses_with_balance', 0),
                'total_trb_balance': snapshot.get('total_trb_balance', 0),
                'completeness_score': snapshot.get('data_completeness_score', 0)
            })
        
        return {
            "timeline": timeline_data,
            "count": len(timeline_data),
            "hours_back": hours_back,
            "min_completeness": min_completeness
        }
    except Exception as e:
        logger.error(f"Error getting unified timeline: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/unified/summary")
async def get_unified_summary():
    """Get summary of unified data collection status."""
    try:
        # Get latest unified snapshot
        snapshots = db.get_unified_snapshots(limit=1, min_completeness=0.0)
        latest_snapshot = snapshots[0] if snapshots else None
        
        # Get collection statistics
        all_snapshots = db.get_unified_snapshots(limit=1000, min_completeness=0.0)
        total_snapshots = len(all_snapshots)
        complete_snapshots = sum(1 for s in all_snapshots if s.get('data_completeness_score', 0) >= 1.0)
        
        # Get incomplete snapshots for backfill info
        incomplete_snapshots = db.get_incomplete_snapshots(min_completeness=1.0)
        
        summary = {
            "latest_snapshot": latest_snapshot,
            "statistics": {
                "total_snapshots": total_snapshots,
                "complete_snapshots": complete_snapshots,
                "incomplete_snapshots": len(incomplete_snapshots),
                "completion_rate": complete_snapshots / total_snapshots if total_snapshots > 0 else 0
            }
        }
        
        if latest_snapshot:
            summary["latest_eth_datetime"] = latest_snapshot.get('eth_block_datetime')
            summary["latest_data_age_hours"] = (
                datetime.now().timestamp() - latest_snapshot.get('eth_block_timestamp', 0)
            ) / 3600
        
        return summary
        
    except Exception as e:
        logger.error(f"Error getting unified summary: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/block-time/data")
async def get_block_time_data(
    hours_back: int = Query(24, description="Hours back to analyze", ge=1, le=8760)
):
    """Get block time data for the specified time period."""
    try:
        # Calculate the cutoff timestamp
        cutoff_timestamp = int((datetime.now() - timedelta(hours=hours_back)).timestamp())
        
        # Get unified snapshots with layer block data, ordered by timestamp
        import sqlite3
        with sqlite3.connect(db.db_path) as conn:
            cursor = conn.execute('''
                SELECT 
                    eth_block_timestamp,
                    layer_block_height,
                    layer_block_timestamp,
                    eth_block_datetime
                FROM unified_snapshots 
                WHERE eth_block_timestamp >= ?
                  AND layer_block_height IS NOT NULL 
                  AND layer_block_timestamp IS NOT NULL
                ORDER BY eth_block_timestamp ASC
            ''', (cutoff_timestamp,))
            
            rows = cursor.fetchall()
        
        if len(rows) < 2:
            return {
                "block_times": [],
                "count": 0,
                "hours_back": hours_back,
                "message": "Insufficient data for block time calculation"
            }
        
        # Calculate block times between consecutive rows
        block_times = []
        for i in range(1, len(rows)):
            prev_row = rows[i-1]
            curr_row = rows[i]
            
            # Extract data
            prev_height = prev_row[1]
            prev_timestamp = prev_row[2]
            curr_height = curr_row[1]
            curr_timestamp = curr_row[2]
            curr_eth_timestamp = curr_row[0]
            curr_datetime = curr_row[3]
            
            # Calculate block time
            height_diff = curr_height - prev_height
            time_diff = curr_timestamp - prev_timestamp
            
            if height_diff > 0 and time_diff > 0:
                block_time_seconds = time_diff / height_diff
                block_times.append({
                    "timestamp": curr_eth_timestamp,
                    "datetime": curr_datetime,
                    "block_time_seconds": round(block_time_seconds, 3),
                    "height_range": f"{prev_height}-{curr_height}",
                    "blocks_counted": height_diff,
                    "time_span_seconds": time_diff
                })
        
        return {
            "block_times": block_times,
            "count": len(block_times),
            "hours_back": hours_back,
            "average_block_time": round(sum(bt["block_time_seconds"] for bt in block_times) / len(block_times), 3) if block_times else 0
        }
        
    except Exception as e:
        logger.error(f"Error getting block time data: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/block-time/estimate")
async def estimate_future_block_time(
    target_height: int = Query(..., description="Target block height to estimate", ge=1)
):
    """Estimate when a future block height will be reached based on current block time data."""
    try:
        import sqlite3
        import subprocess
        import json
        import os
        
        # FIRST: Get the REAL-TIME current block height from layerd status
        real_time_height = None
        layerd_path = './layerd'
        tellor_layer_rpc_url = os.getenv('TELLOR_LAYER_RPC_URL')
        
        try:
            cmd = [layerd_path, 'status', '--output', 'json', '--node', tellor_layer_rpc_url]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0:
                status_data = json.loads(result.stdout)
                real_time_height = int(status_data['sync_info']['latest_block_height'])
                logger.info(f"Got real-time height from layerd status: {real_time_height}")
            else:
                logger.warning(f"layerd status failed: {result.stderr}")
        except Exception as e:
            logger.warning(f"Could not get real-time height from layerd: {e}")
        
        # Get current block height and timestamp from latest snapshot (for timestamp reference)
        with sqlite3.connect(db.db_path) as conn:
            cursor = conn.execute('''
                SELECT 
                    layer_block_height,
                    layer_block_timestamp,
                    eth_block_datetime
                FROM unified_snapshots 
                WHERE layer_block_height IS NOT NULL 
                  AND layer_block_timestamp IS NOT NULL
                ORDER BY eth_block_timestamp DESC 
                LIMIT 1
            ''')
            
            latest_row = cursor.fetchone()
            
            if not latest_row:
                raise HTTPException(status_code=404, detail="No current block data available")
            
            db_height = latest_row[0]
            db_timestamp = latest_row[1]
            db_datetime = latest_row[2]
        
        # Use real-time height if available, otherwise fall back to database height
        if real_time_height is not None:
            current_height = real_time_height
            # Estimate the current timestamp based on blocks elapsed since database snapshot
            blocks_since_snapshot = current_height - db_height
            # Use a conservative 1.7 second average for this small adjustment
            estimated_time_diff = blocks_since_snapshot * 1.7
            current_timestamp = db_timestamp + int(estimated_time_diff)
            from datetime import timezone
            current_datetime = datetime.fromtimestamp(current_timestamp, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
            data_source_note = f"real-time (layerd status: {current_height}, db snapshot: {db_height})"
        else:
            # Fallback to database height
            current_height = db_height
            current_timestamp = db_timestamp
            current_datetime = db_datetime
            data_source_note = "database snapshot (WARNING: may be outdated)"
            logger.warning("Using database snapshot height - estimation may be inaccurate")
        
        # Validate target height
        if target_height <= current_height:
            raise HTTPException(
                status_code=400, 
                detail=f"Target height ({target_height}) must be greater than current height ({current_height})"
            )
        
        # Get average block time from recent data (last 24 hours by default)
        cutoff_timestamp = int((datetime.now() - timedelta(hours=24)).timestamp())
        
        with sqlite3.connect(db.db_path) as conn:
            cursor = conn.execute('''
                SELECT 
                    layer_block_height,
                    layer_block_timestamp
                FROM unified_snapshots 
                WHERE eth_block_timestamp >= ?
                  AND layer_block_height IS NOT NULL 
                  AND layer_block_timestamp IS NOT NULL
                ORDER BY eth_block_timestamp ASC
            ''', (cutoff_timestamp,))
            
            rows = cursor.fetchall()
        
        # Calculate average block time from recent data
        if len(rows) < 2:
            # Fallback: use a default block time estimate
            avg_block_time = 1.7  # seconds, based on typical Tellor Layer performance
            data_source = "default estimate"
            total_blocks_analyzed = 0
        else:
            # Calculate block times between consecutive rows
            block_times = []
            for i in range(1, len(rows)):
                prev_height = rows[i-1][0]
                prev_timestamp = rows[i-1][1]
                curr_height = rows[i][0]
                curr_timestamp = rows[i][1]
                
                height_diff = curr_height - prev_height
                time_diff = curr_timestamp - prev_timestamp
                
                if height_diff > 0 and time_diff > 0:
                    block_time = time_diff / height_diff
                    block_times.append(block_time)
            
            if block_times:
                avg_block_time = sum(block_times) / len(block_times)
                data_source = f"last 24 hours ({len(block_times)} data points)"
                total_blocks_analyzed = sum(rows[i][0] - rows[i-1][0] for i in range(1, len(rows)) if rows[i][0] > rows[i-1][0])
            else:
                avg_block_time = 1.7
                data_source = "default estimate"
                total_blocks_analyzed = 0
        
        # Calculate estimation
        blocks_remaining = target_height - current_height
        seconds_until = blocks_remaining * avg_block_time
        
        # Calculate estimated arrival time
        from datetime import timezone
        current_dt = datetime.fromtimestamp(current_timestamp, tz=timezone.utc)
        estimated_arrival_utc = current_dt + timedelta(seconds=seconds_until)
        
        # Format time until in human-readable format
        def format_time_until(seconds):
            if seconds < 60:
                return f"{int(seconds)} seconds"
            elif seconds < 3600:
                minutes = seconds / 60
                return f"{int(minutes)} minutes"
            elif seconds < 86400:
                hours = seconds / 3600
                return f"{hours:.1f} hours"
            else:
                days = seconds / 86400
                return f"{days:.1f} days"
        
        return {
            "current_height": current_height,
            "current_timestamp": current_timestamp,
            "current_datetime": current_datetime,
            "target_height": target_height,
            "blocks_remaining": blocks_remaining,
            "avg_block_time_seconds": round(avg_block_time, 3),
            "data_source": f"{data_source} | Height: {data_source_note}",
            "total_blocks_analyzed": total_blocks_analyzed,
            "seconds_until": round(seconds_until, 1),
            "time_until_formatted": format_time_until(seconds_until),
            "estimated_arrival_utc": estimated_arrival_utc.isoformat(),
            "estimated_arrival_formatted": estimated_arrival_utc.strftime('%Y-%m-%d %H:%M:%S UTC')
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error estimating future block time: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/api/unified/collect")
async def trigger_unified_collection(
    hours_back: int = Query(6, description="Hours back to collect", ge=1, le=48),
    max_blocks: int = Query(20, description="Max blocks to process", ge=1, le=100)
):
    """Trigger a unified collection run."""
    try:
        logger.info(f"Unified collection triggered via API - hours_back: {hours_back}, max_blocks: {max_blocks}")
        
        # Import here to avoid circular dependencies
        from src.tellor_supply_analytics.unified_collector import UnifiedDataCollector
        
        collector = UnifiedDataCollector()
        processed = collector.run_unified_collection(
            hours_back=hours_back, 
            max_blocks=max_blocks
        )
        
        logger.info(f"Unified collection completed: {processed} blocks processed")
        
        return {
            "status": "success",
            "message": f"Unified collection completed: {processed} blocks processed",
            "blocks_processed": processed,
            "hours_back": hours_back
        }
        
    except Exception as e:
        logger.error(f"Error during unified collection: {e}")
        raise HTTPException(status_code=500, detail="Unified collection failed")


@app.get("/api/unified/incomplete")
async def get_incomplete_snapshots(
    limit: int = Query(50, description="Number of incomplete snapshots to return", ge=1, le=200),
    min_completeness: float = Query(0.8, description="Minimum completeness score", ge=0.0, le=1.0)
):
    """Get snapshots with incomplete data that need backfill."""
    try:
        incomplete_snapshots = db.get_incomplete_snapshots(min_completeness=min_completeness)
        
        if len(incomplete_snapshots) > limit:
            incomplete_snapshots = incomplete_snapshots[:limit]
        
        return {
            "incomplete_snapshots": incomplete_snapshots,
            "count": len(incomplete_snapshots),
            "limit": limit,
            "min_completeness": min_completeness
        }
    except Exception as e:
        logger.error(f"Error getting incomplete snapshots: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


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
    global app_shutdown, collection_thread, collection_interval, root_path
    
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
        default=8001,
        help='Port for the web server (default: 8001)'
    )
    parser.add_argument(
        '--root-path',
        default='supply',
        help='Root path for the application when served behind a proxy (e.g., /supply)'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug logging'
    )
    
    args = parser.parse_args()
    
    # Set the global root_path
    root_path = args.root_path
    
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
            log_level="info" if not args.debug else "debug",
            root_path=root_path
        )
    except Exception as e:
        logger.error(f"Failed to start web server: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main() 