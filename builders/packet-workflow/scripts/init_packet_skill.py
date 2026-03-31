#!/usr/bin/env python3
"""Generate a packet-driven repo workflow skill scaffold from builder-spec.json."""

from __future__ import annotations

import argparse
import copy
import json
import os
import pprint
import re
import sys
import tomllib
from collections.abc import Mapping
from pathlib import Path

from packet_workflow_versioning import (
    compare_builder_semver,
    load_builder_versioning,
    normalize_versioning_block,
)


def foundry_root_dir() -> Path:
    return Path(__file__).resolve().parents[3]


def core_templates_dir() -> Path:
    return foundry_root_dir() / "core" / "templates" / "packet-workflow"


def core_defaults_dir() -> Path:
    return foundry_root_dir() / "core" / "defaults" / "packet-workflow"


def retained_skills_root(root_dir: Path) -> Path:
    return root_dir / "builders" / "packet-workflow" / "retained-skills"


def wrapper_skills_root(root_dir: Path) -> Path:
    return root_dir / ".agents" / "skills"


def load_json_document(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def load_string_list_default(filename: str, *, key: str | None = None) -> list[str]:
    payload = load_json_document(core_defaults_dir() / filename)
    if key is not None:
        if not isinstance(payload, dict):
            raise RuntimeError(f"Default file must be an object: {filename}")
        payload = payload.get(key)
    if not isinstance(payload, list) or any(not isinstance(item, str) for item in payload):
        raise RuntimeError(f"Default file must resolve to a list of strings: {filename}")
    return payload


REVIEW_MODE_DEFAULTS = load_json_document(core_defaults_dir() / "review-modes.json")
if not isinstance(REVIEW_MODE_DEFAULTS, dict):
    raise RuntimeError("review-modes.json must be an object")


ARCHETYPE_DEFAULTS = {
    "audit-only": {"needs_lint": False, "needs_validate": False, "needs_apply": False},
    "audit-and-apply": {"needs_lint": True, "needs_validate": True, "needs_apply": True},
    "plan-validate-apply": {"needs_lint": False, "needs_validate": True, "needs_apply": True},
}
DEFAULT_ORCHESTRATOR_PROFILE = "standard"
ORCHESTRATOR_PROFILES = {"standard", "packet-heavy-orchestrator"}

REQUIRED_FIELDS = [
    "skill_name",
    "description",
    "domain_slug",
    "workflow_family",
    "archetype",
    "primary_goal",
    "trigger_phrases",
]

DEFAULT_AUTHORITY_ORDER = load_string_list_default("authority-order.json")
DEFAULT_STOP_CONDITIONS = load_string_list_default(
    "stop-taxonomy.json", key="default_stop_conditions"
)
SUPPORTED_REVIEW_MODES = load_string_list_default(
    "review-modes.json", key="supported_modes"
)
DEFAULT_REVIEW_MODE_OVERRIDES = load_string_list_default(
    "review-modes.json", key="default_override_signals"
)
CURRENT_BUILDER_VERSIONING = load_builder_versioning()
DEFAULT_REPO_PROFILE = {
    "name": "default",
    "summary": (
        "Replace this scaffold profile with repo-specific path bindings, "
        "packet review docs, and lint expectations before trusting deterministic checks."
    ),
    "repo_match": {
        "root_markers": [],
        "remote_patterns": [],
    },
    "bindings": {
        "primary_readme_path": "README.md",
        "settings_source_path": None,
        "publish_config_path": None,
    },
    "packet_defaults": {
        "review_docs": {},
        "source_path_globs": {},
    },
    "lint_rules": {
        "require_readme_settings_table": False,
        "missing_review_docs_are_errors": False,
    },
    "extra": {},
    "notes": [
        "Populate repo-specific doc paths, code bindings, and packet ownership rules here.",
        "Keep the repo profile data-only: store declarative paths, globs, doc lists, booleans, and notes only.",
        "Add more profiles under profiles/<name>/profile.json when one skill must support multiple repositories.",
    ],
}
PACKET_HEAVY_COMMON_PATH_CONTRACT = {
    "shared_local_packet": "synthesis_packet.json",
    "max_additional_focused_packets": 1,
    "raw_reread_policy": "exception-only",
    "packet_insufficiency_is_failure": True,
}

DEFAULT_WORKER_RETURN_CONTRACT = "generic"
WORKER_RETURN_CONTRACTS = {"generic", "classification-oriented"}
DEFAULT_WORKER_OUTPUT_SHAPE = "flat"
WORKER_OUTPUT_SHAPES = {"flat", "hierarchical"}
DEFAULT_XHIGH_REREAD_POLICY = (
    "Do not reopen raw evidence by default after packet generation. "
    "Only reopen raw evidence when reread control points to an allowed reason such as "
    "conflicting signals, missing required evidence, schema mismatch, or insufficient "
    "excerpt quality."
)
DEFAULT_CANDIDATE_FIELD_BUNDLES = [
    {
        "name": "fact_and_evidence",
        "description": "Candidate-level factual summary and supporting references.",
        "required": True,
        "fields": ["fact_summary", "supporting_references"],
    },
    {
        "name": "proposal_assessment",
        "description": "Worker proposal, rationale, ambiguity, and confidence signals.",
        "required": True,
        "fields": [
            "proposal_classification",
            "classification_rationale",
            "ambiguity",
            "confidence",
        ],
    },
    {
        "name": "reread_control",
        "description": "Exception-only raw reread control.",
        "required": True,
        "fields": ["reread_control"],
    },
]
DEFAULT_WORKER_FOOTER_FIELDS = [
    "packet_ids",
    "candidate_ids",
    "primary_outcome",
    "overall_confidence",
    "coverage_gaps",
    "overall_risk",
]
DEFAULT_REREAD_REASON_VALUES = [
    "conflicting_signals",
    "missing_required_evidence",
    "schema_mismatch",
    "insufficient_excerpt_quality",
]
LEGACY_REQUIRED_BUNDLE_NAME = "legacy_required_fields"
GENERIC_FIELD_DESCRIPTIONS = {
    "fact_summary": "candidate-level factual summary",
    "proposal_classification": "worker proposal classification",
    "classification_rationale": "classification rationale for the worker proposal",
    "supporting_references": "supporting references",
    "ambiguity": "open ambiguity affecting adjudication",
    "confidence": "worker confidence for the candidate",
    "reread_control": "allowed reread reason or null",
}
GENERIC_FIELD_PLACEHOLDERS = {
    "fact_summary": "Summarize the candidate facts here.",
    "proposal_classification": "worker-proposal",
    "classification_rationale": "Explain why the worker proposed this classification.",
    "supporting_references": [],
    "ambiguity": None,
    "confidence": "medium",
    "reread_control": None,
}
FOOTER_FIELD_DESCRIPTIONS = {
    "packet_ids": "packets or packet slices the worker actually used",
    "candidate_ids": "candidate ids in the same stable order as `candidates[]`",
    "primary_outcome": "worker-level batch summary only",
    "overall_confidence": "worker batch confidence only; final plan confidence is recomputed locally",
    "coverage_gaps": "unread or insufficiently verified scope",
    "overall_risk": "remaining worker batch risk",
}
OVERLAY_PRECEDENCE_RULES = [
    "generic structural keys stay fixed and are never overridden by the domain overlay",
    "generic `candidate_field_bundles` establish the workflow semantic slots first",
    "overlay `bundle_overrides` adjust bundle composition or requiredness second",
    "overlay `candidate_field_aliases` apply last to rename the resolved semantic slots",
    "when no alias is provided for a resolved semantic slot, keep the generic slot name",
]
KNOWN_WORKER_AGENT_TYPES = [
    "repo_mapper",
    "packet_explorer",
    "docs_verifier",
    "evidence_summarizer",
    "large_diff_auditor",
    "log_triager",
]
KNOWN_WORKER_AGENT_TYPE_SET = set(KNOWN_WORKER_AGENT_TYPES)
MANAGED_AGENTS_DIR_ENV_VAR = "CODEX_MANAGED_AGENTS_DIR"
CODEX_HOME_ENV_VAR = "CODEX_HOME"
DEFAULT_PREFERRED_WORKER_FAMILIES = {
    "context_findings": ["repo_mapper", "packet_explorer", "docs_verifier"],
    "candidate_producers": [
        "evidence_summarizer",
        "large_diff_auditor",
        "log_triager",
    ],
    "verifiers": ["docs_verifier"],
}
WORKER_FAMILY_ORDER = [
    "context_findings",
    "candidate_producers",
    "verifiers",
]
WORKER_FAMILY_DESCRIPTIONS = {
    "context_findings": (
        "mapping, packet-scoped code analysis, touched-surface, and packet-membership findings"
    ),
    "candidate_producers": (
        "decision-ready candidate records for local adjudication-heavy workflows"
    ),
    "verifiers": "narrow claim or version-sensitive verification",
}
DEFAULT_WORKER_SELECTION_GUIDANCE = [
    "Use `repo_mapper` when packet membership, execution path, touched surfaces, or authority mapping is unclear.",
    "Use `packet_explorer` when one focused packet needs narrow code, behavior, or workflow analysis grounded by only the explicitly referenced file slices.",
    "Use `docs_verifier` only when a disputed claim, version-sensitive assumption, or policy interpretation needs exact verification.",
    "Use `evidence_summarizer` for long narrative evidence that should be condensed into decision-ready candidate records.",
    "Use `large_diff_auditor` for large diffs, high-risk hotspots, regressions, invariants, and missing tests.",
    "Use `log_triager` for logs, CI failures, runtime incidents, and earliest-useful-signal triage.",
    "Treat `worker_selection_guidance` as explanatory only. `packet_worker_map` is the concrete routing authority when configured.",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", required=True, help="Path to builder-spec.json")
    parser.add_argument(
        "--output-dir",
        required=True,
        help=(
            "Repository-like root directory that will receive both "
            "`builders/packet-workflow/retained-skills/<skill>` and "
            "`.agents/skills/<skill>`."
        ),
    )
    parser.add_argument(
        "--managed-agents-dir",
        help=(
            "Optional override for the managed agents registry directory. "
            "Resolution order otherwise uses environment overrides, the standard "
            "install location, then the bundled test fixture."
        ),
    )
    return parser.parse_args()


def normalize_skill_name(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    normalized = re.sub(r"-{2,}", "-", normalized)
    if not normalized:
        raise ValueError("skill_name normalized to an empty value")
    return normalized


def normalize_domain_slug(value: str) -> str:
    normalized = value.strip().lower().replace("-", "_")
    normalized = re.sub(r"[^a-z0-9_]+", "_", normalized)
    normalized = re.sub(r"_{2,}", "_", normalized).strip("_")
    if not normalized:
        raise ValueError("domain_slug normalized to an empty value")
    return normalized


def title_case(value: str) -> str:
    return " ".join(part.capitalize() for part in value.replace("_", "-").split("-"))


def ensure_non_empty_string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def ensure_string_list(
    value: object, field_name: str, *, allow_empty: bool = False
) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be an array")
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{field_name} items must be non-empty strings")
        normalized.append(item.strip())
    if not allow_empty and not normalized:
        raise ValueError(f"{field_name} must be a non-empty array")
    return normalized


def ensure_string_mapping(value: object, field_name: str) -> dict[str, str]:
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be an object")
    normalized: dict[str, str] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not key.strip():
            raise ValueError(f"{field_name} keys must be non-empty strings")
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{field_name} values must be non-empty strings")
        normalized[key.strip()] = item.strip()
    return normalized


def ensure_optional_string(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return ensure_non_empty_string(value, field_name)


def ensure_string_list_mapping(
    value: object,
    field_name: str,
    *,
    allow_empty_lists: bool = True,
) -> dict[str, list[str]]:
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be an object")
    normalized: dict[str, list[str]] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not key.strip():
            raise ValueError(f"{field_name} keys must be non-empty strings")
        normalized[key.strip()] = ensure_string_list(
            item,
            f"{field_name}.{key.strip()}",
            allow_empty=allow_empty_lists,
        )
    return normalized


def ensure_known_worker_agent_list(
    value: object, field_name: str, *, allow_empty: bool = False
) -> list[str]:
    normalized = ensure_string_list(value, field_name, allow_empty=allow_empty)
    duplicates: list[str] = []
    seen: set[str] = set()
    for item in normalized:
        if item in seen and item not in duplicates:
            duplicates.append(item)
        seen.add(item)
    if duplicates:
        raise ValueError(
            f"{field_name} contains duplicate agent types: {', '.join(duplicates)}"
        )
    unknown = sorted(set(normalized) - KNOWN_WORKER_AGENT_TYPE_SET)
    if unknown:
        raise ValueError(
            f"{field_name} contains unknown agent types: {', '.join(unknown)}"
        )
    return normalized


def unique_preserving_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            ordered.append(item)
    return ordered


def normalize_candidate_bundles(
    value: object, field_name: str, *, allow_empty: bool = False
) -> list[dict]:
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be an array")

    bundles: list[dict] = []
    bundle_names: set[str] = set()
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise ValueError(f"{field_name}[{index}] must be an object")
        name = ensure_non_empty_string(item.get("name"), f"{field_name}[{index}].name")
        if name in bundle_names:
            raise ValueError(f"{field_name} bundle names must be unique: {name}")
        fields = unique_preserving_order(
            ensure_string_list(item.get("fields"), f"{field_name}[{index}].fields")
        )
        description = item.get("description")
        description_value = (
            ""
            if description is None
            else ensure_non_empty_string(description, f"{field_name}[{index}].description")
        )
        required_value = item.get("required", True)
        if not isinstance(required_value, bool):
            raise ValueError(f"{field_name}[{index}].required must be a boolean")
        bundles.append(
            {
                "name": name,
                "description": description_value,
                "required": required_value,
                "fields": fields,
            }
        )
        bundle_names.add(name)

    if not allow_empty and not bundles:
        raise ValueError(f"{field_name} must be a non-empty array")
    return bundles


def normalize_output_inclusion_rules(value: object, field_name: str) -> dict[str, list[str]]:
    if value is None:
        return {"standalone": [], "reference_only": [], "excluded": []}
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be an object")
    allowed_keys = {"standalone", "reference_only", "excluded"}
    unexpected = sorted(set(value) - allowed_keys)
    if unexpected:
        raise ValueError(
            f"{field_name} contains unsupported keys: {', '.join(unexpected)}"
        )
    return {
        key: ensure_string_list(value.get(key, []), f"{field_name}.{key}", allow_empty=True)
        for key in sorted(allowed_keys)
    }


def normalize_bundle_overrides(value: object, field_name: str) -> dict[str, dict]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be an object")
    overrides: dict[str, dict] = {}
    for bundle_name, override in value.items():
        if not isinstance(bundle_name, str) or not bundle_name.strip():
            raise ValueError(f"{field_name} keys must be non-empty strings")
        if not isinstance(override, dict):
            raise ValueError(f"{field_name}.{bundle_name} must be an object")
        normalized: dict[str, object] = {}
        if "fields" in override:
            normalized["fields"] = unique_preserving_order(
                ensure_string_list(
                    override["fields"], f"{field_name}.{bundle_name}.fields"
                )
            )
        if "required" in override:
            if not isinstance(override["required"], bool):
                raise ValueError(
                    f"{field_name}.{bundle_name}.required must be a boolean"
                )
            normalized["required"] = override["required"]
        if "description" in override:
            normalized["description"] = ensure_non_empty_string(
                override["description"], f"{field_name}.{bundle_name}.description"
            )
        if not normalized:
            raise ValueError(
                f"{field_name}.{bundle_name} must set at least one of fields, required, or description"
            )
        overrides[bundle_name.strip()] = normalized
    return overrides


def normalize_json_data(value: object, field_name: str) -> object:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, list):
        return [
            normalize_json_data(item, f"{field_name}[{index}]")
            for index, item in enumerate(value)
        ]
    if isinstance(value, dict):
        normalized: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str) or not key.strip():
                raise ValueError(f"{field_name} keys must be non-empty strings")
            normalized[key] = normalize_json_data(item, f"{field_name}.{key}")
        return normalized
    raise ValueError(
        f"{field_name} must contain only JSON-serializable data-only values"
    )


def normalize_domain_overlay(value: object) -> dict:
    if value is None:
        return {
            "enabled": False,
            "proposal_enum_values": [],
            "candidate_field_aliases": {},
            "reference_only_candidate_values": [],
            "output_inclusion_rules": {
                "standalone": [],
                "reference_only": [],
                "excluded": [],
            },
            "bundle_overrides": {},
        }
    if not isinstance(value, dict):
        raise ValueError("domain_overlay must be an object when provided")

    overlay = {
        "enabled": True,
        "proposal_enum_values": ensure_string_list(
            value.get("proposal_enum_values", []),
            "domain_overlay.proposal_enum_values",
            allow_empty=True,
        ),
        "candidate_field_aliases": ensure_string_mapping(
            value.get("candidate_field_aliases", {}),
            "domain_overlay.candidate_field_aliases",
        ),
        "reference_only_candidate_values": ensure_string_list(
            value.get("reference_only_candidate_values", []),
            "domain_overlay.reference_only_candidate_values",
            allow_empty=True,
        ),
        "output_inclusion_rules": normalize_output_inclusion_rules(
            value.get("output_inclusion_rules"),
            "domain_overlay.output_inclusion_rules",
        ),
        "bundle_overrides": normalize_bundle_overrides(
            value.get("bundle_overrides"), "domain_overlay.bundle_overrides"
        ),
    }

    proposal_values = set(overlay["proposal_enum_values"])
    reference_only_values = set(overlay["reference_only_candidate_values"])
    if proposal_values and not reference_only_values.issubset(proposal_values):
        missing = sorted(reference_only_values - proposal_values)
        raise ValueError(
            "domain_overlay.reference_only_candidate_values must be a subset of "
            "domain_overlay.proposal_enum_values: " + ", ".join(missing)
        )

    all_rule_values = set()
    for values in overlay["output_inclusion_rules"].values():
        all_rule_values.update(values)
    if proposal_values and not all_rule_values.issubset(proposal_values):
        missing = sorted(all_rule_values - proposal_values)
        raise ValueError(
            "domain_overlay.output_inclusion_rules values must be a subset of "
            "domain_overlay.proposal_enum_values: " + ", ".join(missing)
        )

    if (
        overlay["reference_only_candidate_values"]
        and overlay["output_inclusion_rules"]["reference_only"]
        and set(overlay["reference_only_candidate_values"])
        != set(overlay["output_inclusion_rules"]["reference_only"])
    ):
        raise ValueError(
            "domain_overlay.reference_only_candidate_values must match "
            "domain_overlay.output_inclusion_rules.reference_only when both are set"
        )

    if (
        overlay["reference_only_candidate_values"]
        and not overlay["output_inclusion_rules"]["reference_only"]
    ):
        overlay["output_inclusion_rules"]["reference_only"] = list(
            overlay["reference_only_candidate_values"]
        )

    return overlay


def normalize_packet_name(value: str) -> str:
    normalized = value.strip().lower().replace(".json", "")
    normalized = re.sub(r"[^a-z0-9_-]+", "-", normalized)
    normalized = re.sub(r"-{2,}", "-", normalized).strip("-")
    if not normalized:
        raise ValueError("task_packet_names contains an empty packet name")
    return normalized


def normalize_profile_name(value: str) -> str:
    normalized = normalize_skill_name(value)
    if not normalized:
        raise ValueError("repo_profile.name normalized to an empty value")
    return normalized


def normalize_preferred_worker_families(value: object | None) -> dict[str, list[str]]:
    if value is None:
        return copy.deepcopy(DEFAULT_PREFERRED_WORKER_FAMILIES)
    if not isinstance(value, dict):
        raise ValueError("preferred_worker_families must be an object")
    unexpected = sorted(set(value) - set(WORKER_FAMILY_ORDER))
    if unexpected:
        raise ValueError(
            "preferred_worker_families contains unsupported keys: "
            + ", ".join(unexpected)
        )
    normalized: dict[str, list[str]] = {}
    for family_name in WORKER_FAMILY_ORDER:
        family_value = value.get(
            family_name, copy.deepcopy(DEFAULT_PREFERRED_WORKER_FAMILIES[family_name])
        )
        normalized[family_name] = ensure_known_worker_agent_list(
            family_value,
            f"preferred_worker_families.{family_name}",
            allow_empty=True,
        )
    return normalized


def normalize_packet_worker_map(
    value: object | None,
    *,
    task_packet_names: list[str],
    uses_batch_packets: bool,
) -> dict[str, list[str]]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("packet_worker_map must be an object")
    allowed_packets = set(task_packet_names)
    if uses_batch_packets:
        allowed_packets.add("batch-packet-01")
    normalized: dict[str, list[str]] = {}
    for packet_name, agent_types in value.items():
        if not isinstance(packet_name, str) or not packet_name.strip():
            raise ValueError("packet_worker_map keys must be non-empty strings")
        normalized_packet = normalize_packet_name(packet_name)
        if normalized_packet not in allowed_packets:
            raise ValueError(
                "packet_worker_map contains unknown packet name: "
                + normalized_packet
            )
        normalized[normalized_packet] = ensure_known_worker_agent_list(
            agent_types,
            f"packet_worker_map.{normalized_packet}",
        )
    ordered_packets: list[str] = []
    if uses_batch_packets and "batch-packet-01" in normalized:
        ordered_packets.append("batch-packet-01")
    ordered_packets.extend(
        packet_name for packet_name in task_packet_names if packet_name in normalized
    )
    return {packet_name: normalized[packet_name] for packet_name in ordered_packets}


def normalize_repo_profile(
    value: object | None,
    *,
    task_packet_names: list[str],
    uses_batch_packets: bool,
    builder_versioning: dict[str, object],
) -> dict:
    if value is None:
        profile = copy.deepcopy(DEFAULT_REPO_PROFILE)
    else:
        if not isinstance(value, dict):
            raise ValueError("repo_profile must be an object when provided")
        allowed_top_level = {
            "name",
            "summary",
            "repo_match",
            "bindings",
            "packet_defaults",
            "lint_rules",
            "extra",
            "notes",
        }
        unexpected = sorted(set(value) - allowed_top_level)
        if unexpected:
            raise ValueError(
                "repo_profile contains unsupported keys: " + ", ".join(unexpected)
            )
        profile = copy.deepcopy(DEFAULT_REPO_PROFILE)
        if "name" in value:
            profile["name"] = normalize_profile_name(
                ensure_non_empty_string(value["name"], "repo_profile.name")
            )
        if "summary" in value:
            profile["summary"] = ensure_non_empty_string(
                value["summary"], "repo_profile.summary"
            )

        repo_match = value.get("repo_match")
        if repo_match is not None:
            if not isinstance(repo_match, dict):
                raise ValueError("repo_profile.repo_match must be an object")
            unexpected = sorted(set(repo_match) - {"root_markers", "remote_patterns"})
            if unexpected:
                raise ValueError(
                    "repo_profile.repo_match contains unsupported keys: "
                    + ", ".join(unexpected)
                )
            profile["repo_match"] = {
                "root_markers": ensure_string_list(
                    repo_match.get("root_markers", []),
                    "repo_profile.repo_match.root_markers",
                    allow_empty=True,
                ),
                "remote_patterns": ensure_string_list(
                    repo_match.get("remote_patterns", []),
                    "repo_profile.repo_match.remote_patterns",
                    allow_empty=True,
                ),
            }

        bindings = value.get("bindings")
        if bindings is not None:
            if not isinstance(bindings, dict):
                raise ValueError("repo_profile.bindings must be an object")
            unexpected = sorted(
                set(bindings)
                - {
                    "primary_readme_path",
                    "settings_source_path",
                    "publish_config_path",
                }
            )
            if unexpected:
                raise ValueError(
                    "repo_profile.bindings contains unsupported keys: "
                    + ", ".join(unexpected)
                )
            profile["bindings"] = {
                "primary_readme_path": ensure_non_empty_string(
                    bindings.get(
                        "primary_readme_path",
                        DEFAULT_REPO_PROFILE["bindings"]["primary_readme_path"],
                    ),
                    "repo_profile.bindings.primary_readme_path",
                ),
                "settings_source_path": ensure_optional_string(
                    bindings.get("settings_source_path"),
                    "repo_profile.bindings.settings_source_path",
                ),
                "publish_config_path": ensure_optional_string(
                    bindings.get("publish_config_path"),
                    "repo_profile.bindings.publish_config_path",
                ),
            }

        packet_defaults = value.get("packet_defaults")
        if packet_defaults is not None:
            if not isinstance(packet_defaults, dict):
                raise ValueError("repo_profile.packet_defaults must be an object")
            unexpected = sorted(
                set(packet_defaults) - {"review_docs", "source_path_globs"}
            )
            if unexpected:
                raise ValueError(
                    "repo_profile.packet_defaults contains unsupported keys: "
                    + ", ".join(unexpected)
                )
            allowed_packets = set(task_packet_names)
            if uses_batch_packets:
                allowed_packets.add("batch-packet-01")

            def normalize_packet_mapping(
                mapping_value: object,
                field_name: str,
            ) -> dict[str, list[str]]:
                mapping = ensure_string_list_mapping(mapping_value, field_name)
                normalized_mapping: dict[str, list[str]] = {}
                for packet_name, items in mapping.items():
                    normalized_packet = normalize_packet_name(packet_name)
                    if normalized_packet not in allowed_packets:
                        raise ValueError(
                            f"{field_name} contains unknown packet name: {normalized_packet}"
                        )
                    normalized_mapping[normalized_packet] = items
                ordered_packets: list[str] = []
                if uses_batch_packets and "batch-packet-01" in normalized_mapping:
                    ordered_packets.append("batch-packet-01")
                ordered_packets.extend(
                    packet_name
                    for packet_name in task_packet_names
                    if packet_name in normalized_mapping
                )
                return {
                    packet_name: normalized_mapping[packet_name]
                    for packet_name in ordered_packets
                }

            profile["packet_defaults"] = {
                "review_docs": normalize_packet_mapping(
                    packet_defaults.get("review_docs", {}),
                    "repo_profile.packet_defaults.review_docs",
                ),
                "source_path_globs": normalize_packet_mapping(
                    packet_defaults.get("source_path_globs", {}),
                    "repo_profile.packet_defaults.source_path_globs",
                ),
            }

        lint_rules = value.get("lint_rules")
        if lint_rules is not None:
            if not isinstance(lint_rules, dict):
                raise ValueError("repo_profile.lint_rules must be an object")
            unexpected = sorted(
                set(lint_rules)
                - {
                    "require_readme_settings_table",
                    "missing_review_docs_are_errors",
                }
            )
            if unexpected:
                raise ValueError(
                    "repo_profile.lint_rules contains unsupported keys: "
                    + ", ".join(unexpected)
                )
            normalized_lint_rules: dict[str, bool] = {}
            for key, default_value in DEFAULT_REPO_PROFILE["lint_rules"].items():
                lint_value = lint_rules.get(key, default_value)
                if not isinstance(lint_value, bool):
                    raise ValueError(f"repo_profile.lint_rules.{key} must be a boolean")
                normalized_lint_rules[key] = lint_value
            profile["lint_rules"] = normalized_lint_rules

        if "extra" in value:
            extra = value["extra"]
            if not isinstance(extra, dict):
                raise ValueError("repo_profile.extra must be an object")
            profile["extra"] = normalize_json_data(extra, "repo_profile.extra")

        if "notes" in value:
            profile["notes"] = ensure_string_list(
                value["notes"], "repo_profile.notes", allow_empty=True
            )

    profile["name"] = normalize_profile_name(profile["name"])
    profile["profile_path"] = f"profiles/{profile['name']}/profile.json"
    profile["metadata"] = {
        "versioning": {
            "builder_family": builder_versioning["builder_family"],
            "builder_semver": builder_versioning["builder_semver"],
            "compatibility_epoch": builder_versioning["compatibility_epoch"],
            "repo_profile_schema_version": builder_versioning[
                "repo_profile_schema_version"
            ],
        }
    }
    return profile


def load_spec(path: Path) -> dict:
    try:
        payload = load_json_document(path)
        if not isinstance(payload, dict):
            raise SystemExit(f"[ERROR] Spec file must contain a JSON object: {path}")
        return payload
    except FileNotFoundError as exc:
        raise SystemExit(f"[ERROR] Missing spec file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"[ERROR] Invalid JSON in {path}: {exc}") from exc


def codex_home_dir() -> Path:
    return foundry_root_dir()


def managed_agents_dir() -> Path:
    return codex_home_dir() / "agents"


def managed_agents_fixture_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "agents"


def normalize_directory_candidate(path_value: str | Path) -> Path:
    return Path(path_value).expanduser().resolve()


def environment_managed_agents_dir(
    env: Mapping[str, str] | None = None,
) -> tuple[Path | None, str | None]:
    env_map = os.environ if env is None else env
    explicit_dir = env_map.get(MANAGED_AGENTS_DIR_ENV_VAR)
    if isinstance(explicit_dir, str) and explicit_dir.strip():
        return normalize_directory_candidate(explicit_dir.strip()), MANAGED_AGENTS_DIR_ENV_VAR
    codex_home = env_map.get(CODEX_HOME_ENV_VAR)
    if isinstance(codex_home, str) and codex_home.strip():
        return (
            normalize_directory_candidate(Path(codex_home.strip()) / "agents"),
            CODEX_HOME_ENV_VAR,
        )
    return None, None


def resolve_managed_agents_dir(
    override: str | Path | None = None,
    *,
    env: Mapping[str, str] | None = None,
) -> Path:
    if override is not None:
        explicit = normalize_directory_candidate(override)
        if explicit.is_dir():
            return explicit
        raise ValueError(f"Managed agents override is not a directory: {explicit}")

    env_path, env_source = environment_managed_agents_dir(env)
    if env_path is not None:
        if env_path.is_dir():
            return env_path
        raise ValueError(
            f"{env_source} points to a missing managed agents directory: {env_path}"
        )

    standard_dir = managed_agents_dir()
    if standard_dir.is_dir():
        return standard_dir

    fixture_dir = managed_agents_fixture_dir()
    if fixture_dir.is_dir():
        return fixture_dir

    raise ValueError(
        "Managed agents directory is missing. Checked "
        f"standard default {standard_dir} and test fixture {fixture_dir}."
    )


def validate_managed_agent_registry(
    agents_dir_override: str | Path | None = None,
    *,
    env: Mapping[str, str] | None = None,
) -> Path:
    agents_dir = resolve_managed_agents_dir(agents_dir_override, env=env)
    discovered_agent_types: set[str] = set()
    for path in sorted(agents_dir.glob("*.toml")):
        try:
            with path.open("rb") as handle:
                payload = tomllib.load(handle)
        except tomllib.TOMLDecodeError as exc:
            raise ValueError(f"Invalid TOML in managed agent file {path}: {exc}") from exc
        agent_name = payload.get("name")
        if isinstance(agent_name, str) and agent_name.strip():
            discovered_agent_types.add(agent_name.strip())
    missing = sorted(KNOWN_WORKER_AGENT_TYPE_SET - discovered_agent_types)
    if missing:
        raise ValueError(
            "Managed worker agents are missing from "
            f"{agents_dir}: {', '.join(missing)}"
        )
    return agents_dir


def apply_bundle_overrides(bundles: list[dict], overrides: dict[str, dict]) -> list[dict]:
    resolved = copy.deepcopy(bundles)
    index = {bundle["name"]: position for position, bundle in enumerate(resolved)}
    for bundle_name, override in overrides.items():
        if bundle_name not in index:
            raise ValueError(
                f"domain_overlay.bundle_overrides references unknown bundle: {bundle_name}"
            )
        target = resolved[index[bundle_name]]
        if "fields" in override:
            target["fields"] = unique_preserving_order(list(override["fields"]))
        if "required" in override:
            target["required"] = override["required"]
        if "description" in override:
            target["description"] = override["description"]
    return resolved


def flatten_bundle_fields(bundles: list[dict]) -> list[str]:
    ordered: list[str] = []
    for bundle in bundles:
        ordered.extend(bundle["fields"])
    return unique_preserving_order(ordered)


def validate_alias_keys(bundles: list[dict], aliases: dict[str, str]) -> None:
    bundle_fields = set(flatten_bundle_fields(bundles))
    unknown = sorted(set(aliases) - bundle_fields)
    if unknown:
        raise ValueError(
            "domain_overlay.candidate_field_aliases contains unknown semantic slots: "
            + ", ".join(unknown)
        )


def resolve_candidate_bundles(
    bundles: list[dict], aliases: dict[str, str]
) -> list[dict]:
    resolved_bundles: list[dict] = []
    seen_resolved_names: dict[str, str] = {}
    for bundle in bundles:
        resolved_fields: list[dict] = []
        for semantic_name in bundle["fields"]:
            resolved_name = aliases.get(semantic_name, semantic_name)
            prior = seen_resolved_names.get(resolved_name)
            if prior is not None and prior != semantic_name:
                raise ValueError(
                    "domain_overlay.candidate_field_aliases produced duplicate resolved "
                    f"field name `{resolved_name}` from `{prior}` and `{semantic_name}`"
                )
            seen_resolved_names[resolved_name] = semantic_name
            resolved_fields.append(
                {
                    "semantic_name": semantic_name,
                    "field_name": resolved_name,
                    "description": GENERIC_FIELD_DESCRIPTIONS.get(
                        semantic_name, f"domain-specific candidate field `{semantic_name}`"
                    ),
                }
            )
        resolved_bundles.append(
            {
                "name": bundle["name"],
                "description": bundle["description"],
                "required": bundle["required"],
                "fields": resolved_fields,
            }
        )
    return resolved_bundles


def build_candidate_template(resolved_bundles: list[dict]) -> dict:
    template = {"candidate_id": "candidate-001"}
    for bundle in resolved_bundles:
        for field in bundle["fields"]:
            semantic_name = field["semantic_name"]
            field_name = field["field_name"]
            template[field_name] = copy.deepcopy(
                GENERIC_FIELD_PLACEHOLDERS.get(semantic_name, "todo")
            )
    return template


def build_footer_template(worker_footer_fields: list[str]) -> dict:
    placeholders = {
        "packet_ids": [],
        "candidate_ids": [],
        "primary_outcome": "Summarize the worker batch outcome here.",
        "overall_confidence": "medium",
        "coverage_gaps": [],
        "overall_risk": "todo",
    }
    return {
        field_name: copy.deepcopy(placeholders.get(field_name, "todo"))
        for field_name in worker_footer_fields
    }


def active_worker_family_order(worker_return_contract: str) -> list[str]:
    if worker_return_contract == "classification-oriented":
        return list(WORKER_FAMILY_ORDER)
    return ["context_findings", "verifiers"]


def build_worker_selection_guidance() -> dict:
    return {
        "routing_authority": "packet_worker_map",
        "notes": list(DEFAULT_WORKER_SELECTION_GUIDANCE),
    }


def surfaced_optional_worker_pool(spec: dict) -> list[str]:
    ordered: list[str] = []
    for family_name in active_worker_family_order(spec["worker_return_contract"]):
        ordered.extend(spec["preferred_worker_families"][family_name])
    return unique_preserving_order(ordered)


def mapped_worker_types(spec: dict) -> list[str]:
    ordered: list[str] = []
    for packet_name in spec["packet_worker_map"]:
        ordered.extend(spec["packet_worker_map"][packet_name])
    return unique_preserving_order(ordered)


def surfaced_optional_worker_list_for_docs(spec: dict) -> list[str]:
    remaining = list(surfaced_optional_worker_pool(spec))
    if not spec["packet_worker_map"]:
        return remaining
    mapped = set(mapped_worker_types(spec))
    return [agent_type for agent_type in remaining if agent_type not in mapped]


def worker_family_markdown(spec: dict) -> str:
    sections: list[str] = []
    for family_name in active_worker_family_order(spec["worker_return_contract"]):
        sections.append(
            f"- `{family_name}`: {WORKER_FAMILY_DESCRIPTIONS[family_name]}"
        )
        worker_types = spec["preferred_worker_families"][family_name]
        if worker_types:
            sections.append(
                bullet_list([f"`{agent_type}`" for agent_type in worker_types], indent="  ")
            )
        else:
            sections.append("  - no worker types configured")
    return "\n".join(sections)


def packet_worker_map_markdown(packet_worker_map: dict[str, list[str]]) -> str:
    if not packet_worker_map:
        return (
            "- No `packet_worker_map` is configured for this scaffold.\n"
            "- `worker_selection_guidance` stays explanatory only until a packet map is provided."
        )
    lines: list[str] = [
        "- `packet_worker_map` is the routing authority when configured.",
        "- The same agent type may appear on multiple packets when those assignments are intentional.",
    ]
    for packet_name, agent_types in packet_worker_map.items():
        lines.append(f"- `{packet_name}`")
        lines.append(
            bullet_list([f"`{agent_type}`" for agent_type in agent_types], indent="  ")
        )
    return "\n".join(lines)


def worker_selection_guidance_markdown(guidance: dict) -> str:
    lines = [
        "- `worker_selection_guidance` is explanatory only and does not override `packet_worker_map`.",
        "- Guidance notes:",
        bullet_list(guidance["notes"], indent="  "),
    ]
    return "\n".join(lines)


def derive_spec(raw: dict) -> dict:
    missing = [field for field in REQUIRED_FIELDS if field not in raw]
    if missing:
        raise ValueError(f"Missing required fields: {', '.join(missing)}")

    builder_versioning = normalize_versioning_block(
        raw.get("builder_versioning"),
        require_builder_spec_schema_version=True,
    )
    if builder_versioning is None:
        raise ValueError("builder_versioning is required and must be a valid object")
    if builder_versioning["builder_family"] != CURRENT_BUILDER_VERSIONING["builder_family"]:
        raise ValueError(
            "builder_versioning.builder_family must match the current builder family"
        )
    if builder_versioning["compatibility_epoch"] != CURRENT_BUILDER_VERSIONING["compatibility_epoch"]:
        raise ValueError(
            "builder_versioning.compatibility_epoch must match the current builder compatibility epoch"
        )
    if (
        builder_versioning["builder_spec_schema_version"]
        != CURRENT_BUILDER_VERSIONING["builder_spec_schema_version"]
    ):
        raise ValueError(
            "builder_versioning.builder_spec_schema_version must match the current builder spec schema version"
        )
    if (
        builder_versioning["repo_profile_schema_version"]
        != CURRENT_BUILDER_VERSIONING["repo_profile_schema_version"]
    ):
        raise ValueError(
            "builder_versioning.repo_profile_schema_version must match the current repo profile schema version"
        )
    if compare_builder_semver(
        builder_versioning["builder_semver"],
        CURRENT_BUILDER_VERSIONING["builder_semver"],
    ) > 0:
        raise ValueError(
            "builder_versioning.builder_semver cannot be ahead of the current builder"
        )

    archetype = raw["archetype"]
    if archetype not in ARCHETYPE_DEFAULTS:
        raise ValueError(
            "archetype must be one of: " + ", ".join(sorted(ARCHETYPE_DEFAULTS))
        )

    trigger_phrases = ensure_string_list(raw["trigger_phrases"], "trigger_phrases")
    task_packet_names = ensure_string_list(
        raw.get("task_packet_names", ["task_packet"]), "task_packet_names"
    )
    task_packet_names = [normalize_packet_name(item) for item in task_packet_names]
    uses_batch_packets = bool(raw.get("uses_batch_packets", False))
    orchestrator_profile = ensure_non_empty_string(
        raw.get("orchestrator_profile", DEFAULT_ORCHESTRATOR_PROFILE),
        "orchestrator_profile",
    )
    if orchestrator_profile not in ORCHESTRATOR_PROFILES:
        raise ValueError(
            "orchestrator_profile must be one of: "
            + ", ".join(sorted(ORCHESTRATOR_PROFILES))
        )

    optional_local_helper = raw.get("optional_local_helper")
    if optional_local_helper is not None:
        if not isinstance(optional_local_helper, dict):
            raise ValueError("optional_local_helper must be an object when provided")
        path_value = ensure_non_empty_string(
            optional_local_helper.get("path"), "optional_local_helper.path"
        )
        description = optional_local_helper.get("description") or "optional local helper"
        description = ensure_non_empty_string(
            description, "optional_local_helper.description"
        )
        optional_local_helper = {
            "path": path_value,
            "description": description,
            "is_authoritative": False,
        }

    defaults = ARCHETYPE_DEFAULTS[archetype]
    authority_order = ensure_string_list(
        raw.get("authority_order", DEFAULT_AUTHORITY_ORDER), "authority_order"
    )
    stop_conditions = ensure_string_list(
        raw.get("stop_conditions", DEFAULT_STOP_CONDITIONS), "stop_conditions"
    )
    review_mode_overrides = ensure_string_list(
        raw.get("review_mode_overrides", DEFAULT_REVIEW_MODE_OVERRIDES),
        "review_mode_overrides",
    )
    decision_ready_packets = bool(raw.get("decision_ready_packets", False))
    worker_return_contract = raw.get("worker_return_contract")
    if worker_return_contract is None:
        worker_return_contract = (
            "classification-oriented"
            if decision_ready_packets
            else DEFAULT_WORKER_RETURN_CONTRACT
        )
    worker_return_contract = ensure_non_empty_string(
        worker_return_contract, "worker_return_contract"
    )
    if worker_return_contract not in WORKER_RETURN_CONTRACTS:
        raise ValueError(
            "worker_return_contract must be one of: "
            + ", ".join(sorted(WORKER_RETURN_CONTRACTS))
        )

    worker_output_shape = raw.get("worker_output_shape")
    if worker_output_shape is None:
        worker_output_shape = (
            "hierarchical"
            if decision_ready_packets or worker_return_contract == "classification-oriented"
            else DEFAULT_WORKER_OUTPUT_SHAPE
        )
    worker_output_shape = ensure_non_empty_string(
        worker_output_shape, "worker_output_shape"
    )
    if worker_output_shape not in WORKER_OUTPUT_SHAPES:
        raise ValueError(
            "worker_output_shape must be one of: "
            + ", ".join(sorted(WORKER_OUTPUT_SHAPES))
        )
    if (
        worker_output_shape == "hierarchical"
        and worker_return_contract != "classification-oriented"
    ):
        raise ValueError(
            "worker_output_shape=hierarchical requires "
            "worker_return_contract=classification-oriented"
        )
    if (
        worker_return_contract == "classification-oriented"
        and not decision_ready_packets
    ):
        raise ValueError(
            "worker_return_contract=classification-oriented requires "
            "decision_ready_packets=true"
        )

    xhigh_reread_policy = raw.get(
        "xhigh_reread_policy", DEFAULT_XHIGH_REREAD_POLICY
    )
    xhigh_reread_policy = ensure_non_empty_string(
        xhigh_reread_policy, "xhigh_reread_policy"
    )

    required_candidate_fields = ensure_string_list(
        raw.get("required_candidate_fields", []),
        "required_candidate_fields",
        allow_empty=True,
    )

    candidate_field_bundles_raw = raw.get("candidate_field_bundles")
    if candidate_field_bundles_raw is None:
        if worker_output_shape == "hierarchical" or decision_ready_packets:
            if required_candidate_fields:
                candidate_field_bundles = [
                    {
                        "name": LEGACY_REQUIRED_BUNDLE_NAME,
                        "description": "Legacy shorthand bundle derived from required_candidate_fields.",
                        "required": True,
                        "fields": required_candidate_fields,
                    }
                ]
            else:
                candidate_field_bundles = copy.deepcopy(DEFAULT_CANDIDATE_FIELD_BUNDLES)
        else:
            candidate_field_bundles = []
    else:
        candidate_field_bundles = normalize_candidate_bundles(
            candidate_field_bundles_raw, "candidate_field_bundles", allow_empty=True
        )
    if (
        candidate_field_bundles_raw is not None
        and worker_return_contract != "classification-oriented"
    ):
        raise ValueError(
            "candidate_field_bundles requires "
            "worker_return_contract=classification-oriented"
        )

    worker_footer_fields_raw = raw.get("worker_footer_fields")
    if worker_footer_fields_raw is None:
        worker_footer_fields = (
            list(DEFAULT_WORKER_FOOTER_FIELDS)
            if worker_output_shape == "hierarchical"
            else []
        )
    else:
        worker_footer_fields = ensure_string_list(
            worker_footer_fields_raw, "worker_footer_fields", allow_empty=True
        )
    if worker_footer_fields_raw is not None and not decision_ready_packets:
        raise ValueError(
            "worker_footer_fields requires decision_ready_packets=true"
        )
    if worker_footer_fields_raw is not None and worker_output_shape != "hierarchical":
        raise ValueError(
            "worker_footer_fields requires worker_output_shape=hierarchical"
        )

    reread_reason_values_raw = raw.get("reread_reason_values")
    if reread_reason_values_raw is None:
        reread_reason_values = (
            list(DEFAULT_REREAD_REASON_VALUES)
            if decision_ready_packets or worker_return_contract == "classification-oriented"
            else []
        )
    else:
        reread_reason_values = ensure_string_list(
            reread_reason_values_raw, "reread_reason_values", allow_empty=True
        )

    domain_overlay = normalize_domain_overlay(raw.get("domain_overlay"))
    if domain_overlay["enabled"] and worker_return_contract != "classification-oriented":
        raise ValueError(
            "domain_overlay requires worker_return_contract=classification-oriented"
        )

    preferred_worker_families = normalize_preferred_worker_families(
        raw.get("preferred_worker_families")
    )
    packet_worker_map = normalize_packet_worker_map(
        raw.get("packet_worker_map"),
        task_packet_names=task_packet_names,
        uses_batch_packets=uses_batch_packets,
    )
    repo_profile = normalize_repo_profile(
        raw.get("repo_profile"),
        task_packet_names=task_packet_names,
        uses_batch_packets=uses_batch_packets,
        builder_versioning=builder_versioning,
    )

    if worker_output_shape == "hierarchical" and not candidate_field_bundles:
        raise ValueError(
            "worker_output_shape=hierarchical requires candidate_field_bundles or "
            "required_candidate_fields"
        )

    candidate_field_bundles = apply_bundle_overrides(
        candidate_field_bundles, domain_overlay["bundle_overrides"]
    )
    validate_alias_keys(candidate_field_bundles, domain_overlay["candidate_field_aliases"])
    resolved_candidate_field_bundles = resolve_candidate_bundles(
        candidate_field_bundles, domain_overlay["candidate_field_aliases"]
    )

    derived = {
        "skill_name": normalize_skill_name(raw["skill_name"]),
        "description": ensure_non_empty_string(raw["description"], "description"),
        "domain_slug": normalize_domain_slug(raw["domain_slug"]),
        "workflow_family": ensure_non_empty_string(
            raw["workflow_family"], "workflow_family"
        ),
        "builder_versioning": builder_versioning,
        "archetype": archetype,
        "primary_goal": ensure_non_empty_string(raw["primary_goal"], "primary_goal"),
        "trigger_phrases": trigger_phrases,
        "task_packet_names": task_packet_names,
        "uses_batch_packets": uses_batch_packets,
        "orchestrator_profile": orchestrator_profile,
        "needs_lint": bool(raw.get("needs_lint", defaults["needs_lint"])),
        "needs_validate": bool(raw.get("needs_validate", defaults["needs_validate"])),
        "needs_apply": bool(raw.get("needs_apply", defaults["needs_apply"])),
        "optional_local_helper": optional_local_helper,
        "authority_order": authority_order,
        "stop_conditions": stop_conditions,
        "review_mode_overrides": review_mode_overrides,
        "decision_ready_packets": decision_ready_packets,
        "worker_return_contract": worker_return_contract,
        "worker_output_shape": worker_output_shape,
        "xhigh_reread_policy": xhigh_reread_policy,
        "required_candidate_fields": required_candidate_fields,
        "candidate_field_bundles": candidate_field_bundles,
        "resolved_candidate_field_bundles": resolved_candidate_field_bundles,
        "worker_footer_fields": worker_footer_fields,
        "reread_reason_values": reread_reason_values,
        "known_worker_agent_types": list(KNOWN_WORKER_AGENT_TYPES),
        "preferred_worker_families": preferred_worker_families,
        "packet_worker_map": packet_worker_map,
        "worker_selection_guidance": build_worker_selection_guidance(),
        "repo_profile": repo_profile,
        "domain_overlay": domain_overlay,
        "candidate_template": build_candidate_template(resolved_candidate_field_bundles),
        "footer_template": build_footer_template(worker_footer_fields),
        "shared_local_packet": (
            "synthesis_packet.json"
            if orchestrator_profile == "packet-heavy-orchestrator"
            else None
        ),
        "common_path_contract": (
            copy.deepcopy(PACKET_HEAVY_COMMON_PATH_CONTRACT)
            if orchestrator_profile == "packet-heavy-orchestrator"
            else None
        ),
    }

    if derived["needs_apply"] and not derived["needs_validate"]:
        raise ValueError(
            "needs_apply=true requires needs_validate=true in this scaffold"
        )

    return derived


def templates_dir() -> Path:
    return core_templates_dir()


def load_template(template_name: str) -> str:
    template_path = templates_dir() / template_name
    return template_path.read_text(encoding="utf-8")


def render(template_name: str, context: dict[str, str]) -> str:
    rendered = load_template(template_name)
    for key, value in sorted(context.items(), key=lambda item: len(item[0]), reverse=True):
        rendered = rendered.replace(f"__{key}__", value)
    return rendered


def bullet_list(items: list[str], indent: str = "") -> str:
    return "\n".join(f"{indent}- {item}" for item in items)


def json_block(value: object) -> str:
    return json.dumps(value, indent=2, sort_keys=True)


def python_block(value: object) -> str:
    return pprint.pformat(value, sort_dicts=True)


def short_description(value: str) -> str:
    trimmed = value.strip()
    if len(trimmed) <= 52:
        return trimmed
    return trimmed[:49].rstrip() + "..."


def helper_note(spec: dict) -> str:
    helper = spec["optional_local_helper"]
    if not helper:
        return "- No optional local helper is configured for this scaffold."
    return (
        f"- Treat `{helper['path']}` as an optional local-only helper for "
        f"{helper['description']}; never treat it as an authoritative shared asset."
    )


def helper_collect_arg(spec: dict) -> str:
    helper = spec["optional_local_helper"]
    if not helper:
        return ""
    default_path = helper["path"].replace("\\", "/")
    return (
        '    parser.add_argument(\n'
        '        "--local-helper",\n'
        f'        default="{default_path}",\n'
        '        help="Optional repo-relative local helper path.",\n'
        "    )"
    )


def helper_collect_functions(spec: dict) -> str:
    helper = spec["optional_local_helper"]
    if not helper:
        return ""
    description = helper["description"]
    return f"""
def collect_optional_local_helper(repo_root: Path, helper_path: str) -> dict:
    helper = Path(helper_path)
    if helper.is_absolute():
        raise SystemExit("[ERROR] --local-helper must stay repo-relative")
    candidate = (repo_root / helper).resolve()
    try:
        candidate.relative_to(repo_root)
    except ValueError as exc:
        raise SystemExit("[ERROR] --local-helper must stay within the repo root") from exc

    if not candidate.exists():
        return {{
            "path": helper.as_posix(),
            "description": "{description}",
            "status": "missing_optional_local_helper",
            "is_authoritative": False,
        }}

    preview_lines = candidate.read_text(encoding="utf-8", errors="replace").splitlines()[:12]
    return {{
        "path": helper.as_posix(),
        "description": "{description}",
        "status": "present",
        "is_authoritative": False,
        "preview": preview_lines,
    }}
""".strip(
        "\n"
    )


def helper_collect_context_line(spec: dict) -> str:
    if spec["optional_local_helper"]:
        return '    context["optional_local_helper"] = collect_optional_local_helper(repo_root, args.local_helper)'
    return '    context["optional_local_helper"] = None'


def format_profile_binding_value(value: str | None) -> str:
    if value is None:
        return "`null`"
    return f"`{value}`"


def repo_profile_note(spec: dict) -> str:
    profile = spec["repo_profile"]
    return "\n".join(
        [
            f"- Default repo profile scaffold: `{profile['profile_path']}`.",
            "- Keep repo-specific paths, packet review docs, and deterministic lint toggles in the repo profile instead of hardcoding them into the generic core templates.",
            "- Keep the repo profile data-only: paths, globs, doc lists, booleans, and notes only. Do not add executable hooks, prompt text, or worker-routing logic there.",
        ]
    )


def repo_profile_bindings_markdown(spec: dict) -> str:
    bindings = spec["repo_profile"]["bindings"]
    return "\n".join(
        [
            f"- `primary_readme_path`: {format_profile_binding_value(bindings['primary_readme_path'])}",
            f"- `settings_source_path`: {format_profile_binding_value(bindings['settings_source_path'])}",
            f"- `publish_config_path`: {format_profile_binding_value(bindings['publish_config_path'])}",
        ]
    )


def repo_profile_packet_defaults_markdown(spec: dict) -> str:
    packet_defaults = spec["repo_profile"]["packet_defaults"]
    review_docs = packet_defaults["review_docs"]
    source_path_globs = packet_defaults["source_path_globs"]
    lines = ["- review docs:"]
    if review_docs:
        for packet_name, docs in review_docs.items():
            lines.append(f"  - `{packet_name}`")
            lines.append(bullet_list([f"`{item}`" for item in docs], indent="    "))
    else:
        lines.append("  - none configured in the scaffold profile")
    lines.append("- source path globs:")
    if source_path_globs:
        for packet_name, globs in source_path_globs.items():
            lines.append(f"  - `{packet_name}`")
            lines.append(bullet_list([f"`{item}`" for item in globs], indent="    "))
    else:
        lines.append("  - none configured in the scaffold profile")
    return "\n".join(lines)


def repo_profile_lint_rules_markdown(spec: dict) -> str:
    lint_rules = spec["repo_profile"]["lint_rules"]
    return "\n".join(
        [
            f"- `require_readme_settings_table`: {'true' if lint_rules['require_readme_settings_table'] else 'false'}",
            f"- `missing_review_docs_are_errors`: {'true' if lint_rules['missing_review_docs_are_errors'] else 'false'}",
        ]
    )


def repo_profile_notes_markdown(spec: dict) -> str:
    notes = spec["repo_profile"].get("notes", [])
    if not notes:
        return "- no repo-profile notes are configured"
    return bullet_list(notes)


def format_resolved_candidate_field(field: dict) -> str:
    semantic_name = field["semantic_name"]
    field_name = field["field_name"]
    label = GENERIC_FIELD_DESCRIPTIONS.get(semantic_name)
    if label:
        return f"{label} (`{field_name}`)"
    if field_name != semantic_name:
        return f"`{field_name}` (alias for `{semantic_name}`)"
    return f"`{field_name}`"


def candidate_bundle_markdown(bundles: list[dict]) -> str:
    if not bundles:
        return "- No candidate field bundles are configured for this scaffold."
    sections: list[str] = []
    for bundle in bundles:
        lines = [
            f"- `{bundle['name']}`",
            f"  - required: {'yes' if bundle['required'] else 'no'}",
        ]
        if bundle["description"]:
            lines.append(f"  - {bundle['description']}")
        lines.append("  - fields:")
        lines.extend(
            [f"    - {format_resolved_candidate_field(field)}" for field in bundle["fields"]]
        )
        sections.append("\n".join(lines))
    return "\n".join(sections)


def worker_footer_markdown(fields: list[str]) -> str:
    if not fields:
        return "- No worker footer fields are configured for this scaffold."
    return bullet_list(
        [
            f"`{field_name}`: {FOOTER_FIELD_DESCRIPTIONS.get(field_name, 'worker footer field')}"
            for field_name in fields
        ]
    )


def reread_reason_markdown(values: list[str]) -> str:
    if not values:
        return "- No explicit reread reasons are configured for this scaffold."
    return bullet_list([f"`{value}`" for value in values])


def overlay_precedence_markdown() -> str:
    return bullet_list(OVERLAY_PRECEDENCE_RULES)


def overlay_example_block() -> str:
    example = {
        "domain_overlay": {
            "proposal_enum_values": [
                "standalone_item",
                "reference_only",
                "ignore",
            ],
            "candidate_field_aliases": {
                "fact_summary": "summary",
                "proposal_classification": "proposed_classification",
                "supporting_references": "source_refs",
                "ambiguity": "open_ambiguity",
                "reread_control": "raw_reread_reason",
            },
            "reference_only_candidate_values": ["reference_only"],
            "output_inclusion_rules": {
                "standalone": ["standalone_item"],
                "reference_only": ["reference_only"],
                "excluded": ["ignore"],
            },
            "bundle_overrides": {
                "fact_and_evidence": {
                    "fields": ["fact_summary", "supporting_references"],
                }
            },
        }
    }
    return "\n".join(
        [
            "- No domain overlay is configured for this scaffold.",
            "- Use a domain overlay when you need domain-specific proposal enums, field names, reference-only classes, or output inclusion rules.",
            "```jsonc",
            json_block(example),
            "```",
        ]
    )


def overlay_markdown(spec: dict) -> str:
    overlay = spec["domain_overlay"]
    if not overlay["enabled"]:
        return overlay_example_block()

    sections: list[str] = ["- Domain overlay is enabled for this scaffold."]
    if overlay["proposal_enum_values"]:
        sections.append("- Proposal enum values:")
        sections.append(
            bullet_list(
                [f"`{value}`" for value in overlay["proposal_enum_values"]], indent="  "
            )
        )
    else:
        sections.append("- Proposal enum values are left to domain implementation.")

    if overlay["candidate_field_aliases"]:
        sections.append("- Candidate field aliases:")
        sections.append(
            bullet_list(
                [
                    f"`{semantic}` -> `{field_name}`"
                    for semantic, field_name in overlay["candidate_field_aliases"].items()
                ],
                indent="  ",
            )
        )
    else:
        sections.append("- Candidate field aliases are not configured; generic slot names stay in place.")

    if overlay["reference_only_candidate_values"]:
        sections.append("- Reference-only candidate values:")
        sections.append(
            bullet_list(
                [f"`{value}`" for value in overlay["reference_only_candidate_values"]],
                indent="  ",
            )
        )

    rules = overlay["output_inclusion_rules"]
    if any(rules.values()):
        sections.append("- Output inclusion rules:")
        for rule_name in ["standalone", "reference_only", "excluded"]:
            values = rules[rule_name]
            if values:
                sections.append(
                    f"  - `{rule_name}`: " + ", ".join(f"`{value}`" for value in values)
                )

    if overlay["bundle_overrides"]:
        sections.append("- Bundle overrides:")
        sections.append(
            bullet_list(
                [f"`{bundle_name}`" for bundle_name in overlay["bundle_overrides"]],
                indent="  ",
            )
        )

    sections.extend(
        [
            "- Normalized overlay:",
            "```json",
            json_block(
                {key: value for key, value in overlay.items() if key != "enabled"}
            ),
            "```",
        ]
    )
    return "\n".join(sections)


def lint_cli_section(spec: dict) -> tuple[str, str, str]:
    if not spec["needs_lint"]:
        return "", "", ""
    step = (
        f"- Run `<python-bin> -B <skill-dir>/scripts/lint_{spec['domain_slug']}.py --context <context-json> "
        "--output <lint-json>`."
    )
    script_line = (
        f"- `scripts/lint_{spec['domain_slug']}.py`\n"
        "  - Run deterministic checks and emit warnings, errors, and override signals."
    )
    arg = " --lint <lint-json>"
    return step, script_line, arg


def workflow_tail(spec: dict) -> str:
    step_number = 5
    sections: list[str] = []
    if spec["needs_validate"]:
        sections.append(
            "\n".join(
                [
                    f"{step_number}. Validate before mutating.",
                    f"- Run `<python-bin> -B <skill-dir>/scripts/validate_{spec['domain_slug']}.py --context <context-json> --plan <plan-json> --output <validation-json>`.",
                    "- Stop if validation reports errors, stale context, low-confidence findings, or an apply-gate failure.",
                ]
            )
        )
        step_number += 1
    if spec["needs_apply"]:
        sections.append(
            "\n".join(
                [
                    f"{step_number}. Apply only after local verification.",
                    f"- Run `<python-bin> -B <skill-dir>/scripts/apply_{spec['domain_slug']}.py --validation <validation-json>` after the validation output is locally reviewed.",
                    "- Apply must consume validator-normalized output only; do not wire raw plan JSON directly into the mutation step.",
                    "- If the user asked for `dry-run`, keep the same validation path and stop before any external mutation.",
                ]
            )
        )
    return "\n\n".join(sections)


def mutation_output_note(spec: dict) -> str:
    if spec["needs_apply"]:
        return "- Tell the user whether the run stopped at planning, validation, or apply."
    return "- Tell the user whether the run stopped at analysis or produced a non-mutating plan."


def batch_note(spec: dict) -> str:
    if spec["uses_batch_packets"]:
        return "- Prefer `batch-packet-*.json` before singleton packets when both exist."
    return "- This scaffold defaults to singleton focused packets only."


def profile_runtime_note(spec: dict) -> str:
    if spec["orchestrator_profile"] == "packet-heavy-orchestrator":
        return "\n".join(
            [
                "- Orchestrator profile: `packet-heavy-orchestrator`.",
                "- Keep runtime contract metadata lean. Put packet sizing, byte proxies, and delegation-efficiency counters in `packet_metrics.json` and evaluation logs instead of `orchestrator.json`.",
                "- Read `synthesis_packet.json` as the shared local drafting packet before reopening raw artifacts.",
            ]
        )
    return "\n".join(
        [
            "- Orchestrator profile: `standard`.",
            "- Keep runtime metadata focused on routing, authority, stop conditions, and adjudication support only.",
        ]
    )


def profile_runtime_artifacts(spec: dict) -> str:
    if spec["orchestrator_profile"] == "packet-heavy-orchestrator":
        return "\n".join(
            [
                "- Additional runtime packet:",
                "  - `synthesis_packet.json` for common-path local drafting and synthesis.",
            ]
        )
    return "- No additional orchestrator-profile-specific runtime packet is required."


def profile_evaluation_artifacts(spec: dict) -> str:
    if spec["orchestrator_profile"] == "packet-heavy-orchestrator":
        return "\n".join(
            [
                "- Evaluation-only sidecar:",
                "  - `packet_metrics.json` for packet sizing, byte proxies, and regression-oriented token-efficiency estimates.",
            ]
        )
    return "- No orchestrator-profile-specific evaluation sidecar is required."


def build_result_note(spec: dict) -> str:
    if spec["orchestrator_profile"] == "packet-heavy-orchestrator":
        return (
            "- Recommended: add `--result-output <build-result-json>` so evaluation logging can merge build-phase packet metrics without expanding runtime contract metadata."
        )
    return (
        "- Optional: add `--result-output <build-result-json>` when you want a machine-readable build summary for smoke runs or evaluation logging."
    )


def common_path_note(spec: dict) -> str:
    if spec["orchestrator_profile"] != "packet-heavy-orchestrator":
        return "- This scaffold does not add an orchestrator-profile-level common-path drafting packet."
    return "\n".join(
        [
            "- Packet-heavy common path contract:",
            "  - read `global_packet.json` first",
            "  - keep `synthesis_packet.json` open for local drafting",
            "  - reopen at most one focused packet in the common path",
            "  - treat packet insufficiency as a build/contract failure instead of compensating with broad raw rereads",
        ]
    )


def validate_result_contract(spec: dict) -> str:
    if not spec["needs_validate"]:
        return ""
    return "\n".join(
        [
            "- Validation output must at least include:",
            "  - `valid`",
            "  - `can_apply`",
            "  - `errors`",
            "  - `warnings`",
            "  - `stop_reasons`",
            "  - `normalized_plan`",
            "  - `normalized_plan_fingerprint`",
            "  - `apply_gate_status`",
        ]
    )


def validate_script_section(spec: dict) -> str:
    if not spec["needs_validate"]:
        return ""
    return (
        f"- `scripts/validate_{spec['domain_slug']}.py`\n"
        "  - Validate the planned actions against the collected context, normalize the plan, and emit apply-gate status before apply."
    )


def apply_script_section(spec: dict) -> str:
    if not spec["needs_apply"]:
        return ""
    return (
        f"- `scripts/apply_{spec['domain_slug']}.py`\n"
        "  - Dry-run or apply only from validator-normalized output after local verification."
    )


def contract_plan_note(spec: dict) -> str:
    if not spec["needs_apply"] and not spec["needs_validate"]:
        return "- This archetype does not require a dedicated plan file by default."
    return (
        "- Suggested plan artifact: `<domain>-plan.json` with `context_id`, "
        "`overall_confidence`, `selected_packets`, `actions`, `stop_reasons`, and optional "
        "`draft_basis` notes for common-path local drafting."
    )


def validate_plan_contract(spec: dict) -> str:
    if not spec["needs_validate"]:
        return ""
    return "\n".join(
        [
            "## Validate Contract",
            "",
            f"- `scripts/validate_{spec['domain_slug']}.py` should accept:",
            "  - `--context <json>`",
            "  - `--plan <json>`",
            "  - `--output <json>`",
            "- Plan field policy for the generated skeleton:",
            "  - required: `skill_name`, `context_id`, `selected_packets`, `actions`, `stop_reasons`",
            "  - allowed: required fields plus `overall_confidence`, `review_mode`, `notes`, `draft_basis`",
            "  - ignored: `metadata`",
            "- Unknown extra plan fields should be dropped from the normalized plan and surfaced with a fixed warning code.",
            validate_result_contract(spec),
            "",
        ]
    )


def apply_plan_contract(spec: dict) -> str:
    if not spec["needs_apply"]:
        return ""
    return "\n".join(
        [
            "## Apply Contract",
            "",
            f"- `scripts/apply_{spec['domain_slug']}.py` should accept:",
            "  - `--validation <json>`",
            "  - optional `--dry-run`",
            "  - optional `--result-output <json>`",
            "- Apply must consume validator-normalized output only and recompute the normalized plan fingerprint before mutating.",
            "- The default generated skeleton is intentionally conservative and does not perform real mutations until domain logic is implemented.",
            "",
        ]
    )


def lint_template_blocks(spec: dict) -> tuple[str, str]:
    if spec["needs_lint"]:
        return (
            '    parser.add_argument("--lint", help="Optional lint findings JSON.")',
            "    lint = load_json(Path(args.lint)) if args.lint else {}",
        )
    return "", "    lint = {}"


def batch_block(spec: dict) -> str:
    if not spec["uses_batch_packets"]:
        return ""
    return """
    batch_packet = {
        "packet_id": "batch-packet-01",
        "packet_kind": "batch",
        "packet_targets": PACKET_NAMES,
        "context_id": context.get("context_id"),
        "todo": "Group related singleton packets here when the workflow benefits from clustering.",
    }
    write_json(output_dir / "batch-packet-01.json", batch_packet)
""".rstrip("\n")


def lint_warning_block(spec: dict) -> str:
    if spec["optional_local_helper"]:
        return """
    helper = context.get("optional_local_helper") or {}
    if helper.get("status") == "missing_optional_local_helper":
        findings["warnings"].append(
            "Optional local helper is missing; omit handoff commands until the helper exists."
        )
"""
    return ""


def active_worker_contract_note(spec: dict) -> str:
    if spec["worker_return_contract"] == "generic":
        return "\n".join(
            [
                "- Active worker return contract: `generic`.",
                "- Active worker output shape: `flat`.",
                "- Return exactly:",
                "  - `packet ids`",
                "  - `primary outcome`",
                "  - `evidence files`",
                "  - `recommended next step`",
                "  - `risk`",
                "  - `tests or checks`",
            ]
        )

    if spec["worker_output_shape"] == "hierarchical":
        return "\n".join(
            [
                "- Active worker return contract: `classification-oriented`.",
                "- Active worker output shape: `hierarchical`.",
                "- Return exactly:",
                "  - `candidates[]`",
                "  - `footer`",
                "- Each `candidates[]` entry must include:",
                "  - fixed `candidate_id`",
                candidate_bundle_markdown(spec["resolved_candidate_field_bundles"]).replace(
                    "\n", "\n  "
                ),
                "- Keep candidate-level factual summaries inside `candidates[]` only.",
                "- `footer` must include:",
                worker_footer_markdown(spec["worker_footer_fields"]).replace("\n", "\n  "),
                "- Use `footer.primary_outcome` as the worker-level batch summary only.",
                "- Treat proposal classifications as worker proposal only; the main agent may override them.",
                "- Treat `footer.overall_confidence` as worker batch confidence only; final plan confidence is recomputed locally.",
            ]
        )

    return "\n".join(
        [
            "- Active worker return contract: `classification-oriented`.",
            "- Active worker output shape: `flat`.",
            "- Return exactly:",
            "  - `packet ids`",
            "  - `candidate records`",
            "  - `packet confidence`",
            "  - `missing evidence`",
            "  - `candidate conflicts`",
            "  - `recommended next step`",
            "  - `tests or checks`",
            "- Treat proposal classifications as worker proposal only; the main agent may override them.",
        ]
    )


def worker_prompt_return_block(spec: dict) -> str:
    if spec["worker_return_contract"] == "generic":
        return "\n".join(
            [
                "Return exactly:",
                "- packet ids",
                "- primary outcome",
                "- evidence files",
                "- recommended next step",
                "- risk",
                "- tests or checks",
            ]
        )

    if spec["worker_output_shape"] == "hierarchical":
        return "\n".join(
            [
                "Return exactly:",
                "- candidates[]",
                "- footer",
                "",
                "Each candidate must include:",
                "- candidate_id",
                candidate_bundle_markdown(spec["resolved_candidate_field_bundles"]),
                "",
                "Footer must include:",
                worker_footer_markdown(spec["worker_footer_fields"]),
                "",
                "Treat proposal classifications as worker proposal only.",
                "Keep candidate-level factual summaries inside candidates[].",
                "Use footer.primary_outcome as the worker-level batch summary only.",
                "Treat footer.overall_confidence as worker batch confidence only; final plan confidence is recomputed locally.",
            ]
        )

    return "\n".join(
        [
            "Return exactly:",
            "- packet ids",
            "- candidate records",
            "- packet confidence",
            "- missing evidence",
            "- candidate conflicts",
            "- recommended next step",
            "- tests or checks",
            "",
            "Treat proposal classifications as worker proposal only.",
        ]
    )


def worker_output_guidance(spec: dict) -> str:
    if spec["worker_return_contract"] == "generic":
        return "\n".join(
            [
                "- Keep final adjudication local.",
                "- Keep worker outputs narrow and use them as inputs to local synthesis, not as final decisions.",
                "- Recompute final plan confidence locally during synthesis from packet evidence, worker outputs, unresolved reread exceptions, and authority conflicts.",
                "- Use the named context/findings worker family when delegation is needed and keep candidate-producing workers optional unless the workflow becomes adjudication-heavy.",
            ]
        )

    lines = [
        "- Final adjudication stays local even when mini workers propose candidate classifications.",
        "- Treat proposal classifications as worker proposal only; the main agent may override them.",
        "- Recompute final plan confidence locally during synthesis from packet evidence, worker outputs, unresolved reread exceptions, and authority conflicts.",
        f"- Domain-specific candidate semantics come from `references/{spec['domain_slug'].replace('_', '-')}-contract.md`, not from the base builder contract.",
        "- Prefer named worker families: `repo_mapper` and `docs_verifier` for context/findings, `evidence_summarizer`, `large_diff_auditor`, and `log_triager` for candidate production.",
    ]
    if spec["worker_output_shape"] == "hierarchical":
        lines.extend(
            [
                "- Workers return `candidates[]` plus `footer` in hierarchical mode.",
                "- Keep candidate-level fact summaries inside `candidates[]`.",
                "- Keep the worker batch summary inside `footer.primary_outcome` only.",
                "- Treat `footer.overall_confidence` as worker batch confidence only, not final plan confidence.",
            ]
        )
    else:
        lines.append(
            "- Keep proposal-grade candidate records flat only when compatibility requires it; do not treat worker classifications as final adjudication."
        )
    return "\n".join(lines)


def decision_ready_skill_guidance(spec: dict) -> str:
    if spec["worker_return_contract"] != "classification-oriented":
        return (
            "- Start from packetized evidence first and only widen to raw artifact rereads when "
            "the reread policy is triggered."
        )
    lines = [
        "- Treat focused packets as decision-ready candidate inputs, not hint-only summaries.",
        f"- Worker output shape for this skill: `{spec['worker_output_shape']}`.",
        "- Keep final adjudication local even when workers propose classifications.",
        "- Recompute final plan confidence locally from packet evidence, worker outputs, unresolved reread exceptions, and authority conflicts.",
        f"- Use `references/{spec['domain_slug'].replace('_', '-')}-contract.md` for domain-specific proposal enums, candidate aliases, reference-only classes, and inclusion rules.",
    ]
    if spec["worker_output_shape"] == "hierarchical":
        lines.extend(
            [
                "- Keep candidate-level fact summaries inside `candidates[]` and the worker batch summary inside `footer.primary_outcome` only.",
                "- Treat `footer.overall_confidence` as worker batch confidence only, not final plan confidence.",
            ]
        )
    return "\n".join(lines)


def confidence_layering_note(spec: dict) -> str:
    if spec["worker_return_contract"] == "classification-oriented":
        if spec["worker_output_shape"] == "hierarchical":
            return (
                "Final plan confidence is recomputed locally even when "
                "`footer.overall_confidence` is present."
            )
        return (
            "Final plan confidence is recomputed locally even when packet or "
            "candidate confidence signals are present."
        )
    return (
        "Final plan confidence is recomputed locally even when worker confidence "
        "signals are present."
    )


def generic_adjudication_section(spec: dict) -> str:
    lines = [
        "## Generic Adjudication Structure",
        "",
        f"- This scaffold uses the `{spec['worker_return_contract']}` worker return contract.",
        f"- XHigh reread policy: {spec['xhigh_reread_policy']}",
        "- Final plan confidence is recomputed locally during synthesis. Do not copy worker confidence through unchanged.",
    ]
    if spec["worker_return_contract"] == "classification-oriented":
        lines.extend(
            [
                f"- Worker output shape: `{spec['worker_output_shape']}`",
                "- Proposal classifications are worker proposal only. The main agent may override them during local adjudication.",
            ]
        )
        if spec["worker_output_shape"] == "hierarchical":
            lines.extend(
                [
                    "- Hierarchical worker output uses fixed top-level keys:",
                    "  - `candidates[]`",
                    "  - `footer`",
                    "- Candidate field bundles:",
                    candidate_bundle_markdown(spec["resolved_candidate_field_bundles"]),
                    "- Worker footer fields:",
                    worker_footer_markdown(spec["worker_footer_fields"]),
                    "- Allowed reread reasons:",
                    reread_reason_markdown(spec["reread_reason_values"]),
                ]
            )
    else:
        lines.extend(
            [
                "- Generic flat mode does not require hierarchical `candidates[]` plus `footer` worker output.",
            ]
        )
    return "\n".join(lines)


def worker_family_section(spec: dict) -> str:
    lines = [
        "## Worker Families",
        "",
        "- The builder keeps worker-family structure generic and reusable across packet-driven workflows.",
        "- Preferred worker families for this scaffold:",
        worker_family_markdown(spec),
        "",
        "- Surfaced optional worker pool for generated docs stays deduped even when a worker belongs to multiple families:",
        bullet_list([f"`{agent_type}`" for agent_type in surfaced_optional_worker_pool(spec)]),
        "",
        "- Packet routing hook:",
        packet_worker_map_markdown(spec["packet_worker_map"]),
        "",
        worker_selection_guidance_markdown(spec["worker_selection_guidance"]),
    ]
    return "\n".join(lines)


def domain_overlay_section(spec: dict) -> str:
    return "\n".join(
        [
            "## Domain Overlay",
            "",
            "- Domain overlays specialize semantics without changing the shared adjudication structure.",
            "- Precedence order:",
            overlay_precedence_markdown(),
            "",
            overlay_markdown(spec),
        ]
    )


def focused_packet_template(spec: dict) -> str:
    if spec["worker_return_contract"] == "classification-oriented":
        if spec["worker_output_shape"] == "hierarchical":
            return "\n".join(
                [
                    "{",
                    '                "packet_id": packet_name,',
                    '                "packet_kind": "focused",',
                    '                "context_id": context.get("context_id"),',
                    '                "repo_profile_name": context.get("repo_profile_name"),',
                    '                "decision_ready": True,',
                    '                "worker_return_contract": SPEC_METADATA["worker_return_contract"],',
                    '                "worker_output_shape": SPEC_METADATA["worker_output_shape"],',
                    '                "candidate_field_bundles": SPEC_METADATA["resolved_candidate_field_bundles"],',
                    '                "worker_footer_fields": SPEC_METADATA["worker_footer_fields"],',
                    '                "reread_reason_values": SPEC_METADATA["reread_reason_values"],',
                    '                "domain_overlay": SPEC_METADATA["domain_overlay"],',
                    '                "candidates": [],',
                    '                "candidate_template": SPEC_METADATA["candidate_template"],',
                    '                "footer": SPEC_METADATA["footer_template"],',
                    '                "todo": "Populate candidates[] plus footer with decision-ready worker proposals. Keep final adjudication and final plan confidence local.",',
                    "            }",
                ]
            )
        return "\n".join(
            [
                "{",
                '                "packet_id": packet_name,',
                '                "packet_kind": "focused",',
                '                "context_id": context.get("context_id"),',
                '                "repo_profile_name": context.get("repo_profile_name"),',
                '                "decision_ready": True,',
                '                "worker_return_contract": SPEC_METADATA["worker_return_contract"],',
                '                "worker_output_shape": SPEC_METADATA["worker_output_shape"],',
                '                "candidate_field_bundles": SPEC_METADATA["resolved_candidate_field_bundles"],',
                '                "reread_reason_values": SPEC_METADATA["reread_reason_values"],',
                '                "domain_overlay": SPEC_METADATA["domain_overlay"],',
                '                "todo": "Populate this packet with flat classification-oriented worker outputs only if hierarchical output is intentionally disabled for compatibility.",',
                "            }",
            ]
        )
    return "\n".join(
        [
            "{",
            '                "packet_id": packet_name,',
            '                "packet_kind": "focused",',
            '                "context_id": context.get("context_id"),',
            '                "repo_profile_name": context.get("repo_profile_name"),',
            '                "decision_ready": False,',
            '                "worker_return_contract": SPEC_METADATA["worker_return_contract"],',
            '                "todo": "Populate this packet with one narrow workflow concern.",',
            "            }",
        ]
    )


def worker_instruction(agent_type: str, spec: dict) -> str:
    if agent_type == "repo_mapper":
        return (
            "Read global_packet.json first and return packet-friendly mapping findings "
            "covering execution path, touched surfaces, packet membership hints, "
            "assumptions, unknowns, and exact refs."
        )
    if agent_type == "packet_explorer":
        return (
            "Read global_packet.json first, then exactly one focused packet or one "
            "batch packet. Open extra file slices only when the packet cannot carry "
            "enough evidence on its own. Return packet-friendly code, behavior, or "
            "workflow findings without final adjudication or mutation."
        )
    if agent_type == "docs_verifier":
        return (
            "Read global_packet.json first and return narrow verification findings with "
            "verified claims, inferred claims, unknowns or claim gaps, and exact refs."
        )
    if spec["worker_return_contract"] == "classification-oriented":
        if spec["worker_output_shape"] == "hierarchical":
            return (
                "Read global_packet.json first and return hierarchical proposal-grade "
                "candidate output with candidates[] plus footer."
            )
        return (
            "Read global_packet.json first and return flat proposal-grade candidate output."
        )
    return "Read global_packet.json first and stay narrow."


def worker_instruction_map(spec: dict) -> dict[str, str]:
    return {
        agent_type: worker_instruction(agent_type, spec)
        for agent_type in KNOWN_WORKER_AGENT_TYPES
    }


def build_render_context(spec: dict) -> dict[str, str]:
    lint_step, lint_script_section, build_lint_arg = lint_cli_section(spec)
    skill_title = title_case(spec["skill_name"])
    contract_file = spec["domain_slug"].replace("_", "-") + "-contract.md"
    spec_metadata = {
        "skill_name": spec["skill_name"],
        "domain_slug": spec["domain_slug"],
        "workflow_family": spec["workflow_family"],
        "archetype": spec["archetype"],
        "orchestrator_profile": spec["orchestrator_profile"],
        "primary_goal": spec["primary_goal"],
        "task_packet_names": spec["task_packet_names"],
        "uses_batch_packets": spec["uses_batch_packets"],
        "needs_lint": spec["needs_lint"],
        "needs_validate": spec["needs_validate"],
        "needs_apply": spec["needs_apply"],
        "authority_order": spec["authority_order"],
        "stop_conditions": spec["stop_conditions"],
        "review_mode_overrides": spec["review_mode_overrides"],
        "trigger_phrases": spec["trigger_phrases"],
        "decision_ready_packets": spec["decision_ready_packets"],
        "worker_return_contract": spec["worker_return_contract"],
        "worker_output_shape": spec["worker_output_shape"],
        "xhigh_reread_policy": spec["xhigh_reread_policy"],
        "required_candidate_fields": spec["required_candidate_fields"],
        "candidate_field_bundles": spec["candidate_field_bundles"],
        "resolved_candidate_field_bundles": spec["resolved_candidate_field_bundles"],
        "worker_footer_fields": spec["worker_footer_fields"],
        "reread_reason_values": spec["reread_reason_values"],
        "known_worker_agent_types": spec["known_worker_agent_types"],
        "preferred_worker_families": spec["preferred_worker_families"],
        "packet_worker_map": spec["packet_worker_map"],
        "worker_selection_guidance": spec["worker_selection_guidance"],
        "builder_versioning": spec["builder_versioning"],
        "repo_profile": spec["repo_profile"],
        "domain_overlay": spec["domain_overlay"],
        "candidate_template": spec["candidate_template"],
        "footer_template": spec["footer_template"],
        "shared_local_packet": spec["shared_local_packet"],
        "common_path_contract": spec["common_path_contract"],
    }
    if spec["optional_local_helper"]:
        spec_metadata["optional_local_helper"] = spec["optional_local_helper"]

    lint_arg_block, lint_load_block = lint_template_blocks(spec)
    return {
        "SKILL_NAME": spec["skill_name"],
        "SKILL_TITLE": skill_title,
        "DESCRIPTION": spec["description"],
        "SHORT_DESCRIPTION": short_description(spec["primary_goal"]),
        "DEFAULT_PROMPT": spec["primary_goal"],
        "RETAINED_SKILL_DIR": (
            f"../../../builders/packet-workflow/retained-skills/{spec['skill_name']}"
        ),
        "RETAINED_SKILL_MD": (
            f"../../../builders/packet-workflow/retained-skills/{spec['skill_name']}/SKILL.md"
        ),
        "DOMAIN_SLUG": spec["domain_slug"],
        "WORKFLOW_FAMILY": spec["workflow_family"],
        "PRIMARY_GOAL": spec["primary_goal"],
        "ARCHETYPE": spec["archetype"],
        "ORCHESTRATOR_PROFILE": spec["orchestrator_profile"],
        "TRIGGER_PHRASES_BULLETS": bullet_list(spec["trigger_phrases"]),
        "TASK_PACKET_BULLETS": bullet_list(
            [f"`{name}.json`" for name in spec["task_packet_names"]]
        ),
        "AUTHORITY_ORDER_BULLETS": bullet_list(spec["authority_order"]),
        "STOP_CONDITIONS_BULLETS": bullet_list(spec["stop_conditions"]),
        "REVIEW_MODE_OVERRIDES_BULLETS": bullet_list(spec["review_mode_overrides"]),
        "OPTIONAL_LOCAL_HELPER_NOTE": helper_note(spec),
        "REPO_PROFILE_NOTE": repo_profile_note(spec),
        "REPO_PROFILE_FILE": spec["repo_profile"]["profile_path"],
        "REPO_PROFILE_NAME": spec["repo_profile"]["name"],
        "REPO_PROFILE_SUMMARY": spec["repo_profile"]["summary"],
        "REPO_PROFILE_BINDINGS_MARKDOWN": repo_profile_bindings_markdown(spec),
        "REPO_PROFILE_PACKET_DEFAULTS_MARKDOWN": repo_profile_packet_defaults_markdown(spec),
        "REPO_PROFILE_LINT_RULES_MARKDOWN": repo_profile_lint_rules_markdown(spec),
        "REPO_PROFILE_NOTES_MARKDOWN": repo_profile_notes_markdown(spec),
        "REPO_PROFILE_JSON": json_block(spec["repo_profile"]),
        "CORE_CONTRACT_FILE": "core-contract.md",
        "WORKFLOW_TAIL": workflow_tail(spec),
        "MUTATION_OUTPUT_NOTE": mutation_output_note(spec),
        "BATCH_PACKET_NOTE": batch_note(spec),
        "PROFILE_RUNTIME_NOTE": profile_runtime_note(spec),
        "PROFILE_RUNTIME_ARTIFACTS": profile_runtime_artifacts(spec),
        "PROFILE_EVALUATION_ARTIFACTS": profile_evaluation_artifacts(spec),
        "BUILD_RESULT_NOTE": build_result_note(spec),
        "COMMON_PATH_NOTE": common_path_note(spec),
        "LINT_STEP": lint_step,
        "LINT_SCRIPT_SECTION": lint_script_section,
        "VALIDATE_SCRIPT_SECTION": validate_script_section(spec),
        "APPLY_SCRIPT_SECTION": apply_script_section(spec),
        "BUILD_LINT_ARG": build_lint_arg,
        "DOMAIN_CONTRACT_FILE": contract_file,
        "DOMAIN_CONTRACT_PLAN_NOTE": contract_plan_note(spec),
        "VALIDATE_PLAN_CONTRACT": validate_plan_contract(spec),
        "APPLY_PLAN_CONTRACT": apply_plan_contract(spec),
        "DECISION_READY_PACKETS": "true" if spec["decision_ready_packets"] else "false",
        "WORKER_RETURN_CONTRACT": spec["worker_return_contract"],
        "WORKER_OUTPUT_SHAPE": spec["worker_output_shape"],
        "XHIGH_REREAD_POLICY": spec["xhigh_reread_policy"],
        "WORKER_OUTPUT_GUIDANCE": worker_output_guidance(spec),
        "KNOWN_WORKER_AGENT_TYPES_BULLETS": bullet_list(
            [f"`{agent_type}`" for agent_type in spec["known_worker_agent_types"]]
        ),
        "WORKER_FAMILY_MARKDOWN": worker_family_markdown(spec),
        "PACKET_WORKER_MAP_MARKDOWN": packet_worker_map_markdown(
            spec["packet_worker_map"]
        ),
        "WORKER_SELECTION_GUIDANCE_MARKDOWN": worker_selection_guidance_markdown(
            spec["worker_selection_guidance"]
        ),
        "SURFACED_OPTIONAL_WORKERS_BULLETS": (
            bullet_list(
                [
                    f"`{agent_type}`"
                    for agent_type in surfaced_optional_worker_list_for_docs(spec)
                ]
            )
            or "- no additional optional workers remain after explicit packet routing"
        ),
        "CANDIDATE_FIELD_BUNDLES_MARKDOWN": candidate_bundle_markdown(
            spec["resolved_candidate_field_bundles"]
        ),
        "WORKER_FOOTER_FIELDS_MARKDOWN": worker_footer_markdown(
            spec["worker_footer_fields"]
        ),
        "REREAD_REASON_VALUES_MARKDOWN": reread_reason_markdown(
            spec["reread_reason_values"]
        ),
        "OVERLAY_PRECEDENCE_MARKDOWN": overlay_precedence_markdown(),
        "DOMAIN_OVERLAY_MARKDOWN": overlay_markdown(spec),
        "ACTIVE_WORKER_CONTRACT_NOTE": active_worker_contract_note(spec),
        "WORKER_PROMPT_RETURN_BLOCK": worker_prompt_return_block(spec),
        "CONFIDENCE_LAYERING_NOTE": confidence_layering_note(spec),
        "DECISION_READY_SKILL_GUIDANCE": decision_ready_skill_guidance(spec),
        "GENERIC_ADJUDICATION_SECTION": generic_adjudication_section(spec),
        "WORKER_FAMILY_SECTION": worker_family_section(spec),
        "DOMAIN_OVERLAY_SECTION": domain_overlay_section(spec),
        "FOCUSED_PACKET_TEMPLATE": focused_packet_template(spec),
        "WORKER_INSTRUCTION_MAP_JSON": python_block(worker_instruction_map(spec)),
        "SPEC_METADATA_JSON": python_block(spec_metadata),
        "TASK_PACKET_NAMES_JSON": python_block(spec["task_packet_names"]),
        "USES_BATCH_PACKETS": "True" if spec["uses_batch_packets"] else "False",
        "REVIEW_MODE_OVERRIDES_JSON": python_block(spec["review_mode_overrides"]),
        "AUTHORITY_ORDER_JSON": python_block(spec["authority_order"]),
        "STOP_CONDITIONS_JSON": python_block(spec["stop_conditions"]),
        "LINT_ARG_BLOCK": lint_arg_block,
        "LINT_LOAD_BLOCK": lint_load_block,
        "BATCH_BLOCK": batch_block(spec),
        "EXPECTS_LOCAL_HELPER": "True" if spec["optional_local_helper"] else "False",
        "LINT_WARNING_BLOCK": lint_warning_block(spec),
        "HELPER_COLLECT_ARG_BLOCK": helper_collect_arg(spec),
        "HELPER_COLLECT_FUNCTIONS": helper_collect_functions(spec),
        "HELPER_COLLECT_CONTEXT_LINE": helper_collect_context_line(spec),
    }


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8", newline="\n")


def generate_retained_files(skill_dir: Path, spec: dict) -> list[Path]:
    context = build_render_context(spec)
    generated: list[Path] = []

    outputs = {
        "SKILL.md": "skill_md.tmpl",
        "agents/openai.yaml": "openai_yaml.tmpl",
        "references/core-contract.md": "core_contract.tmpl",
        "references/delegation-playbook.md": "delegation_playbook.tmpl",
        f"references/{spec['domain_slug'].replace('_', '-')}-contract.md": "domain_contract.tmpl",
        "references/evaluation-log-contract.md": "evaluation_log_contract.tmpl",
        f"references/{spec['domain_slug'].replace('_', '-')}-evaluation-contract.md": "domain_evaluation_contract.tmpl",
        f"scripts/collect_{spec['domain_slug']}_context.py": "collect_context.py.tmpl",
        f"scripts/build_{spec['domain_slug']}_packets.py": "build_packets.py.tmpl",
        "scripts/write_evaluation_log.py": "write_evaluation_log.py.tmpl",
        spec["repo_profile"]["profile_path"]: "repo_profile_json.tmpl",
    }
    if spec["needs_lint"]:
        outputs[f"scripts/lint_{spec['domain_slug']}.py"] = "lint.py.tmpl"
    if spec["needs_validate"]:
        outputs[f"scripts/validate_{spec['domain_slug']}.py"] = "validate.py.tmpl"
    if spec["needs_apply"]:
        outputs[f"scripts/apply_{spec['domain_slug']}.py"] = "apply.py.tmpl"

    for relative_path, template_name in outputs.items():
        destination = skill_dir / relative_path
        write_text(destination, render(template_name, context))
        generated.append(destination)

    return generated


def generate_wrapper_files(wrapper_dir: Path, spec: dict) -> list[Path]:
    context = build_render_context(spec)
    generated: list[Path] = []
    outputs = {
        "SKILL.md": "skill_wrapper_md.tmpl",
        "agents/openai.yaml": "openai_yaml.tmpl",
    }
    for relative_path, template_name in outputs.items():
        destination = wrapper_dir / relative_path
        write_text(destination, render(template_name, context))
        generated.append(destination)
    return generated


def generate_files(skill_dir: Path, spec: dict) -> list[Path]:
    return generate_retained_files(skill_dir, spec)


def ensure_target_is_empty(path: Path, *, label: str) -> None:
    if path.exists() and any(path.iterdir()):
        raise ValueError(f"Refusing to overwrite non-empty {label}: {path}")


def generate_skill_layout(
    output_root: Path, spec: dict
) -> tuple[Path, list[Path], Path, list[Path]]:
    retained_dir = retained_skills_root(output_root) / str(spec["skill_name"])
    wrapper_dir = wrapper_skills_root(output_root) / str(spec["skill_name"])
    ensure_target_is_empty(retained_dir, label="retained skill directory")
    ensure_target_is_empty(wrapper_dir, label="wrapper skill directory")
    retained_dir.mkdir(parents=True, exist_ok=True)
    wrapper_dir.mkdir(parents=True, exist_ok=True)
    retained_files = generate_retained_files(retained_dir, spec)
    wrapper_files = generate_wrapper_files(wrapper_dir, spec)
    return retained_dir, retained_files, wrapper_dir, wrapper_files


def main() -> int:
    args = parse_args()
    spec_path = Path(args.spec).resolve()
    output_dir = Path(args.output_dir).resolve()

    try:
        validate_managed_agent_registry(args.managed_agents_dir)
        spec = derive_spec(load_spec(spec_path))
        retained_dir, retained_files, wrapper_dir, wrapper_files = generate_skill_layout(
            output_dir, spec
        )
    except ValueError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    print(f"[OK] Generated retained {spec['skill_name']} kernel at {retained_dir}")
    for path in retained_files:
        print(f" - retained {path.relative_to(retained_dir)}")
    print(f"[OK] Generated thin wrapper for {spec['skill_name']} at {wrapper_dir}")
    for path in wrapper_files:
        print(f" - wrapper {path.relative_to(wrapper_dir)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
