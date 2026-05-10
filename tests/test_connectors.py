from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from src.connectors.seq import SeqConnector
from src.connectors.file_log import FileLogConnector
from src.connectors.azure_insights import AzureInsightsConnector


class TestSeqConnector:
    def test_name(self):
        connector = SeqConnector(url="http://seq:5341", api_key="secret")
        assert connector.name == "Seq"

    @pytest.mark.asyncio
    async def test_search_with_api_key(self):
        connector = SeqConnector(url="http://seq:5341", api_key="my-api-key")

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = [
            {
                "@t": "2024-06-01T12:00:00.000Z",
                "@l": "Error",
                "@m": "NullPointerException in PaymentService",
                "service": "payment",
            }
        ]

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=mock_response)

            results = await connector.search("PaymentService", limit=10)

        mock_client.get.assert_called_once()
        call_kwargs = mock_client.get.call_args
        assert "Authorization" in call_kwargs.kwargs.get("headers", {})
        assert call_kwargs.kwargs["headers"]["Authorization"] == "apikey my-api-key"

        assert len(results) == 1
        assert results[0].level == "Error"
        assert "PaymentService" in results[0].message
        assert results[0].source == "Seq"

    @pytest.mark.asyncio
    async def test_search_returns_empty_on_error(self):
        connector = SeqConnector(url="http://seq:5341")

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(side_effect=Exception("Connection refused"))

            results = await connector.search("error")

        assert results == []

    @pytest.mark.asyncio
    async def test_search_no_api_key(self):
        connector = SeqConnector(url="http://seq:5341")

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = []

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=mock_response)

            results = await connector.search("test")

        call_kwargs = mock_client.get.call_args
        headers = call_kwargs.kwargs.get("headers", {})
        assert "Authorization" not in headers
        assert results == []


class TestFileLogConnector:
    @pytest.mark.asyncio
    async def test_search_plain_text(self, tmp_path: Path):
        log_file = tmp_path / "app.log"
        log_file.write_text(
            "2024-06-01 12:00:00 ERROR NullPointerException in PaymentService\n"
            "2024-06-01 12:00:01 INFO Request received\n"
            "2024-06-01 12:00:02 ERROR Database timeout occurred\n"
        )

        connector = FileLogConnector(paths=[str(log_file)])
        results = await connector.search("NullPointerException")

        assert len(results) == 1
        assert "NullPointerException" in results[0].message
        assert results[0].level == "ERROR"

    @pytest.mark.asyncio
    async def test_search_json_lines(self, tmp_path: Path):
        log_file = tmp_path / "app.jsonl"
        lines = [
            json.dumps({"timestamp": "2024-06-01T12:00:00Z", "level": "ERROR", "message": "Payment failed"}),
            json.dumps({"timestamp": "2024-06-01T12:00:01Z", "level": "INFO", "message": "Health check OK"}),
            json.dumps({"timestamp": "2024-06-01T12:00:02Z", "level": "ERROR", "message": "Payment timeout"}),
        ]
        log_file.write_text("\n".join(lines))

        connector = FileLogConnector(paths=[str(log_file)])
        results = await connector.search("Payment")

        assert len(results) == 2
        assert all("Payment" in r.message for r in results)

    @pytest.mark.asyncio
    async def test_search_missing_file(self):
        connector = FileLogConnector(paths=["/nonexistent/path/app.log"])
        results = await connector.search("error")
        assert results == []

    @pytest.mark.asyncio
    async def test_search_respects_limit(self, tmp_path: Path):
        log_file = tmp_path / "big.log"
        lines = [f"2024-06-01 12:00:{i:02d} ERROR Error number {i}" for i in range(100)]
        log_file.write_text("\n".join(lines))

        connector = FileLogConnector(paths=[str(log_file)])
        results = await connector.search("Error", limit=10)

        assert len(results) <= 10

    @pytest.mark.asyncio
    async def test_search_case_insensitive(self, tmp_path: Path):
        log_file = tmp_path / "app.log"
        log_file.write_text("2024-06-01 12:00:00 ERROR NullPointerException in PaymentService\n")

        connector = FileLogConnector(paths=[str(log_file)])
        results = await connector.search("nullpointerexception")
        assert len(results) == 1


class TestAzureInsightsConnector:
    def test_name(self):
        connector = AzureInsightsConnector(
            connection_string="WorkspaceId=abc123;InstrumentationKey=def456"
        )
        assert connector.name == "AzureInsights"

    @pytest.mark.asyncio
    async def test_search_returns_empty_on_import_error(self, monkeypatch):
        connector = AzureInsightsConnector(connection_string="WorkspaceId=test123")
        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "azure.monitor.query.aio":
                raise ImportError("Mocked import error")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)
        results = await connector.search("error")
        assert results == []

    def test_parse_workspace_id(self):
        connector = AzureInsightsConnector(
            connection_string="WorkspaceId=my-workspace-id;other=stuff"
        )
        assert "my-workspace-id" in connector._workspace_id
