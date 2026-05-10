from __future__ import annotations
import logging
from datetime import datetime, timezone
import httpx
from .base import BaseLogConnector, LogEntry

logger = logging.getLogger(__name__)


class SeqConnector(BaseLogConnector, plugin_name="seq"):
    def __init__(self, url: str, api_key: str | None = None) -> None:
        self._url = url.rstrip("/")
        self._api_key = api_key

    @property
    def name(self) -> str:
        return "Seq"

    async def search(self, query: str, limit: int = 50) -> list[LogEntry]:
        headers: dict[str, str] = {}
        if self._api_key:
            headers["Authorization"] = f"apikey {self._api_key}"

        params = {
            "filter": f'Contains(@Message, "{query}")',
            "count": limit,
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    f"{self._url}/api/events/signal",
                    params=params,
                    headers=headers,
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            logger.warning("SeqConnector search failed: %s", exc)
            return []

        entries: list[LogEntry] = []
        events = data if isinstance(data, list) else data.get("Events", [])
        for event in events:
            try:
                ts_raw = event.get("@t") or event.get("@Timestamp", "")
                ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00")) if ts_raw else datetime.now(timezone.utc)
                entries.append(
                    LogEntry(
                        timestamp=ts,
                        level=event.get("@l") or event.get("@Level", "Information"),
                        message=event.get("@m") or event.get("@MessageTemplate", ""),
                        source=self.name,
                        properties={k: v for k, v in event.items() if not k.startswith("@")},
                    )
                )
            except Exception as exc:
                logger.debug("Failed to parse Seq event: %s", exc)

        return entries
