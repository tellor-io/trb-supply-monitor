"""
Discord alerter for block size anomalies.

Sends a webhook message when an anomaly is detected, subject to a per-metric
cooldown period.  Ported from the compare-block-sizes project alerter.
"""

import logging
from datetime import datetime, timezone
from typing import List, TYPE_CHECKING

import httpx

from .block_size_analyzer import Anomaly

if TYPE_CHECKING:
    from .database import BalancesDatabase

logger = logging.getLogger(__name__)


def _now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


def _is_on_cooldown(db: "BalancesDatabase", metric: str, cooldown_seconds: int) -> bool:
    last = db.get_last_block_size_alert_time(metric)
    if last is None:
        return False
    try:
        last_dt = datetime.fromisoformat(last.replace("Z", "+00:00"))
    except ValueError:
        return False
    return (_now_utc() - last_dt).total_seconds() < cooldown_seconds


def _build_message(anomaly: Anomaly) -> str:
    direction = "above" if anomaly.zscore > 0 else "below"
    expected_low = anomaly.mean - 2 * anomaly.std
    expected_high = anomaly.mean + 2 * anomaly.std
    return (
        f"**Block Size Alert** — `{anomaly.metric}`\n"
        f"Block: `{anomaly.height}`\n"
        f"Value: `{anomaly.value:,.0f}` ({direction} normal)\n"
        f"Expected range: `{expected_low:,.0f}` – `{expected_high:,.0f}`\n"
        f"Z-score: `{anomaly.zscore:+.2f}`"
    )


async def send_discord_alert(webhook_url: str, message: str) -> None:
    payload = {"content": message}
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(webhook_url, json=payload)
        resp.raise_for_status()


async def process_anomalies(
    db: "BalancesDatabase",
    webhook_url: str,
    anomalies: List[Anomaly],
    cooldown_seconds: int,
) -> None:
    """
    For each anomaly: skip if on cooldown, send Discord alert (if webhook
    configured), and record the alert in the database.
    """
    for anomaly in anomalies:
        if _is_on_cooldown(db, anomaly.metric, cooldown_seconds):
            logger.debug(
                "Alert for %s suppressed (cooldown active)", anomaly.metric
            )
            continue

        message = _build_message(anomaly)
        sent_at = _now_utc().isoformat()

        if webhook_url:
            try:
                await send_discord_alert(webhook_url, message)
                logger.info("Discord alert sent for metric=%s height=%d", anomaly.metric, anomaly.height)
            except Exception as exc:
                logger.warning("Failed to send Discord alert: %s", exc)

        db.insert_block_size_alert(
            sent_at=sent_at,
            metric=anomaly.metric,
            height=anomaly.height,
            value=anomaly.value,
            zscore=anomaly.zscore,
            message=message,
        )
