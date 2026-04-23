"""Abstract base for strategy modules (ICT, indicators, etc.)."""
from abc import ABC, abstractmethod
from typing import Any, Dict

import pandas as pd


class BaseModule(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def description(self) -> str: ...

    @abstractmethod
    def get_config_schema(self) -> Dict[str, Any]: ...

    @abstractmethod
    def calculate(self, data: pd.DataFrame, config: Dict[str, Any]) -> pd.DataFrame: ...

    @abstractmethod
    def check_entry_condition(
        self, data: pd.DataFrame, index: int, config: Dict[str, Any], direction: str,
    ) -> bool: ...
