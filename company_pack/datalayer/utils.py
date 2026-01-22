from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, Optional


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            b = f.read(chunk_size)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def stable_id(prefix: str, parts: Iterable[str], *, n: int = 16) -> str:
    s = "|".join([p for p in parts])
    h = sha256_text(s)
    return f"{prefix}_{h[:n]}"


def write_json_stable(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Stable formatting for reproducibility
    data = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    path.write_text(data + "\n", encoding="utf-8")


def iter_jsonl(path: Path) -> Iterator[Dict[str, Any]]:
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        yield json.loads(line)


def write_jsonl_stable(path: Path, rows: Iterable[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
            f.write("\n")


def safe_rmtree(dir_path: Path) -> None:
    # Small, dependency-free rmtree
    if not dir_path.exists():
        return
    for root, dirs, files in os.walk(str(dir_path), topdown=False):
        for name in files:
            try:
                Path(root, name).unlink()
            except Exception:
                pass
        for name in dirs:
            try:
                Path(root, name).rmdir()
            except Exception:
                pass
    try:
        dir_path.rmdir()
    except Exception:
        pass
