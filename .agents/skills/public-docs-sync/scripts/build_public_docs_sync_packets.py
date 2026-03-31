#!/usr/bin/env python3
"""Build focused packets for public-docs-sync from collected context."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from public_docs_sync_contract import (
    ARCHETYPE,
    DECISION_READY_PACKETS,
    ORCHESTRATOR_PROFILE,
    PACKET_NAMES,
    PACKET_WORKER_MAP,
    PREFERRED_WORKER_FAMILIES,
    RAW_REREAD_ALLOWED_REASONS,
    REVIEW_MODE_OVERRIDES,
    WORKER_OUTPUT_SHAPE,
    WORKER_RETURN_CONTRACT,
    WORKER_SELECTION_GUIDANCE,
    WORKFLOW_FAMILY,
    XHIGH_REREAD_POLICY,
    compute_packet_metrics,
    dedupe_preserve,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context", required=True, help="Collected context JSON.")
    parser.add_argument("--lint", help="Optional lint findings JSON.")
    parser.add_argument("--output-dir", required=True, help="Packet output directory.")
    parser.add_argument("--result-output", help="Optional build result JSON.")
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def next_mode(mode: str) -> str:
    order = ["local-only", "targeted-delegation", "broad-delegation"]
    return order[min(order.index(mode) + 1, len(order) - 1)]


def truthy_override_signals(context: dict[str, Any], lint: dict[str, Any]) -> list[str]:
    signals: list[str] = []
    for payload in (context.get("override_signals", {}), lint.get("override_signals", {})):
        if not isinstance(payload, dict):
            continue
        for name, value in payload.items():
            if bool(value):
                signals.append(str(name))
    return dedupe_preserve(signals)


def compute_review_mode(context: dict[str, Any], lint: dict[str, Any]) -> tuple[str, bool, list[str]]:
    counts = context.get("counts", {})
    active_packets = int(counts.get("active_packet_count", 0))
    changed_files = int(counts.get("changed_files", 0))
    doc_changes = int(counts.get("doc_changes", 0))
    code_changes = int(counts.get("code_changes", 0))

    mode = "local-only"
    if active_packets >= 4 or changed_files > 20:
        mode = "broad-delegation"
    elif active_packets >= 2 or (doc_changes > 0 and code_changes > 0):
        mode = "targeted-delegation"

    applied_signals = truthy_override_signals(context, lint)
    if applied_signals:
        mode = next_mode(mode)
    return mode, bool(applied_signals), applied_signals


def routed_packet_names(active_packet_names: list[str], uses_batch_packets: bool) -> list[str]:
    routed = []
    for packet_name in active_packet_names:
        if packet_name == "forms_batch_packet" and uses_batch_packets:
            routed.append("batch-packet-01")
        else:
            routed.append(packet_name)
    return routed


def recommended_workers(
    packet_names: list[str],
    review_mode: str,
) -> list[dict[str, str]]:
    if review_mode == "local-only":
        return []
    max_workers = 2 if review_mode == "targeted-delegation" else 4
    workers: list[dict[str, str]] = []
    for packet_name in packet_names[:max_workers]:
        agent_types = PACKET_WORKER_MAP.get(packet_name) or ["docs_verifier"]
        agent_type = agent_types[0]
        workers.append(
            {
                "name": packet_name,
                "agent_type": agent_type,
                "packet": f"{packet_name}.json",
                "instruction": "Read global_packet.json first, stay narrow, and return only evidence-backed doc drift or sync gaps.",
            }
        )
    return workers


def optional_workers(
    review_mode: str,
    recommended: list[dict[str, str]],
) -> list[dict[str, Any]]:
    if review_mode != "broad-delegation":
        return []
    chosen = {item["agent_type"] for item in recommended}
    remaining = dedupe_preserve(
        [
            *PREFERRED_WORKER_FAMILIES["context_findings"],
            *PREFERRED_WORKER_FAMILIES["candidate_producers"],
            *PREFERRED_WORKER_FAMILIES["verifiers"],
        ]
    )
    optional: list[dict[str, Any]] = []
    for agent_type in remaining:
        if agent_type in chosen:
            continue
        optional.append(
            {
                "name": agent_type,
                "agent_type": agent_type,
                "packets": ["global_packet.json"],
                "responsibility": WORKER_SELECTION_GUIDANCE["agent_type_guidance"].get(agent_type, ""),
                "reasoning_effort": "low",
            }
        )
    return optional


def lint_issues_for_packet(lint: dict[str, Any], packet_name: str) -> list[dict[str, Any]]:
    return [
        issue
        for issue in lint.get("issues", [])
        if issue.get("packet") == packet_name
    ]


def doc_summaries(context: dict[str, Any], packet: dict[str, Any]) -> list[dict[str, Any]]:
    inventory = context.get("public_doc_inventory", {})
    summaries: list[dict[str, Any]] = []
    for relpath in packet.get("review_docs", []):
        entry = inventory.get(relpath, {})
        summaries.append(
            {
                "path": relpath,
                "exists": entry.get("exists", False),
                "kind": entry.get("kind"),
                "sha256": entry.get("sha256"),
                "headings": entry.get("headings", []),
                "preview_lines": entry.get("preview_lines", []),
                "issue_form": entry.get("issue_form"),
                "publish_configuration": entry.get("publish_configuration"),
                "settings_table": entry.get("settings_table"),
            }
        )
    return summaries


def changed_summaries(context: dict[str, Any], packet: dict[str, Any]) -> list[dict[str, Any]]:
    inventory = context.get("changed_path_summaries", {})
    summaries: list[dict[str, Any]] = []
    for relpath in packet.get("changed_paths", []):
        entry = inventory.get(relpath, {})
        summaries.append(
            {
                "path": relpath,
                "kind": entry.get("kind"),
                "exists": entry.get("exists"),
                "preview_lines": entry.get("preview_lines", []),
                "headings": entry.get("headings", []),
            }
        )
    return summaries


def github_evidence_slice(context: dict[str, Any], packet_name: str) -> dict[str, Any]:
    evidence = context.get("github_evidence", {})
    summary = context.get("evidence_summary", {})
    artifacts = [
        artifact
        for artifact in evidence.get("artifacts", [])
        if packet_name in artifact.get("packet_hints", [])
    ]
    return {
        "required": bool(context.get("github_evidence_required")),
        "auth_policy": evidence.get("auth_policy"),
        "packet_signals": summary.get("packet_signals", {}).get(packet_name, []),
        "artifacts": artifacts,
        "evidence_urls": [artifact.get("url") for artifact in artifacts if artifact.get("url")],
    }


def packet_basis(lint: dict[str, Any], packet_name: str) -> dict[str, Any]:
    basis = (lint.get("packet_basis") or {}).get(packet_name) or {}
    return {
        "deterministic_action_candidates": list(basis.get("deterministic_action_candidates") or []),
        "manual_review_residuals": list(basis.get("manual_review_residuals") or []),
        "marker_gate_signals": dict(basis.get("marker_gate_signals") or {}),
    }


def ownership_summary(packet_name: str, packet: dict[str, Any]) -> dict[str, Any]:
    return {
        "packet": packet_name,
        "packet_kind": packet.get("packet_kind", "focused"),
        "review_docs": packet.get("review_docs", []),
        "changed_paths": packet.get("changed_paths", []),
        "direct_doc_changes": packet.get("direct_doc_changes", []),
        "direct_source_changes": packet.get("direct_source_changes", []),
        "activation_reasons": packet.get("activation_reasons", []),
    }


def build_packet_payload(
    context: dict[str, Any],
    lint: dict[str, Any],
    packet_name: str,
    packet: dict[str, Any],
) -> dict[str, Any]:
    basis = packet_basis(lint, packet_name)
    marker_gate_signals = basis["marker_gate_signals"] or {
        "marker_blocked_by_packet": False,
        "blocking_reasons": [],
        "manual_review_residual_count": len(basis["manual_review_residuals"]),
        "deterministic_candidate_count": len(basis["deterministic_action_candidates"]),
    }
    return {
        "packet_id": packet_name,
        "packet_kind": packet.get("packet_kind", "focused"),
        "active": bool(packet.get("active")),
        "context_id": context.get("context_id"),
        "baseline_mode": context.get("baseline", {}).get("mode"),
        "relevant_ref": context.get("relevant_ref"),
        "activation_reasons": packet.get("activation_reasons", []),
        "ownership_summary": ownership_summary(packet_name, packet),
        "review_docs": packet.get("review_docs", []),
        "changed_paths": packet.get("changed_paths", []),
        "direct_doc_changes": packet.get("direct_doc_changes", []),
        "direct_source_changes": packet.get("direct_source_changes", []),
        "doc_summaries": doc_summaries(context, packet),
        "changed_path_summaries": changed_summaries(context, packet),
        "github_evidence_slice": github_evidence_slice(context, packet_name),
        "lint_issues": lint_issues_for_packet(lint, packet_name),
        "deterministic_action_candidates": basis["deterministic_action_candidates"],
        "manual_review_residuals": basis["manual_review_residuals"],
        "marker_gate_signals": marker_gate_signals,
        "deterministic_apply_boundaries": context.get("deterministic_apply_boundaries", {}),
    }


def build_batch_packet(
    context: dict[str, Any],
    lint: dict[str, Any],
    packet: dict[str, Any],
) -> dict[str, Any]:
    basis = packet_basis(lint, "forms_batch_packet")
    return {
        "packet_id": "batch-packet-01",
        "packet_kind": "batch",
        "active": True,
        "context_id": context.get("context_id"),
        "ownership_summary": ownership_summary("forms_batch_packet", packet),
        "packet_targets": packet.get("review_docs", []),
        "lint_issues": lint_issues_for_packet(lint, "forms_batch_packet"),
        "deterministic_action_candidates": basis["deterministic_action_candidates"],
        "manual_review_residuals": basis["manual_review_residuals"],
        "marker_gate_signals": basis["marker_gate_signals"],
        "github_evidence_slice": github_evidence_slice(context, "forms_batch_packet"),
        "note": "Review affected public issue forms as one grouped docs surface.",
    }


def build_result_payload(
    *,
    review_mode: str,
    applied_override_signals: list[str],
    active_packet_names: list[str],
    recommended: list[dict[str, str]],
    selected_packets: list[str],
    packet_order: list[str],
    packet_metrics: dict[str, int],
    lint: dict[str, Any],
    uses_batch_packets: bool,
) -> dict[str, Any]:
    return {
        "review_mode": review_mode,
        "recommended_worker_count": len(recommended),
        "recommended_workers": recommended,
        "selected_packets": selected_packets,
        "packet_order": packet_order,
        "active_packets": active_packet_names,
        "active_packet_count": len(active_packet_names),
        "uses_batch_packets": uses_batch_packets,
        "applied_override_signals": applied_override_signals,
        "auto_apply_candidate_count": len(lint.get("auto_apply_candidates", [])),
        "packet_metrics": packet_metrics,
    }


def main() -> int:
    args = parse_args()
    context = load_json(Path(args.context).resolve())
    lint = load_json(Path(args.lint).resolve()) if args.lint else {}
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    packet_candidates = context.get("packet_candidates", {})
    active_packet_names = [
        name
        for name in PACKET_NAMES
        if packet_candidates.get(name, {}).get("active")
    ]
    review_mode, override_applied, applied_override_signals = compute_review_mode(context, lint)
    uses_batch_packets = bool(
        packet_candidates.get("forms_batch_packet", {}).get("active")
        and len(packet_candidates.get("forms_batch_packet", {}).get("review_docs", [])) > 1
    )
    selected_packets = [f"{name}.json" for name in active_packet_names]
    if uses_batch_packets:
        selected_packets.append("batch-packet-01.json")

    routed_packets = routed_packet_names(active_packet_names, uses_batch_packets)
    recommended = recommended_workers(routed_packets, review_mode)
    packet_order = ["global_packet.json", *selected_packets]

    orchestrator = {
        "skill_name": context.get("skill_name"),
        "workflow_family": WORKFLOW_FAMILY,
        "archetype": ARCHETYPE,
        "orchestrator_profile": ORCHESTRATOR_PROFILE,
        "review_mode": review_mode,
        "decision_ready_packets": DECISION_READY_PACKETS,
        "worker_return_contract": WORKER_RETURN_CONTRACT,
        "worker_output_shape": WORKER_OUTPUT_SHAPE,
        "preferred_worker_families": PREFERRED_WORKER_FAMILIES,
        "packet_worker_map": PACKET_WORKER_MAP,
        "worker_selection_guidance": WORKER_SELECTION_GUIDANCE,
        "uses_batch_packets": uses_batch_packets,
        "recommended_worker_count": len(recommended),
        "recommended_workers": recommended,
        "optional_workers": optional_workers(review_mode, recommended),
        "local_responsibilities": [
            "read global_packet.json and active focused packets",
            "decide deterministic vs manual public-doc drift",
            "keep marker updates blocked when manual narrative review remains",
            "respect the fail-closed GitHub evidence policy before using remote claims",
            "persist the last-success marker only after doc updates are done",
        ],
        "shared_packet": "global_packet.json",
        "packet_order": packet_order,
        "selected_packets": selected_packets,
        "applied_override_signals": applied_override_signals,
        "override_applied": override_applied,
        "xhigh_reread_policy": XHIGH_REREAD_POLICY,
        "raw_reread_allowed_reasons": RAW_REREAD_ALLOWED_REASONS,
    }

    global_packet = {
        "skill_name": context.get("skill_name"),
        "workflow_family": WORKFLOW_FAMILY,
        "archetype": ARCHETYPE,
        "orchestrator_profile": ORCHESTRATOR_PROFILE,
        "primary_goal": "Keep public docs synchronized with runtime defaults, shipped metadata, and recent changes.",
        "authority_order": context.get("authority_order", []),
        "stop_conditions": context.get("stop_conditions", []),
        "review_mode_overrides": REVIEW_MODE_OVERRIDES,
        "decision_ready_packets": DECISION_READY_PACKETS,
        "worker_return_contract": WORKER_RETURN_CONTRACT,
        "worker_output_shape": WORKER_OUTPUT_SHAPE,
        "preferred_worker_families": PREFERRED_WORKER_FAMILIES,
        "packet_worker_map": PACKET_WORKER_MAP,
        "worker_selection_guidance": WORKER_SELECTION_GUIDANCE,
        "xhigh_reread_policy": XHIGH_REREAD_POLICY,
        "raw_reread_allowed_reasons": RAW_REREAD_ALLOWED_REASONS,
        "context_id": context.get("context_id"),
        "context_fingerprint": context.get("context_fingerprint"),
        "repo_root": context.get("repo_root"),
        "baseline": context.get("baseline"),
        "relevant_ref": context.get("relevant_ref"),
        "github_evidence_required": bool(context.get("github_evidence_required")),
        "github_evidence_urls": context.get("evidence_summary", {}).get("urls", []),
        "github_auth_policy": context.get("github_evidence", {}).get("auth_policy"),
        "counts": context.get("counts", {}),
        "active_packets": active_packet_names,
        "selected_packets": selected_packets,
        "lint_summary": {
            "error_count": len(lint.get("errors", [])),
            "warning_count": len(lint.get("warnings", [])),
            "info_count": len(lint.get("infos", [])),
        },
        "deterministic_apply_boundaries": context.get("deterministic_apply_boundaries", {}),
        "last_success_policy": "The last-success marker is baseline-only state; it is never a facts source for the docs narrative.",
        "notes": context.get("notes", []),
    }

    packet_payloads: dict[str, dict[str, Any]] = {
        "orchestrator.json": orchestrator,
        "global_packet.json": global_packet,
    }
    write_json(output_dir / "orchestrator.json", orchestrator)
    write_json(output_dir / "global_packet.json", global_packet)

    for packet_name in PACKET_NAMES:
        payload = build_packet_payload(context, lint, packet_name, packet_candidates.get(packet_name, {}))
        if not payload["active"]:
            payload["activation_reasons"] = payload.get("activation_reasons", []) + ["packet inactive for this run"]
        write_json(output_dir / f"{packet_name}.json", payload)
        if payload["active"]:
            packet_payloads[f"{packet_name}.json"] = payload

    if uses_batch_packets:
        batch_payload = build_batch_packet(context, lint, packet_candidates["forms_batch_packet"])
        write_json(output_dir / "batch-packet-01.json", batch_payload)
        packet_payloads["batch-packet-01.json"] = batch_payload

    packet_metrics = compute_packet_metrics(
        packet_payloads,
        local_only_sources={
            "context.json": context,
            "lint.json": lint,
        },
    )
    write_json(output_dir / "packet_metrics.json", packet_metrics)

    if args.result_output:
        build_result = build_result_payload(
            review_mode=review_mode,
            applied_override_signals=applied_override_signals,
            active_packet_names=active_packet_names,
            recommended=recommended,
            selected_packets=selected_packets,
            packet_order=packet_order,
            packet_metrics=packet_metrics,
            lint=lint,
            uses_batch_packets=uses_batch_packets,
        )
        write_json(Path(args.result_output).resolve(), build_result)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
