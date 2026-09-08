"""
Tellor Layer block size collector.

Fetches per-block metrics from the Tellor Layer REST API and CometBFT RPC,
then stores them in the layer_block_sizes table via BalancesDatabase.
Logic ported from the compare-block-sizes project.
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


def parse_block_results(payload: dict) -> dict:
    """Sum gas_used and event counts from a CometBFT block_results JSON body."""
    if payload.get("error"):
        return {"gas_used": 0, "num_events": 0}

    result = payload.get("result") or {}
    txs_results = result.get("txs_results") or []
    gas_used = 0
    num_events = 0
    for tx_result in txs_results:
        gas_used += int(tx_result.get("gas_used") or 0)
        num_events += len(tx_result.get("events") or [])
    return {"gas_used": gas_used, "num_events": num_events}


async def get_block_results(rpc_url: str, height: int) -> dict:
    """
    Fetch gas_used and event count from CometBFT `/block_results`.

    This avoids `/cosmos/tx/v1beta1/txs/block/{height}` (GetBlockWithTxs),
    which protobuf-decodes every tx and logs
    `failed to decode tx ... module=baseapp` on the node.

    Returns zeros when the height is missing or the node returns an empty
    result — some nodes error instead of returning an empty tx list.
    """
    url = f"{rpc_url.rstrip('/')}/block_results?height={height}"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url)
        if resp.status_code in (500, 400, 404):
            return {"gas_used": 0, "num_events": 0}
        resp.raise_for_status()
        return parse_block_results(resp.json())


async def fetch_block_metrics(api_url: str, rpc_url: str, height: int) -> BlockMetrics:
    """
    Fetch block body and results concurrently and return a BlockMetrics object.

    Raises BlockNotAvailable if the block cannot be fetched.
    """
    block_task = asyncio.create_task(get_block(api_url, height))
    results_task = asyncio.create_task(get_block_results(rpc_url, height))
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
