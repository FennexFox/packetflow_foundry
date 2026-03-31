#!/usr/bin/env python3
"""Run deterministic lint checks for public-docs-sync."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from public_docs_sync_contract import DETERMINISTIC_ACTION_ALIASES, PACKET_NAMES


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context", required=True, help="Collected context JSON.")
    parser.add_argument("--output", required=True, help="Output lint JSON.")
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def ensure_packet_basis(findings: dict[str, Any], packet: str | None) -> dict[str, Any] | None:
    if not packet:
        return None
    packet_basis = findings.setdefault("packet_basis", {})
    return packet_basis.setdefault(
        packet,
        {
            "deterministic_action_candidates": [],
            "manual_review_residuals": [],
            "marker_gate_signals": {
                "marker_blocked_by_packet": False,
                "blocking_reasons": [],
                "manual_review_residual_count": 0,
                "deterministic_candidate_count": 0,
            },
        },
    )


def push_issue(
    findings: dict[str, Any],
    *,
    classification: str,
    packet: str | None,
    path: str | None,
    message: str,
    severity: str,
    related_paths: list[str] | None = None,
    resolution_mode: str = "manual-only-review",
    blocking_scope: str = "marker-update",
    evidence_anchor: str | None = None,
) -> None:
    issue = {
        "classification": classification,
        "packet": packet,
        "path": path,
        "message": message,
        "severity": severity,
        "related_paths": related_paths or [],
        "resolution_mode": resolution_mode,
        "blocking_scope": blocking_scope,
        "evidence_anchor": evidence_anchor,
    }
    findings["issues"].append(issue)
    findings["classifications"][classification].append(issue)
    bucket = {"error": "errors", "warning": "warnings", "info": "infos"}[severity]
    findings[bucket].append(message)


def packet_for_path(context: dict[str, Any], relpath: str) -> str | None:
    packets = context.get("packet_candidates", {})
    for packet_name, packet in packets.items():
        if relpath in packet.get("review_docs", []) or relpath in packet.get("changed_paths", []):
            return packet_name
    if relpath.startswith(".github/ISSUE_TEMPLATE/"):
        return "forms_batch_packet"
    return None


def add_auto_apply_candidate(
    findings: dict[str, Any],
    *,
    packet: str | None,
    kind: str,
    path: str,
    message: str,
    details: dict[str, Any] | None = None,
    evidence_anchor: str | None = None,
    expected_edit_scope: str | None = None,
) -> None:
    candidate = {
        "packet": packet,
        "kind": kind,
        "canonical_type": DETERMINISTIC_ACTION_ALIASES.get(kind, kind),
        "path": path,
        "message": message,
        "details": details or {},
        "evidence_anchor": evidence_anchor,
        "expected_edit_scope": expected_edit_scope,
    }
    findings["auto_apply_candidates"].append(candidate)
    basis = ensure_packet_basis(findings, packet)
    if basis is not None:
        basis["deterministic_action_candidates"].append(candidate)


def finalize_packet_basis(context: dict[str, Any], findings: dict[str, Any]) -> None:
    for packet_name in PACKET_NAMES:
        basis = ensure_packet_basis(findings, packet_name)
        packet_issues = [
            issue
            for issue in findings["issues"]
            if issue.get("packet") == packet_name and issue.get("resolution_mode") != "deterministic-edit"
        ]
        manual_review_residuals = [
            {
                "classification": issue.get("classification"),
                "path": issue.get("path"),
                "message": issue.get("message"),
                "severity": issue.get("severity"),
                "blocking_scope": issue.get("blocking_scope"),
                "related_paths": issue.get("related_paths", []),
                "evidence_anchor": issue.get("evidence_anchor"),
            }
            for issue in packet_issues
        ]
        basis["manual_review_residuals"] = manual_review_residuals
        basis["marker_gate_signals"] = {
            "marker_blocked_by_packet": bool(manual_review_residuals),
            "blocking_reasons": [item["message"] for item in manual_review_residuals],
            "manual_review_residual_count": len(manual_review_residuals),
            "deterministic_candidate_count": len(basis["deterministic_action_candidates"]),
            "requires_github_evidence": bool(context.get("github_evidence_required")),
        }


def lint_readme_settings(context: dict[str, Any], findings: dict[str, Any]) -> None:
    settings = context.get("settings", {}).get("defaults", {})
    readme_settings = context.get("readme", {}).get("settings_table", {})
    readme_path = context.get("readme", {}).get("path", "README.md")
    packet = "claims_packet"

    for name, info in settings.items():
        expected = str(info.get("default"))
        documented = readme_settings.get(name)
        if documented is None:
            push_issue(
                findings,
                classification="hard_drift",
                packet=packet,
                path=readme_path,
                message=f"README settings table is missing `{name}`.",
                severity="error",
                related_paths=[context.get("settings", {}).get("source_path", "")],
                resolution_mode="deterministic-edit",
                blocking_scope="apply",
                evidence_anchor=f"runtime default for {name}",
            )
            add_auto_apply_candidate(
                findings,
                packet=packet,
                kind="settings_table_row",
                path=readme_path,
                message=f"Add `{name}` to the README settings table.",
                details={"setting": name, "expected_default": expected},
                evidence_anchor=f"runtime default for {name}",
                expected_edit_scope="single README settings-table row insert",
            )
            continue
        actual = str(documented.get("default"))
        if actual != expected:
            push_issue(
                findings,
                classification="hard_drift",
                packet=packet,
                path=readme_path,
                message=f"README default for `{name}` is `{actual}` but code default is `{expected}`.",
                severity="error",
                related_paths=[context.get("settings", {}).get("source_path", "")],
                resolution_mode="deterministic-edit",
                blocking_scope="apply",
                evidence_anchor=f"runtime default for {name}",
            )
            add_auto_apply_candidate(
                findings,
                packet=packet,
                kind="settings_default_sync",
                path=readme_path,
                message=f"Sync README default for `{name}` to `{expected}`.",
                details={"setting": name, "expected_default": expected, "documented_default": actual},
                evidence_anchor=f"runtime default for {name}",
                expected_edit_scope="single README settings-table cell update",
            )

    for name in sorted(readme_settings):
        if name not in settings:
            push_issue(
                findings,
                classification="hard_drift",
                packet=packet,
                path=readme_path,
                message=f"README settings table contains `{name}` but it is not present in `Setting.cs`.",
                severity="error",
                related_paths=[context.get("settings", {}).get("source_path", "")],
                resolution_mode="manual-only-review",
                blocking_scope="marker-update",
                evidence_anchor=f"README settings row {name}",
            )


def lint_missing_links(context: dict[str, Any], findings: dict[str, Any]) -> None:
    inventory = context.get("public_doc_inventory", {})
    for relpath, summary in inventory.items():
        packet = packet_for_path(context, relpath)
        for missing in summary.get("missing_links", []):
            target = str(missing.get("target") or "").strip()
            push_issue(
                findings,
                classification="link_error",
                packet=packet,
                path=relpath,
                message=f"Broken relative link `{target}` in `{relpath}`.",
                severity="error",
                related_paths=[missing.get("resolved_path", "")],
                resolution_mode="deterministic-edit",
                blocking_scope="apply",
                evidence_anchor=target,
            )
            replacement_target = str(missing.get("resolved_path") or "").strip()
            if replacement_target:
                if not replacement_target.startswith((".", "/")):
                    replacement_target = "./" + replacement_target
                add_auto_apply_candidate(
                    findings,
                    packet=packet,
                    kind="relative_link_fix",
                    path=relpath,
                    message=f"Fix broken link `{target}` in `{relpath}`.",
                    details={
                        "target": target,
                        "replacement_target": replacement_target,
                        "resolved_path": missing.get("resolved_path"),
                    },
                    evidence_anchor=target,
                    expected_edit_scope="single markdown link target replacement",
                )


def lint_packet_reviews(context: dict[str, Any], findings: dict[str, Any]) -> None:
    if context.get("audit_mode") == "full":
        findings["infos"].append(
            "Full audit requested; review-required drift is reported through packet activation instead of missing-doc warnings."
        )
        return

    packets = context.get("packet_candidates", {})
    packet_signals = context.get("evidence_summary", {}).get("packet_signals", {})
    for packet_name, packet in packets.items():
        direct_sources = packet.get("direct_source_changes", [])
        direct_docs = packet.get("direct_doc_changes", [])
        remote_signals = packet_signals.get(packet_name, [])
        if direct_docs or (not direct_sources and not remote_signals):
            continue
        review_docs = packet.get("review_docs", [])
        if not review_docs:
            continue
        message = (
            f"{packet_name} has runtime, workflow, or selected GitHub evidence changes without matching "
            "public-doc changes since the baseline."
        )
        if remote_signals:
            message += " Evidence: " + remote_signals[0]
        push_issue(
            findings,
            classification="review_required",
            packet=packet_name,
            path=review_docs[0],
            message=message,
            severity="warning",
            related_paths=direct_sources[:6] + review_docs[:6],
            resolution_mode="manual-only-review",
            blocking_scope="marker-update",
            evidence_anchor=remote_signals[0] if remote_signals else None,
        )


def lint_baseline(context: dict[str, Any], findings: dict[str, Any]) -> None:
    baseline = context.get("baseline", {})
    fallback_reason = baseline.get("fallback_reason")
    if not fallback_reason:
        return
    audit_mode = context.get("audit_mode")
    if audit_mode == "full":
        message = f"Saved baseline was not reusable and the run fell back to a full audit: {fallback_reason}."
    else:
        message = f"Saved baseline was not reusable; the run used an auto-discovered relevant ref instead: {fallback_reason}."
    push_issue(
        findings,
        classification="stale_baseline",
        packet=None,
        path=None,
        message=message,
        severity="warning",
        related_paths=[],
        resolution_mode="manual-only-review",
        blocking_scope="marker-update",
        evidence_anchor="baseline reuse failed",
    )


def lint_missing_review_docs(context: dict[str, Any], findings: dict[str, Any]) -> None:
    inventory = context.get("public_doc_inventory", {})
    for packet_name, packet in context.get("packet_candidates", {}).items():
        for relpath in packet.get("review_docs", []):
            if inventory.get(relpath, {}).get("exists"):
                continue
            push_issue(
                findings,
                classification="hard_drift",
                packet=packet_name,
                path=relpath,
                message=f"Expected review doc `{relpath}` is missing from the repository.",
                severity="error",
                related_paths=[],
                resolution_mode="manual-only-review",
                blocking_scope="marker-update",
                evidence_anchor=relpath,
            )


def main() -> int:
    args = parse_args()
    context = load_json(Path(args.context).resolve())
    findings: dict[str, Any] = {
        "errors": [],
        "warnings": [],
        "infos": [],
        "issues": [],
        "classifications": {
            "hard_drift": [],
            "review_required": [],
            "link_error": [],
            "stale_baseline": [],
        },
        "auto_apply_candidates": [],
        "packet_basis": {},
        "override_signals": dict(context.get("override_signals", {})),
        "can_proceed": True,
    }

    lint_baseline(context, findings)
    lint_readme_settings(context, findings)
    lint_missing_links(context, findings)
    lint_missing_review_docs(context, findings)
    lint_packet_reviews(context, findings)
    finalize_packet_basis(context, findings)

    if not findings["issues"]:
        findings["infos"].append("No deterministic public-doc drift was detected.")
    findings["can_proceed"] = True

    write_json(Path(args.output).resolve(), findings)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
