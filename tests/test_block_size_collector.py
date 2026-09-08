import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.tellor_supply_analytics.block_size_collector import parse_block_results


class ParseBlockResultsTests(unittest.TestCase):
    def test_sums_gas_and_events_from_txs_results(self):
        payload = {
            "jsonrpc": "2.0",
            "result": {
                "txs_results": [
                    {"gas_used": "0", "events": [], "log": "tx parse error"},
                    {"gas_used": "142186", "events": [{"type": "message"}, {"type": "tx"}]},
                    {"gas_used": 144998, "events": [{"type": "message"}]},
                ]
            },
        }

        parsed = parse_block_results(payload)

        self.assertEqual(parsed["gas_used"], 287184)
        self.assertEqual(parsed["num_events"], 3)

    def test_empty_block_returns_zeros(self):
        parsed = parse_block_results({"jsonrpc": "2.0", "result": {"txs_results": None}})

        self.assertEqual(parsed, {"gas_used": 0, "num_events": 0})

    def test_jsonrpc_error_returns_zeros(self):
        parsed = parse_block_results(
            {"jsonrpc": "2.0", "error": {"code": -32603, "message": "Internal error"}}
        )

        self.assertEqual(parsed, {"gas_used": 0, "num_events": 0})


if __name__ == "__main__":
    unittest.main()
