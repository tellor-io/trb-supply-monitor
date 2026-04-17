"""
Block size anomaly detector.

Uses a rolling z-score approach to flag blocks whose size, tx_count, or
num_events deviate significantly from recent history.  Ported from the
compare-block-sizes project analyzer.
"""

from dataclasses import dataclass
from typing import List, TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from .database import BalancesDatabase

METRICS = ("block_size_bytes", "tx_count", "num_events")
MIN_WINDOW = 50  # require at least this many baseline rows before alerting


@dataclass
class Anomaly:
    metric: str
    height: int
    value: float
    zscore: float
    mean: float
    std: float


def _zscore(values: np.ndarray, current: float) -> float:
    std = float(np.std(values))
    if std == 0:
        return 0.0
    return (current - float(np.mean(values))) / std


def check_anomaly(
    db: "BalancesDatabase",
    height: int,
    window: int = 100,
    threshold: float = 3.0,
) -> List[Anomaly]:
    """
    Check whether the block at *height* is anomalous relative to the previous
    *window* blocks.

    Returns an empty list when there is not yet enough history (< MIN_WINDOW
    baseline rows) or when no metric exceeds *threshold* standard deviations.
    """
    rows = db.get_recent_block_sizes(window + 1)
    if len(rows) < MIN_WINDOW + 1:
        return []

    current_row = next((r for r in rows if r["height"] == height), None)
    if current_row is None:
        return []

    baseline_rows = [r for r in rows if r["height"] != height]
    if len(baseline_rows) < MIN_WINDOW:
        return []

    anomalies: List[Anomaly] = []
    for metric in METRICS:
        baseline = np.array([float(r[metric]) for r in baseline_rows])
        current_val = float(current_row[metric])
        z = _zscore(baseline, current_val)
        if abs(z) > threshold:
            anomalies.append(
                Anomaly(
                    metric=metric,
                    height=height,
                    value=current_val,
                    zscore=z,
                    mean=float(np.mean(baseline)),
                    std=float(np.std(baseline)),
                )
            )
    return anomalies
