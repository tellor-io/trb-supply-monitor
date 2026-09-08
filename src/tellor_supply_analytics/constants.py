"""
Shared constants and helpers for Tellor Supply Analytics.

Single source of truth for contract addresses, token decimals, ABI definitions,
and bridge contract selection logic used across all modules.
"""

import os
import logging
from typing import Optional

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv() -> bool:
        return True

load_dotenv()

logger = logging.getLogger(__name__)

# Token decimal constants
TRB_DECIMALS = 18          # ERC20 TRB uses 18 decimals (wei)
LOYA_DECIMALS = 6           # Tellor Layer loya uses 6 decimals
TRB_WEI_FACTOR = 10 ** TRB_DECIMALS
LOYA_TO_TRB_FACTOR = 10 ** LOYA_DECIMALS

# Network timeout
REQUEST_TIMEOUT = 30

# User-Agent for HTTP requests
USER_AGENT = "Tellor-Supply-Analytics/1.0"

# Tellor Layer Configuration
TELLOR_LAYER_RPC_URL = os.getenv("TELLOR_LAYER_RPC_URL")
LAYER_API_URL = os.getenv("LAYER_API_URL")

# Ethereum Configuration
ETHEREUM_RPC_URL = os.getenv("ETHEREUM_RPC_URL", "https://rpc.sepolia.org")

# Contract Addresses
TRB_CONTRACT = os.getenv("TRB_CONTRACT")
CURRENT_BRIDGE_CONTRACT = os.getenv("CURRENT_BRIDGE_CONTRACT")
OLD_BRIDGE_CONTRACT_1 = os.getenv("OLD_BRIDGE_CONTRACT_1")
BRIDGE_V2_CONTRACT = os.getenv("TRBBRIDGEV2_CONTRACT_ADDRESS")

# Bridge contract transition height on Tellor Layer
BRIDGE_CONTRACT_TRANSITION_HEIGHT = 9569214

# Discord alerts
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")

# Collection intervals
CURRENT_DATA_INTERVAL = int(os.getenv("CURRENT_DATA_INTERVAL", "300"))

# Bridge CSV configuration
BRIDGE_DEPOSITS_CSV_PATH = os.getenv("BRIDGE_DEPOSITS_CSV_PATH", "example_bridge_deposits.csv")
BRIDGE_WITHDRAWALS_CSV_PATH = os.getenv(
    "BRIDGE_WITHDRAWALS_CSV_PATH", "example_bridge_withdrawals.csv"
)

# ERC20 ABI for balanceOf function
ERC20_ABI = [
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function",
    }
]

# Completeness scoring: total fields tracked per unified snapshot
COMPLETENESS_TOTAL_FIELDS = 8


def get_current_layer_height() -> Optional[int]:
    """
    Get the current Tellor Layer block height via HTTP RPC.

    Prefers the HTTP /status endpoint (no binary dependency) and falls back
    to None if the RPC is unreachable.
    """
    import requests as _requests

    if not TELLOR_LAYER_RPC_URL:
        logger.error("TELLOR_LAYER_RPC_URL is not configured")
        return None

    try:
        url = f"{TELLOR_LAYER_RPC_URL.rstrip('/')}/status"
        response = _requests.get(url, timeout=REQUEST_TIMEOUT, headers={"User-Agent": USER_AGENT})
        response.raise_for_status()
        data = response.json()
        height = int(data["result"]["sync_info"]["latest_block_height"])
        logger.info(f"Current Tellor Layer height: {height}")
        return height
    except Exception as e:
        logger.error(f"Error getting current layer height via HTTP: {e}")
        return None


def get_bridge_contract_for_height(layer_height: Optional[int]) -> str:
    """
    Determine which bridge contract to use based on Tellor Layer height.

    Args:
        layer_height: Tellor Layer block height, or None to use current contract

    Returns:
        Bridge contract address to use
    """
    if layer_height is None or layer_height >= BRIDGE_CONTRACT_TRANSITION_HEIGHT:
        return CURRENT_BRIDGE_CONTRACT

    if OLD_BRIDGE_CONTRACT_1 and OLD_BRIDGE_CONTRACT_1.strip():
        return OLD_BRIDGE_CONTRACT_1

    logger.warning(
        f"OLD_BRIDGE_CONTRACT_1 not configured, using CURRENT_BRIDGE_CONTRACT "
        f"for layer height {layer_height}"
    )
    return CURRENT_BRIDGE_CONTRACT
