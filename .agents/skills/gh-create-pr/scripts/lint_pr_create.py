#!/usr/bin/env python3
"""Run deterministic lint checks for gh-create-pr."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from pr_create_tools import PR_TITLE_RE


PLACEHOLDER_PATTERNS = [
    (re.compile(r"^- $", re.MULTILINE), "Template contains an empty bullet (`- `)."),
    (re.compile(r"Refs:\s*#$", re.MULTILINE), "Template still contains the placeholder `Refs: #`."),
    (
        re.compile(r"Note any important defaults, thresholds, reload/restart requirements, or", re.MULTILINE),
        "Template guidance text is still present in `How`.",
    ),
    (re.compile(r"^\s*-\s*$", re.MULTILINE), "Body contains a blank nested bullet."),
    (
        re.compile(r"If not tested, state why\.", re.MULTILINE),
        "Template reminder `If not tested, state why.` was not replaced.",
    ),
]
ISSUE_REF_PATTERN = re.compile(r"#(?P<number>\d+)")
CLOSING_REF_PATTERN = re.compile(r"\b(?:fixes|closes)\s+#(?P<number>\d+)", re.IGNORECASE)
NO_BEHAVIOR_CHANGE_PATTERN = re.compile(r"\bno behavior change\b", re.IGNORECASE)
ROLLOUT_PATTERN = re.compile(r"\brollout\b", re.IGNORECASE)
RESTART_PATTERN = re.compile(r"\b(restart|reload)\b", re.IGNORECASE)
MIGRATION_PATTERN = re.compile(r"\b(migration|backward[- ]compat(?:ibility)?)\b", re.IGNORECASE)
POSITIVE_TEST_PATTERN = re.compile(r"\b(tested|verified|validated|manual(?:ly)?|ran)\b", re.IGNORECASE)
NOT_RUN_PATTERN = re.compile(r"\bnot run\b", re.IGNORECASE)
COMMAND_PATTERN = re.compile(r"`([^`]+)`")
GENERATED_FILE_PATTERNS = (
    re.compile(r"(^|/)(bin|obj|dist|build|coverage|generated|gen)/"),
    re.compile(r"\.(g|generated)\.[^.]+$"),
    re.compile(r"\.designer\.[^.]+$"),
    re.compile(r"(^|/)(package-lock\.json|pnpm-lock\.yaml|yarn\.lock|poetry\.lock|cargo\.lock)$"),
    re.compile(r"\.min\.(js|css)$"),
)


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


def section_bodies(markdown_text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    current = None
    buffer: list[str] = []
    for line in markdown_text.splitlines():
        if line.startswith("## "):
            if current is not None:
                result[current] = "\n".join(buffer).strip()
            current = line[3:].strip()
            buffer = []
        elif current is not None:
            buffer.append(line)
    if current is not None:
        result[current] = "\n".join(buffer).strip()
    return result


def ordered_subset(expected: list[str], actual: list[str]) -> bool:
    position = 0
    for heading in expected:
        while position < len(actual) and actual[position] != heading:
            position += 1
        if position >= len(actual):
            return False
        position += 1
    return True


def parse_diff_totals(diff_stat: str | None) -> dict[str, int]:
    if not diff_stat:
        return {"files_changed": 0, "insertions": 0, "deletions": 0, "churn": 0}
    last_line = diff_stat.strip().splitlines()[-1]
    files_match = re.search(r"(?P<files>\d+) files? changed", last_line)
    insertions_match = re.search(r"(?P<insertions>\d+) insertions?\(\+\)", last_line)
    deletions_match = re.search(r"(?P<deletions>\d+) deletions?\(-\)", last_line)
    files_changed = int(files_match.group("files")) if files_match else 0
    insertions = int(insertions_match.group("insertions")) if insertions_match else 0
    deletions = int(deletions_match.group("deletions")) if deletions_match else 0
    return {
        "files_changed": files_changed,
        "insertions": insertions,
        "deletions": deletions,
        "churn": insertions + deletions,
    }


def referenced_issue_numbers(text: str) -> list[str]:
    seen: list[str] = []
    for match in ISSUE_REF_PATTERN.finditer(text):
        number = match.group("number")
        if number not in seen:
            seen.append(number)
    return seen


def is_generated_file(path: str) -> bool:
    lowered = path.replace("\\", "/").lower()
    return any(pattern.search(lowered) for pattern in GENERATED_FILE_PATTERNS)


def supported_claims(context: dict[str, Any]) -> list[dict[str, str]]:
    groups = context.get("changed_file_groups") or {}
    claims: list[dict[str, str]] = []
    runtime_count = int((groups.get("runtime") or {}).get("count", 0))
    if runtime_count > 0:
        claims.append(
            {
                "cluster": "runtime",
                "basis": "runtime files changed",
                "evidence_anchor": ", ".join(list((groups.get("runtime") or {}).get("sample_files", []))[:2]),
            }
        )
    else:
        claims.append(
            {
                "cluster": "runtime",
                "basis": "no runtime files changed",
                "evidence_anchor": "runtime packet is empty",
            }
        )
    process_files: list[str] = []
    for name in ("automation", "docs", "config"):
        process_files.extend(list((groups.get(name) or {}).get("sample_files", []))[:1])
    if process_files:
        claims.append(
            {
                "cluster": "process",
                "basis": "workflow/docs/config files changed",
                "evidence_anchor": ", ".join(process_files[:2]),
            }
        )
    claims.append(
        {
            "cluster": "testing",
            "basis": "positive testing claims require explicit external evidence; neutral `Not run.` wording is safe by default",
            "evidence_anchor": "testing packet exact_commands",
        }
    )
    return claims


def coverage_gaps(context: dict[str, Any], findings: dict[str, Any]) -> list[str]:
    gaps: list[str] = []
    template_selection = context.get("template_selection") or {}
    status = str(template_selection.get("status") or "")
    if status != "selected":
        gaps.append("template selection is not stable enough for safe body drafting.")
    if not context.get("checks", {}).get("repo_slug_resolved"):
        gaps.append("repo slug is unresolved; duplicate PR checks cannot be trusted.")
    if not context.get("checks", {}).get("remote_head_exists"):
        gaps.append("remote head is missing; PR creation is out of scope for v1.")
    if not context.get("issue_reference_hints", {}).get("numbers"):
        gaps.append("issue references have no external hint source; `Refs:` / `Fixes:` claims should stay out of the draft.")
    for message in findings.get("warnings", []):
        if message not in gaps:
            gaps.append(message)
    return gaps


def focused_packet_hint(context: dict[str, Any]) -> str | None:
    groups = context.get("changed_file_groups") or {}
    if int((groups.get("tests") or {}).get("count", 0)) > 0:
        return "testing_packet.json"
    if int((groups.get("runtime") or {}).get("count", 0)) > 0:
        return "runtime_packet.json"
    if any(int((groups.get(name) or {}).get("count", 0)) > 0 for name in ("automation", "docs", "config")):
        return "process_packet.json"
    return None


def build_drafting_basis(context: dict[str, Any], findings: dict[str, Any]) -> dict[str, Any]:
    expected = list(context.get("expected_template_sections") or [])
    duplicate_hint = context.get("duplicate_check_hint") or {}
    template_selection = context.get("template_selection") or {}
    return {
        "active_rule_gates": [
            "title_pattern",
            "required_sections",
            "section_order",
            "issue_reference_gate",
            "testing_claim_gate",
            "strict_claim_gate",
            "duplicate_pr_gate",
        ],
        "template_status": template_selection.get("status"),
        "required_sections_status": {
            "required": expected,
            "selected_template_path": template_selection.get("selected_path"),
            "template_fingerprint": template_selection.get("fingerprint"),
        },
        "supported_claims": supported_claims(context),
        "issue_reference_hints": dict(context.get("issue_reference_hints") or {}),
        "testing_evidence_status": dict(context.get("testing_signal_candidates") or {}),
        "duplicate_check_hint": {
            "status": duplicate_hint.get("status"),
            "existing_pr_url": duplicate_hint.get("existing_pr_url"),
        },
        "coverage_gaps": coverage_gaps(context, findings),
        "focused_packet_hint": focused_packet_hint(context),
    }


def context_override_signals(context: dict[str, Any]) -> dict[str, bool]:
    groups = context.get("changed_file_groups") or {}
    changed_files = list(context.get("changed_files") or [])
    diff_totals = parse_diff_totals(context.get("diff_stat"))
    generated_count = sum(1 for path in changed_files if is_generated_file(path))
    generated_ratio = (generated_count / len(changed_files)) if changed_files else 0.0
    core_group_count = sum(
        1 for name in ("runtime", "automation", "config") if int((groups.get(name) or {}).get("count", 0)) > 0
    )
    return {
        "high_churn": diff_totals.get("churn", 0) >= 1500,
        "multi_group_core_files": core_group_count >= 2,
        "generated_not_majority": generated_count >= 3 and 0.2 <= generated_ratio < 0.5,
    }


def collect_context_findings(context: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    info: list[str] = []
    template_selection = context.get("template_selection") or {}
    duplicate_hint = context.get("duplicate_check_hint") or {}
    checks = context.get("checks") or {}

    if not checks.get("repo_slug_resolved"):
        errors.append("Repository slug could not be inferred; duplicate PR checks will fail closed.")
    if not checks.get("base_resolved"):
        errors.append("Base branch could not be resolved from --base, branch.gh-merge-base, or remote default branch.")
    status = str(template_selection.get("status") or "")
    if status == "not_found":
        errors.append("No unique default PR template was found.")
    elif status == "ambiguous":
        errors.append("Multiple PR template candidates were found; fail closed until one default template is selected.")
    if not checks.get("remote_head_exists"):
        errors.append("Resolved head branch does not exist on origin; branch publication is out of scope for v1.")
    if checks.get("remote_head_exists") and not checks.get("local_remote_match"):
        errors.append("Local and remote head OIDs differ; refresh or push before creating a PR.")

    duplicate_status = str(duplicate_hint.get("status") or "")
    if duplicate_status == "existing-open-pr":
        warnings.append("A same-head open PR already exists; validator should stop and hand off to gh-fix-pr-writeup.")
    elif duplicate_status == "unavailable":
        warnings.append("Duplicate PR hint could not be collected locally; validator must re-check live GitHub state.")

    groups = context.get("changed_file_groups") or {}
    active_groups = [
        name
        for name in ("runtime", "automation", "docs", "tests", "config")
        if int((groups.get(name) or {}).get("count", 0)) > 0
    ]
    info.append("Changed areas: " + (", ".join(active_groups) if active_groups else "none detected"))
    if context.get("issue_reference_hints", {}).get("numbers"):
        info.append("Issue hints: " + ", ".join(f"#{item}" for item in context["issue_reference_hints"]["numbers"]))
    else:
        info.append("Issue hints: none")

    result = {
        "errors": errors,
        "warnings": warnings,
        "info": info,
        "detected": {
            "template_status": status,
            "duplicate_hint_status": duplicate_status,
            "expected_sections": list(context.get("expected_template_sections") or []),
            "active_groups": active_groups,
        },
        "override_signals": context_override_signals(context),
    }
    result["drafting_basis"] = build_drafting_basis(context, result)
    result["can_proceed"] = not errors
    return result


def collect_candidate_findings(context: dict[str, Any], title: str, body: str) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    info: list[str] = []
    title_errors: list[str] = []
    body_errors: list[str] = []
    unsupported_claims: list[str] = []

    expected_sections = list(context.get("expected_template_sections") or [])
    actual_sections = list(section_bodies(body).keys())
    bodies = section_bodies(body)
    issue_hints = set(str(item) for item in context.get("issue_reference_hints", {}).get("numbers", []))
    runtime_count = int(((context.get("changed_file_groups") or {}).get("runtime") or {}).get("count", 0))
    testing_signals = context.get("testing_signal_candidates") or {}
    allowed_commands = set(str(item).strip() for item in testing_signals.get("exact_commands", []) if str(item).strip())

    if not PR_TITLE_RE.match(title.strip()):
        title_errors.append(
            "Title does not match the repository Conventional Commit pattern `<type>(<scope>): <summary>`."
        )
    if len(title.strip()) > 72:
        warnings.append("Title is longer than the preferred 72-character limit.")

    missing_sections = [section for section in expected_sections if section not in actual_sections]
    if missing_sections:
        body_errors.append("Body is missing template sections: " + ", ".join(missing_sections) + ".")
    elif expected_sections and not ordered_subset(expected_sections, actual_sections):
        body_errors.append("Body sections do not follow the repository template order.")

    for pattern, message in PLACEHOLDER_PATTERNS:
        if pattern.search(body):
            body_errors.append(message)

    testing_text = bodies.get("Testing", "")
    testing_commands = {match.group(1).strip() for match in COMMAND_PATTERN.finditer(testing_text)}
    if POSITIVE_TEST_PATTERN.search(testing_text) and not NOT_RUN_PATTERN.search(testing_text):
        if not testing_commands:
            unsupported_claims.append(
                "Positive testing claims require an exact command from the testing packet."
            )
        elif not testing_commands.issubset(allowed_commands):
            unsupported_claims.append(
                "Positive testing claims cite commands that are not grounded in the testing packet."
            )

    all_refs = set(referenced_issue_numbers(body))
    closing_refs = {match.group("number") for match in CLOSING_REF_PATTERN.finditer(body)}
    if all_refs and not all_refs.issubset(issue_hints):
        unsupported_claims.append(
            "Issue references are present without matching issue hints from the process packet."
        )
    elif closing_refs and not closing_refs.issubset(issue_hints):
        unsupported_claims.append(
            "Closing issue references require explicit issue hints before they can be claimed."
        )

    if NO_BEHAVIOR_CHANGE_PATTERN.search(body) and runtime_count > 0:
        unsupported_claims.append("`No behavior change` is unsupported because runtime files changed.")
    if RESTART_PATTERN.search(body):
        unsupported_claims.append("Restart or reload claims require direct runtime evidence and are blocked by default.")
    if MIGRATION_PATTERN.search(body):
        unsupported_claims.append("Migration or compatibility claims require direct runtime/process evidence and are blocked by default.")
    if ROLLOUT_PATTERN.search(body):
        unsupported_claims.append("Rollout claims require direct process evidence and are blocked by default.")

    if testing_text and not testing_text.strip():
        body_errors.append("`Testing` is present but empty.")

    errors.extend(title_errors)
    errors.extend(body_errors)
    errors.extend(unsupported_claims)
    info.append("Candidate sections: " + (", ".join(actual_sections) if actual_sections else "none"))

    return {
        "errors": errors,
        "warnings": warnings,
        "info": info,
        "detected": {
            "expected_sections": expected_sections,
            "actual_sections": actual_sections,
            "title_errors": title_errors,
            "body_errors": body_errors,
            "unsupported_claims": unsupported_claims,
            "issue_hints": sorted(issue_hints),
            "testing_commands": sorted(testing_commands),
        },
        "drafting_basis": build_drafting_basis(context, {"errors": errors, "warnings": warnings}),
    }


def main() -> int:
    args = parse_args()
    context = load_json(Path(args.context).resolve())
    findings = collect_context_findings(context)
    report = {
        "repo_slug": context.get("repo_slug"),
        "head_ref": context.get("resolved_head"),
        "base_ref": context.get("resolved_base"),
        "template_selection": context.get("template_selection"),
        "duplicate_check_hint": context.get("duplicate_check_hint"),
        "findings": findings,
        "drafting_basis": findings.get("drafting_basis"),
    }
    write_json(Path(args.output).resolve(), report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
