"""Tests for new trackers: Linear, PagerDuty, GitHub Issues."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.trackers.linear import LinearTracker
from src.trackers.pagerduty import PagerDutyTracker
from src.trackers.github_issues import GitHubIssuesTracker


# ---------------------------------------------------------------------------
# LinearTracker
# ---------------------------------------------------------------------------

class TestLinearTracker:
    def test_plugin_name_registered(self):
        from src.trackers.base import BaseTracker
        assert "linear" in BaseTracker._registry
        assert BaseTracker._registry["linear"] is LinearTracker

    @pytest.mark.asyncio
    async def test_search_returns_work_items(self):
        tracker = LinearTracker(api_key="lin_api_test")

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "data": {
                "issueSearch": {
                    "nodes": [
                        {
                            "identifier": "ENG-42",
                            "title": "NullPointerException in PaymentService",
                            "state": {"name": "In Progress"},
                            "url": "https://linear.app/myteam/issue/ENG-42",
                        }
                    ]
                }
            }
        }

        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)

            results = await tracker.search("NullPointerException")

        assert len(results) == 1
        assert results[0].id == "ENG-42"
        assert results[0].title == "NullPointerException in PaymentService"
        assert results[0].status == "In Progress"
        assert results[0].url == "https://linear.app/myteam/issue/ENG-42"
        assert results[0].item_type == "Issue"

    @pytest.mark.asyncio
    async def test_search_sends_correct_auth(self):
        tracker = LinearTracker(api_key="lin_api_mykey")

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"data": {"issueSearch": {"nodes": []}}}

        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)

            await tracker.search("error")

        call_kwargs = mock_client.post.call_args.kwargs
        assert call_kwargs["headers"]["Authorization"] == "lin_api_mykey"

    @pytest.mark.asyncio
    async def test_search_returns_empty_on_error(self):
        tracker = LinearTracker(api_key="key")

        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(side_effect=Exception("network"))

            results = await tracker.search("error")

        assert results == []

    @pytest.mark.asyncio
    async def test_search_empty_results(self):
        tracker = LinearTracker(api_key="key")

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"data": {"issueSearch": {"nodes": []}}}

        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)

            results = await tracker.search("nonexistent")

        assert results == []


# ---------------------------------------------------------------------------
# PagerDutyTracker
# ---------------------------------------------------------------------------

class TestPagerDutyTracker:
    def test_plugin_name_registered(self):
        from src.trackers.base import BaseTracker
        assert "pagerduty" in BaseTracker._registry
        assert BaseTracker._registry["pagerduty"] is PagerDutyTracker

    @pytest.mark.asyncio
    async def test_search_returns_incidents(self):
        tracker = PagerDutyTracker(api_key="pd_key_test")

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "incidents": [
                {
                    "id": "Q1W2E3",
                    "incident_number": 7,
                    "title": "Payment service down",
                    "status": "triggered",
                    "html_url": "https://example.pagerduty.com/incidents/Q1W2E3",
                }
            ]
        }

        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=mock_response)

            results = await tracker.search("payment")

        assert len(results) == 1
        assert results[0].id == "7"
        assert results[0].title == "Payment service down"
        assert results[0].status == "triggered"
        assert results[0].item_type == "Incident"
        assert "Q1W2E3" in results[0].url

    @pytest.mark.asyncio
    async def test_search_sends_correct_auth(self):
        tracker = PagerDutyTracker(api_key="my_pd_key")

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"incidents": []}

        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=mock_response)

            await tracker.search("error")

        call_kwargs = mock_client.get.call_args.kwargs
        assert call_kwargs["headers"]["Authorization"] == "Token token=my_pd_key"

    @pytest.mark.asyncio
    async def test_search_returns_empty_on_error(self):
        tracker = PagerDutyTracker(api_key="key")

        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(side_effect=Exception("timeout"))

            results = await tracker.search("error")

        assert results == []


# ---------------------------------------------------------------------------
# GitHubIssuesTracker
# ---------------------------------------------------------------------------

class TestGitHubIssuesTracker:
    def test_plugin_name_registered(self):
        from src.trackers.base import BaseTracker
        assert "github_issues" in BaseTracker._registry
        assert BaseTracker._registry["github_issues"] is GitHubIssuesTracker

    @pytest.mark.asyncio
    async def test_search_returns_issues(self):
        tracker = GitHubIssuesTracker(
            token="ghp_token",
            repos=["myorg/myrepo"],
        )

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "items": [
                {
                    "number": 99,
                    "title": "NullPointerException in PaymentService",
                    "html_url": "https://github.com/myorg/myrepo/issues/99",
                    "state": "open",
                    "labels": [{"name": "bug"}],
                    "pull_request": None,
                }
            ]
        }

        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=mock_response)

            results = await tracker.search("NullPointerException")

        assert len(results) == 1
        assert results[0].id == "#99"
        assert results[0].title == "NullPointerException in PaymentService"
        assert results[0].status == "open"
        assert results[0].item_type == "Issue"

    @pytest.mark.asyncio
    async def test_pr_is_typed_as_pr(self):
        tracker = GitHubIssuesTracker(token="tok", repos=["org/repo"])

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "items": [
                {
                    "number": 10,
                    "title": "Fix NPE",
                    "html_url": "https://github.com/org/repo/pull/10",
                    "state": "closed",
                    "labels": [],
                    "pull_request": {"url": "..."},  # presence marks it as PR
                }
            ]
        }

        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=mock_response)

            results = await tracker.search("NPE")

        assert results[0].item_type == "PR"

    @pytest.mark.asyncio
    async def test_search_scopes_to_repos(self):
        tracker = GitHubIssuesTracker(token="tok", repos=["myorg/repo1", "myorg/repo2"])

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"items": []}

        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=mock_response)

            await tracker.search("error")

        call_kwargs = mock_client.get.call_args.kwargs
        query = call_kwargs["params"]["q"]
        assert "repo:myorg/repo1" in query
        assert "repo:myorg/repo2" in query

    @pytest.mark.asyncio
    async def test_search_returns_empty_on_error(self):
        tracker = GitHubIssuesTracker(token="tok", repos=["org/repo"])

        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(side_effect=Exception("rate limited"))

            results = await tracker.search("error")

        assert results == []
