from __future__ import annotations

import time
import uuid
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


class TicketMockTool(PluginBase):
    """Mock ticket creation tool (no external side effects)."""

    @classmethod
    def meta(cls) -> PluginMeta:
        return PluginMeta(
            plugin_id="tool.ticket.mock_v1",
            plugin_type=PluginType.TOOL,
            plugin_version="1.0.0",
            min_platform_version=PLATFORM_VERSION,
            max_platform_version=PLATFORM_VERSION,
            description="Create a mock support ticket (for demos/tests).",
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
                "default_priority": FieldSpec(str, required=False, default="normal", allowed=["low", "normal", "high"]),
                "max_title_len": FieldSpec(int, required=False, default=120),
            }
        )

    def run(self, ctx: PluginCallContext, payload: Any) -> PluginResult:
        if not isinstance(payload, dict):
            return PluginResult(status=PluginStatus.FAILED, error="payload must be dict")

        subject = str(payload.get("subject", "")).strip()
        message = str(payload.get("message", "")).strip()
        if not subject:
            return PluginResult(status=PluginStatus.FAILED, error="missing subject")

        max_len = int(self.settings.get("max_title_len", 120))
        if len(subject) > max_len:
            subject = subject[:max_len]

        ticket = {
            "ticket_id": "TCK-" + uuid.uuid4().hex[:10],
            "subject": subject,
            "priority": payload.get("priority") or self.settings.get("default_priority", "normal"),
            "created_at": int(time.time()),
            "conversation_id": ctx.conversation_id,
            "company_id": ctx.company_id,
            "status": "open",
            "message_preview": message[:200],
        }
        return PluginResult(status=PluginStatus.OK, result=ticket, metadata={"mock": True})
