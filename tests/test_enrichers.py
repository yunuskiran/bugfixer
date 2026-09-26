"""Tests for enrichers: CorrelationEnricher and TrendEnricher."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from src.connectors.base import LogEntry
from src.enrichers.base import BaseEnricher, Enrichment
from src.enrichers.correlation import CorrelationEnricher
from src.enrichers.trend import TrendEnricher, _extract_error_keyword
from src.agent.core import AnalysisResult


def _make_result(entries: list[LogEntry] | None = None, root_cause: str = "") -> AnalysisResult:
    return AnalysisResult(
        root_cause=root_cause,
        suggested_fix="",
        log_entries=entries or [],
        sources_queried=[],
    )


# ---------------------------------------------------------------------------
# CorrelationEnricher
# ---------------------------------------------------------------------------

class TestCorrelationEnricher:
    def test_plugin_name_registered(self):
        assert "correlation" in BaseEnricher._registry
        assert BaseEnricher._registry["correlation"] is CorrelationEnricher

    @pytest.mark.asyncio
    async def test_no_entries_returns_no_ids(self):
        enricher = CorrelationEnricher()
        result = _make_result()
        enrichment = await enricher.enrich(result, "why fail?", [])
        assert enrichment.name == "correlation"
        assert "No correlation" in enrichment.summary

    @pytest.mark.asyncio
    async def test_extracts_trace_id(self):
        now = datetime.now(timezone.utc)
        entries = [
            LogEntry(
                timestamp=now,
                level="ERROR",
                message='traceId="abc123def456" Payment failed',
                source="Seq",
                properties={},
            )
        ]
        enricher = CorrelationEnricher()
        result = _make_result(entries)
        enrichment = await enricher.enrich(result, "why?", [])
        assert "abc123def456" in enrichment.summary
        assert "trace_id" in enrichment.data["found_ids"]

    @pytest.mark.asyncio
    async def test_extracts_correlation_id(self):
        now = datetime.now(timezone.utc)
        entries = [
            LogEntry(
                timestamp=now,
                level="ERROR",
                message="correlationId=deadbeef-1234-abcd request failed",
                source="Loki",
                properties={},
            )
        ]
        enricher = CorrelationEnricher()
        result = _make_result(entries)
        enrichment = await enricher.enrich(result, "why?", [])
        assert "deadbeef" in enrichment.summary
        assert enrichment.data["found_ids"].get("correlation_id")

    @pytest.mark.asyncio
    async def test_re_queries_connectors_with_found_ids(self):
        now = datetime.now(timezone.utc)
        entries = [
            LogEntry(
                timestamp=now,
                level="ERROR",
                message='traceId="aabbccdd1122" payment error',
                source="Seq",
                properties={},
            )
        ]
        extra = LogEntry(
            timestamp=now,
            level="INFO",
            message="linked entry for aabbccdd1122",
            source="Loki",
            properties={},
        )

        mock_connector = AsyncMock()
        mock_connector.search = AsyncMock(return_value=[extra])

        enricher = CorrelationEnricher()
        result = _make_result(entries)
        enrichment = await enricher.enrich(result, "why?", [mock_connector])

        assert len(enrichment.data["extra_entries"]) == 1
        assert enrichment.data["extra_entries"][0]["message"] == extra.message

    @pytest.mark.asyncio
    async def test_connector_failure_does_not_break_enricher(self):
        now = datetime.now(timezone.utc)
        entries = [
            LogEntry(
                timestamp=now,
                level="ERROR",
                message='requestId=ff00ff00 boom',
                source="Seq",
                properties={},
            )
        ]

        mock_connector = AsyncMock()
        mock_connector.search = AsyncMock(side_effect=Exception("boom"))

        enricher = CorrelationEnricher()
        result = _make_result(entries)
        # Should not raise
        enrichment = await enricher.enrich(result, "why?", [mock_connector])
        assert enrichment.name == "correlation"


# ---------------------------------------------------------------------------
# TrendEnricher
# ---------------------------------------------------------------------------

class TestTrendEnricher:
    def test_plugin_name_registered(self):
        assert "trend" in BaseEnricher._registry
        assert BaseEnricher._registry["trend"] is TrendEnricher

    @pytest.mark.asyncio
    async def test_no_entries(self):
        enricher = TrendEnricher()
        result = _make_result()
        enrichment = await enricher.enrich(result, "why?", [])
        assert enrichment.name == "trend"
        assert "No log entries" in enrichment.summary

    @pytest.mark.asyncio
    async def test_counts_entries_in_windows(self):
        now = datetime.now(timezone.utc)
        entries = [
            LogEntry(timestamp=now - timedelta(minutes=5), level="ERROR", message="err", source="S", properties={}),
            LogEntry(timestamp=now - timedelta(minutes=30), level="ERROR", message="err", source="S", properties={}),
            LogEntry(timestamp=now - timedelta(hours=12), level="ERROR", message="err", source="S", properties={}),
        ]
        enricher = TrendEnricher()
        result = _make_result(entries, root_cause="NullPointerException occurred")
        enrichment = await enricher.enrich(result, "why?", [])
        data = enrichment.data
        assert data["windows"]["15min"] == 1
        assert data["windows"]["1h"] == 2
        assert data["windows"]["24h"] == 3

    @pytest.mark.asyncio
    async def test_detects_spike(self):
        now = datetime.now(timezone.utc)
        # 5 in last 15min, 6 total in 24h → spike (5/6 = 83%)
        entries = [
            LogEntry(timestamp=now - timedelta(minutes=i), level="ERROR", message="err", source="S", properties={})
            for i in range(1, 6)
        ] + [
            LogEntry(timestamp=now - timedelta(hours=12), level="ERROR", message="err", source="S", properties={})
        ]
        enricher = TrendEnricher()
        result = _make_result(entries, root_cause="NullPointerException")
        enrichment = await enricher.enrich(result, "why?", [])
        assert enrichment.data["is_spiking"] is True
        assert "SPIKE" in enrichment.summary

    @pytest.mark.asyncio
    async def test_no_spike_when_distributed(self):
        now = datetime.now(timezone.utc)
        # Only 1 in 15min out of 20 in 24h → 5%, no spike
        entries = [
            LogEntry(timestamp=now - timedelta(minutes=5), level="ERROR", message="err", source="S", properties={})
        ] + [
            LogEntry(timestamp=now - timedelta(hours=i), level="ERROR", message="err", source="S", properties={})
            for i in range(1, 20)
        ]
        enricher = TrendEnricher()
        result = _make_result(entries, root_cause="SomeException")
        enrichment = await enricher.enrich(result, "why?", [])
        assert enrichment.data["is_spiking"] is False

    @pytest.mark.asyncio
    async def test_connector_count_included(self):
        now = datetime.now(timezone.utc)
        entries = [
            LogEntry(timestamp=now - timedelta(minutes=5), level="ERROR", message="err", source="S", properties={})
        ]
        mock_connector = AsyncMock()
        mock_connector.search = AsyncMock(return_value=[entries[0]] * 15)

        enricher = TrendEnricher()
        result = _make_result(entries, root_cause="SomeException")
        enrichment = await enricher.enrich(result, "why?", [mock_connector])
        assert enrichment.data["total_from_sources"] == 15


class TestExtractErrorKeyword:
    def test_quoted_phrase(self):
        kw = _extract_error_keyword('"connection pool exhausted"', "?")
        assert kw == "connection pool exhausted"

    def test_exception_class(self):
        kw = _extract_error_keyword("NullPointerException was raised", "?")
        assert kw == "NullPointerException"

    def test_falls_back_to_question(self):
        kw = _extract_error_keyword("something vague happened", "payment gateway fail")
        assert "payment" in kw
