from __future__ import annotations
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from .base import BaseLogConnector, LogEntry

logger = logging.getLogger(__name__)

# Common timestamp patterns
_TS_PATTERNS = [
    re.compile(r"(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)"),
    re.compile(r"(\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2})"),
    re.compile(r"(\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})"),
]
_LEVEL_PATTERN = re.compile(r"\b(DEBUG|INFO|WARN(?:ING)?|ERROR|CRITICAL|FATAL|TRACE)\b", re.IGNORECASE)

_JSON_RESERVED_KEYS = frozenset({
    "timestamp", "@t", "time", "Timestamp",
    "level", "@l", "Level", "severity",
    "message", "@m", "Message", "msg",
})


def _parse_timestamp(text: str) -> datetime:
    for pattern in _TS_PATTERNS:
        m = pattern.search(text)
        if m:
            raw = m.group(1).replace("T", " ").strip()
            for fmt in (
                "%Y-%m-%d %H:%M:%S.%f%z",
                "%Y-%m-%d %H:%M:%S%z",
                "%Y-%m-%d %H:%M:%S.%f",
                "%Y-%m-%d %H:%M:%S",
                "%Y/%m/%d %H:%M:%S",
            ):
                try:
                    dt = datetime.strptime(raw, fmt)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    return dt
                except ValueError:
                    continue
    return datetime.now(timezone.utc)


def _parse_level(text: str) -> str:
    m = _LEVEL_PATTERN.search(text)
    return m.group(1).upper() if m else "INFO"


class FileLogConnector(BaseLogConnector, plugin_name="file_log"):
    def __init__(self, paths: list[str]) -> None:
        self._paths = paths

    @property
    def name(self) -> str:
        return "FileLog"

    async def search(self, query: str, limit: int = 50) -> list[LogEntry]:
        entries: list[LogEntry] = []
        query_lower = query.lower()

        for path_str in self._paths:
            path = Path(path_str)
            if not path.exists():
                logger.warning("FileLogConnector: path does not exist: %s", path)
                continue
            try:
                with path.open("r", encoding="utf-8", errors="replace") as fh:
                    for line in fh:
                        line = line.rstrip("\n")
                        if query_lower not in line.lower():
                            continue
                        entry = self._parse_line(line, str(path))
                        if entry:
                            entries.append(entry)
                            if len(entries) >= limit:
                                break
            except Exception as exc:
                logger.warning("FileLogConnector failed reading %s: %s", path, exc)

        return entries[:limit]

    def _parse_line(self, line: str, source_path: str) -> LogEntry | None:
        line = line.strip()
        if not line:
            return None
        # Try JSON first
        if line.startswith("{"):
            try:
                obj = json.loads(line)
                ts_raw = obj.get("timestamp") or obj.get("@t") or obj.get("time") or obj.get("Timestamp") or ""
                if ts_raw:
                    ts = _parse_timestamp(ts_raw)
                else:
                    ts = datetime.now(timezone.utc)
                level = obj.get("level") or obj.get("@l") or obj.get("Level") or obj.get("severity") or "INFO"
                msg = obj.get("message") or obj.get("@m") or obj.get("Message") or obj.get("msg") or line
                props = {k: v for k, v in obj.items() if k not in _JSON_RESERVED_KEYS}
                return LogEntry(
                    timestamp=ts,
                    level=str(level).upper(),
                    message=str(msg),
                    source=f"FileLog:{source_path}",
                    properties=props,
                )
            except json.JSONDecodeError:
                pass
        # Plain text fallback
        return LogEntry(
            timestamp=_parse_timestamp(line),
            level=_parse_level(line),
            message=line,
            source=f"FileLog:{source_path}",
            properties={},
        )
