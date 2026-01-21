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


class CRMMockTool(PluginBase):
    """Mock CRM lookup (returns synthetic record)."""

    @classmethod
    def meta(cls) -> PluginMeta:
        return PluginMeta(
            plugin_id="tool.crm.mock_v1",
            plugin_type=PluginType.TOOL,
            plugin_version="1.0.0",
            min_platform_version=PLATFORM_VERSION,
            max_platform_version=PLATFORM_VERSION,
            description="Mock CRM lookup by email/customer_id.",
            author="TFM",
            license="MIT",
        )

    @classmethod
    def capabilities(cls) -> PluginCapabilities:
        return PluginCapabilities(
            side_effects=SideEffects.NONE,
            data_access=DataAccess.CONVERSATION,
            sensitive_output_risk=SensitiveOutputRisk.MEDIUM,
        )

    @classmethod
    def schema(cls) -> ConfigSchema:
        return ConfigSchema(
            fields={
                "allow_email_lookup": FieldSpec(bool, required=False, default=True),
                "allow_id_lookup": FieldSpec(bool, required=False, default=True),
            }
        )

    def run(self, ctx: PluginCallContext, payload: Any) -> PluginResult:
        if not isinstance(payload, dict):
            return PluginResult(status=PluginStatus.FAILED, error="payload must be dict")

        email = payload.get("email")
        cust_id = payload.get("customer_id")

        if email and not self.settings.get("allow_email_lookup", True):
            return PluginResult(status=PluginStatus.SKIPPED, result=None, warnings=["email lookup disabled by settings"])
        if cust_id and not self.settings.get("allow_id_lookup", True):
            return PluginResult(status=PluginStatus.SKIPPED, result=None, warnings=["id lookup disabled by settings"])

        if not email and not cust_id:
            return PluginResult(status=PluginStatus.FAILED, error="Provide 'email' or 'customer_id'.")

        key = str(email or cust_id).lower()
        record = {
            "customer_id": cust_id or ("CUST-" + key.replace("@", "_")[:12]),
            "email": email,
            "tier": "standard" if "vip" not in key else "vip",
            "open_tickets": 0 if "new" in key else 2,
            "notes": "Mock CRM record (demo only).",
        }
        return PluginResult(status=PluginStatus.OK, result=record, metadata={"mock": True})
