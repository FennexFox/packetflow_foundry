#!/usr/bin/env python3
"""Shared helpers for release-copy validate/apply flows."""

from __future__ import annotations

import hashlib
import json
import re
import xml.sax.saxutils as xml_utils
from pathlib import Path
from typing import Any

import collect_release_copy_context as collect_tools
import release_copy_plan_contract as contract


ATTRIBUTE_FIELD_TAGS = {
    "short_description": "ShortDescription",
    "mod_version": "ModVersion",
}

BLOCK_FIELD_TAGS = {
    "long_description": "LongDescription",
    "change_log": "ChangeLog",
}

README_ALLOWED_SECTIONS = {"Current Release", "Current Status"}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def json_fingerprint(payload: Any) -> str:
    return contract.json_fingerprint(payload)


def expected_context_fingerprint(context: dict[str, Any]) -> str:
    return contract.expected_context_fingerprint(context)


def expected_freshness_tuple(context: dict[str, Any]) -> dict[str, Any]:
    return contract.expected_freshness_tuple(context)


def normalize_release_version(value: str) -> str:
    return contract.normalize_release_version(value)


def current_head_commit(repo_root: Path) -> str:
    return collect_tools.git_head_commit(repo_root)


def existing_issue_snapshot(issue: dict[str, Any] | None) -> dict[str, Any] | None:
    return collect_tools.existing_issue_snapshot(issue)


def fetch_issue_snapshot(repo_root: Path, repo_slug: str | None, issue_number: int) -> dict[str, Any] | None:
    return collect_tools.release_issue_by_number(repo_root, repo_slug, issue_number)


def replace_publish_fields(text: str, fields: dict[str, str]) -> str:
    updated = text
    for field_name, tag_name in ATTRIBUTE_FIELD_TAGS.items():
        if field_name not in fields:
            continue
        value = str(fields[field_name])
        escaped = xml_utils.escape(value, {'"': "&quot;"})
        pattern = re.compile(rf"(<{tag_name}\s+Value=\")([^\"]*)(\"\s*/>)")
        # Use a callable replacement so numeric-leading values are never parsed as backreferences.
        updated, count = pattern.subn(
            lambda match, replacement=escaped: match.group(1) + replacement + match.group(3),
            updated,
            count=1,
        )
        if count != 1:
            raise RuntimeError(f"unsupported layout: missing <{tag_name} Value=\"...\" /> field")

    for field_name, tag_name in BLOCK_FIELD_TAGS.items():
        if field_name not in fields:
            continue
        value = xml_utils.escape(str(fields[field_name]))
        pattern = re.compile(rf"(<{tag_name}>)(.*?)(</{tag_name}>)", re.DOTALL)
        updated, count = pattern.subn(lambda match: match.group(1) + value + match.group(3), updated, count=1)
        if count != 1:
            raise RuntimeError(f"unsupported layout: missing <{tag_name}>...</{tag_name}> block")

    return updated


def split_markdown_document(text: str) -> tuple[str, list[tuple[str, str]]]:
    lines = text.splitlines()
    intro_lines: list[str] = []
    sections: list[tuple[str, str]] = []
    current_heading: str | None = None
    current_lines: list[str] = []

    for line in lines:
        if line.startswith("## "):
            if current_heading is None:
                intro = "\n".join(intro_lines).strip()
            else:
                sections.append((current_heading, "\n".join(current_lines).strip()))
            current_heading = line[3:].strip()
            current_lines = []
            if len(sections) == 0 and current_heading is not None and not intro_lines:
                intro_lines = []
            continue
        if current_heading is None:
            intro_lines.append(line)
        else:
            current_lines.append(line)

    if current_heading is not None:
        sections.append((current_heading, "\n".join(current_lines).strip()))

    intro_text = "\n".join(intro_lines).strip()
    return intro_text, sections


def render_markdown_document(intro_text: str, sections: list[tuple[str, str]]) -> str:
    parts: list[str] = []
    if intro_text.strip():
        parts.append(intro_text.strip())
    for heading, body in sections:
        section_text = f"## {heading}".rstrip()
        if body.strip():
            section_text += "\n" + body.strip()
        parts.append(section_text)
    return "\n\n".join(parts).rstrip() + "\n"


def replace_readme_blocks(text: str, intro_text: str | None, sections: dict[str, str]) -> str:
    current_intro, current_sections = split_markdown_document(text)
    updated_intro = current_intro if intro_text is None else intro_text.strip()

    section_map = {heading: body for heading, body in current_sections}
    for heading in sections:
        if heading not in README_ALLOWED_SECTIONS:
            raise RuntimeError(f"unsupported layout: section `{heading}` is outside the deterministic allowlist")
        if heading not in section_map:
            raise RuntimeError(f"unsupported layout: missing README section `{heading}`")
    updated_sections = [
        (heading, sections.get(heading, body).strip())
        for heading, body in current_sections
    ]
    return render_markdown_document(updated_intro, updated_sections)


def apply_publish_update(path: Path, fields: dict[str, str], dry_run: bool) -> dict[str, Any]:
    original = path.read_text(encoding="utf-8")
    updated = replace_publish_fields(original, fields)
    changed = updated != original
    if changed and not dry_run:
        path.write_text(updated, encoding="utf-8")
    return {
        "kind": "publish_configuration",
        "path": str(path),
        "changed": changed,
        "fields": sorted(fields.keys()),
    }


def apply_readme_update(path: Path, intro_text: str | None, sections: dict[str, str], dry_run: bool) -> dict[str, Any]:
    original = path.read_text(encoding="utf-8")
    updated = replace_readme_blocks(original, intro_text, sections)
    changed = updated != original
    if changed and not dry_run:
        path.write_text(updated, encoding="utf-8")
    return {
        "kind": "readme",
        "path": str(path),
        "changed": changed,
        "intro_updated": intro_text is not None,
        "sections": sorted(sections.keys()),
    }
