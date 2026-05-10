"""GitHub Issues tracker — searches issues across configured repos via GitHub REST API."""
from __future__ import annotations

import logging

import httpx

from .base import BaseTracker, WorkItem

logger = logging.getLogger(__name__)

_GH_BASE = "https://api.github.com"


class GitHubIssuesTracker(BaseTracker, plugin_name="github_issues"):
    """Search GitHub issues across a set of configured repositories."""

    def __init__(self, token: str, repos: list[str]) -> None:
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        self._repos = repos

    async def search(self, query: str) -> list[WorkItem]:
        # Scope search to configured repos; GitHub search allows up to 5 repo: filters
        repo_filter = " ".join(f"repo:{r}" for r in self._repos[:5])
        full_query = f"{query} {repo_filter} is:issue"

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    f"{_GH_BASE}/search/issues",
                    headers=self._headers,
                    params={"q": full_query, "per_page": 5, "sort": "updated"},
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            logger.warning("GitHub Issues tracker failed: %s", exc)
            return []

        items: list[WorkItem] = []
        for issue in data.get("items", []):
            item_type = "PR" if issue.get("pull_request") else "Issue"
            items.append(
                WorkItem(
                    id=f"#{issue.get('number', '?')}",
                    title=issue.get("title", ""),
                    url=issue.get("html_url", ""),
                    status=issue.get("state", "unknown"),
                    item_type=item_type,
                )
            )

        return items
