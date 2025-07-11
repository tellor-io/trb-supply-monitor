#!/usr/bin/env python3
"""
FastAPI Backend for Tellor Layer Active Balances Dashboard

This API provides endpoints for accessing balance data stored in SQLite database.
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from typing import List, Dict, Optional
import logging
from datetime import datetime
from pathlib import Path

# Local imports
from src.tellor_supply_analytics.database import BalancesDatabase
from src.tellor_supply_analytics.get_active_balances import EnhancedActiveBalancesCollector

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Tellor Layer Balance Analytics API",
    description="API for accessing Tellor Layer active balance data",
    version="1.0.0"
)

# Initialize database
db = BalancesDatabase()

# Mount static files (CSS, JS)
app.mount("/static", StaticFiles(directory="static"), name="static")


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
            <body>
                <h1>Tellor Layer Balance Dashboard</h1>
                <p>Dashboard is initializing... Please ensure templates/dashboard.html exists.</p>
                <p><a href="/docs">View API Documentation</a></p>
            </body>
        </html>
        """)


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
    hours_back: int = Query(24, description="Hours of data to include", ge=1, le=168),
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
                "eth_timestamp": snapshot.get('eth_block_timestamp'),
                "eth_datetime": snapshot.get('eth_block_datetime'),
                "eth_block_number": snapshot.get('eth_block_number'),
                "bridge_balance_trb": snapshot.get('bridge_balance_trb'),
                "layer_total_supply_trb": snapshot.get('layer_total_supply_trb'),
                "not_bonded_tokens": snapshot.get('not_bonded_tokens'),
                "bonded_tokens": snapshot.get('bonded_tokens'),
                "free_floating_trb": snapshot.get('free_floating_trb'),
                "total_addresses": snapshot.get('total_addresses'),
                "addresses_with_balance": snapshot.get('addresses_with_balance'),
                "total_trb_balance": snapshot.get('total_trb_balance'),
                "data_completeness_score": snapshot.get('data_completeness_score')
            })
        
        return {
            "timeline": timeline_data,
            "count": len(timeline_data),
            "hours_back": hours_back,
            "min_completeness": min_completeness,
            "oldest_timestamp": timeline_data[-1]["eth_timestamp"] if timeline_data else None,
            "newest_timestamp": timeline_data[0]["eth_timestamp"] if timeline_data else None
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


@app.get("/api/unified/incomplete")
async def get_incomplete_snapshots(
    limit: int = Query(50, description="Number of incomplete snapshots", ge=1, le=200)
):
    """Get snapshots with incomplete data (for backfill purposes)."""
    try:
        incomplete = db.get_incomplete_snapshots(min_completeness=1.0)
        
        # Limit results
        if len(incomplete) > limit:
            incomplete = incomplete[:limit]
        
        return {
            "incomplete_snapshots": incomplete,
            "count": len(incomplete),
            "limit": limit
        }
        
    except Exception as e:
        logger.error(f"Error getting incomplete snapshots: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ================================
# LEGACY ENDPOINTS (for backward compatibility)
# ================================

@app.get("/api/summary")
async def get_summary():
    """Get summary of latest balance collection."""
    try:
        summary = db.get_latest_snapshot()
        if not summary:
            raise HTTPException(status_code=404, detail="No balance data found")
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
            "search": search
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
        if not history:
            raise HTTPException(status_code=404, detail="Address not found")
        
        return {
            "address": address,
            "history": history
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


@app.post("/api/unified/collect")
async def trigger_unified_collection(
    hours_back: int = Query(6, description="Hours back to collect", ge=1, le=48),
    max_blocks: int = Query(20, description="Max blocks to process", ge=1, le=100)
):
    """Trigger a unified collection run."""
    try:
        # Import here to avoid circular dependencies
        from src.tellor_supply_analytics.unified_collector import UnifiedDataCollector
        
        collector = UnifiedDataCollector()
        processed = collector.run_unified_collection(
            hours_back=hours_back, 
            max_blocks=max_blocks
        )
        
        return {
            "status": "success",
            "message": f"Unified collection completed: {processed} blocks processed",
            "blocks_processed": processed,
            "hours_back": hours_back
        }
        
    except Exception as e:
        logger.error(f"Error during unified collection: {e}")
        raise HTTPException(status_code=500, detail="Unified collection failed")


@app.get("/api/status")
async def get_api_status():
    """Get API and database status."""
    try:
        latest = db.get_latest_snapshot()
        
        # Also check unified data
        unified_snapshots = db.get_unified_snapshots(limit=1)
        latest_unified = unified_snapshots[0] if unified_snapshots else None
        
        return {
            "status": "healthy",
            "database_connected": True,
            "latest_collection": latest.get('run_time') if latest else None,
            "total_addresses": latest.get('total_addresses', 0) if latest else 0,
            "unified_data": {
                "available": latest_unified is not None,
                "latest_eth_timestamp": latest_unified.get('eth_block_timestamp') if latest_unified else None,
                "latest_completeness": latest_unified.get('data_completeness_score') if latest_unified else None
            }
        }
    except Exception as e:
        logger.error(f"Error getting status: {e}")
        return {
            "status": "error",
            "database_connected": False,
            "error": str(e)
        }


if __name__ == "__main__":
    import uvicorn
    
    # Create directories if they don't exist
    Path("templates").mkdir(exist_ok=True)
    Path("static/css").mkdir(parents=True, exist_ok=True)
    Path("static/js").mkdir(parents=True, exist_ok=True)
    
    logger.info("Starting Tellor Balance Analytics API")
    uvicorn.run(
        "api:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    ) 