"""Datadog connector — searches logs via the Datadog Logs v2 API."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import httpx

from .base import BaseLogConnector, LogEntry

logger = logging.getLogger(__name__)


class DatadogConnector(BaseLogConnector, plugin_name="datadog"):
    """Search Datadog Logs using the v2 Logs Search API."""

    def __init__(
        self,
        api_key: str,
        app_key: str,
        site: str = "datadoghq.com",
    ) -> None:
        self._base_url = f"https://api.{site}/api/v2/logs/events/search"
        self._headers = {
            "DD-API-KEY": api_key,
            "DD-APPLICATION-KEY": app_key,
            "Content-Type": "application/json",
        }

    @property
    def name(self) -> str:
        return "Datadog"

    async def search(self, query: str, limit: int = 50) -> list[LogEntry]:
        now = datetime.now(timezone.utc)
        start = now - timedelta(hours=24)

        body = {
            "filter": {
                "query": query,
                "from": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "to": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
            "sort": "-timestamp",
            "page": {"limit": min(limit, 1000)},
        }

        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.post(
                    self._base_url, headers=self._headers, json=body
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            logger.warning("Datadog connector failed: %s", exc)
            return []

        entries: list[LogEntry] = []
        for log in data.get("data", [])[:limit]:
            attrs = log.get("attributes", {})
            try:
                ts = datetime.fromisoformat(
                    attrs.get("timestamp", "").rstrip("Z")
                ).replace(tzinfo=timezone.utc)
            except (ValueError, AttributeError):
                ts = datetime.now(timezone.utc)

            level = (attrs.get("status") or attrs.get("level") or "info").upper()
            message = attrs.get("message") or attrs.get("content") or str(attrs)
            service = attrs.get("service") or attrs.get("source") or "datadog"

            entries.append(
                LogEntry(
                    timestamp=ts,
                    level=level,
                    message=message,
                    source=f"Datadog/{service}",
                    properties={
                        k: v
                        for k, v in attrs.items()
                        if k not in {"message", "timestamp", "status"}
                    },
                )
            )

        return entries
