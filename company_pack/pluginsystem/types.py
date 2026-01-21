from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


class PluginType(str, Enum):
    TOOL = "tool"
    RETRIEVER = "retriever"
    RERANKER = "reranker"
    VERIFIER = "verifier"
    POSTPROCESSOR = "postprocessor"


class PluginStatus(str, Enum):
    OK = "ok"
    FAILED = "failed"
    SKIPPED = "skipped"


class SideEffects(str, Enum):
    NONE = "none"
    EXTERNAL_CALL = "external_call"
    WRITE_FILE = "write_file"
    NETWORK = "network"


class DataAccess(str, Enum):
    COMPANY_DOCS = "company_docs"
    CONVERSATION = "conversation"
    BOTH = "both"


class SensitiveOutputRisk(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True)
class PluginMeta:
    plugin_id: str
    plugin_type: PluginType
    plugin_version: str
    min_platform_version: str
    max_platform_version: str
    description: str = ""
    author: Optional[str] = None
    license: Optional[str] = None


@dataclass(frozen=True)
class PluginCapabilities:
    side_effects: SideEffects = SideEffects.NONE
    data_access: DataAccess = DataAccess.CONVERSATION
    sensitive_output_risk: SensitiveOutputRisk = SensitiveOutputRisk.LOW


@dataclass(frozen=True)
class PluginCallContext:
    company_id: str
    pack_root: Path
    conversation_id: str
    trace_id: str
    user_id: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PluginResult:
    status: PluginStatus
    result: Any = None
    error: Optional[str] = None
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class PluginError(Exception):
    """Base error for plugin system."""


class PluginValidationError(PluginError):
    """Plugin class or metadata invalid."""


class PluginCompatibilityError(PluginError):
    """Plugin/platform version mismatch."""


class PluginSettingsError(PluginError):
    """Settings provided for a plugin are invalid."""


class PluginNotFoundError(PluginError):
    """Plugin id not registered/discovered."""


class PluginNotEnabledError(PluginError):
    """Plugin is registered but not enabled for this company."""
