"""Tests for new log connectors: Loki, Sentry, Datadog."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.connectors.loki import LokiConnector
from src.connectors.sentry import SentryConnector
from src.connectors.datadog import DatadogConnector


# ---------------------------------------------------------------------------
# LokiConnector
# ---------------------------------------------------------------------------

class TestLokiConnector:
    def test_name(self):
        assert LokiConnector(url="http://loki:3100").name == "Loki"

    def test_plugin_name_registered(self):
        from src.connectors.base import BaseLogConnector
        assert "loki" in BaseLogConnector._registry
        assert BaseLogConnector._registry["loki"] is LokiConnector

    @pytest.mark.asyncio
    async def test_search_returns_entries(self):
        connector = LokiConnector(url="http://loki:3100")

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "data": {
                "result": [
                    {
                        "stream": {"job": "myapp", "env": "production"},
                        "values": [
                            ["1717243200000000000", "NullPointerException in PaymentService"],
                            ["1717243201000000000", "Retrying after failure"],
                        ],
                    }
                ]
            }
        }

        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=mock_response)

            results = await connector.search("NullPointerException", limit=10)

        assert len(results) == 2
        assert results[0].source == "Loki/myapp"
        assert "NullPointerException" in results[0].message

    @pytest.mark.asyncio
    async def test_search_with_auth(self):
        connector = LokiConnector(url="http://loki:3100", user="admin", password="secret")

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"data": {"result": []}}

        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=mock_response)

            results = await connector.search("error")

        call_kwargs = mock_client.get.call_args.kwargs
        assert "auth" in call_kwargs
        assert call_kwargs["auth"] == ("admin", "secret")
        assert results == []

    @pytest.mark.asyncio
    async def test_search_no_auth(self):
        connector = LokiConnector(url="http://loki:3100")

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"data": {"result": []}}

        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=mock_response)

            results = await connector.search("error")

        call_kwargs = mock_client.get.call_args.kwargs
        assert "auth" not in call_kwargs

    @pytest.mark.asyncio
    async def test_search_returns_empty_on_error(self):
        connector = LokiConnector(url="http://loki:3100")

        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(side_effect=Exception("connection refused"))

            results = await connector.search("error")

        assert results == []

    @pytest.mark.asyncio
    async def test_search_respects_limit(self):
        connector = LokiConnector(url="http://loki:3100")

        values = [[str(i * 1_000_000_000), f"line {i}"] for i in range(100)]
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "data": {"result": [{"stream": {"job": "app"}, "values": values}]}
        }

        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=mock_response)

            results = await connector.search("line", limit=5)

        assert len(results) <= 5


# ---------------------------------------------------------------------------
# SentryConnector
# ---------------------------------------------------------------------------

class TestSentryConnector:
    def test_name(self):
        assert SentryConnector(auth_token="tok", org="myorg", project="myproj").name == "Sentry"

    def test_plugin_name_registered(self):
        from src.connectors.base import BaseLogConnector
        assert "sentry" in BaseLogConnector._registry

    @pytest.mark.asyncio
    async def test_search_returns_entries(self):
        connector = SentryConnector(auth_token="tok", org="myorg", project="myproj")

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = [
            {
                "id": "123",
                "title": "NullPointerException in PaymentService",
                "culprit": "PaymentService.process",
                "level": "error",
                "count": "42",
                "firstSeen": "2024-06-01T12:00:00Z",
                "lastSeen": "2024-06-01T13:00:00Z",
                "status": "unresolved",
                "permalink": "https://sentry.io/issues/123",
            }
        ]

        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=mock_response)

            results = await connector.search("NullPointerException")

        assert len(results) == 1
        assert results[0].source == "Sentry"
        assert results[0].level == "ERROR"
        assert "NullPointerException" in results[0].message
        assert results[0].properties["issue_id"] == "123"

    @pytest.mark.asyncio
    async def test_search_includes_auth_header(self):
        connector = SentryConnector(auth_token="mytoken", org="myorg", project="myproj")

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = []

        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=mock_response)

            await connector.search("error")

        call_kwargs = mock_client.get.call_args.kwargs
        assert call_kwargs["headers"]["Authorization"] == "Bearer mytoken"

    @pytest.mark.asyncio
    async def test_search_returns_empty_on_error(self):
        connector = SentryConnector(auth_token="tok", org="myorg", project="myproj")

        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(side_effect=Exception("network"))

            results = await connector.search("error")

        assert results == []


# ---------------------------------------------------------------------------
# DatadogConnector
# ---------------------------------------------------------------------------

class TestDatadogConnector:
    def test_name(self):
        assert DatadogConnector(api_key="key", app_key="app").name == "Datadog"

    def test_plugin_name_registered(self):
        from src.connectors.base import BaseLogConnector
        assert "datadog" in BaseLogConnector._registry

    def test_custom_site(self):
        c = DatadogConnector(api_key="k", app_key="a", site="datadoghq.eu")
        assert "datadoghq.eu" in c._base_url

    @pytest.mark.asyncio
    async def test_search_returns_entries(self):
        connector = DatadogConnector(api_key="key", app_key="app")

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "data": [
                {
                    "attributes": {
                        "timestamp": "2024-06-01T12:00:00Z",
                        "status": "error",
                        "message": "NullPointerException in PaymentService",
                        "service": "payment-api",
                    }
                }
            ]
        }

        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)

            results = await connector.search("NullPointerException")

        assert len(results) == 1
        assert results[0].level == "ERROR"
        assert results[0].source == "Datadog/payment-api"
        assert "NullPointerException" in results[0].message

    @pytest.mark.asyncio
    async def test_search_includes_api_key_headers(self):
        connector = DatadogConnector(api_key="MY-API-KEY", app_key="MY-APP-KEY")

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"data": []}

        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)

            await connector.search("error")

        call_kwargs = mock_client.post.call_args.kwargs
        assert call_kwargs["headers"]["DD-API-KEY"] == "MY-API-KEY"
        assert call_kwargs["headers"]["DD-APPLICATION-KEY"] == "MY-APP-KEY"

    @pytest.mark.asyncio
    async def test_search_returns_empty_on_error(self):
        connector = DatadogConnector(api_key="key", app_key="app")

        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(side_effect=Exception("timeout"))

            results = await connector.search("error")

        assert results == []
