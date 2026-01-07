from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from .errors import CompanyPackValidationError

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None


def read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise CompanyPackValidationError(f"Missing file: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        raise CompanyPackValidationError(f"Invalid JSON in {path}: {e}") from e


def write_json(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")


def read_yaml(path: Path) -> Dict[str, Any]:
    if yaml is None:
        raise CompanyPackValidationError("PyYAML not installed. Run: pip install pyyaml")
    if not path.exists():
        raise CompanyPackValidationError(f"Missing file: {path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if data is None:
            return {}
        if not isinstance(data, dict):
            raise CompanyPackValidationError(f"YAML root must be a mapping in {path}")
        return data
    except CompanyPackValidationError:
        raise
    except Exception as e:
        raise CompanyPackValidationError(f"Invalid YAML in {path}: {e}") from e


def write_yaml(path: Path, obj: Dict[str, Any]) -> None:
    if yaml is None:
        raise CompanyPackValidationError("PyYAML not installed. Run: pip install pyyaml")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(obj, sort_keys=False), encoding="utf-8")
