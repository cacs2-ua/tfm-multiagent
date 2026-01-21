from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Sequence, Tuple, Type, Union

from .types import PluginSettingsError

Validator = Callable[[Any], Tuple[bool, str]]


@dataclass(frozen=True)
class FieldSpec:
    typ: Union[Type[Any], Tuple[Type[Any], ...]]
    required: bool = False
    default: Any = None
    allowed: Optional[Sequence[Any]] = None
    validator: Optional[Validator] = None
    description: str = ""
    secret: bool = False  # if True, should come from env vars in production


@dataclass(frozen=True)
class ConfigSchema:
    fields: Dict[str, FieldSpec]

    def validate_and_resolve(self, settings: Dict[str, Any], *, strict: bool = True) -> Dict[str, Any]:
        if settings is None:
            settings = {}
        if not isinstance(settings, dict):
            raise PluginSettingsError("Plugin settings must be a dict.")

        out: Dict[str, Any] = {}

        if strict:
            unknown = [k for k in settings.keys() if k not in self.fields]
            if unknown:
                raise PluginSettingsError(f"Unknown plugin settings keys: {unknown}")

        for key, spec in self.fields.items():
            if key in settings:
                val = settings[key]
            else:
                if spec.required and spec.default is None:
                    raise PluginSettingsError(f"Missing required setting: '{key}'")
                val = spec.default

            if val is None and spec.required:
                raise PluginSettingsError(f"Setting '{key}' cannot be None.")

            if val is not None and not isinstance(val, spec.typ):
                exp = spec.typ if isinstance(spec.typ, tuple) else (spec.typ,)
                exp_names = [t.__name__ for t in exp]
                raise PluginSettingsError(
                    f"Setting '{key}' must be of type {exp_names}, got {type(val).__name__}."
                )

            if spec.allowed is not None and val is not None and val not in spec.allowed:
                raise PluginSettingsError(f"Setting '{key}' must be one of {list(spec.allowed)}, got {val!r}.")

            if spec.validator is not None and val is not None:
                ok, msg = spec.validator(val)
                if not ok:
                    raise PluginSettingsError(f"Setting '{key}' invalid: {msg}")

            out[key] = val

        return out
