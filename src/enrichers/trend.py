"""TrendEnricher — detects error frequency spikes across time windows."""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from .base import BaseEnricher, Enrichment

if TYPE_CHECKING:
    from ..agent.core import AnalysisResult
    from ..connectors.base import BaseLogConnector

logger = logging.getLogger(__name__)

_WINDOWS: dict[str, timedelta] = {
    "15min": timedelta(minutes=15),
    "1h": timedelta(hours=1),
    "24h": timedelta(hours=24),
}


class TrendEnricher(BaseEnricher, plugin_name="trend"):
    """
    Counts how many times the same error appeared in 15min / 1h / 24h windows
    and detects frequency spikes so the team knows whether an issue just started
    or has been slowly growing worse.
    """

    async def enrich(
        self,
        result: "AnalysisResult",
        question: str,
        connectors: list["BaseLogConnector"],
    ) -> Enrichment:
        if not result.log_entries:
            return Enrichment(
                name="trend",
                data={},
                summary="No log entries to analyse for trends.",
            )

        search_term = _extract_error_keyword(result.root_cause, question)
        now = datetime.now(timezone.utc)

        # Count existing entries per window
        window_counts: dict[str, int] = {}
        for label, delta in _WINDOWS.items():
            cutoff = now - delta
            window_counts[label] = sum(
                1 for e in result.log_entries if e.timestamp >= cutoff
            )

        # Best-effort fresh count from connectors (larger window, more data)
        async def _count(connector: "BaseLogConnector") -> int:
            try:
                entries = await connector.search(search_term, limit=500)
                return len(entries)
            except Exception:
                return 0

        raw_counts = await asyncio.gather(*[_count(c) for c in connectors])
        total_from_sources = sum(raw_counts)

        count_15 = window_counts.get("15min", 0)
        count_24 = window_counts.get("24h", 0)
        spike_pct = round((count_15 / count_24 * 100) if count_24 > 0 else 0, 1)
        is_spiking = spike_pct > 20 and count_15 > 2

        parts = [
            f"Error frequency — last 15min: {count_15}, "
            f"last 1h: {window_counts.get('1h', 0)}, "
            f"last 24h: {count_24}."
        ]
        if total_from_sources > 0:
            parts.append(f"Total matches across log sources: {total_from_sources}.")
        if is_spiking:
            parts.append(
                f"⚠️ SPIKE DETECTED: {spike_pct}% of 24h occurrences happened "
                f"in the last 15 minutes."
            )
        else:
            parts.append("No unusual frequency spike detected.")

        return Enrichment(
            name="trend",
            data={
                "windows": window_counts,
                "total_from_sources": total_from_sources,
                "search_term": search_term,
                "is_spiking": is_spiking,
                "spike_pct": spike_pct,
            },
            summary=" ".join(parts),
        )


def _extract_error_keyword(root_cause: str, question: str) -> str:
    """Pull the most specific error keyword from the root cause text."""
    # Prefer a quoted phrase
    m = re.search(r'"([^"]{4,40})"', root_cause)
    if m:
        return m.group(1)
    # Common exception/error class names
    m = re.search(
        r"\b([A-Z][a-z]+(?:[A-Z][a-z]+)+(?:Exception|Error|Fault|Timeout))\b",
        root_cause,
    )
    if m:
        return m.group(1)
    # Fall back to first few words of the question
    words = question.split()
    return " ".join(words[:4]) if words else "error"
