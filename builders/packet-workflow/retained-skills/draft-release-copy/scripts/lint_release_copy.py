#!/usr/bin/env python3
"""Lint release-facing copy against tracked release sources and helper status."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


STOPWORDS = {
    "the",
    "and",
    "with",
    "that",
    "this",
    "from",
    "into",
    "then",
    "when",
    "while",
    "were",
    "have",
    "has",
    "keep",
    "keeps",
    "plus",
    "after",
    "before",
    "into",
    "only",
    "more",
    "still",
    "current",
    "release",
    "default",
}

CHANGELOG_TOPIC_RULES = (
    {
        "id": "diagnostics",
        "label": "diagnostics or troubleshooting",
        "file_keywords": (
            "officedemanddiagnosticssystem.cs",
            "setting.cs",
            "readme.md",
        ),
        "subject_keywords": ("diagnostic", "diagnostics", "troubleshooting", "logging"),
        "bullet_keywords": ("diagnostic", "diagnostics", "troubleshooting", "logging"),
        "min_churn": 120,
        "min_subject_matches": 1,
        "allow_subject_only": False,
    },
    {
        "id": "telemetry",
        "label": "performance telemetry",
        "file_keywords": (
            "performancetelemetry",
            "perf_reporting.md",
            "perf-telemetry",
        ),
        "subject_keywords": ("telemetry", "perf"),
        "bullet_keywords": ("telemetry", "performance"),
        "min_churn": 160,
        "min_subject_matches": 2,
        "allow_subject_only": True,
    },
    {
        "id": "seller",
        "label": "outside-connection seller fallback",
        "file_keywords": (
            "outsideconnectionvirtualsellerfixpatch.cs",
            "seller",
        ),
        "subject_keywords": ("seller", "outside-connection", "outside connection"),
        "bullet_keywords": ("seller", "outside-connection", "outside connection"),
        "min_churn": 20,
        "min_subject_matches": 1,
        "allow_subject_only": False,
    },
    {
        "id": "buyer",
        "label": "virtual office buyer fallback",
        "file_keywords": (
            "virtualofficeresourcebuyerfixsystem.cs",
            "correctivesoftwarebuyerprovenance.cs",
            "buyer",
        ),
        "subject_keywords": ("buyer", "resourcebuyer"),
        "bullet_keywords": ("buyer",),
        "min_churn": 120,
        "min_subject_matches": 1,
        "allow_subject_only": False,
    },
    {
        "id": "signature",
        "label": "signature phantom-vacancy cleanup",
        "file_keywords": (
            "signaturepropertymarketguardsystem.cs",
            "signature",
            "phantom",
        ),
        "subject_keywords": ("signature", "phantom"),
        "bullet_keywords": ("signature", "phantom vacancy", "market cleanup"),
        "min_churn": 60,
        "min_subject_matches": 1,
        "allow_subject_only": False,
    },
    {
        "id": "office_ai",
        "label": "office AI hotfix",
        "file_keywords": (
            "officeaihotfixsystem.cs",
            "officeaihotfixpatch.cs",
            "office ai",
        ),
        "subject_keywords": ("office ai", "chunk-iteration", "low stock"),
        "bullet_keywords": ("office ai", "chunk-iteration", "low stock"),
        "min_churn": 140,
        "min_subject_matches": 1,
        "allow_subject_only": False,
    },
)

SOFTWARE_GATE_TOPIC_IDS = {"diagnostics", "seller", "buyer"}
TELEMETRY_VALIDATION_TOPIC_IDS = {"telemetry"}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def add_finding(bucket: list[dict[str, str]], code: str, area: str, message: str) -> None:
    bucket.append({"code": code, "area": area, "message": message})


def applicable_validation_tracks(context: dict[str, Any]) -> dict[str, bool]:
    active_topic_ids = {
        str(signal.get("id"))
        for signal in significant_changelog_topics(context)
    }
    return {
        "software_gate": bool(active_topic_ids & SOFTWARE_GATE_TOPIC_IDS),
        "telemetry_validation": bool(active_topic_ids & TELEMETRY_VALIDATION_TOPIC_IDS),
    }


def evidence_complete(evidence: dict[str, Any] | None, tracks: dict[str, bool]) -> bool:
    if not any(tracks.values()):
        return True
    if not evidence:
        return False

    if tracks.get("software_gate"):
        required_software_fields = (
            "software_track_status",
            "comparable_evidence",
            "anchor_comparison",
            "release_pr_validation_note",
        )
        if any(not str(evidence.get(field) or "").strip() for field in required_software_fields):
            return False
        if str(evidence.get("software_track_status") or "").strip().lower() in {"unknown", ""}:
            return False

    if tracks.get("telemetry_validation"):
        required_telemetry_fields = (
            "telemetry_validation_artifact",
            "telemetry_validation_summary",
        )
        if any(not str(evidence.get(field) or "").strip() for field in required_telemetry_fields):
            return False

    return True


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def has_experimental_language(text: str) -> bool:
    normalized = normalize_text(text)
    keywords = (
        "experimental",
        "under investigation",
        "investigational",
        "does not claim",
        "not a proven fix",
        "remains under investigation",
    )
    return any(keyword in normalized for keyword in keywords)


def has_strong_software_claim(text: str) -> bool:
    normalized = normalize_text(text)
    patterns = (
        r"software.{0,20}(solved|stable|fixed)",
        r"(solved|stable|fixed).{0,20}software",
        r"confirmed fix.{0,20}software",
    )
    return any(re.search(pattern, normalized) for pattern in patterns)


def change_log_bullets(change_log: str) -> list[str]:
    bullets: list[str] = []
    for line in change_log.splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            bullets.append(stripped[2:].strip())
    return bullets


def normalize_substring(value: str) -> str:
    return normalize_text(value).replace("`", "")


def bullet_matches_keywords(bullets: list[str], keywords: tuple[str, ...]) -> bool:
    normalized_bullets = [normalize_substring(bullet) for bullet in bullets]
    return any(any(keyword in bullet for keyword in keywords) for bullet in normalized_bullets)


def overlapping_prior_release_bullets(current_bullets: list[str], prior_bullets: list[str]) -> list[str]:
    normalized_prior = {normalize_substring(bullet): bullet for bullet in prior_bullets}
    overlaps: list[str] = []
    for bullet in current_bullets:
        normalized = normalize_substring(bullet)
        if normalized in normalized_prior:
            overlaps.append(bullet)
    return overlaps


def significant_changelog_topics(context: dict[str, Any]) -> list[dict[str, Any]]:
    changed_file_stats = context.get("changed_file_stats", {})
    if not isinstance(changed_file_stats, dict):
        changed_file_stats = {}
    normalized_subjects = [normalize_substring(subject) for subject in context.get("commit_subjects", [])]

    signals: list[dict[str, Any]] = []
    for rule in CHANGELOG_TOPIC_RULES:
        matching_files: list[dict[str, Any]] = []
        churn_sum = 0
        for raw_path, raw_stats in changed_file_stats.items():
            path = normalize_substring(str(raw_path))
            if not any(keyword in path for keyword in rule["file_keywords"]):
                continue
            stats = raw_stats if isinstance(raw_stats, dict) else {}
            file_churn = int(stats.get("churn", 0) or 0)
            churn_sum += file_churn
            matching_files.append(
                {
                    "path": str(raw_path),
                    "churn": file_churn,
                }
            )

        subject_matches = [
            subject
            for subject in normalized_subjects
            if any(keyword in subject for keyword in rule["subject_keywords"])
        ]

        has_significant_file_signal = churn_sum >= rule["min_churn"]
        has_significant_subject_signal = len(subject_matches) >= rule["min_subject_matches"]
        significant = (has_significant_file_signal and matching_files) or (
            rule["allow_subject_only"] and has_significant_subject_signal
        ) or (has_significant_file_signal and has_significant_subject_signal)
        if not significant:
            continue

        signals.append(
            {
                "id": rule["id"],
                "label": rule["label"],
                "bullet_keywords": rule["bullet_keywords"],
                "matching_files": matching_files,
                "matching_file_count": len(matching_files),
                "churn_sum": churn_sum,
                "matching_subject_count": len(subject_matches),
            }
        )
    return signals


def bullet_supported(bullet: str, context: dict[str, Any]) -> bool:
    if not bullet:
        return True
    corpus_parts = list(context.get("commit_subjects", [])) + list(context.get("changed_files", []))
    corpus = normalize_text(" ".join(corpus_parts))
    tokens = [
        token
        for token in re.findall(r"[A-Za-z][A-Za-z0-9-]{3,}", bullet.lower())
        if token not in STOPWORDS
    ]
    if not tokens:
        return True
    if any(token in corpus for token in tokens):
        return True

    keyword_hints = {
        "diagnostic": ("diagnostic", "log", "setting.cs", "readme.md"),
        "telemetry": ("telemetry", "perf", "setting.cs", "perf_reporting"),
        "seller": ("seller", "outsideconnectionvirtualseller", "outside connection"),
        "buyer": ("buyer", "virtualofficeresourcebuyer", "resourcebuyer"),
        "signature": ("signature", "propertymarket", "phantom"),
        "publish": ("publishconfiguration", "readme", "maintaining"),
        "readme": ("readme",),
    }
    lowered = bullet.lower()
    for keyword, hints in keyword_hints.items():
        if keyword in lowered and any(hint in corpus for hint in hints):
            return True
    return False


def expected_default_literal(value: str) -> str:
    normalized = str(value).strip().lower()
    if normalized in {"true", "false"}:
        return normalized
    try:
        number_text = normalized.removesuffix("f").removesuffix("d").removesuffix("m")
        number = float(number_text)
        if number.is_integer():
            return str(int(number))
        return format(number, "g")
    except ValueError:
        return normalized


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Lint release-facing copy against tracked release sources and helper status."
    )
    parser.add_argument("--context", required=True, help="Path to JSON from collect_release_copy_context.py")
    parser.add_argument("--output", required=True, help="Output JSON path")
    args = parser.parse_args()

    context = load_json(Path(args.context))
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    info: list[dict[str, str]] = []

    publish = context.get("publish_configuration", {})
    readme = context.get("readme", {})
    readme_sections = readme.get("sections", {})
    readme_release_text = "\n".join(
        [
            str(readme.get("intro_text") or ""),
            str(readme_sections.get("Current Release") or ""),
            str(readme_sections.get("Current Status") or ""),
        ]
    )
    publish_release_text = "\n".join(
        [
            str(publish.get("short_description") or ""),
            str(publish.get("long_description") or ""),
            str(publish.get("change_log") or ""),
        ]
    )
    local_helper = context.get("local_release_helper", {})
    target_version = str(context.get("target_version") or "").strip()
    configured_version = str(publish.get("mod_version") or "").strip()

    if configured_version != target_version:
        add_finding(
            errors,
            "target_version_mismatch",
            "publish",
            f"Target version `{target_version}` does not match PublishConfiguration ModVersion `{configured_version}`.",
        )

    if local_helper.get("status") == "missing_local_release_script":
        add_finding(
            info,
            "missing_local_release_script",
            "helper",
            "The repo-relative local release helper is missing. Release-copy preparation may continue, but no helper handoff command should be generated.",
        )

    evidence = context.get("evidence")
    tracks = applicable_validation_tracks(context)
    evidence_is_complete = evidence_complete(evidence if isinstance(evidence, dict) else None, tracks)
    if not evidence_is_complete:
        add_finding(
            warnings,
            "release_gate_validation_incomplete",
            "evidence",
            "Applicable release-gate evidence or validation is missing or incomplete. Keep conservative wording and leave unresolved checklist placeholders in the issue draft.",
        )

    readme_experimental = has_experimental_language(readme_release_text)
    publish_experimental = has_experimental_language(publish_release_text)
    if readme_experimental != publish_experimental:
        add_finding(
            warnings,
            "experimental_language_mismatch",
            "copy",
            "README and PublishConfiguration disagree on whether the software path is still experimental or under investigation.",
        )

    if tracks.get("software_gate") and not evidence_is_complete and has_strong_software_claim(
        readme_release_text + "\n" + publish_release_text
    ):
        add_finding(
            errors,
            "unsupported_strong_software_claim",
            "copy",
            "Release-facing copy makes strong software-track claims without complete applicable software-gate evidence.",
        )

    readme_defaults = readme.get("settings_defaults", {})
    setting_defaults = context.get("setting_defaults", {})
    for setting_name, readme_entry in readme_defaults.items():
        readme_default = expected_default_literal(readme_entry.get("default", ""))
        setting_default = expected_default_literal(setting_defaults.get(setting_name, ""))
        if not setting_default:
            continue
        if readme_default != setting_default:
            add_finding(
                warnings,
                "setting_default_mismatch",
                "readme",
                f"`{setting_name}` default is `{readme_default}` in README but `{setting_default}` in Setting.cs.",
            )

    for bullet in change_log_bullets(str(publish.get("change_log") or "")):
        if not bullet_supported(bullet, context):
            add_finding(
                warnings,
                "unsupported_changelog_bullet",
                "publish",
                f"ChangeLog bullet is not clearly supported by the diff since {context.get('base_tag')}: `{bullet}`.",
            )

    change_log = str(publish.get("change_log") or "")
    bullets = change_log_bullets(change_log)
    prior_publish = context.get("base_tag_publish_configuration") or {}
    prior_bullets = change_log_bullets(str(prior_publish.get("change_log") or ""))
    repeated_bullets = overlapping_prior_release_bullets(bullets, prior_bullets)
    if repeated_bullets:
        repeated_text = "; ".join(f"`{bullet}`" for bullet in repeated_bullets)
        add_finding(
            warnings,
            "changelog_carries_forward_prior_release_bullets",
            "publish",
            "ChangeLog should be rewritten for the current release only, but it still carries forward "
            f"bullet(s) from {context.get('base_tag')}: {repeated_text}.",
        )

    for signal in significant_changelog_topics(context):
        if bullet_matches_keywords(bullets, signal["bullet_keywords"]):
            continue
        add_finding(
            warnings,
            "missing_changelog_topic",
            "publish",
            "ChangeLog may be missing a significant shipped topic for "
            f"`{signal['label']}` since {context.get('base_tag')} "
            f"({signal['matching_file_count']} file(s), {signal['churn_sum']} churn, "
            f"{signal['matching_subject_count']} matching commit subject(s)).",
        )

    if not evidence_is_complete:
        add_finding(
            warnings,
            "checklist_field_unresolved",
            "checklist",
            "The release checklist `Release-gate evidence / validation` field cannot be fully filled from the current artifacts.",
        )

    handoff_allowed = (
        local_helper.get("status") == "present"
        and configured_version == target_version
    )

    result = {
        "findings": {
            "errors": errors,
            "warnings": warnings,
            "info": info,
        },
        "checks": {
            "target_version_matches_publish": configured_version == target_version,
            "evidence_complete": evidence_is_complete,
            "applicable_validation_tracks": tracks,
            "helper_status": local_helper.get("status"),
            "helper_handoff_allowed": handoff_allowed,
            "readme_has_experimental_language": readme_experimental,
            "publish_has_experimental_language": publish_experimental,
            "rewrite_publish_recommended": bool(errors or any(item["area"] == "publish" for item in warnings)),
            "rewrite_readme_recommended": bool(
                any(item["area"] in {"readme", "copy"} for item in errors + warnings)
            ),
        },
    }
    output_path.write_text(json.dumps(result, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f"lint_release_copy.py: {exc}", file=sys.stderr)
        raise SystemExit(1)
