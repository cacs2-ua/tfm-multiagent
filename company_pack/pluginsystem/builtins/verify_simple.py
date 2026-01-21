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


class SimpleEvidenceVerifier(PluginBase):
    """
    Toy verifier:
      - if ctx.tags contains "policy", enforce that draft includes a marker like "[doc:".
    """

    @classmethod
    def meta(cls) -> PluginMeta:
        return PluginMeta(
            plugin_id="verify.simple_v1",
            plugin_type=PluginType.VERIFIER,
            plugin_version="1.0.0",
            min_platform_version=PLATFORM_VERSION,
            max_platform_version=PLATFORM_VERSION,
            description="Simple citation presence check (toy verifier).",
            author="TFM",
            license="MIT",
        )

    @classmethod
    def capabilities(cls) -> PluginCapabilities:
        return PluginCapabilities(
            side_effects=SideEffects.NONE,
            data_access=DataAccess.BOTH,
            sensitive_output_risk=SensitiveOutputRisk.LOW,
        )

    @classmethod
    def schema(cls) -> ConfigSchema:
        return ConfigSchema(fields={"require_marker": FieldSpec(str, default="[doc:")})

    def run(self, ctx: PluginCallContext, payload: Any) -> PluginResult:
        if not isinstance(payload, dict) or "draft" not in payload:
            return PluginResult(status=PluginStatus.FAILED, error="payload must be dict with 'draft'")

        draft = str(payload.get("draft", ""))
        marker = str(self.settings.get("require_marker", "[doc:"))

        needs_citations = "policy" in (ctx.tags or [])
        ok = (marker in draft) if needs_citations else True

        result = {
            "verified": bool(ok),
            "reason": None if ok else "Missing citation marker in draft.",
            "needs_citations": needs_citations,
        }
        status = PluginStatus.OK if ok else PluginStatus.FAILED
        return PluginResult(status=status, result=result)
