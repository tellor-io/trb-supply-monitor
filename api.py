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
from src.tellor_supply_analytics.get_active_balances_enhanced import EnhancedActiveBalancesCollector

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


@app.get("/api/status")
async def get_api_status():
    """Get API and database status."""
    try:
        latest = db.get_latest_snapshot()
        return {
            "status": "healthy",
            "database_connected": True,
            "latest_collection": latest.get('run_time') if latest else None,
            "total_addresses": latest.get('total_addresses', 0) if latest else 0
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