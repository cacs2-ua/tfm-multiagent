from __future__ import annotations

from typing import Any

from ..base import PluginBase
from ..schema import ConfigSchema, FieldSpec
from ..types import (
    PluginCallContext,
    PluginCapabilities,
    PluginMeta,
    PluginResult,
    PluginStatus,
    PluginType,
    SideEffects,
    DataAccess,
    SensitiveOutputRisk,
)
from ...versioning import PLATFORM_VERSION


class BasicFormatPostprocessor(PluginBase):
    """Simple formatting normalization."""

    @classmethod
    def meta(cls) -> PluginMeta:
        return PluginMeta(
            plugin_id="post.format.basic_v1",
            plugin_type=PluginType.POSTPROCESSOR,
            plugin_version="1.0.0",
            min_platform_version=PLATFORM_VERSION,
            max_platform_version=PLATFORM_VERSION,
            description="Normalize whitespace and ensure the answer starts with a short summary line.",
            author="TFM",
            license="MIT",
        )

    @classmethod
    def capabilities(cls) -> PluginCapabilities:
        return PluginCapabilities(
            side_effects=SideEffects.NONE,
            data_access=DataAccess.CONVERSATION,
            sensitive_output_risk=SensitiveOutputRisk.LOW,
        )

    @classmethod
    def schema(cls) -> ConfigSchema:
        return ConfigSchema(fields={"summary_prefix": FieldSpec(str, default="Summary: ")})

    def run(self, ctx: PluginCallContext, payload: Any) -> PluginResult:
        if not isinstance(payload, dict) or "text" not in payload:
            return PluginResult(status=PluginStatus.FAILED, error="payload must be dict with 'text'")

        text = str(payload.get("text", "")).strip()
        text = "\n".join([ln.rstrip() for ln in text.splitlines()]).strip()

        prefix = str(self.settings.get("summary_prefix", "Summary: "))
        if text and not text.lower().startswith(prefix.lower()):
            first_line = text.splitlines()[0].strip()
            if len(first_line) > 0 and len(first_line) < 120 and first_line.endswith(":"):
                out = text
            else:
                out = prefix + first_line + "\n" + text
        else:
            out = text

        return PluginResult(status=PluginStatus.OK, result={"text": out})
