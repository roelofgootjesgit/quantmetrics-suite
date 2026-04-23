"""Abstract base for news sources."""
from abc import ABC, abstractmethod

from src.quantbuild.models.news_event import RawNewsItem, SourceTier


class NewsSource(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def tier(self) -> SourceTier: ...

    @abstractmethod
    def fetch(self) -> list[RawNewsItem]: ...

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name!r}, tier={self.tier})"
