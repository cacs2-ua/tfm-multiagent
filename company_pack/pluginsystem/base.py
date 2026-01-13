from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from .schema import ConfigSchema
from .types import PluginCapabilities, PluginCallContext, PluginMeta, PluginResult


class PluginBase(ABC):
    """
    Base class for all plugins.

    Plugins are instantiated lazily (per-company) and should be stateless
    or company-scoped (no global mutable state).
    """

    def __init__(self, settings: Dict[str, Any], services: Optional[Dict[str, Any]] = None) -> None:
        self.settings = settings
        self.services = services or {}

    @classmethod
    @abstractmethod
    def meta(cls) -> PluginMeta:
        raise NotImplementedError

    @classmethod
    def capabilities(cls) -> PluginCapabilities:
        return PluginCapabilities()

    @classmethod
    def schema(cls) -> ConfigSchema:
        return ConfigSchema(fields={})

    def initialize(self) -> None:
        """Optional hook (called once after instantiation)."""
        return None

    def shutdown(self) -> None:
        """Optional hook (called once when registry shuts down)."""
        return None

    @abstractmethod
    def run(self, ctx: PluginCallContext, payload: Any) -> PluginResult:
        raise NotImplementedError
