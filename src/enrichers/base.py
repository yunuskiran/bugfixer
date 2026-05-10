from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from ..agent.core import AnalysisResult
    from ..connectors.base import BaseLogConnector


@dataclass
class Enrichment:
    name: str
    data: dict = field(default_factory=dict)
    summary: str = ""


class BaseEnricher(ABC):
    _registry: ClassVar[dict[str, type]] = {}
    plugin_name: ClassVar[str | None] = None

    def __init_subclass__(cls, plugin_name: str | None = None, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        if plugin_name:
            cls.plugin_name = plugin_name
            BaseEnricher._registry[plugin_name] = cls

    @abstractmethod
    async def enrich(
        self,
        result: "AnalysisResult",
        question: str,
        connectors: list["BaseLogConnector"],
    ) -> Enrichment:
        ...
