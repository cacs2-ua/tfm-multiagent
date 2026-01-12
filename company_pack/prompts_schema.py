from __future__ import annotations

from typing import Any, Dict, List


SUPPORTED_PROMPTS_SCHEMA_VERSIONS = {1}
REQUIRED_AGENT_KEYS = {"care", "manager", "researcher"}


def default_prompts_dict(company_name: str, sector: str, primary_language: str) -> Dict[str, Any]:
    return {
        "schema_version": 1,
        "agents": {
            "care": {
                "system": (
                    "You are the Care Agent for {company_name} (sector: {sector}). "
                    "You speak in {primary_language}. You are customer-facing and must be clear and helpful.\n"
                    "Rules:\n"
                    "- Follow Manager decisions.\n"
                    "- Use Researcher evidence when provided.\n"
                    "- If evidence is insufficient, ask clarification or abstain.\n"
                    "- Keep the answer concise, structured, and safe."
                ),
                "persona": "Helpful, precise, customer-friendly assistant.",
                "guidelines": [
                    "Ask clarifying questions when the user request is ambiguous.",
                    "Avoid speculation; prefer evidence-backed statements.",
                    "If citations are required by policy, include them or abstain.",
                ],
            },
            "manager": {
                "system": (
                    "You are the Manager Agent for {company_name} (sector: {sector}). "
                    "You enforce business rules and decide routing.\n"
                    "Responsibilities:\n"
                    "- Decide when to call Researcher.\n"
                    "- Enforce answer policy (citations, disclaimers, refusals).\n"
                    "- Resolve conflicts between drafts and evidence.\n"
                    "- Prefer safe, evidence-first outcomes."
                ),
                "persona": "Policy enforcer and arbitration agent (rules-first).",
                "guidelines": [
                    "Apply company rules deterministically where possible.",
                    "Call Researcher for policy/product factual queries.",
                    "If Researcher reports insufficient evidence, instruct Care to abstain/clarify.",
                ],
            },
            "researcher": {
                "system": (
                    "You are the Researcher Agent for {company_name} (sector: {sector}). "
                    "You perform retrieval (RAG) over company documents and return evidence.\n"
                    "Rules:\n"
                    "- Return structured evidence with citations (document + page/section if available).\n"
                    "- Do not invent facts beyond retrieved sources.\n"
                    "- If insufficient evidence, say so explicitly."
                ),
                "persona": "Evidence retrieval and verification agent.",
                "guidelines": [
                    "Retrieve relevant passages and summarize them faithfully.",
                    "Provide citations for each claim where possible.",
                    "Flag contradictions or uncertainty explicitly.",
                ],
            },
        },
        "templates": {
            "insufficient_evidence": (
                "I can’t confirm this from the available company documents. "
                "Could you clarify what exactly you need, or provide more details?"
            ),
            "refusal": "I can’t help with that request.",
        },
    }


def validate_prompts_file_minimal(d: Dict[str, Any]) -> None:
    """
    Validation for the *file itself* (prompts.yaml):
    - must contain agents with keys care/manager/researcher
    - agent entries must be dicts (can be empty to rely on defaults)
    - does NOT require system/persona/guidelines (defaults will fill)
    """
    if not isinstance(d, dict):
        raise ValueError("prompts root must be a mapping/dict")

    sv = d.get("schema_version", 1)
    if not isinstance(sv, int) or sv not in SUPPORTED_PROMPTS_SCHEMA_VERSIONS:
        raise ValueError(f"prompts.schema_version must be one of {sorted(SUPPORTED_PROMPTS_SCHEMA_VERSIONS)}")

    agents = d.get("agents")
    if not isinstance(agents, dict):
        raise ValueError("prompts.agents must be a mapping/dict")

    missing = [k for k in REQUIRED_AGENT_KEYS if k not in agents]
    if missing:
        raise ValueError(f"prompts.agents is missing required agents: {missing}")

    for agent_id in REQUIRED_AGENT_KEYS:
        cfg = agents.get(agent_id)
        if not isinstance(cfg, dict):
            raise ValueError(f"prompts.agents.{agent_id} must be a dict")

    templates = d.get("templates", {})
    if templates is None:
        templates = {}
    if not isinstance(templates, dict) or any(
        not isinstance(k, str) or not isinstance(v, str) for k, v in templates.items()
    ):
        raise ValueError("prompts.templates must be a dict[str,str]")


def validate_prompts_dict(d: Dict[str, Any]) -> None:
    """
    Validation for the *resolved merged* prompts (defaults + prompts.yaml):
    - requires non-empty system prompts
    - requires guidelines list-of-strings
    """
    if not isinstance(d, dict):
        raise ValueError("prompts root must be a mapping/dict")

    sv = d.get("schema_version", 1)
    if not isinstance(sv, int) or sv not in SUPPORTED_PROMPTS_SCHEMA_VERSIONS:
        raise ValueError(f"prompts.schema_version must be one of {sorted(SUPPORTED_PROMPTS_SCHEMA_VERSIONS)}")

    agents = d.get("agents")
    if not isinstance(agents, dict):
        raise ValueError("prompts.agents must be a mapping/dict")

    missing = [k for k in REQUIRED_AGENT_KEYS if k not in agents]
    if missing:
        raise ValueError(f"prompts.agents is missing required agents: {missing}")

    for agent_id in REQUIRED_AGENT_KEYS:
        cfg = agents.get(agent_id)
        if not isinstance(cfg, dict):
            raise ValueError(f"prompts.agents.{agent_id} must be a dict")
        system = cfg.get("system")
        if not isinstance(system, str) or not system.strip():
            raise ValueError(f"prompts.agents.{agent_id}.system must be a non-empty string")

        persona = cfg.get("persona", "")
        if persona is not None and not isinstance(persona, str):
            raise ValueError(f"prompts.agents.{agent_id}.persona must be a string")

        guidelines = cfg.get("guidelines", [])
        if guidelines is None:
            guidelines = []
        if not isinstance(guidelines, list) or any(not isinstance(x, str) for x in guidelines):
            raise ValueError(f"prompts.agents.{agent_id}.guidelines must be a list of strings")

    templates = d.get("templates", {})
    if templates is None:
        templates = {}
    if not isinstance(templates, dict) or any(
        not isinstance(k, str) or not isinstance(v, str) for k, v in templates.items()
    ):
        raise ValueError("prompts.templates must be a dict[str,str]")


def deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base)
    for k, v in override.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def safe_format(template: str, variables: Dict[str, Any]) -> str:
    class _Safe(dict):
        def __missing__(self, key: str) -> str:  # type: ignore[override]
            return "{" + key + "}"
    return template.format_map(_Safe(**variables))


def list_guidelines(d: Dict[str, Any], agent_id: str) -> List[str]:
    agents = d.get("agents", {})
    if not isinstance(agents, dict):
        return []
    a = agents.get(agent_id, {})
    if not isinstance(a, dict):
        return []
    g = a.get("guidelines", [])
    if not isinstance(g, list):
        return []
    return [x for x in g if isinstance(x, str)]
