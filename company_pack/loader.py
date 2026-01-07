from __future__ import annotations

import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Optional, Tuple, Union

from .errors import (
    CompanyPackExtractionError,
    CompanyPackNotFoundError,
    CompanyPackValidationError,
)
from .io_utils import read_json, read_yaml
from .models import CompanyPack, Manifest, Metadata, PluginsConfig, RetrievalConfig, Rules
from .versioning import PLATFORM_VERSION

REQUIRED_FILES = {"manifest.json", "metadata.yaml", "rules.yaml", "plugins.yaml"}
DOCS_DIRNAME = "docs"


def _is_zip(p: Path) -> bool:
    return p.is_file() and p.suffix.lower() == ".zip"


def _safe_extract_zip(zip_path: Path, extract_to: Path) -> None:
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            for member in zf.namelist():
                # Prevent ZipSlip path traversal
                dest = (extract_to / member).resolve()
                if not str(dest).startswith(str(extract_to.resolve())):
                    raise CompanyPackExtractionError(
                        f"Unsafe zip entry (path traversal): {member}"
                    )
            zf.extractall(extract_to)
    except CompanyPackExtractionError:
        raise
    except Exception as e:
        raise CompanyPackExtractionError(f"Failed to extract zip '{zip_path}': {e}") from e


def _find_pack_root(dir_path: Path) -> Path:
    # Accept direct pack root
    if (dir_path / "manifest.json").exists():
        return dir_path

    # Accept a folder that contains exactly 1 child folder which is the pack root
    children = [p for p in dir_path.iterdir() if p.is_dir()]
    if len(children) == 1 and (children[0] / "manifest.json").exists():
        return children[0]

    raise CompanyPackNotFoundError(
        f"Could not locate pack root in '{dir_path}'. "
        "Expected manifest.json at root (or inside the single child folder)."
    )


def _validate_files_and_dirs(pack_root: Path) -> None:
    missing = [f for f in REQUIRED_FILES if not (pack_root / f).exists()]
    if missing:
        raise CompanyPackValidationError(f"Missing required files: {missing}")

    docs_dir = pack_root / DOCS_DIRNAME
    if not docs_dir.exists() or not docs_dir.is_dir():
        raise CompanyPackValidationError("Missing required directory: docs/")


def load_company_pack(
    pack_path: Union[str, Path],
    platform_version: str = PLATFORM_VERSION,
    keep_temp: bool = False,
) -> Tuple[CompanyPack, Optional[Path]]:
    """
    Load and validate a company pack from a folder or .zip.

    Returns:
      (CompanyPack, temp_dir_if_zip)
    If input is a folder -> temp_dir_if_zip is None.
    If input is a zip -> temp dir path is returned; caller may delete it.
    """
    p = Path(pack_path).expanduser().resolve()
    if not p.exists():
        raise CompanyPackNotFoundError(f"Pack path does not exist: {p}")

    temp_dir: Optional[Path] = None
    try:
        if _is_zip(p):
            temp_dir = Path(tempfile.mkdtemp(prefix="company_pack_"))
            _safe_extract_zip(p, temp_dir)
            pack_root = _find_pack_root(temp_dir)
        else:
            if not p.is_dir():
                raise CompanyPackNotFoundError(f"Pack path must be a folder or .zip: {p}")
            pack_root = _find_pack_root(p)

        _validate_files_and_dirs(pack_root)

        manifest = Manifest.from_dict(read_json(pack_root / "manifest.json"))
        manifest.compatibility.check(platform_version)

        metadata = Metadata.from_dict(read_yaml(pack_root / "metadata.yaml"))
        rules = Rules.from_dict(read_yaml(pack_root / "rules.yaml"))
        plugins = PluginsConfig.from_dict(read_yaml(pack_root / "plugins.yaml"))

        retrieval_path = pack_root / "retrieval.yaml"
        retrieval = (
            RetrievalConfig.from_dict(read_yaml(retrieval_path))
            if retrieval_path.exists()
            else None
        )

        pack = CompanyPack(
            root=pack_root,
            manifest=manifest,
            metadata=metadata,
            rules=rules,
            plugins=plugins,
            retrieval=retrieval,
            docs_dir=pack_root / DOCS_DIRNAME,
        )

        pack.validate_consistency(platform_version=platform_version)
        return pack, temp_dir

    except Exception:
        if temp_dir is not None and not keep_temp:
            shutil.rmtree(temp_dir, ignore_errors=True)
        raise
