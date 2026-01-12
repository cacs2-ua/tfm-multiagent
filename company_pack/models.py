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


SUPPORTED_PACK_SCHEMA_VERSIONS = {1}


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
        if schema_version not in SUPPORTED_PACK_SCHEMA_VERSIONS:
            raise CompanyPackValidationError(
                f"Unsupported pack schema_version: {schema_version}. Supported: {sorted(SUPPORTED_PACK_SCHEMA_VERSIONS)}"
            )

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
        enabled = _opt_list_str(d, "enabled")
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
    chunk_size: int
    chunk_overlap: int
    top_k: int
    filters: Dict[str, Any]
    schema_version: int = 1

    @staticmethod
    def default() -> "RetrievalConfig":
        return RetrievalConfig(
            chunk_size=800,
            chunk_overlap=100,
            top_k=5,
            filters={},
            schema_version=1,
        )

    @staticmethod
    def from_dict(d: Dict[str, Any], defaults: Optional["RetrievalConfig"] = None) -> "RetrievalConfig":
        base = defaults or RetrievalConfig.default()

        sv = d.get("schema_version", base.schema_version)
        if not isinstance(sv, int) or sv != 1:
            raise CompanyPackValidationError("retrieval.schema_version must be 1 (supported)")

        def opt_int(key: str, default_val: int) -> int:
            v = d.get(key, default_val)
            if not isinstance(v, int):
                raise CompanyPackValidationError(f"retrieval.{key} must be int.")
            return v

        chunk_size = opt_int("chunk_size", base.chunk_size)
        chunk_overlap = opt_int("chunk_overlap", base.chunk_overlap)
        top_k = opt_int("top_k", base.top_k)
        filters = _opt_dict(d, "filters") if "filters" in d else dict(base.filters)

        if not (50 <= chunk_size <= 5000):
            raise CompanyPackValidationError("retrieval.chunk_size out of range (50..5000).")
        if chunk_overlap < 0:
            raise CompanyPackValidationError("retrieval.chunk_overlap must be >= 0.")
        if not (1 <= top_k <= 50):
            raise CompanyPackValidationError("retrieval.top_k out of range (1..50).")

        return RetrievalConfig(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            top_k=top_k,
            filters=filters,
            schema_version=sv,
        )


@dataclass(frozen=True)
class PromptsConfig:
    """
    Parsed representation of prompts.yaml (schema v1).
    We intentionally keep it flexible as dict, but validated.
    """
    raw: Dict[str, Any]

    def agent_system(self, agent_id: str) -> str:
        agents = self.raw.get("agents", {})
        if not isinstance(agents, dict):
            raise CompanyPackValidationError("prompts.agents invalid")
        cfg = agents.get(agent_id, {})
        if not isinstance(cfg, dict):
            raise CompanyPackValidationError(f"prompts.agents.{agent_id} invalid")
        system = cfg.get("system")
        if not isinstance(system, str) or not system.strip():
            raise CompanyPackValidationError(f"prompts.agents.{agent_id}.system missing/invalid")
        return system

    def agent_persona(self, agent_id: str) -> str:
        agents = self.raw.get("agents", {})
        if not isinstance(agents, dict):
            return ""
        cfg = agents.get(agent_id, {})
        if not isinstance(cfg, dict):
            return ""
        persona = cfg.get("persona", "")
        return persona if isinstance(persona, str) else ""

    def templates(self) -> Dict[str, str]:
        t = self.raw.get("templates", {})
        if t is None:
            return {}
        if not isinstance(t, dict):
            raise CompanyPackValidationError("prompts.templates must be dict")
        out: Dict[str, str] = {}
        for k, v in t.items():
            if isinstance(k, str) and isinstance(v, str):
                out[k] = v
        return out


@dataclass(frozen=True)
class CompanyPack:
    root: Path
    manifest: Manifest
    metadata: Metadata
    rules: Rules
    plugins: PluginsConfig
    retrieval: RetrievalConfig
    prompts: PromptsConfig
    docs_dir: Path

    def list_pdfs(self) -> List[Path]:
        if not self.docs_dir.exists():
            return []
        return sorted([p for p in self.docs_dir.rglob("*.pdf") if p.is_file()])

    def validate_consistency(self, platform_version: str = PLATFORM_VERSION) -> None:
        if self.manifest.company_id != self.metadata.company_id:
            raise CompanyPackValidationError(
                f"company_id mismatch: manifest '{self.manifest.company_id}' != metadata '{self.metadata.company_id}'"
            )

        self.manifest.compatibility.check(platform_version)

        if not self.list_pdfs() and not self.manifest.allow_empty_docs:
            raise CompanyPackValidationError(
                "No PDFs found under docs/ and manifest.allow_empty_docs is false."
            )

    def prompt_variables(self) -> Dict[str, Any]:
        return {
            "company_id": self.manifest.company_id,
            "company_name": self.manifest.company_name,
            "sector": self.metadata.sector,
            "primary_language": self.metadata.primary_language,
            "tone_style": self.metadata.tone.style,
            "tone_verbosity": self.metadata.tone.verbosity,
            "tone_empathy": self.metadata.tone.empathy,
        }
