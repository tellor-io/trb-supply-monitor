import sys
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.tellor_supply_analytics.get_active_balances import EnhancedActiveBalancesCollector

def test_get_bridge_balance():
    # Create an instance of the collector
    collector = EnhancedActiveBalancesCollector()
    
    layer_height = 8557454
    balance = collector.get_bridge_balance(layer_height)
    
    assert balance is not None
    assert balance > 0
    assert balance < 1999999999000000000000000000
    print(f"Bridge balance at height {layer_height}: {balance}")

if __name__ == "__main__":
    test_get_bridge_balance()