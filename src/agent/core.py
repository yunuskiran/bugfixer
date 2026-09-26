from __future__ import annotations
import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

from openai import AsyncOpenAI

from ..config import Settings
from ..connectors.base import BaseLogConnector, LogEntry
from ..connectors.seq import SeqConnector
from ..connectors.azure_insights import AzureInsightsConnector
from ..connectors.file_log import FileLogConnector
from ..connectors.loki import LokiConnector
from ..connectors.sentry import SentryConnector
from ..connectors.datadog import DatadogConnector
from ..trackers.base import BaseTracker, WorkItem
from ..trackers.jira import JiraTracker
from ..trackers.azure_devops import AzureDevOpsTracker
from ..trackers.linear import LinearTracker
from ..trackers.pagerduty import PagerDutyTracker
from ..trackers.github_issues import GitHubIssuesTracker
from ..enrichers.base import BaseEnricher, Enrichment
from ..enrichers.correlation import CorrelationEnricher
from ..enrichers.trend import TrendEnricher
from .prompts import ROOT_CAUSE_PROMPT, ISSUE_SEARCH_PROMPT

logger = logging.getLogger(__name__)


@dataclass
class AnalysisResult:
    root_cause: str
    suggested_fix: str
    log_entries: list[LogEntry] = field(default_factory=list)
    related_items: list[dict] = field(default_factory=list)
    sources_queried: list[str] = field(default_factory=list)
    enrichments: list[Enrichment] = field(default_factory=list)
    error: str | None = None


