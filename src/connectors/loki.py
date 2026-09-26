"""Grafana Loki connector — queries logs via the Loki HTTP API (LogQL)."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import httpx

from .base import BaseLogConnector, LogEntry

logger = logging.getLogger(__name__)


class LokiConnector(BaseLogConnector, plugin_name="loki"):
    """Query Grafana Loki using LogQL over the HTTP query range API."""

    def __init__(
        self,
        url: str,
        user: str | None = None,
        password: str | None = None,
    ) -> None:
        self._url = url.rstrip("/")
        self._auth = (user, password) if user and password else None

    @property
    def name(self) -> str:
        return "Loki"

    async def search(self, query: str, limit: int = 50) -> list[LogEntry]:
        # Match any stream that contains the query string
        logql = f'{{job=~".+"}} |= `{query}`'
        now = datetime.now(timezone.utc)
        start = now - timedelta(hours=24)

        params = {
            "query": logql,
            "limit": str(limit),
            # Loki expects nanosecond timestamps as strings
            "start": str(int(start.timestamp() * 1_000_000_000)),
            "end": str(int(now.timestamp() * 1_000_000_000)),
            "direction": "backward",
        }

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                kwargs: dict = {"params": params}
                if self._auth:
                    kwargs["auth"] = self._auth
                response = await client.get(
                    f"{self._url}/loki/api/v1/query_range", **kwargs
                )
                response.raise_for_status()
                data = response.json()
        except Exception as exc:
            logger.warning("Loki connector failed: %s", exc)
            return []

        entries: list[LogEntry] = []
        for stream in data.get("data", {}).get("result", []):
            labels = stream.get("stream", {})
            source_label = (
                labels.get("job")
                or labels.get("app")
                or labels.get("service")
                or "loki"
            )
            for ts_ns, line in stream.get("values", []):
                try:
                    ts = datetime.fromtimestamp(
                        int(ts_ns) / 1_000_000_000, tz=timezone.utc
                    )
                except (ValueError, OverflowError):
                    ts = datetime.now(timezone.utc)

                entries.append(
                    LogEntry(
                        timestamp=ts,
                        level="INFO",
                        message=line,
                        source=f"Loki/{source_label}",
                        properties=dict(labels),
                    )
                )
                if len(entries) >= limit:
                    return entries

        return entries
