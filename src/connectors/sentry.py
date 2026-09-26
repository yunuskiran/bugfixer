"""Sentry connector — surfaces past Sentry issues as log entries."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

from .base import BaseLogConnector, LogEntry

logger = logging.getLogger(__name__)

_SENTRY_BASE = "https://sentry.io/api/0"


class SentryConnector(BaseLogConnector, plugin_name="sentry"):
    """Search Sentry issues that match a query string."""

    def __init__(self, auth_token: str, org: str, project: str) -> None:
        self._org = org
        self._project = project
        self._headers = {
            "Authorization": f"Bearer {auth_token}",
            "Content-Type": "application/json",
        }

    @property
    def name(self) -> str:
        return "Sentry"

    async def search(self, query: str, limit: int = 50) -> list[LogEntry]:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    f"{_SENTRY_BASE}/projects/{self._org}/{self._project}/issues/",
                    headers=self._headers,
                    params={"query": query, "limit": min(limit, 100)},
                )
                resp.raise_for_status()
                issues = resp.json()
        except Exception as exc:
            logger.warning("Sentry connector failed: %s", exc)
            return []

        entries: list[LogEntry] = []
        for issue in issues[:limit]:
            try:
                ts_raw = issue.get("firstSeen") or issue.get("lastSeen") or ""
                ts = (
                    datetime.fromisoformat(ts_raw.rstrip("Z")).replace(
                        tzinfo=timezone.utc
                    )
                    if ts_raw
                    else datetime.now(timezone.utc)
                )
            except ValueError:
                ts = datetime.now(timezone.utc)

            level = (issue.get("level") or "error").upper()
            title = issue.get("title") or issue.get("culprit") or "Unknown"
            count = issue.get("count", "?")
            entries.append(
                LogEntry(
                    timestamp=ts,
                    level=level,
                    message=f"{title} (occurrences: {count})",
                    source="Sentry",
                    properties={
                        "issue_id": issue.get("id"),
                        "culprit": issue.get("culprit"),
                        "permalink": issue.get("permalink"),
                        "status": issue.get("status"),
                        "project": self._project,
                    },
                )
            )

        return entries