class SupportAgent:
    def __init__(
        self,
        settings: Settings,
        extra_connectors: list[BaseLogConnector] | None = None,
        extra_trackers: list[BaseTracker] | None = None,
    ) -> None:
        self._settings = settings
        self._openai = AsyncOpenAI(api_key=settings.openai_api_key)
        self._connectors: list[BaseLogConnector] = (
            self._build_connectors(settings) + (extra_connectors or [])
        )
        self._trackers: list[BaseTracker] = (
            self._build_trackers(settings) + (extra_trackers or [])
        )
        self._enrichers: list[BaseEnricher] = self._build_enrichers()

    # ------------------------------------------------------------------
    # Factory helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_connectors(settings: Settings) -> list[BaseLogConnector]:
        connectors: list[BaseLogConnector] = []
        if settings.seq_url:
            connectors.append(SeqConnector(url=settings.seq_url, api_key=settings.seq_api_key))
            logger.info("Seq connector enabled")
        if settings.azure_insights_connection_string:
            connectors.append(
                AzureInsightsConnector(
                    connection_string=settings.azure_insights_connection_string,
                    tenant_id=settings.azure_tenant_id,
                    client_id=settings.azure_client_id,
                    client_secret=settings.azure_client_secret,
                )
            )
            logger.info("Azure Application Insights connector enabled")
        paths = settings.file_log_paths_list
        if paths:
            connectors.append(FileLogConnector(paths=paths))
            logger.info("FileLog connector enabled with %d path(s)", len(paths))
        if settings.loki_url:
            connectors.append(
                LokiConnector(
                    url=settings.loki_url,
                    user=settings.loki_user,
                    password=settings.loki_password,
                )
            )
            logger.info("Loki connector enabled")
        if settings.sentry_auth_token and settings.sentry_org and settings.sentry_project:
            connectors.append(
                SentryConnector(
                    auth_token=settings.sentry_auth_token,
                    org=settings.sentry_org,
                    project=settings.sentry_project,
                )
            )
            logger.info("Sentry connector enabled")
        if settings.datadog_api_key and settings.datadog_app_key:
            connectors.append(
                DatadogConnector(
                    api_key=settings.datadog_api_key,
                    app_key=settings.datadog_app_key,
                    site=settings.datadog_site,
                )
            )
            logger.info("Datadog connector enabled")
        if not connectors:
            logger.warning("No log connectors configured — analysis will have no log data")
        return connectors

    @staticmethod
    def _build_trackers(settings: Settings) -> list[BaseTracker]:
        trackers: list[BaseTracker] = []
        if settings.jira_url and settings.jira_email and settings.jira_api_token:
            trackers.append(
                JiraTracker(
                    url=settings.jira_url,
                    email=settings.jira_email,
                    api_token=settings.jira_api_token,
                    project_key=settings.jira_project_key or "",
                )
            )
            logger.info("Jira tracker enabled")
        if settings.azure_devops_url and settings.azure_devops_pat and settings.azure_devops_project:
            trackers.append(
                AzureDevOpsTracker(
                    url=settings.azure_devops_url,
                    pat=settings.azure_devops_pat,
                    project=settings.azure_devops_project,
                )
            )
            logger.info("Azure DevOps tracker enabled")
        if settings.linear_api_key:
            trackers.append(LinearTracker(api_key=settings.linear_api_key))
            logger.info("Linear tracker enabled")
        if settings.pagerduty_api_key:
            trackers.append(PagerDutyTracker(api_key=settings.pagerduty_api_key))
            logger.info("PagerDuty tracker enabled")
        repos = settings.github_repos_list
        if settings.github_token and repos:
            trackers.append(GitHubIssuesTracker(token=settings.github_token, repos=repos))
            logger.info("GitHub Issues tracker enabled with %d repo(s)", len(repos))
        if not trackers:
            logger.warning("No work-item trackers configured")
        return trackers

    @staticmethod
    def _build_enrichers() -> list[BaseEnricher]:
        return [CorrelationEnricher(), TrendEnricher()]

    # ------------------------------------------------------------------
    # Core analysis
    # ------------------------------------------------------------------

    async def analyze(self, question: str) -> AnalysisResult:
        if not self._connectors:
            return AnalysisResult(
                root_cause="No log sources configured.",
                suggested_fix="Configure at least one log source (SEQ_URL, AZURE_INSIGHTS_CONNECTION_STRING, or FILE_LOG_PATHS).",
                error="no_connectors",
            )

        # 1. Query all connectors concurrently
        search_results = await asyncio.gather(
            *[self._safe_search(connector, question) for connector in self._connectors],
            return_exceptions=False,
        )

        all_entries: list[LogEntry] = []
        sources_queried: list[str] = []
        for connector, entries in zip(self._connectors, search_results):
            sources_queried.append(connector.name)
            all_entries.extend(entries)

        # Sort by timestamp descending, keep top 50
        all_entries.sort(key=lambda e: e.timestamp, reverse=True)
        top_entries = all_entries[:50]

        if not top_entries:
            return AnalysisResult(
                root_cause="No relevant log entries found for the given query.",
                suggested_fix="Verify the process name or error message and try again. Ensure log sources contain data for the time period.",
                log_entries=[],
                related_items=[],
                sources_queried=sources_queried,
            )

        # 2. Format log entries for LLM
        log_text = self._format_log_entries(top_entries)
        sources_str = ", ".join(sources_queried) if sources_queried else "unknown"

        # 3. Call OpenAI for root cause analysis
        prompt = ROOT_CAUSE_PROMPT.format(
            question=question,
            sources=sources_str,
            log_entries=log_text,
        )

        try:
            response = await self._openai.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=1500,
            )
            analysis_text = response.choices[0].message.content or ""
        except Exception as exc:
            logger.error("OpenAI call failed: %s", exc)
            return AnalysisResult(
                root_cause="Failed to get AI analysis.",
                suggested_fix="Check OPENAI_API_KEY and network connectivity.",
                log_entries=top_entries,
                sources_queried=sources_queried,
                error=str(exc),
            )

        # 4. Extract sections from response
        root_cause = self._extract_section(analysis_text, "Root Cause")
        suggested_fix = self._extract_section(analysis_text, "Suggested Fix")
        search_terms_raw = self._extract_section(analysis_text, "Search Terms")
        search_terms = [t.strip() for t in search_terms_raw.split(",") if t.strip()][:5]

        # 5. Search trackers concurrently
        related_items: list[dict] = []
        if self._trackers and search_terms:
            tracker_results = await asyncio.gather(
                *[self._safe_tracker_search(tracker, term) for tracker in self._trackers for term in search_terms[:2]],
                return_exceptions=False,
            )
            seen_ids: set[str] = set()
            for items in tracker_results:
                for item in items:
                    key = f"{item.id}:{item.url}"
                    if key not in seen_ids:
                        seen_ids.add(key)
                        related_items.append({
                            "id": item.id,
                            "title": item.title,
                            "url": item.url,
                            "status": item.status,
                            "type": item.item_type,
                        })
            related_items = related_items[:10]

        result = AnalysisResult(
            root_cause=root_cause or analysis_text,
            suggested_fix=suggested_fix,
            log_entries=top_entries,
            related_items=related_items,
            sources_queried=sources_queried,
        )

        # 6. Run enrichers concurrently
        enrichment_results: list[Enrichment] = []
        if self._enrichers:
            enrichments = await asyncio.gather(
                *[
                    self._safe_enrich(enricher, result, question)
                    for enricher in self._enrichers
                ],
                return_exceptions=False,
            )
            enrichment_results = list(enrichments)
        result.enrichments = enrichment_results

        return result

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _safe_enrich(
        self, enricher: BaseEnricher, result: AnalysisResult, question: str
    ) -> Enrichment:
        try:
            return await enricher.enrich(result, question, self._connectors)
        except Exception as exc:
            logger.warning("Enricher %s failed: %s", type(enricher).__name__, exc)
            return Enrichment(name=enricher.plugin_name or type(enricher).__name__, summary="")

    async def _safe_search(self, connector: BaseLogConnector, query: str) -> list[LogEntry]:
        try:
            return await connector.search(query)
        except Exception as exc:
            logger.warning("Connector %s failed: %s", connector.name, exc)
            return []

    async def _safe_tracker_search(self, tracker: BaseTracker, query: str) -> list[WorkItem]:
        try:
            return await tracker.search(query)
        except Exception as exc:
            logger.warning("Tracker %s failed: %s", type(tracker).__name__, exc)
            return []

    @staticmethod
    def _format_log_entries(entries: list[LogEntry]) -> str:
        lines: list[str] = []
        for e in entries:
            ts = e.timestamp.strftime("%Y-%m-%d %H:%M:%S UTC") if e.timestamp else "unknown"
            props = ""
            if e.properties:
                top_props = dict(list(e.properties.items())[:5])
                props = f" | props={top_props}"
            lines.append(f"[{ts}] [{e.level}] [{e.source}] {e.message}{props}")
        return "\n".join(lines)

    @staticmethod
    def _extract_section(text: str, section: str) -> str:
        pattern = re.compile(
            rf"(?:^|\n)\s*\d*\.?\s*{re.escape(section)}[:\-]?\s*\n?(.*?)(?=\n\s*\d*\.?\s*(?:Root Cause|Contributing Factors|Suggested Fix|Search Terms)[:\-]|$)",
            re.IGNORECASE | re.DOTALL,
        )
        m = pattern.search(text)
        return m.group(1).strip() if m else ""

    # ------------------------------------------------------------------
    # Formatters
    # ------------------------------------------------------------------

    def format_slack_message(self, result: AnalysisResult, question: str) -> str:
        lines = [
            f"*🔍 Analysis for:* {question}",
            "",
            f"*Root Cause*\n{result.root_cause}",
            "",
            f"*Suggested Fix*\n{result.suggested_fix}",
        ]

        if result.log_entries:
            lines.append("")
            lines.append(f"*Log Sources Queried:* {', '.join(result.sources_queried)}")
            lines.append(f"*Log Entries Found:* {len(result.log_entries)}")

        if result.related_items:
            lines.append("")
            lines.append("*Related Work Items*")
            for item in result.related_items[:5]:
                lines.append(f"• <{item['url']}|[{item['id']}] {item['title']}> — {item['status']}")

        for enrichment in result.enrichments:
            if enrichment.summary:
                icon = "🔗" if enrichment.name == "correlation" else "📈"
                lines.append("")
                lines.append(f"*{icon} {enrichment.name.title()} Analysis*\n{enrichment.summary}")

        if result.error:
            lines.append("")
            lines.append(f"⚠️ _Partial result — error: {result.error}_")

        return "\n".join(lines)

    def format_teams_card(self, result: AnalysisResult, question: str) -> dict:
        """Return an Adaptive Card dict for Microsoft Teams."""
        body = [
            {
                "type": "TextBlock",
                "text": f"🔍 Analysis for: {question}",
                "weight": "bolder",
                "size": "medium",
                "wrap": True,
            },
            {"type": "TextBlock", "text": "**Root Cause**", "weight": "bolder", "wrap": True},
            {"type": "TextBlock", "text": result.root_cause, "wrap": True},
            {"type": "TextBlock", "text": "**Suggested Fix**", "weight": "bolder", "wrap": True},
            {"type": "TextBlock", "text": result.suggested_fix, "wrap": True},
        ]

        if result.log_entries:
            body.append({
                "type": "TextBlock",
                "text": f"📋 Sources: {', '.join(result.sources_queried)} | Entries found: {len(result.log_entries)}",
                "isSubtle": True,
                "wrap": True,
            })

        if result.related_items:
            body.append({"type": "TextBlock", "text": "**Related Work Items**", "weight": "bolder", "wrap": True})
            for item in result.related_items[:5]:
                body.append({
                    "type": "TextBlock",
                    "text": f"• [{item['id']}] {item['title']} — {item['status']}",
                    "wrap": True,
                })

        for enrichment in result.enrichments:
            if enrichment.summary:
                icon = "🔗" if enrichment.name == "correlation" else "📈"
                body.append({
                    "type": "TextBlock",
                    "text": f"**{icon} {enrichment.name.title()} Analysis**",
                    "weight": "bolder",
                    "wrap": True,
                })
                body.append({
                    "type": "TextBlock",
                    "text": enrichment.summary,
                    "isSubtle": True,
                    "wrap": True,
                })

        return {
            "type": "AdaptiveCard",
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "version": "1.4",
            "body": body,
        }
