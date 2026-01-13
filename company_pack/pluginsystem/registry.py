from __future__ import annotations

import importlib
import importlib.util
import logging
import time
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Type

try:
    from importlib import metadata as importlib_metadata  # py3.8+
except Exception:  # pragma: no cover
    import importlib_metadata  # type: ignore

from ..models import CompanyPack
from ..versioning import PLATFORM_VERSION, parse_semver, semver_gte, semver_lte
from .base import PluginBase
from .schema import ConfigSchema
from .types import (
    PluginCallContext,
    PluginCompatibilityError,
    PluginMeta,
    PluginNotEnabledError,
    PluginNotFoundError,
    PluginResult,
    PluginStatus,
    PluginValidationError,
    PluginSettingsError,
)


def _default_logger() -> logging.Logger:
    logger = logging.getLogger("plugin_registry")
    if not logger.handlers:
        handler = logging.StreamHandler()
        fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        handler.setFormatter(fmt)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger


def _validate_plugin_id(plugin_id: str) -> None:
    import re

    if not isinstance(plugin_id, str) or not plugin_id.strip():
        raise PluginValidationError("plugin_id must be a non-empty string.")
    if not re.fullmatch(r"[a-z0-9_.\-]+", plugin_id):
        raise PluginValidationError(
            f"plugin_id '{plugin_id}' contains invalid characters. Use [a-z0-9_.-]."
        )


def _validate_meta(meta: PluginMeta) -> None:
    _validate_plugin_id(meta.plugin_id)

    try:
        parse_semver(meta.plugin_version)
        parse_semver(meta.min_platform_version)
        parse_semver(meta.max_platform_version)
    except Exception as e:
        raise PluginValidationError(f"Invalid semver in plugin metadata for '{meta.plugin_id}': {e}") from e

    if not semver_lte(meta.min_platform_version, meta.max_platform_version):
        raise PluginValidationError(
            f"Plugin '{meta.plugin_id}' metadata invalid: min_platform_version must be <= max_platform_version."
        )


def _check_compat(meta: PluginMeta, platform_version: str) -> None:
    if not semver_gte(platform_version, meta.min_platform_version):
        raise PluginCompatibilityError(
            f"Plugin '{meta.plugin_id}' requires platform >= {meta.min_platform_version}, got {platform_version}."
        )
    if not semver_lte(platform_version, meta.max_platform_version):
        raise PluginCompatibilityError(
            f"Plugin '{meta.plugin_id}' requires platform <= {meta.max_platform_version}, got {platform_version}."
        )


def _schema_is_valid(schema: ConfigSchema) -> None:
    if not isinstance(schema, ConfigSchema):
        raise PluginValidationError("Plugin.schema() must return a ConfigSchema instance.")
    if not isinstance(schema.fields, dict):
        raise PluginValidationError("ConfigSchema.fields must be a dict.")


@dataclass(frozen=True)
class PluginSpec:
    cls: Type[PluginBase]
    meta: PluginMeta
    schema: ConfigSchema


