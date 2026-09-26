"""Linear tracker — searches issues via Linear's GraphQL API."""
from __future__ import annotations

import logging

import httpx

from .base import BaseTracker, WorkItem

logger = logging.getLogger(__name__)

_LINEAR_API = "https://api.linear.app/graphql"

_SEARCH_QUERY = """
query SearchIssues($query: String!) {
  issueSearch(query: $query, first: 5) {
    nodes {
      identifier
      title
      state { name }
      url
    }
  }
}
"""


class LinearTracker(BaseTracker, plugin_name="linear"):
    """Search Linear issues using the GraphQL API."""

    def __init__(self, api_key: str) -> None:
        self._headers = {
            "Authorization": api_key,
            "Content-Type": "application/json",
        }

    async def search(self, query: str) -> list[WorkItem]:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    _LINEAR_API,
                    headers=self._headers,
                    json={"query": _SEARCH_QUERY, "variables": {"query": query}},
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            logger.warning("Linear tracker failed: %s", exc)
            return []

        items: list[WorkItem] = []
        for node in (
            data.get("data", {}).get("issueSearch", {}).get("nodes", [])
        ):
            items.append(
                WorkItem(
                    id=node.get("identifier", "?"),
                    title=node.get("title", ""),
                    url=node.get("url", ""),
                    status=node.get("state", {}).get("name", "Unknown"),
                    item_type="Issue",
                )
            )

        return items
