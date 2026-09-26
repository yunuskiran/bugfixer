from __future__ import annotations
import base64
import logging
import httpx
from .base import BaseTracker, WorkItem

logger = logging.getLogger(__name__)


class AzureDevOpsTracker(BaseTracker, plugin_name="azure_devops"):
    def __init__(self, url: str, pat: str, project: str) -> None:
        self._url = url.rstrip("/")
        self._project = project
        token = base64.b64encode(f":{pat}".encode()).decode()
        self._headers = {
            "Authorization": f"Basic {token}",
            "Content-Type": "application/json",
        }

    @property
    def _wiql_url(self) -> str:
        return f"{self._url}/{self._project}/_apis/wit/wiql?api-version=7.1"

    async def search(self, query: str) -> list[WorkItem]:
        safe_query = query.replace("'", "''")
        wiql = (
            f"SELECT [Id],[Title],[State],[Work Item Type] FROM workitems "
            f"WHERE [System.TeamProject] = '{self._project}' "
            f"AND [System.Title] CONTAINS '{safe_query}' "
            f"ORDER BY [System.ChangedDate] DESC"
        )

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(self._wiql_url, json={"query": wiql}, headers=self._headers)
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            logger.warning("AzureDevOpsTracker WIQL query failed: %s", exc)
            return []

        work_item_refs = data.get("workItems", [])[:5]
        if not work_item_refs:
            return []

        ids = [str(ref["id"]) for ref in work_item_refs]
        ids_str = ",".join(ids)
        details_url = f"{self._url}/{self._project}/_apis/wit/workitems?ids={ids_str}&fields=System.Id,System.Title,System.State,System.WorkItemType&api-version=7.1"

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(details_url, headers=self._headers)
                resp.raise_for_status()
                details = resp.json()
        except Exception as exc:
            logger.warning("AzureDevOpsTracker fetch details failed: %s", exc)
            return []

        results: list[WorkItem] = []
        for item in details.get("value", []):
            f = item.get("fields", {})
            item_id = str(f.get("System.Id", item.get("id", "")))
            results.append(
                WorkItem(
                    id=item_id,
                    title=f.get("System.Title", "Untitled"),
                    url=f"{self._url}/{self._project}/_workitems/edit/{item_id}",
                    status=f.get("System.State", "Unknown"),
                    item_type=f.get("System.WorkItemType", "Work Item"),
                )
            )
        return results
