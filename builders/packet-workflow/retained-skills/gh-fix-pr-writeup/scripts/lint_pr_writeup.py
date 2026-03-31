from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from pr_writeup_tools import PR_TITLE_RE, build_context


PLACEHOLDER_PATTERNS = [
    (re.compile(r"^- $", re.MULTILINE), "Template contains an empty bullet (`- `)."),
    (
        re.compile(r"Refs:\s*#$", re.MULTILINE),
        "Template still contains the placeholder `Refs: #`.",
    ),
    (
        re.compile(r"Note any important defaults, thresholds, reload/restart requirements, or", re.MULTILINE),
        "Template guidance text is still present in `How`.",
    ),
    (
        re.compile(r"^\s*-\s*$", re.MULTILINE),
        "Body contains a blank nested bullet.",
    ),
    (
        re.compile(r"If not tested, state why\.", re.MULTILINE),
        "Template reminder `If not tested, state why.` was not replaced.",
    ),
]
ISSUE_REF_PATTERN = re.compile(r"#(?P<number>\d+)")
CANDIDATE_CLAIM_PATTERNS = (
    (
        re.compile(r"\b(restart|reload)\b", re.IGNORECASE),
        "Candidate writeup introduces restart or reload claims that need direct verification.",
    ),
    (
        re.compile(r"\bmigration\b", re.IGNORECASE),
        "Candidate writeup introduces migration claims that need direct verification.",
    ),
    (
        re.compile(r"\b(default|defaults|threshold|thresholds)\b", re.IGNORECASE),
        "Candidate writeup introduces default or threshold claims that need direct verification.",
    ),
)


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


def section_text(context: dict, heading: str) -> str:
    body = context.get("pr", {}).get("body") or ""
    return section_bodies(body).get(heading, "")


def referenced_issue_numbers(body: str) -> set[str]:
    refs_line = next((line for line in body.splitlines() if line.lower().startswith("refs:")), "")
    return {match.group("number") for match in ISSUE_REF_PATTERN.finditer(refs_line)}


def support_corpus(context: dict) -> str:
    pr = context.get("pr") or {}
    parts = [
        str(pr.get("title") or ""),
        str(pr.get("body") or ""),
        str(context.get("diff_stat") or ""),
        " ".join(str(path) for path in context.get("changed_files", []) if str(path).strip()),
    ]
    return "\n".join(parts).lower()


def candidate_claim_findings(candidate_context: dict, original_context: dict) -> list[str]:
    body = str(candidate_context.get("pr", {}).get("body") or "")
    original_corpus = support_corpus(original_context)
    findings: list[str] = []
    for pattern, message in CANDIDATE_CLAIM_PATTERNS:
        if pattern.search(body) and not pattern.search(original_corpus):
            findings.append(message)
    testing = section_text(candidate_context, "Testing")
    if testing and re.search(r"\b(verified|validated|manual(?:ly)?|tested)\b", testing, flags=re.IGNORECASE):
        if not re.search(r"`[^`]+`", testing):
            findings.append(
                "Candidate `Testing` claims verification without citing an exact command or concrete step."
            )
    return findings


def full_rewrite_relative_to_original(candidate_context: dict, original_context: dict) -> bool:
    candidate_sections = section_bodies(str(candidate_context.get("pr", {}).get("body") or ""))
    original_sections = section_bodies(str(original_context.get("pr", {}).get("body") or ""))
    shared_sections = [name for name in candidate_sections if name in original_sections]
    if not shared_sections:
        return False
    changed_sections = 0
    for section in shared_sections:
        if candidate_sections.get(section, "").strip() != original_sections.get(section, "").strip():
            changed_sections += 1
    if len(shared_sections) >= 4 and changed_sections >= max(4, len(shared_sections) - 1):
        return True
    candidate_title = str(candidate_context.get("pr", {}).get("title") or "").strip()
    original_title = str(original_context.get("pr", {}).get("title") or "").strip()
    return candidate_title != original_title and changed_sections == len(shared_sections)


