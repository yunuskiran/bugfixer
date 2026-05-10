"""CorrelationEnricher — extracts trace/correlation IDs from logs and re-queries connectors."""
from __future__ import annotations

import asyncio
import logging
import re
from typing import TYPE_CHECKING

from .base import BaseEnricher, Enrichment

if TYPE_CHECKING:
    from ..agent.core import AnalysisResult
    from ..connectors.base import BaseLogConnector

logger = logging.getLogger(__name__)

# Patterns for common ID types, in priority order
_ID_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("trace_id", re.compile(
        r'(?:trace[_-]?id|traceId|traceid|x-trace-id)["\s:=]+([a-f0-9\-]{8,64})',
        re.IGNORECASE,
    )),
    ("correlation_id", re.compile(
        r'(?:correlation[_-]?id|correlationId|correlationid)["\s:=]+([a-f0-9\-]{8,64})',
        re.IGNORECASE,
    )),
    ("request_id", re.compile(
        r'(?:request[_-]?id|requestId|req[_-]?id)["\s:=]+([a-f0-9\-]{8,64})',
        re.IGNORECASE,
    )),
    ("span_id", re.compile(
        r'(?:span[_-]?id|spanId)["\s:=]+([a-f0-9\-]{8,64})',
        re.IGNORECASE,
    )),
]


class CorrelationEnricher(BaseEnricher, plugin_name="correlation"):
    """
    Extracts distributed trace / correlation IDs from log entries,
    then re-queries all connectors with those IDs to stitch together
    the full distributed trace picture across services.
    """

    async def enrich(
        self,
        result: "AnalysisResult",
        question: str,
        connectors: list["BaseLogConnector"],
    ) -> Enrichment:
        found_ids: dict[str, set[str]] = {key: set() for key, _ in _ID_PATTERNS}

        for entry in result.log_entries:
            text = entry.message + " " + str(entry.properties)
            for key, pattern in _ID_PATTERNS:
                for m in pattern.finditer(text):
                    found_ids[key].add(m.group(1))

        all_ids = {v for values in found_ids.values() for v in values}
        if not all_ids:
            return Enrichment(
                name="correlation",
                data={"found_ids": {}},
                summary="No correlation or trace IDs found in log entries.",
            )

        # Re-query connectors with up to 3 IDs (avoid hammering APIs)
        sampled_ids = list(all_ids)[:3]

        async def _fetch(connector: "BaseLogConnector", trace_id: str) -> list:
            try:
                return await connector.search(trace_id, limit=20)
            except Exception:
                return []

        tasks = [_fetch(c, tid) for c in connectors for tid in sampled_ids]
        gathered = await asyncio.gather(*tasks, return_exceptions=False)

        seen_messages: set[str] = {e.message for e in result.log_entries}
        extra_entries: list[dict] = []
        for entries in gathered:
            for e in entries:
                if e.message not in seen_messages:
                    seen_messages.add(e.message)
                    extra_entries.append({
                        "timestamp": e.timestamp.isoformat(),
                        "level": e.level,
                        "message": e.message,
                        "source": e.source,
                    })

        summary = (
            f"Found {len(all_ids)} correlation/trace ID(s): "
            f"{', '.join(list(all_ids)[:5])}. "
            f"Re-queried connectors and found {len(extra_entries)} additional "
            f"log entries linked to these IDs."
        )

        return Enrichment(
            name="correlation",
            data={
                "found_ids": {k: list(v) for k, v in found_ids.items() if v},
                "extra_entries": extra_entries[:20],
            },
            summary=summary,
        )
