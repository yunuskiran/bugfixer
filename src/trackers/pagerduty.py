"""PagerDuty tracker — searches incidents via the PagerDuty REST API v2."""
from __future__ import annotations

import logging

import httpx

from .base import BaseTracker, WorkItem

logger = logging.getLogger(__name__)

_PD_BASE = "https://api.pagerduty.com"


class PagerDutyTracker(BaseTracker, plugin_name="pagerduty"):
    """Search PagerDuty incidents that match a query string."""

    def __init__(self, api_key: str) -> None:
        self._headers = {
            "Authorization": f"Token token={api_key}",
            "Accept": "application/vnd.pagerduty+json;version=2",
            "Content-Type": "application/json",
        }

    async def search(self, query: str) -> list[WorkItem]:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    f"{_PD_BASE}/incidents",
                    headers=self._headers,
                    params={
                        "query": query,
                        "limit": 5,
                        "statuses[]": ["triggered", "acknowledged", "resolved"],
                    },
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            logger.warning("PagerDuty tracker failed: %s", exc)
            return []

        items: list[WorkItem] = []
        for inc in data.get("incidents", []):
            items.append(
                WorkItem(
                    id=str(inc.get("incident_number", inc.get("id", "?"))),
                    title=inc.get("title") or inc.get("summary", "Unknown"),
                    url=inc.get("html_url") or inc.get("self", ""),
                    status=inc.get("status", "unknown"),
                    item_type="Incident",
                )
            )

        return items
