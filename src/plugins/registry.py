"""
Plugin registry for bugfixer.

Connectors, trackers, and enrichers self-register via __init_subclass__ on their
respective base classes. Importing a module is sufficient to register its classes.

load_all_plugins() imports all built-in plugin modules so they appear in the registries
before SupportAgent tries to build instances.
"""
from __future__ import annotations

import importlib
import logging

logger = logging.getLogger(__name__)

BUILTIN_CONNECTOR_MODULES = [
    "src.connectors.seq",
    "src.connectors.azure_insights",
    "src.connectors.file_log",
    "src.connectors.loki",
    "src.connectors.sentry",
    "src.connectors.datadog",
]

BUILTIN_TRACKER_MODULES = [
    "src.trackers.jira",
    "src.trackers.azure_devops",
    "src.trackers.linear",
    "src.trackers.pagerduty",
    "src.trackers.github_issues",
]

BUILTIN_ENRICHER_MODULES = [
    "src.enrichers.correlation",
    "src.enrichers.trend",
]


def _import_silently(module: str) -> bool:
    try:
        importlib.import_module(module)
        return True
    except ImportError as exc:
        logger.debug("Optional module %s not available: %s", module, exc)
        return False


def load_all_plugins() -> None:
    """Import all built-in plugin modules so they register themselves."""
    for mod in BUILTIN_CONNECTOR_MODULES + BUILTIN_TRACKER_MODULES + BUILTIN_ENRICHER_MODULES:
        _import_silently(mod)
