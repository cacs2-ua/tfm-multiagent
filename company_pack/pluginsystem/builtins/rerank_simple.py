from __future__ import annotations

from typing import Any

from ..base import PluginBase
from ..schema import ConfigSchema
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


class SimpleReranker(PluginBase):
    """Toy reranker: sorts candidates by score descending."""

    @classmethod
    def meta(cls) -> PluginMeta:
        return PluginMeta(
            plugin_id="rerank.simple_v1",
            plugin_type=PluginType.RERANKER,
            plugin_version="1.0.0",
            min_platform_version=PLATFORM_VERSION,
            max_platform_version=PLATFORM_VERSION,
            description="Sort candidates by score descending (toy reranker).",
            author="TFM",
            license="MIT",
        )

    @classmethod
    def capabilities(cls) -> PluginCapabilities:
        return PluginCapabilities(
            side_effects=SideEffects.NONE,
            data_access=DataAccess.COMPANY_DOCS,
            sensitive_output_risk=SensitiveOutputRisk.LOW,
        )

    @classmethod
    def schema(cls) -> ConfigSchema:
        return ConfigSchema(fields={})

    def run(self, ctx: PluginCallContext, payload: Any) -> PluginResult:
        if not isinstance(payload, dict) or "candidates" not in payload:
            return PluginResult(status=PluginStatus.FAILED, error="payload must be dict with 'candidates'")

        cands = payload.get("candidates")
        if not isinstance(cands, list):
            return PluginResult(status=PluginStatus.FAILED, error="'candidates' must be a list")

        def score(x: Any) -> float:
            if isinstance(x, dict):
                v = x.get("score", 0.0)
                return float(v) if isinstance(v, (int, float)) else 0.0
            return 0.0

        ranked = sorted(cands, key=score, reverse=True)
        return PluginResult(status=PluginStatus.OK, result={"candidates": ranked})