class PluginRegistry:
    """
    Global registry of *available* plugins.

    Discovers/registers plugins, then binds them per company pack:
      - enforce plugins.enabled allow-list
      - validate plugins.settings against plugin schema
    """

    def __init__(
        self,
        *,
        platform_version: str = PLATFORM_VERSION,
        strict_settings: bool = True,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.platform_version = platform_version
        self.strict_settings = strict_settings
        self.log = logger or _default_logger()
        self._plugins: Dict[str, PluginSpec] = {}

    def list_plugin_ids(self) -> List[str]:
        return sorted(self._plugins.keys())

    def get_spec(self, plugin_id: str) -> PluginSpec:
        spec = self._plugins.get(plugin_id)
        if spec is None:
            raise PluginNotFoundError(f"Plugin not found: '{plugin_id}'")
        return spec

    def register_plugin_class(self, plugin_cls: Type[PluginBase]) -> None:
        if not isinstance(plugin_cls, type) or not issubclass(plugin_cls, PluginBase):
            raise PluginValidationError("register_plugin_class expects a PluginBase subclass.")

        meta = plugin_cls.meta()
        _validate_meta(meta)
        _check_compat(meta, self.platform_version)

        if meta.plugin_id in self._plugins:
            raise PluginValidationError(f"Duplicate plugin_id: '{meta.plugin_id}'")

        schema = plugin_cls.schema()
        _schema_is_valid(schema)

        self._plugins[meta.plugin_id] = PluginSpec(cls=plugin_cls, meta=meta, schema=schema)

    def register_many(self, plugin_classes: Iterable[Type[PluginBase]]) -> None:
        for cls in plugin_classes:
            self.register_plugin_class(cls)

    # -------- Discovery: Entry points --------
    def discover_entry_points(self, *, group: str = "tfm_customer_support.plugins") -> int:
        """
        Discover plugins from Python entry points.

        Each entry point should load either:
          - a PluginBase subclass, or
          - a callable returning a PluginBase subclass or an iterable of them.
        """
        count = 0
        try:
            eps = importlib_metadata.entry_points()
            if hasattr(eps, "select"):
                candidates = list(eps.select(group=group))
            else:  # pragma: no cover
                candidates = list(eps.get(group, []))  # type: ignore[attr-defined]
        except Exception as e:  # pragma: no cover
            self.log.warning("Entry point discovery failed: %s", e)
            return 0

        for ep in candidates:
            try:
                obj = ep.load()
                if isinstance(obj, type) and issubclass(obj, PluginBase):
                    plugin_classes = [obj]
                else:
                    got = obj()
                    if isinstance(got, type) and issubclass(got, PluginBase):
                        plugin_classes = [got]
                    else:
                        plugin_classes = list(got)

                self.register_many(plugin_classes)
                count += len(plugin_classes)
            except Exception as e:
                self.log.warning("Failed loading entry point '%s': %s", getattr(ep, "name", "<?>"), e)
        return count

    # -------- Discovery: Local plugins folder --------
    def discover_local_dir(self, plugins_dir: Path) -> int:
        """
        Discover plugins from a local folder.

        Each .py file can export:
          - PLUGIN_CLASSES: list[PluginBaseSubclass], or
          - get_plugin_classes(): callable returning list[PluginBaseSubclass]
        """
        plugins_dir = Path(plugins_dir).expanduser().resolve()
        if not plugins_dir.exists() or not plugins_dir.is_dir():
            return 0

        count = 0
        for file in sorted(plugins_dir.glob("*.py")):
            if file.name.startswith("_"):
                continue
            try:
                module = _import_module_from_file(file)
                plugin_classes = _extract_plugin_classes(module)
                self.register_many(plugin_classes)
                count += len(plugin_classes)
            except Exception as e:
                self.log.warning("Failed discovering plugins from %s: %s", file, e)
        return count

    # -------- Per-company binding --------
    def bind_company(self, pack: CompanyPack) -> "BoundPluginRegistry":
        enabled = list(pack.plugins.enabled)

        for pid in enabled:
            if pid not in self._plugins:
                raise PluginNotFoundError(
                    f"Company '{pack.manifest.company_id}' enabled unknown plugin '{pid}'."
                )

        resolved_settings: Dict[str, Dict[str, object]] = {}
        for pid in enabled:
            spec = self._plugins[pid]
            settings = pack.plugins.get_settings(pid)
            resolved = spec.schema.validate_and_resolve(settings, strict=self.strict_settings)
            resolved_settings[pid] = resolved

        return BoundPluginRegistry(
            registry=self,
            pack=pack,
            enabled=enabled,
            resolved_settings=resolved_settings,
            logger=self.log,
        )


@dataclass
class BoundPluginRegistry:
    """Registry bound to one CompanyPack (enforces allow-list)."""

    registry: PluginRegistry
    pack: CompanyPack
    enabled: List[str]
    resolved_settings: Dict[str, Dict[str, object]]
    logger: logging.Logger

    def __post_init__(self) -> None:
        self._instances: Dict[str, PluginBase] = {}

    def is_enabled(self, plugin_id: str) -> bool:
        return plugin_id in self.enabled

    def _get_instance(self, plugin_id: str) -> PluginBase:
        if plugin_id in self._instances:
            return self._instances[plugin_id]

        spec = self.registry.get_spec(plugin_id)
        settings = dict(self.resolved_settings.get(plugin_id, {}))
        inst = spec.cls(settings=settings, services={})
        inst.initialize()
        self._instances[plugin_id] = inst
        return inst

    def invoke(self, plugin_id: str, ctx: PluginCallContext, payload: Any) -> PluginResult:
        if plugin_id not in self.registry._plugins:
            raise PluginNotFoundError(f"Plugin not found: '{plugin_id}'")

        if not self.is_enabled(plugin_id):
            raise PluginNotEnabledError(
                f"Plugin '{plugin_id}' is not enabled for company '{self.pack.manifest.company_id}'."
            )

        spec = self.registry.get_spec(plugin_id)

        start = time.time()
        try:
            inst = self._get_instance(plugin_id)
            res = inst.run(ctx, payload)
            if not isinstance(res, PluginResult):
                raise PluginValidationError(
                    f"Plugin '{plugin_id}' returned non-PluginResult ({type(res).__name__})."
                )
        except Exception as e:
            res = PluginResult(status=PluginStatus.FAILED, error=str(e), result=None)

        dur_ms = int((time.time() - start) * 1000)

        payload_summary = _summarize_payload(payload)
        self.logger.info(
            "plugin_call company=%s trace=%s plugin=%s type=%s status=%s dur_ms=%s payload=%s",
            ctx.company_id,
            ctx.trace_id,
            plugin_id,
            spec.meta.plugin_type.value,
            res.status.value,
            dur_ms,
            payload_summary,
        )

        meta = dict(res.metadata)
        meta.setdefault("duration_ms", dur_ms)
        meta.setdefault("plugin_id", plugin_id)
        meta.setdefault("plugin_type", spec.meta.plugin_type.value)

        return PluginResult(
            status=res.status,
            result=res.result,
            error=res.error,
            warnings=list(res.warnings),
            metadata=meta,
        )

    def shutdown(self) -> None:
        for _, inst in list(self._instances.items()):
            try:
                inst.shutdown()
            except Exception:
                pass
        self._instances.clear()


# -------- Local discovery helpers --------

def _import_module_from_file(path: Path) -> types.ModuleType:
    module_name = f"_local_plugin_{path.stem}_{abs(hash(str(path)))}"
    spec = importlib.util.spec_from_file_location(module_name, str(path))
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not import plugin module: {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[attr-defined]
    return mod


def _extract_plugin_classes(mod: types.ModuleType) -> List[Type[PluginBase]]:
    if hasattr(mod, "PLUGIN_CLASSES"):
        val = getattr(mod, "PLUGIN_CLASSES")
        if not isinstance(val, list):
            raise PluginValidationError("PLUGIN_CLASSES must be a list.")
        return _filter_plugin_classes(val)

    if hasattr(mod, "get_plugin_classes"):
        fn = getattr(mod, "get_plugin_classes")
        if not callable(fn):
            raise PluginValidationError("get_plugin_classes must be callable.")
        res = fn()
        if not isinstance(res, list):
            res = list(res)
        return _filter_plugin_classes(res)

    raise PluginValidationError("No PLUGIN_CLASSES or get_plugin_classes() found.")


def _filter_plugin_classes(items: Iterable[Any]) -> List[Type[PluginBase]]:
    out: List[Type[PluginBase]] = []
    for x in items:
        if isinstance(x, type) and issubclass(x, PluginBase):
            out.append(x)
        else:
            raise PluginValidationError(f"Invalid plugin class export: {x!r}")
    return out


def _summarize_payload(payload: Any) -> Dict[str, Any]:
    if isinstance(payload, dict):
        keys = sorted([str(k) for k in payload.keys()])[:30]
        return {"type": "dict", "keys": keys}
    return {"type": type(payload).__name__}
