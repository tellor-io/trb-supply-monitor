"""
Tellor Layer block size collector.

Fetches per-block metrics from the Tellor Layer REST API and stores them in
the layer_block_sizes table via BalancesDatabase.  Logic ported from the
compare-block-sizes project.
"""

import asyncio
import json
import logging
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)


class BlockNotAvailable(Exception):
    """Raised when a requested block height is not yet available on the node."""


@dataclass
class BlockMetrics:
    height: int
    timestamp: str
    block_size_bytes: int
    tx_count: int
    gas_used: int
    num_events: int


async def get_latest_height(api_url: str) -> int:
    """Return the current head block height from the REST API."""
    url = f"{api_url}/cosmos/base/tendermint/v1beta1/blocks/latest"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()
    return int(data["block"]["header"]["height"])


async def get_block(api_url: str, height: int) -> dict:
    """
    Fetch block body and compute block_size_bytes.

    Size is approximated as the sum of decoded byte lengths of base64-encoded
    transactions.  When there are no transactions we fall back to the UTF-8
    byte length of the serialised block JSON, which gives a reasonable lower
    bound.
    """
    url = f"{api_url}/cosmos/base/tendermint/v1beta1/blocks/{height}"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url)
        if resp.status_code in (400, 404):
            raise BlockNotAvailable(f"height {height} unavailable ({resp.status_code})")
        resp.raise_for_status()
        data = resp.json()

    header = data["block"]["header"]
    txs = data["block"].get("data", {}).get("txs") or []
    tx_count = len(txs)

    raw_bytes = sum(len(tx) * 3 // 4 for tx in txs)
    block_size_bytes = raw_bytes if raw_bytes > 0 else len(json.dumps(data["block"]).encode())

    return {
        "timestamp": header["time"],
        "block_size_bytes": block_size_bytes,
        "tx_count": tx_count,
    }


async def get_block_results(api_url: str, height: int) -> dict:
    """
    Fetch gas_used and event count from the transaction search endpoint.

    Returns zeros for empty blocks — some nodes return 500 instead of an
    empty list when a block contains no transactions.
    """
    url = f"{api_url}/cosmos/tx/v1beta1/txs/block/{height}"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url)
        if resp.status_code in (500, 400, 404):
            return {"gas_used": 0, "num_events": 0}
        resp.raise_for_status()
        data = resp.json()

    gas_used = 0
    num_events = 0
    for tx_response in data.get("tx_responses") or []:
        gas_used += int(tx_response.get("gas_used", 0))
        num_events += len(tx_response.get("events") or [])

    return {"gas_used": gas_used, "num_events": num_events}


async def fetch_block_metrics(api_url: str, height: int) -> BlockMetrics:
    """
    Fetch block body and results concurrently and return a BlockMetrics object.

    Raises BlockNotAvailable if the block cannot be fetched.
    """
    block_task = asyncio.create_task(get_block(api_url, height))
    results_task = asyncio.create_task(get_block_results(api_url, height))
    block_data = await block_task
    results_data = await results_task
    return BlockMetrics(
        height=height,
        timestamp=block_data["timestamp"],
        block_size_bytes=block_data["block_size_bytes"],
        tx_count=block_data["tx_count"],
        gas_used=results_data["gas_used"],
        num_events=results_data["num_events"],
    )
