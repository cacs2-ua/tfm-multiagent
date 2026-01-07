from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from .io_utils import write_json, write_yaml
from .versioning import PLATFORM_VERSION


def create_company_pack_skeleton(
    out_dir: str | Path,
    company_id: str,
    company_name: str,
    sector: str = "generic",
    primary_language: str = "en",
) -> Path:
    root = Path(out_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    (root / "docs").mkdir(exist_ok=True)
    (root / "eval").mkdir(exist_ok=True)

    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    manifest: Dict[str, Any] = {
        "schema_version": 1,
        "company_id": company_id,
        "company_name": company_name,
        "pack_version": "1.0.0",
        "created_at": now,
        "compatibility": {
            "min_platform_version": PLATFORM_VERSION,
            "max_platform_version": PLATFORM_VERSION,
        },
        "allow_empty_docs": False,
    }

    metadata: Dict[str, Any] = {
        "company_id": company_id,
        "sector": sector,
        "primary_language": primary_language,
        "allowed_languages": [primary_language],
        "tone": {"style": "neutral", "verbosity": "concise", "empathy": "medium"},
        "support_scope": {},
        "escalation": {
            "human_support_message": "If you want, I can guide you to contact support.",
            "contact": {},
        },
        "compliance_tags": [],
    }

    rules: Dict[str, Any] = {
        "routing": {
            "always_call_researcher_topics": ["refund", "warranty", "policy", "pricing"],
            "skip_researcher_intents": ["greeting", "small_talk"],
        },
        "answer_policy": {
            "require_citations_for_topics": ["refund", "warranty", "policy", "pricing"],
            "forbid_speculation": True,
        },
        "escalation": {
            "ask_clarification_on_low_confidence": True,
            "escalate_on_sensitive_requests": True,
        },
        "arbitration": {
            "prefer_evidence_over_draft": True,
            "on_insufficient_evidence": "abstain_or_clarify",
        },
    }

    plugins: Dict[str, Any] = {
        "enabled": [],     # allow-list; default deny-by-default
        "settings": {},
    }

    retrieval: Dict[str, Any] = {
        "chunk_size": 800,
        "chunk_overlap": 100,
        "top_k": 5,
        "filters": {},
    }

    write_json(root / "manifest.json", manifest)
    write_yaml(root / "metadata.yaml", metadata)
    write_yaml(root / "rules.yaml", rules)
    write_yaml(root / "plugins.yaml", plugins)
    write_yaml(root / "retrieval.yaml", retrieval)

    # Optional eval smoke tests example
    write_yaml(root / "eval" / "smoke_tests.yaml", {
        "cases": [
            {
                "id": "smoke_policy",
                "query": "What is your refund policy?",
                "tags": ["policy"],
                "expected_behavior": "Answer with citations or say insufficient evidence.",
            }
        ]
    })

    return root
