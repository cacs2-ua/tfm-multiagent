from __future__ import annotations

PLATFORM_VERSION = "0.1.0"


def parse_semver(v: str) -> tuple[int, int, int]:
    parts = v.strip().split(".")
    if len(parts) != 3:
        raise ValueError(f"Invalid semver '{v}'. Expected 'MAJOR.MINOR.PATCH'.")
    try:
        return int(parts[0]), int(parts[1]), int(parts[2])
    except ValueError as e:
        raise ValueError(f"Invalid semver '{v}'. Must be numeric.") from e


def semver_gte(a: str, b: str) -> bool:
    return parse_semver(a) >= parse_semver(b)


def semver_lte(a: str, b: str) -> bool:
    return parse_semver(a) <= parse_semver(b)
