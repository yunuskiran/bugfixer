from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class LogEntry:
    timestamp: datetime
    level: str
    message: str
    source: str
    properties: dict = field(default_factory=dict)


class BaseLogConnector(ABC):
    @abstractmethod
    async def search(self, query: str, limit: int = 50) -> list[LogEntry]:
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        ...
