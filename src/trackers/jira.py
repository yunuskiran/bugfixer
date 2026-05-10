from __future__ import annotations
import asyncio
import logging
from .base import BaseTracker, WorkItem

try:
    from jira import JIRA, JIRAError
except ImportError:
    JIRA = None  # type: ignore[assignment,misc]
    JIRAError = Exception  # type: ignore[assignment,misc]

logger = logging.getLogger(__name__)


class JiraTracker(BaseTracker):
    def __init__(self, url: str, email: str, api_token: str, project_key: str) -> None:
        self._url = url
        self._email = email
        self._api_token = api_token
        self._project_key = project_key

    def _sync_search(self, query: str) -> list[WorkItem]:
        if JIRA is None:
            logger.warning("jira package is not installed")
            return []
        jql = f'project = "{self._project_key}" AND text ~ "{query}" ORDER BY updated DESC'
        try:
            client = JIRA(server=self._url, basic_auth=(self._email, self._api_token))
            issues = client.search_issues(jql, maxResults=5)
            results: list[WorkItem] = []
            for issue in issues:
                results.append(
                    WorkItem(
                        id=issue.key,
                        title=issue.fields.summary,
                        url=f"{self._url.rstrip('/')}/browse/{issue.key}",
                        status=issue.fields.status.name,
                        item_type=issue.fields.issuetype.name,
                    )
                )
            return results
        except JIRAError as exc:
            logger.warning("Jira search failed: %s", exc)
            return []
        except Exception as exc:
            logger.warning("JiraTracker unexpected error: %s", exc)
            return []

    async def search(self, query: str) -> list[WorkItem]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._sync_search, query)