def rewrite_strategy_for_findings(context: dict, findings: dict, *, rewrite_hint: bool | None = None) -> str:
    if rewrite_hint is True:
        return "full-rewrite"
    if rewrite_hint is False:
        pass
    if not (context.get("pr", {}).get("body") or "").strip():
        return "full-rewrite"
    error_messages = [str(item).lower() for item in findings.get("errors", [])]
    if any(
        token in message
        for message in error_messages
        for token in (
            "missing template sections",
            "template order",
            "placeholder",
            "template guidance text",
            "blank nested bullet",
            "empty bullet",
        )
    ):
        return "full-rewrite"
    if error_messages:
        return "section-rewrite"
    if findings.get("warnings"):
        return "targeted-touch-up"
    return "keep"


def risky_claim_categories(body: str) -> list[str]:
    categories: list[str] = []
    lowered = body.lower()
    if re.search(r"\b(restart|reload)\b", lowered):
        categories.append("reload_restart")
    if re.search(r"\bmigration\b", lowered):
        categories.append("migration")
    if re.search(r"\b(default|defaults|threshold|thresholds)\b", lowered):
        categories.append("defaults_thresholds")
    return categories


def testing_status(context: dict) -> dict[str, object]:
    testing = section_text(context, "Testing")
    has_command = bool(re.search(r"`[^`]+`", testing))
    return {
        "present": bool(testing.strip()),
        "has_exact_command": has_command,
        "status": "supported" if testing.strip() and has_command else ("missing" if not testing.strip() else "needs-recheck"),
    }


def issue_ref_status(context: dict) -> dict[str, object]:
    body = str(context.get("pr", {}).get("body") or "")
    metadata_refs = {
        str(item.get("number"))
        for item in (context.get("pr", {}).get("closingIssuesReferences") or [])
        if str(item.get("number") or "").strip()
    }
    body_refs = referenced_issue_numbers(body)
    matched = sorted(metadata_refs & body_refs)
    return {
        "metadata_refs": sorted(metadata_refs),
        "body_refs": sorted(body_refs),
        "matched_refs": matched,
        "status": (
            "aligned"
            if matched or (not metadata_refs and not body_refs)
            else ("missing-body-ref" if metadata_refs and not body_refs else "needs-recheck")
        ),
    }


