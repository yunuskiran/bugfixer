from __future__ import annotations
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from src.trackers.jira import JiraTracker
from src.trackers.azure_devops import AzureDevOpsTracker
from src.trackers.base import WorkItem


class TestJiraTracker:
    @pytest.mark.asyncio
    async def test_search_returns_work_items(self):
        tracker = JiraTracker(
            url="https://jira.example.com",
            email="user@example.com",
            api_token="token123",
            project_key="PROJ",
        )

        mock_issue = MagicMock()
        mock_issue.key = "PROJ-42"
        mock_issue.fields.summary = "NullPointerException in PaymentService"
        mock_issue.fields.status.name = "Open"
        mock_issue.fields.issuetype.name = "Bug"

        with patch("src.trackers.jira.JIRA") as MockJira:
            mock_client = MagicMock()
            mock_client.search_issues.return_value = [mock_issue]
            MockJira.return_value = mock_client

            results = await tracker.search("NullPointerException")

        assert len(results) == 1
        assert results[0].id == "PROJ-42"
        assert results[0].title == "NullPointerException in PaymentService"
        assert results[0].status == "Open"
        assert results[0].item_type == "Bug"
        assert "PROJ-42" in results[0].url

    @pytest.mark.asyncio
    async def test_search_returns_empty_on_jira_error(self):
        tracker = JiraTracker(
            url="https://jira.example.com",
            email="user@example.com",
            api_token="bad-token",
            project_key="PROJ",
        )

        with patch("src.trackers.jira.JIRA") as MockJira:
            import src.trackers.jira as jira_module
            MockJira.side_effect = jira_module.JIRAError("Unauthorized")

            results = await tracker.search("error")

        assert results == []

    @pytest.mark.asyncio
    async def test_search_empty_results(self):
        tracker = JiraTracker(
            url="https://jira.example.com",
            email="user@example.com",
            api_token="token",
            project_key="PROJ",
        )

        with patch("src.trackers.jira.JIRA") as MockJira:
            mock_client = MagicMock()
            mock_client.search_issues.return_value = []
            MockJira.return_value = mock_client

            results = await tracker.search("nonexistent")

        assert results == []


class TestAzureDevOpsTracker:
    @pytest.mark.asyncio
    async def test_search_returns_work_items(self):
        tracker = AzureDevOpsTracker(
            url="https://dev.azure.com/myorg",
            pat="my-pat-token",
            project="MyProject",
        )

        wiql_response = MagicMock()
        wiql_response.raise_for_status = MagicMock()
        wiql_response.json.return_value = {
            "workItems": [{"id": 101}, {"id": 202}]
        }

        details_response = MagicMock()
        details_response.raise_for_status = MagicMock()
        details_response.json.return_value = {
            "value": [
                {
                    "fields": {
                        "System.Id": 101,
                        "System.Title": "Payment Gateway NPE",
                        "System.State": "Active",
                        "System.WorkItemType": "Bug",
                    }
                },
                {
                    "fields": {
                        "System.Id": 202,
                        "System.Title": "DB pool exhaustion",
                        "System.State": "Resolved",
                        "System.WorkItemType": "Bug",
                    }
                },
            ]
        }

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=wiql_response)
            mock_client.get = AsyncMock(return_value=details_response)

            results = await tracker.search("NullPointerException")

        assert len(results) == 2
        assert results[0].id == "101"
        assert results[0].title == "Payment Gateway NPE"
        assert results[0].status == "Active"
        assert "101" in results[0].url

    @pytest.mark.asyncio
    async def test_search_returns_empty_on_wiql_error(self):
        tracker = AzureDevOpsTracker(
            url="https://dev.azure.com/myorg",
            pat="pat",
            project="MyProject",
        )

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(side_effect=Exception("Network error"))

            results = await tracker.search("error")

        assert results == []

    @pytest.mark.asyncio
    async def test_search_empty_wiql_result(self):
        tracker = AzureDevOpsTracker(
            url="https://dev.azure.com/myorg",
            pat="pat",
            project="MyProject",
        )

        wiql_response = MagicMock()
        wiql_response.raise_for_status = MagicMock()
        wiql_response.json.return_value = {"workItems": []}

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=wiql_response)

            results = await tracker.search("nonexistent")

        assert results == []

    def test_authorization_header(self):
        import base64
        tracker = AzureDevOpsTracker(
            url="https://dev.azure.com/myorg",
            pat="secret-pat",
            project="MyProject",
        )
        expected = "Basic " + base64.b64encode(b":secret-pat").decode()
        assert tracker._headers["Authorization"] == expected
