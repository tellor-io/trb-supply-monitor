#!/usr/bin/env python3
"""
FastAPI Backend for Tellor Layer Active Balances Dashboard

This API provides endpoints for accessing balance data stored in SQLite database.
"""

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.templating import Jinja2Templates
from typing import List, Dict, Optional
import logging
import requests
import subprocess
import json
import sys
import os
from datetime import datetime
from pathlib import Path
from web3 import Web3

# Local imports
from src.tellor_supply_analytics.database import BalancesDatabase
from src.tellor_supply_analytics.get_active_balances import EnhancedActiveBalancesCollector

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration from environment
TELLOR_LAYER_RPC_URL = os.getenv('TELLOR_LAYER_RPC_URL')
LAYER_GRPC_URL = os.getenv('LAYER_GRPC_URL')
ETHEREUM_RPC_URL = os.getenv('ETHEREUM_RPC_URL')

def check_tellor_layer_rpc() -> bool:
    """
    Check if Tellor Layer RPC is responding.
    
    Returns:
        True if RPC is responding, False otherwise
    """
    try:
        logger.info(f"Checking Tellor Layer RPC connection: {TELLOR_LAYER_RPC_URL}")
        
        # Try using layerd status command if available
        try:
            result = subprocess.run(
                ['./layerd', 'status', '--output', 'json', '--node', TELLOR_LAYER_RPC_URL],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                status_data = json.loads(result.stdout)
                latest_height = status_data.get('sync_info', {}).get('latest_block_height')
                if latest_height:
                    logger.info(f"Tellor Layer RPC responding - Latest block height: {latest_height}")
                    return True
            else:
                logger.warning(f"layerd status command failed: {result.stderr}")
        except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError) as e:
            logger.warning(f"layerd command failed, trying direct RPC call: {e}")
        
        # Fallback: Try direct RPC call
        response = requests.post(
            TELLOR_LAYER_RPC_URL,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "status",
                "params": []
            },
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            if 'result' in data:
                sync_info = data['result'].get('sync_info', {})
                latest_height = sync_info.get('latest_block_height')
                if latest_height:
                    logger.info(f"Tellor Layer RPC responding - Latest block height: {latest_height}")
                    return True
        
        logger.error(f"Tellor Layer RPC not responding properly. Status: {response.status_code}")
        return False
        
    except requests.RequestException as e:
        logger.error(f"Failed to connect to Tellor Layer RPC: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error checking Tellor Layer RPC: {e}")
        return False

def check_ethereum_rpc() -> bool:
    """
    Check if Ethereum RPC is responding.
    
    Returns:
        True if RPC is responding, False otherwise
    """
    try:
        logger.info(f"Checking Ethereum RPC connection: {ETHEREUM_RPC_URL}")
        
        w3 = Web3(Web3.HTTPProvider(ETHEREUM_RPC_URL))
        
        if not w3.is_connected():
            logger.error("Ethereum RPC connection failed")
            return False
        
        # Try to get the latest block
        latest_block = w3.eth.get_block('latest')
        block_number = latest_block.get('number')
        
        if block_number:
            logger.info(f"Ethereum RPC responding - Latest block number: {block_number}")
            return True
        else:
            logger.error("Ethereum RPC responded but could not get block number")
            return False
            
    except Exception as e:
        logger.error(f"Failed to connect to Ethereum RPC: {e}")
        return False

