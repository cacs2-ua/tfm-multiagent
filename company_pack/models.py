from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .errors import CompanyPackValidationError
from .versioning import PLATFORM_VERSION, semver_gte, semver_lte


def _req_str(d: Dict[str, Any], k: str) -> str:
    v = d.get(k)
    if not isinstance(v, str) or not v.strip():
        raise CompanyPackValidationError(f"Field '{k}' must be a non-empty string.")
    return v.strip()


def _req_int(d: Dict[str, Any], k: str) -> int:
    v = d.get(k)
    if not isinstance(v, int):
        raise CompanyPackValidationError(f"Field '{k}' must be an integer.")
    return v


def _opt_bool(d: Dict[str, Any], k: str, default: bool) -> bool:
    v = d.get(k, default)
    if not isinstance(v, bool):
        raise CompanyPackValidationError(f"Field '{k}' must be boolean.")
    return v


def _opt_dict(d: Dict[str, Any], k: str) -> Dict[str, Any]:
    v = d.get(k, {})
    if v is None:
        return {}
    if not isinstance(v, dict):
        raise CompanyPackValidationError(f"Field '{k}' must be a dict.")
    return v


def _opt_list_str(d: Dict[str, Any], k: str) -> List[str]:
    v = d.get(k, [])
    if v is None:
        return []
    if not isinstance(v, list) or any(not isinstance(x, str) for x in v):
        raise CompanyPackValidationError(f"Field '{k}' must be a list of strings.")
    return [x.strip() for x in v if x.strip()]


@dataclass(frozen=True)
class Compatibility:
    min_platform_version: str
    max_platform_version: str

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Compatibility":
        min_v = _req_str(d, "min_platform_version")
        max_v = _req_str(d, "max_platform_version")
        if not semver_lte(min_v, max_v):
            raise CompanyPackValidationError(
                f"compatibility.min_platform_version ({min_v}) must be <= max_platform_version ({max_v})"
            )
        return Compatibility(min_platform_version=min_v, max_platform_version=max_v)

    def check(self, platform_version: str) -> None:
        if not semver_gte(platform_version, self.min_platform_version):
            raise CompanyPackValidationError(
                f"Platform {platform_version} < min supported {self.min_platform_version}"
            )
        if not semver_lte(platform_version, self.max_platform_version):
            raise CompanyPackValidationError(
                f"Platform {platform_version} > max supported {self.max_platform_version}"
            )


@dataclass(frozen=True)
class Manifest:
    schema_version: int
    company_id: str
    company_name: str
    pack_version: str
    created_at: str
    compatibility: Compatibility
    allow_empty_docs: bool

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Manifest":
        schema_version = _req_int(d, "schema_version")
        company_id = _req_str(d, "company_id")
        company_name = _req_str(d, "company_name")
        pack_version = _req_str(d, "pack_version")
        created_at = _req_str(d, "created_at")

        try:
            datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        except Exception as e:
            raise CompanyPackValidationError(
                f"manifest.created_at must be ISO8601. Got '{created_at}'."
            ) from e

        comp_raw = d.get("compatibility", {})
        if not isinstance(comp_raw, dict):
            raise CompanyPackValidationError("manifest.compatibility must be a dict.")
        compatibility = Compatibility.from_dict(comp_raw)

        allow_empty_docs = _opt_bool(d, "allow_empty_docs", False)

        return Manifest(
            schema_version=schema_version,
            company_id=company_id,
            company_name=company_name,
            pack_version=pack_version,
            created_at=created_at,
            compatibility=compatibility,
            allow_empty_docs=allow_empty_docs,
        )


@dataclass(frozen=True)
class Tone:
    style: str
    verbosity: str
    empathy: str

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Tone":
        style = str(d.get("style", "neutral")).strip() or "neutral"
        verbosity = str(d.get("verbosity", "concise")).strip() or "concise"
        empathy = str(d.get("empathy", "medium")).strip() or "medium"
        return Tone(style=style, verbosity=verbosity, empathy=empathy)


