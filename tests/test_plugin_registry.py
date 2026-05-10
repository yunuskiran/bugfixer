"""Tests for the plugin registry and auto-registration mechanism."""
from __future__ import annotations

import pytest
from src.connectors.base import BaseLogConnector
from src.trackers.base import BaseTracker
from src.enrichers.base import BaseEnricher


class TestConnectorRegistry:
    def test_builtin_connectors_registered(self):
        """Importing the connector modules should populate the registry."""
        import src.connectors.seq  # noqa: F401
        import src.connectors.azure_insights  # noqa: F401
        import src.connectors.file_log  # noqa: F401
        import src.connectors.loki  # noqa: F401
        import src.connectors.sentry  # noqa: F401
        import src.connectors.datadog  # noqa: F401

        assert "seq" in BaseLogConnector._registry
        assert "azure_insights" in BaseLogConnector._registry
        assert "file_log" in BaseLogConnector._registry
        assert "loki" in BaseLogConnector._registry
        assert "sentry" in BaseLogConnector._registry
        assert "datadog" in BaseLogConnector._registry

    def test_registry_values_are_classes(self):
        from src.connectors.seq import SeqConnector
        from src.connectors.loki import LokiConnector

        assert BaseLogConnector._registry["seq"] is SeqConnector
        assert BaseLogConnector._registry["loki"] is LokiConnector

    def test_custom_connector_auto_registers(self):
        """A new subclass with plugin_name should be auto-registered."""
        from src.connectors.base import LogEntry

        class _MyConnector(BaseLogConnector, plugin_name="_test_custom"):
            @property
            def name(self) -> str:
                return "_TestCustom"

            async def search(self, query: str, limit: int = 50) -> list[LogEntry]:
                return []

        assert "_test_custom" in BaseLogConnector._registry
        assert BaseLogConnector._registry["_test_custom"] is _MyConnector

    def test_subclass_without_plugin_name_not_registered(self):
        from src.connectors.base import LogEntry

        before = set(BaseLogConnector._registry.keys())

        class _NoName(BaseLogConnector):
            @property
            def name(self) -> str:
                return "noname"

            async def search(self, query: str, limit: int = 50) -> list[LogEntry]:
                return []

        after = set(BaseLogConnector._registry.keys())
        assert after == before  # nothing new was added


class TestTrackerRegistry:
    def test_builtin_trackers_registered(self):
        import src.trackers.jira  # noqa: F401
        import src.trackers.azure_devops  # noqa: F401
        import src.trackers.linear  # noqa: F401
        import src.trackers.pagerduty  # noqa: F401
        import src.trackers.github_issues  # noqa: F401

        assert "jira" in BaseTracker._registry
        assert "azure_devops" in BaseTracker._registry
        assert "linear" in BaseTracker._registry
        assert "pagerduty" in BaseTracker._registry
        assert "github_issues" in BaseTracker._registry

    def test_custom_tracker_auto_registers(self):
        from src.trackers.base import WorkItem

        class _MyTracker(BaseTracker, plugin_name="_test_tracker"):
            async def search(self, query: str) -> list[WorkItem]:
                return []

        assert "_test_tracker" in BaseTracker._registry


class TestEnricherRegistry:
    def test_builtin_enrichers_registered(self):
        import src.enrichers.correlation  # noqa: F401
        import src.enrichers.trend  # noqa: F401

        assert "correlation" in BaseEnricher._registry
        assert "trend" in BaseEnricher._registry

    def test_custom_enricher_auto_registers(self):
        from src.enrichers.base import Enrichment

        class _MyEnricher(BaseEnricher, plugin_name="_test_enricher"):
            async def enrich(self, result, question, connectors) -> Enrichment:
                return Enrichment(name="_test_enricher")

        assert "_test_enricher" in BaseEnricher._registry


class TestLoadAllPlugins:
    def test_load_all_plugins_runs_without_error(self):
        from src.plugins.registry import load_all_plugins
        load_all_plugins()  # should not raise

    def test_load_all_plugins_populates_registries(self):
        from src.plugins.registry import load_all_plugins
        load_all_plugins()

        for name in ("seq", "loki", "sentry", "datadog", "azure_insights", "file_log"):
            assert name in BaseLogConnector._registry, f"{name!r} missing from connector registry"

        for name in ("jira", "azure_devops", "linear", "pagerduty", "github_issues"):
            assert name in BaseTracker._registry, f"{name!r} missing from tracker registry"

        for name in ("correlation", "trend"):
            assert name in BaseEnricher._registry, f"{name!r} missing from enricher registry"
