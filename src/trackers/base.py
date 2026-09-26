from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ClassVar


@dataclass
class WorkItem:
    id: str
    title: str
    url: str
    status: str
    item_type: str


class BaseTracker(ABC):
    _registry: ClassVar[dict[str, type]] = {}
    plugin_name: ClassVar[str | None] = None

    def __init_subclass__(cls, plugin_name: str | None = None, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        if plugin_name:
            cls.plugin_name = plugin_name
            BaseTracker._registry[plugin_name] = cls

    @abstractmethod
    async def search(self, query: str) -> list[WorkItem]:
        ...
