from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class WorkItem:
    id: str
    title: str
    url: str
    status: str
    item_type: str


class BaseTracker(ABC):
    @abstractmethod
    async def search(self, query: str) -> list[WorkItem]:
        ...
