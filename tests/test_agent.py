from __future__ import annotations
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from src.agent.core import SupportAgent, AnalysisResult
from src.connectors.base import LogEntry
from src.trackers.base import WorkItem


@pytest.fixture
def agent_with_mocks(mock_settings, sample_log_entries, mock_openai_response):
    mock_settings.seq_url = "http://seq:5341"
    mock_settings.seq_api_key = "key"

    with patch("src.agent.core.SeqConnector") as MockSeq, \
         patch("src.agent.core.AsyncOpenAI") as MockOpenAI:

        mock_connector = AsyncMock()
        mock_connector.name = "Seq"
        mock_connector.search = AsyncMock(return_value=sample_log_entries)
        MockSeq.return_value = mock_connector

        mock_openai_instance = AsyncMock()
        mock_openai_instance.chat.completions.create = AsyncMock(return_value=mock_openai_response)
        MockOpenAI.return_value = mock_openai_instance

        agent = SupportAgent(mock_settings)

    return agent


class TestSupportAgent:
    @pytest.mark.asyncio
    async def test_analyze_no_connectors(self, mock_settings):
        mock_settings.seq_url = None
        mock_settings.azure_insights_connection_string = None
        mock_settings.file_log_paths_list = []

        with patch("src.agent.core.AsyncOpenAI"):
            agent = SupportAgent(mock_settings)

        result = await agent.analyze("Why did payment fail?")
        assert "No log sources configured" in result.root_cause
        assert result.error == "no_connectors"

    @pytest.mark.asyncio
    async def test_analyze_with_logs(self, agent_with_mocks, sample_log_entries, mock_openai_response):
        agent = agent_with_mocks
        # Patch connectors directly
        mock_connector = AsyncMock()
        mock_connector.name = "Seq"
        mock_connector.search = AsyncMock(return_value=sample_log_entries)
        agent._connectors = [mock_connector]

        mock_openai = AsyncMock()
        mock_openai.chat.completions.create = AsyncMock(return_value=mock_openai_response)
        agent._openai = mock_openai

        result = await agent.analyze("Why did payment fail?")

        assert isinstance(result, AnalysisResult)
        assert result.root_cause
        assert result.suggested_fix
        assert len(result.log_entries) == len(sample_log_entries)

    @pytest.mark.asyncio
    async def test_analyze_connector_failure_graceful(self, mock_settings, mock_openai_response):
        mock_settings.seq_url = "http://seq:5341"
        mock_settings.seq_api_key = None

        with patch("src.agent.core.SeqConnector") as MockSeq, \
             patch("src.agent.core.AsyncOpenAI") as MockOpenAI:

            mock_connector = AsyncMock()
            mock_connector.name = "Seq"
            mock_connector.search = AsyncMock(side_effect=Exception("Connection error"))
            MockSeq.return_value = mock_connector

            mock_openai_instance = AsyncMock()
            MockOpenAI.return_value = mock_openai_instance

            agent = SupportAgent(mock_settings)

        result = await agent.analyze("Why did it fail?")
        # Should not raise, returns graceful message
        assert "No relevant log entries found" in result.root_cause

    @pytest.mark.asyncio
    async def test_format_slack_message(self, mock_settings, sample_log_entries, sample_work_items):
        with patch("src.agent.core.AsyncOpenAI"):
            agent = SupportAgent(mock_settings)

        result = AnalysisResult(
            root_cause="NullPointerException due to uninitialized client",
            suggested_fix="Initialize the client in the constructor",
            log_entries=sample_log_entries,
            related_items=[{"id": "PROJ-1", "title": "NPE in Payment", "url": "https://jira.example.com/PROJ-1", "status": "Open", "type": "Bug"}],
            sources_queried=["Seq"],
        )

        message = agent.format_slack_message(result, "Why did payment fail?")
        assert "Root Cause" in message
        assert "Suggested Fix" in message
        assert "NullPointerException" in message
        assert "PROJ-1" in message

    @pytest.mark.asyncio
    async def test_format_teams_card(self, mock_settings, sample_log_entries):
        with patch("src.agent.core.AsyncOpenAI"):
            agent = SupportAgent(mock_settings)

        result = AnalysisResult(
            root_cause="Database connection pool exhausted",
            suggested_fix="Increase pool size and add monitoring",
            log_entries=sample_log_entries,
            related_items=[],
            sources_queried=["Seq", "FileLog"],
        )

        card = agent.format_teams_card(result, "Why is the DB slow?")
        assert card["type"] == "AdaptiveCard"
        assert "body" in card
        texts = [b.get("text", "") for b in card["body"]]
        assert any("Database connection pool" in t for t in texts)

    @pytest.mark.asyncio
    async def test_analyze_no_log_entries(self, mock_settings):
        mock_settings.seq_url = "http://seq:5341"

        with patch("src.agent.core.SeqConnector") as MockSeq, \
             patch("src.agent.core.AsyncOpenAI") as MockOpenAI:

            mock_connector = AsyncMock()
            mock_connector.name = "Seq"
            mock_connector.search = AsyncMock(return_value=[])
            MockSeq.return_value = mock_connector
            MockOpenAI.return_value = AsyncMock()

            agent = SupportAgent(mock_settings)

        result = await agent.analyze("Why did it fail?")
        assert "No relevant log entries found" in result.root_cause
