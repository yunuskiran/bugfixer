from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import ClassVar


@dataclass
class LogEntry:
    timestamp: datetime
    level: str
    message: str
    source: str
    properties: dict = field(default_factory=dict)


class BaseLogConnector(ABC):
    _registry: ClassVar[dict[str, type]] = {}
    plugin_name: ClassVar[str | None] = None

    def __init_subclass__(cls, plugin_name: str | None = None, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        if plugin_name:
            cls.plugin_name = plugin_name
            BaseLogConnector._registry[plugin_name] = cls

    @abstractmethod
    async def search(self, query: str, limit: int = 50) -> list[LogEntry]:
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        ...
