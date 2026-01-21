from __future__ import annotations

import re
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

_EMAIL_RE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
_PHONE_RE = re.compile(r"(?:(?:\+|00)\s?\d{1,3}[\s-]?)?(?:\d[\s-]?){8,14}\d")


class BasicRedactionPostprocessor(PluginBase):
    """Redact common sensitive tokens (emails / phone-like strings)."""

    @classmethod
    def meta(cls) -> PluginMeta:
        return PluginMeta(
            plugin_id="post.redaction.basic_v1",
            plugin_type=PluginType.POSTPROCESSOR,
            plugin_version="1.0.0",
            min_platform_version=PLATFORM_VERSION,
            max_platform_version=PLATFORM_VERSION,
            description="Redact emails and phone numbers from final answers.",
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
        return ConfigSchema(
            fields={
                "redact_emails": FieldSpec(bool, default=True),
                "redact_phones": FieldSpec(bool, default=True),
                "replacement": FieldSpec(str, default="[REDACTED]"),
            }
        )

    def run(self, ctx: PluginCallContext, payload: Any) -> PluginResult:
        if not isinstance(payload, dict) or "text" not in payload:
            return PluginResult(status=PluginStatus.FAILED, error="payload must be dict with 'text'")

        text = str(payload.get("text", ""))
        rep = str(self.settings.get("replacement", "[REDACTED]"))

        if self.settings.get("redact_emails", True):
            text = _EMAIL_RE.sub(rep, text)
        if self.settings.get("redact_phones", True):
            text = _PHONE_RE.sub(rep, text)

        return PluginResult(status=PluginStatus.OK, result={"text": text})
