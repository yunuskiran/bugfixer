from __future__ import annotations
import logging
from datetime import datetime, timezone
from typing import Any
from .base import BaseLogConnector, LogEntry

logger = logging.getLogger(__name__)


class AzureInsightsConnector(BaseLogConnector, plugin_name="azure_insights"):
    def __init__(
        self,
        connection_string: str,
        tenant_id: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
    ) -> None:
        self._connection_string = connection_string
        self._tenant_id = tenant_id
        self._client_id = client_id
        self._client_secret = client_secret
        self._workspace_id = self._parse_workspace_id(connection_string)

    @staticmethod
    def _parse_workspace_id(connection_string: str) -> str:
        for part in connection_string.split(";"):
            if part.lower().startswith("workspaceid=") or part.lower().startswith("ingestionendpoint="):
                kv = part.split("=", 1)
                if len(kv) == 2:
                    return kv[1].strip()
        return connection_string

    def _get_credential(self) -> Any:
        try:
            if self._tenant_id and self._client_id and self._client_secret:
                from azure.identity import ClientSecretCredential
                return ClientSecretCredential(
                    tenant_id=self._tenant_id,
                    client_id=self._client_id,
                    client_secret=self._client_secret,
                )
            from azure.identity import DefaultAzureCredential
            return DefaultAzureCredential()
        except ImportError as exc:
            raise RuntimeError("azure-identity package is required") from exc

    @property
    def name(self) -> str:
        return "AzureInsights"

    async def search(self, query: str, limit: int = 50) -> list[LogEntry]:
        try:
            from azure.monitor.query.aio import LogsQueryClient
            from azure.monitor.query import LogsQueryStatus
        except ImportError:
            logger.warning("azure-monitor-query not installed; skipping AzureInsights")
            return []

        safe_query = query.replace('"', '\\"')
        kql_traces = (
            f'traces | where message contains "{safe_query}" '
            f"| order by timestamp desc | take {limit}"
        )
        kql_exceptions = (
            f'exceptions | where outerMessage contains "{safe_query}" '
            f"| order by timestamp desc | take {limit // 2}"
        )

        entries: list[LogEntry] = []
        credential = self._get_credential()

        try:
            async with LogsQueryClient(credential) as client:
                for kql, table_name in [(kql_traces, "traces"), (kql_exceptions, "exceptions")]:
                    try:
                        result = await client.query_workspace(
                            workspace_id=self._workspace_id,
                            query=kql,
                            timespan=None,
                        )
                        if result.status == LogsQueryStatus.SUCCESS:
                            for table in result.tables:
                                col_names = [c.name for c in table.columns]
                                for row in table.rows:
                                    row_dict = dict(zip(col_names, row))
                                    ts = row_dict.get("timestamp")
                                    if isinstance(ts, str):
                                        ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                                    elif ts is None:
                                        ts = datetime.now(timezone.utc)
                                    msg = row_dict.get("message") or row_dict.get("outerMessage", "")
                                    level = row_dict.get("severityLevel", "Information")
                                    if isinstance(level, int):
                                        level = {0: "Verbose", 1: "Information", 2: "Warning", 3: "Error", 4: "Critical"}.get(level, str(level))
                                    entries.append(
                                        LogEntry(
                                            timestamp=ts,
                                            level=str(level),
                                            message=str(msg),
                                            source=self.name,
                                            properties={k: v for k, v in row_dict.items() if k not in {"timestamp", "message", "severityLevel"}},
                                        )
                                    )
                    except Exception as exc:
                        logger.warning("AzureInsights query '%s' failed: %s", table_name, exc)
        except Exception as exc:
            logger.warning("AzureInsightsConnector search failed: %s", exc)
        finally:
            try:
                close = getattr(credential, "close", None)
                if close is not None:
                    import inspect
                    if inspect.iscoroutinefunction(close):
                        await close()
                    else:
                        close()
            except Exception:
                pass

        return entries