@dataclass(frozen=True)
class Metadata:
    company_id: str
    sector: str
    primary_language: str
    allowed_languages: List[str]
    tone: Tone
    support_scope: Dict[str, Any]
    escalation: Dict[str, Any]
    compliance_tags: List[str]

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Metadata":
        company_id = _req_str(d, "company_id")
        sector = _req_str(d, "sector")
        primary_language = _req_str(d, "primary_language")
        allowed_languages = _opt_list_str(d, "allowed_languages")
        tone = Tone.from_dict(_opt_dict(d, "tone"))
        support_scope = _opt_dict(d, "support_scope")
        escalation = _opt_dict(d, "escalation")
        compliance_tags = _opt_list_str(d, "compliance_tags")
        return Metadata(
            company_id=company_id,
            sector=sector,
            primary_language=primary_language,
            allowed_languages=allowed_languages,
            tone=tone,
            support_scope=support_scope,
            escalation=escalation,
            compliance_tags=compliance_tags,
        )


@dataclass(frozen=True)
class Rules:
    routing: Dict[str, Any]
    answer_policy: Dict[str, Any]
    escalation: Dict[str, Any]
    arbitration: Dict[str, Any]

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Rules":
        # enforce the stable contract: these top-level keys must exist
        for key in ["routing", "answer_policy", "escalation", "arbitration"]:
            if key not in d:
                raise CompanyPackValidationError(
                    f"rules.yaml must contain top-level '{key}' section."
                )

        routing = _opt_dict(d, "routing")
        answer_policy = _opt_dict(d, "answer_policy")
        escalation = _opt_dict(d, "escalation")
        arbitration = _opt_dict(d, "arbitration")
        return Rules(
            routing=routing,
            answer_policy=answer_policy,
            escalation=escalation,
            arbitration=arbitration,
        )


@dataclass(frozen=True)
class PluginsConfig:
    enabled: List[str]
    settings: Dict[str, Any]

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "PluginsConfig":
        enabled = _opt_list_str(d, "enabled")  # allow-list (deny-by-default)
        settings = _opt_dict(d, "settings")
        for k, v in settings.items():
            if not isinstance(k, str):
                raise CompanyPackValidationError("plugins.settings keys must be strings.")
            if not isinstance(v, dict):
                raise CompanyPackValidationError(f"plugins.settings['{k}'] must be a dict.")
        return PluginsConfig(enabled=enabled, settings=settings)

    def is_enabled(self, plugin_id: str) -> bool:
        return plugin_id in self.enabled

    def get_settings(self, plugin_id: str) -> Dict[str, Any]:
        v = self.settings.get(plugin_id, {})
        return v if isinstance(v, dict) else {}


@dataclass(frozen=True)
class RetrievalConfig:
    chunk_size: Optional[int]
    chunk_overlap: Optional[int]
    top_k: Optional[int]
    filters: Dict[str, Any]

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "RetrievalConfig":
        def opt_int(key: str) -> Optional[int]:
            v = d.get(key)
            if v is None:
                return None
            if not isinstance(v, int):
                raise CompanyPackValidationError(f"retrieval.{key} must be int.")
            return v

        chunk_size = opt_int("chunk_size")
        chunk_overlap = opt_int("chunk_overlap")
        top_k = opt_int("top_k")
        filters = _opt_dict(d, "filters")

        if chunk_size is not None and not (50 <= chunk_size <= 5000):
            raise CompanyPackValidationError("retrieval.chunk_size out of range (50..5000).")
        if chunk_overlap is not None and chunk_overlap < 0:
            raise CompanyPackValidationError("retrieval.chunk_overlap must be >= 0.")
        if top_k is not None and not (1 <= top_k <= 50):
            raise CompanyPackValidationError("retrieval.top_k out of range (1..50).")

        return RetrievalConfig(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            top_k=top_k,
            filters=filters,
        )


@dataclass(frozen=True)
class CompanyPack:
    root: Path
    manifest: Manifest
    metadata: Metadata
    rules: Rules
    plugins: PluginsConfig
    retrieval: Optional[RetrievalConfig]
    docs_dir: Path

    def list_pdfs(self) -> List[Path]:
        if not self.docs_dir.exists():
            return []
        return sorted([p for p in self.docs_dir.rglob("*.pdf") if p.is_file()])

    def validate_consistency(self, platform_version: str = PLATFORM_VERSION) -> None:
        # company_id must match across manifest and metadata
        if self.manifest.company_id != self.metadata.company_id:
            raise CompanyPackValidationError(
                f"company_id mismatch: manifest '{self.manifest.company_id}' != metadata '{self.metadata.company_id}'"
            )

        # platform compatibility
        self.manifest.compatibility.check(platform_version)

        # docs requirement
        if not self.list_pdfs() and not self.manifest.allow_empty_docs:
            raise CompanyPackValidationError(
                "No PDFs found under docs/ and manifest.allow_empty_docs is false."
            )