def supported_claims(context: dict) -> list[dict[str, str]]:
    groups = context.get("changed_file_groups") or {}
    claims: list[dict[str, str]] = []
    if (groups.get("runtime") or {}).get("count", 0) > 0:
        claims.append(
            {
                "cluster": "runtime",
                "basis": "runtime files changed",
                "evidence_anchor": ", ".join(list((groups.get("runtime") or {}).get("sample_files", []))[:2]),
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
    if testing_status(context)["present"]:
        claims.append(
            {
                "cluster": "testing",
                "basis": "testing section is present",
                "evidence_anchor": "Testing",
            }
        )
    return claims


def coverage_gaps(context: dict, findings: dict) -> list[str]:
    gaps: list[str] = []
    groups = context.get("changed_file_groups") or {}
    if (groups.get("runtime") or {}).get("count", 0) > 0 and "What changed" not in section_bodies(str(context.get("pr", {}).get("body") or "")):
        gaps.append("runtime changes exist but the writeup lacks a `What changed` section.")
    if not testing_status(context)["has_exact_command"]:
        gaps.append("testing claims need an exact command or concrete verification step.")
    if issue_ref_status(context)["status"] == "missing-body-ref":
        gaps.append("linked issue metadata exists but the body does not cite it in `Refs:`.")
    for message in findings.get("warnings", []):
        lowered = message.lower()
        if "testing" in lowered or "evidence" in lowered:
            gaps.append(message)
    deduped: list[str] = []
    for gap in gaps:
        if gap not in deduped:
            deduped.append(gap)
    return deduped


def section_rewrite_requirements(context: dict, findings: dict) -> list[dict[str, str]]:
    expected = list(context.get("expected_template_sections") or [])
    actual = list(context.get("current_body_sections") or [])
    missing = [section for section in expected if section not in actual]
    requirements: list[dict[str, str]] = [
        {"section": section, "reason": "missing template section"}
        for section in missing
    ]
    if expected and actual and not ordered_subset(expected, actual) and not missing:
        requirements.append({"section": "all", "reason": "template order must match repository guidance"})
    for pattern, message in PLACEHOLDER_PATTERNS:
        if pattern.search(str(context.get("pr", {}).get("body") or "")):
            requirements.append({"section": "body", "reason": message})
    testing = testing_status(context)
    if testing["present"] and not testing["has_exact_command"]:
        requirements.append({"section": "Testing", "reason": "cite an exact command or concrete verification step"})
    return requirements


def build_drafting_basis(context: dict, findings: dict, *, rewrite_hint: bool | None = None) -> dict[str, object]:
    expected = list(context.get("expected_template_sections") or [])
    actual = list(context.get("current_body_sections") or [])
    issue_status = issue_ref_status(context)
    testing = testing_status(context)
    active_rule_gates = [
        "title_pattern",
        "required_sections",
        "section_order",
        "testing_evidence",
        "issue_ref_alignment",
        "unsupported_claim_screen",
    ]
    current_failures = {
        "errors": list(findings.get("errors", [])),
        "warnings": list(findings.get("warnings", [])),
    }
    title = str(context.get("pr", {}).get("title") or "").strip()
    return {
        "rewrite_strategy": rewrite_strategy_for_findings(context, findings, rewrite_hint=rewrite_hint),
        "active_rule_gates": active_rule_gates,
        "current_failures": current_failures,
        "title_direction": {
            "status": "rewrite" if not PR_TITLE_RE.match(title) else "keep-or-tighten",
            "current_title": title,
            "constraint": "<type>(<scope>): <summary>",
        },
        "required_sections_status": {
            "required": expected,
            "present": [section for section in expected if section in actual],
            "missing": [section for section in expected if section not in actual],
            "ordered": ordered_subset(expected, actual) if expected else True,
        },
        "section_rewrite_requirements": section_rewrite_requirements(context, findings),
        "supported_claims": supported_claims(context),
        "unsupported_claim_risks": risky_claim_categories(str(context.get("pr", {}).get("body") or "")),
        "testing_evidence_status": testing,
        "issue_ref_status": issue_status,
        "coverage_gaps": coverage_gaps(context, findings),
        "focused_packet_hint": None,
    }


def collect_findings(context: dict, *, original_context: dict | None = None) -> dict:
    title = (context["pr"].get("title") or "").strip()
    body = context["pr"].get("body") or ""
    expected_sections = context.get("expected_template_sections") or []
    actual_sections = context.get("current_body_sections") or []
    bodies = section_bodies(body)

    errors: list[str] = []
    warnings: list[str] = []
    info: list[str] = []

    if not PR_TITLE_RE.match(title):
        errors.append(
            "Title does not match the repository Conventional Commit pattern `<type>(<scope>): <summary>`."
        )

    if len(title) > 72:
        warnings.append("Title is longer than the PR instruction limit of 72 characters.")

    missing_sections = [section for section in expected_sections if section not in actual_sections]
    if missing_sections:
        errors.append(
            "Body is missing template sections: " + ", ".join(missing_sections) + "."
        )
    elif not ordered_subset(expected_sections, actual_sections):
        errors.append("Body sections do not follow the repository template order.")

    for pattern, message in PLACEHOLDER_PATTERNS:
        if pattern.search(body):
            errors.append(message)

    what_changed = bodies.get("What changed", "")
    what_changed_bullets = [
        line for line in what_changed.splitlines() if line.lstrip().startswith("- ")
    ]
    if what_changed and not (2 <= len(what_changed_bullets) <= 6):
        warnings.append("`What changed` should usually contain 2-6 bullets.")

    testing = bodies.get("Testing", "")
    if testing:
        has_command = bool(re.search(r"`[^`]+`", testing))
        if not has_command:
            warnings.append(
                "`Testing` does not cite any exact command or concrete verification step."
            )

    classification = bodies.get("PR Classification (optional)", "")
    checked_labels = re.findall(r"- \[x\] ([^\n]+)", classification, flags=re.IGNORECASE)
    justification_match = re.search(r"\nJustification:\s*(.*)$", body, flags=re.DOTALL)
    justification_text = justification_match.group(1).strip() if justification_match else ""
    if len(checked_labels) > 1:
        warnings.append("More than one PR classification label is checked.")
    if checked_labels and not justification_text:
        errors.append("A PR classification is checked but `Justification:` is empty.")

    if original_context is not None:
        closing_refs = {
            str(item.get("number"))
            for item in (original_context.get("pr", {}).get("closingIssuesReferences") or [])
            if str(item.get("number") or "").strip()
        }
        body_refs = referenced_issue_numbers(body)
        if closing_refs and body_refs and closing_refs.isdisjoint(body_refs):
            errors.append(
                "Candidate `Refs:` line does not match any issue linked from the PR metadata."
            )
        errors.extend(candidate_claim_findings(context, original_context))

    groups = context.get("changed_file_groups") or {}
    high_signal_groups = [
        name for name in ("runtime", "automation", "docs", "tests", "config")
        if (groups.get(name) or {}).get("count", 0) > 0
    ]
    info.append("Changed areas: " + ", ".join(high_signal_groups) if high_signal_groups else "Changed areas: none detected")

    rewrite_hint = full_rewrite_relative_to_original(context, original_context) if original_context is not None else None
    result = {
        "errors": errors,
        "warnings": warnings,
        "info": info,
        "detected": {
            "expected_sections": expected_sections,
            "actual_sections": actual_sections,
            "checked_classification_labels": checked_labels,
            "changed_file_groups": groups,
        },
    }
    result["drafting_basis"] = build_drafting_basis(context, result, rewrite_hint=rewrite_hint)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run deterministic checks against a PR title/body and template."
    )
    parser.add_argument("pr_number", type=int, nargs="?", help="Pull request number")
    parser.add_argument(
        "--context",
        default=None,
        help="Existing JSON file generated by collect_pr_context.py",
    )
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Repository root containing .git and PR guidance files",
    )
    parser.add_argument(
        "--repo",
        default=None,
        help="Optional GitHub repo slug such as owner/name",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Optional output file path. Prints JSON to stdout when omitted.",
    )
    parser.add_argument(
        "--candidate-title",
        default=None,
        help="Optional replacement title to lint against the collected context.",
    )
    parser.add_argument(
        "--candidate-body-file",
        default=None,
        help="Optional replacement body markdown file to lint against the collected context.",
    )
    args = parser.parse_args()

    if args.context:
        context = json.loads(Path(args.context).read_text(encoding="utf-8"))
    else:
        if args.pr_number is None:
            parser.error("Provide either <pr_number> or --context.")
        context = build_context(
            pr_number=args.pr_number,
            repo_root=Path(args.repo_root).resolve(),
            repo_slug=args.repo,
        )

    lint_context = context
    original_context = None
    if args.candidate_title is not None or args.candidate_body_file is not None:
        candidate_title = args.candidate_title if args.candidate_title is not None else str(context["pr"].get("title") or "")
        candidate_body = (
            Path(args.candidate_body_file).read_text(encoding="utf-8")
            if args.candidate_body_file
            else str(context["pr"].get("body") or "")
        )
        lint_context = {
            **context,
            "pr": {
                **context["pr"],
                "title": candidate_title,
                "body": candidate_body,
            },
            "current_body_sections": list(section_bodies(candidate_body).keys()),
        }
        original_context = context

    findings = collect_findings(lint_context, original_context=original_context)
    report = {
        "pr_number": lint_context["pr"]["number"],
        "title": lint_context["pr"]["title"],
        "url": lint_context["pr"]["url"],
        "mode": "candidate" if original_context is not None else "current",
        "findings": findings,
        "drafting_basis": findings.get("drafting_basis"),
    }
    payload = json.dumps(report, indent=2, ensure_ascii=True)

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