def check_tellor_layer_grpc() -> bool:
    """
    Check if Tellor Layer GRPC endpoint is responding.
    
    Returns:
        True if GRPC is responding, False otherwise
    """
    try:
        logger.info(f"Checking Tellor Layer GRPC connection: {LAYER_GRPC_URL}")
        
        # Try to get node info from GRPC endpoint
        response = requests.get(
            f"{LAYER_GRPC_URL.rstrip('/')}/cosmos/base/tendermint/v1beta1/node_info",
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            node_info = data.get('default_node_info', {})
            if node_info:
                network = node_info.get('network', 'unknown')
                version = node_info.get('version', 'unknown')
                logger.info(f"Tellor Layer GRPC responding - Network: {network}, Version: {version}")
                return True
        
        logger.error(f"Tellor Layer GRPC not responding properly. Status: {response.status_code}")
        return False
        
    except requests.RequestException as e:
        logger.error(f"Failed to connect to Tellor Layer GRPC: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error checking Tellor Layer GRPC: {e}")
        return False

def perform_startup_health_checks():
    """
    Perform all RPC health checks during startup.
    Exit the program if any critical RPC is not responding.
    """
    logger.info("=== STARTING RPC HEALTH CHECKS ===")
    
    checks_passed = 0
    total_checks = 3
    
    # Check Tellor Layer RPC (critical)
    if check_tellor_layer_rpc():
        checks_passed += 1
    else:
        logger.error("❌ CRITICAL: Tellor Layer RPC is not responding!")
        logger.error(f"   URL: {TELLOR_LAYER_RPC_URL}")
        logger.error("   This RPC is required for blockchain queries.")
        sys.exit(1)
    
    # Check Ethereum RPC (critical)
    if check_ethereum_rpc():
        checks_passed += 1
    else:
        logger.error("❌ CRITICAL: Ethereum RPC is not responding!")
        logger.error(f"   URL: {ETHEREUM_RPC_URL}")
        logger.error("   This RPC is required for bridge balance queries.")
        sys.exit(1)
    
    # Check Tellor Layer GRPC (non-critical but important)
    if check_tellor_layer_grpc():
        checks_passed += 1
    else:
        logger.warning("⚠️  WARNING: Tellor Layer GRPC is not responding")
        logger.warning(f"   URL: {LAYER_GRPC_URL}")
        logger.warning("   Some balance collection features may not work properly.")
    
    logger.info(f"=== HEALTH CHECKS COMPLETED: {checks_passed}/{total_checks} PASSED ===")
    if checks_passed >= 2:  # At least RPC endpoints working
        logger.info("✅ Minimum required RPCs are responding. Starting API server...")
    else:
        logger.error("❌ CRITICAL: Insufficient RPC endpoints responding. Exiting...")
        sys.exit(1)

# Initialize FastAPI app
app = FastAPI(
    title="Tellor Layer Balance Analytics API",
    description="API for accessing Tellor Layer active balance data",
    version="1.0.0"
)

@app.on_event("startup")
async def startup_event():
    """Run startup health checks when the API starts."""
    perform_startup_health_checks()

# Initialize database
db = BalancesDatabase()

# Initialize Jinja2 templates
templates = Jinja2Templates(directory="templates")

# Mount static files (CSS, JS)
app.mount("/static", StaticFiles(directory="static"), name="static")


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
                "eth_timestamp": snapshot.get('eth_block_timestamp'),
                "eth_datetime": snapshot.get('eth_block_datetime'),
                "eth_block_number": snapshot.get('eth_block_number'),
                "layer_block_height": snapshot.get('layer_block_height', 0),
                "bridge_balance_trb": snapshot.get('bridge_balance_trb'),
                "layer_total_supply_trb": snapshot.get('layer_total_supply_trb'),
                "not_bonded_tokens": snapshot.get('not_bonded_tokens'),
                "bonded_tokens": snapshot.get('bonded_tokens'),
                "total_reporter_power": snapshot.get('total_reporter_power', 0),
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
        
        # If no data at all, return 404
        raise HTTPException(status_code=404, detail="No balance data found")
    except HTTPException:
        raise
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


@app.get("/api/unified/layer-blocks")
async def get_layer_blocks_in_database(
    limit: int = Query(100, description="Number of layer blocks to return", ge=1, le=500)
):
    """Get list of Tellor Layer blocks that have data in the database."""
    try:
        from src.tellor_supply_analytics.unified_collector import UnifiedDataCollector
        
        collector = UnifiedDataCollector()
        layer_blocks = collector.list_layer_blocks_in_database(limit=limit)
        
        return {
            "layer_blocks": layer_blocks,
            "count": len(layer_blocks),
            "limit": limit
        }
        
    except Exception as e:
        logger.error(f"Error getting layer blocks: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.delete("/api/unified/layer-block/{layer_block_height}")
async def remove_layer_block_data(layer_block_height: int):
    """Remove all data for a specific Tellor Layer block height."""
    try:
        from src.tellor_supply_analytics.unified_collector import UnifiedDataCollector
        
        collector = UnifiedDataCollector()
        success = collector.remove_data_by_layer_block(layer_block_height)
        
        if success:
            return {
                "status": "success",
                "message": f"Successfully removed data for Tellor Layer block {layer_block_height}",
                "layer_block_height": layer_block_height
            }
        else:
            raise HTTPException(
                status_code=404, 
                detail=f"No data found for Tellor Layer block {layer_block_height}"
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error removing data for layer block {layer_block_height}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/api/unified/layer-block/{layer_block_height}/rerun")
async def rerun_layer_block_collection(layer_block_height: int):
    """Re-collect data for a specific Tellor Layer block height."""
    try:
        from src.tellor_supply_analytics.unified_collector import UnifiedDataCollector
        
        collector = UnifiedDataCollector()
        success = collector.rerun_collection_for_layer_block(layer_block_height)
        
        if success:
            return {
                "status": "success",
                "message": f"Successfully re-collected data for Tellor Layer block {layer_block_height}",
                "layer_block_height": layer_block_height
            }
        else:
            raise HTTPException(
                status_code=500, 
                detail=f"Failed to re-collect data for Tellor Layer block {layer_block_height}"
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error re-collecting data for layer block {layer_block_height}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/api/unified/layer-block/{layer_block_height}/remove-and-rerun")
async def remove_and_rerun_layer_block(layer_block_height: int):
    """Remove existing data and re-collect for a specific Tellor Layer block height."""
    try:
        from src.tellor_supply_analytics.unified_collector import UnifiedDataCollector
        
        collector = UnifiedDataCollector()
        success = collector.remove_and_rerun_layer_block(layer_block_height)
        
        if success:
            return {
                "status": "success",
                "message": f"Successfully removed and re-collected data for Tellor Layer block {layer_block_height}",
                "layer_block_height": layer_block_height
            }
        else:
            raise HTTPException(
                status_code=500, 
                detail=f"Failed to remove and re-collect data for Tellor Layer block {layer_block_height}"
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error removing and re-collecting data for layer block {layer_block_height}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


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
    import argparse
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Tellor Layer Balance Analytics API')
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
        default='',
        help='Root path for the application when served behind a proxy (e.g., /supply)'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug logging and reload'
    )
    
    args = parser.parse_args()
    
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Create directories if they don't exist
    Path("templates").mkdir(exist_ok=True)
    Path("static/css").mkdir(parents=True, exist_ok=True)
    Path("static/js").mkdir(parents=True, exist_ok=True)
    
    # Perform health checks before starting the API server
    perform_startup_health_checks()
    
    logger.info("Starting Tellor Balance Analytics API")
    uvicorn.run(
        "api:app",
        host=args.host,
        port=args.port,
        reload=args.debug,
        log_level="debug" if args.debug else "info",
        root_path=args.root_path
    ) 