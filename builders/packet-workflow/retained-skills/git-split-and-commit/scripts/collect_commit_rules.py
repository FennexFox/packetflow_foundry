#!/usr/bin/env python3
"""Collect repo-specific commit-message rules into a compact JSON artifact."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

RULE_TEXT_SUFFIXES = (".md", ".txt", ".json", ".yml", ".yaml", ".js", ".cjs", ".mjs", ".ts")
SUBJECT_RE = re.compile(
    r"^(?P<type>[a-z][a-z0-9-]*)(?:\((?P<scope>[A-Za-z0-9._/-]+)\))?(?P<breaking>!)?: (?P<summary>.+)$"
)
FIXED_RULE_FILES = {
    "commit_message_instructions": ".github/instructions/commit-message.instructions.md",
    "copilot_instructions": ".github/copilot-instructions.md",
    "contributing": "CONTRIBUTING.md",
    "maintaining": "MAINTAINING.md",
}


def run_git(repo: Path, args: list[str], check: bool = True) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )
    if check and result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "git failed")
    return result.stdout


def read_text_if_exists(path: Path) -> str | None:
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


def parse_heading_blocks(markdown_text: str | None) -> dict[str, str]:
    if not markdown_text:
        return {}
    blocks: dict[str, str] = {}
    current = None
    buffer: list[str] = []
    for line in markdown_text.splitlines():
        if line.startswith("## "):
            if current is not None:
                blocks[current] = "\n".join(buffer).strip()
            current = line[3:].strip()
            buffer = []
        elif current is not None:
            buffer.append(line)
    if current is not None:
        blocks[current] = "\n".join(buffer).strip()
    return blocks


def find_block(blocks: dict[str, str], prefix: str) -> str | None:
    for heading, body in blocks.items():
        if heading.lower().startswith(prefix.lower()):
            return "## " + heading + ("\n" + body if body else "")
    return None


def extract_bullets(block: str | None) -> list[str]:
    if not block:
        return []
    bullets: list[str] = []
    for line in block.splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            bullets.append(stripped[2:].strip())
    return bullets


def extract_backtick_tokens(block: str | None) -> list[str]:
    if not block:
        return []
    seen: list[str] = []
    for token in re.findall(r"`([^`]+)`", block):
        if token not in seen:
            seen.append(token)
    return seen


def normalize_token_list(tokens: list[str]) -> list[str]:
    seen: list[str] = []
    for token in tokens:
        cleaned = token.strip().strip("`").strip()
        lowered = cleaned.lower()
        if not re.fullmatch(r"[a-z][a-z0-9-]*", lowered):
            continue
        if lowered not in seen:
            seen.append(lowered)
    return seen


def subject_length_limit(subject_block: str | None) -> int | None:
    if not subject_block:
        return None
    match = re.search(r"(\d+)\s+characters?\s+or\s+fewer", subject_block, flags=re.IGNORECASE)
    return int(match.group(1)) if match else None


def explicit_scope_requirement(format_block: str | None, scopes_block: str | None) -> bool | None:
    combined = "\n".join(part for part in (format_block, scopes_block) if part)
    if not combined:
        return None
    if re.search(r"scope`?\s+(?:is\s+)?optional", combined, flags=re.IGNORECASE):
        return False
    if re.search(r"scope`?\s+(?:is\s+)?not required", combined, flags=re.IGNORECASE):
        return False
    if re.search(r"scope`?\s+is\s+required", combined, flags=re.IGNORECASE):
        return True
    if "<type>(<scope>): <subject>" in combined:
        return True
    if re.search(r"(?:<type>|type)\s*!?\s*:\s*(?:<subject>|subject)", combined, flags=re.IGNORECASE):
        return False
    return None


def commit_related_excerpt(text: str | None) -> list[str]:
    if not text:
        return []
    matches: list[str] = []
    for line in text.splitlines():
        lowered = line.lower()
        if "commit" in lowered or "conventional commit" in lowered or "subject" in lowered:
            stripped = line.strip()
            if stripped and stripped not in matches:
                matches.append(stripped)
        if len(matches) >= 8:
            break
    return matches


def parse_subject_line(subject: str) -> dict[str, str | bool] | None:
    match = SUBJECT_RE.match(subject.strip())
    if not match:
        return None
    return {
        "type": match.group("type"),
        "scope": match.group("scope") or "",
        "breaking": bool(match.group("breaking")),
        "summary": match.group("summary"),
    }


def recent_subjects(repo_root: Path, count: int = 20) -> list[str]:
    output = run_git(repo_root, ["log", f"-n{count}", "--format=%s"], check=False)
    return [line.strip() for line in output.splitlines() if line.strip()]


def recent_scopes(subjects: list[str]) -> list[str]:
    seen: list[str] = []
    for subject in subjects:
        parsed = parse_subject_line(subject)
        scope = str(parsed.get("scope", "")) if parsed else ""
        if scope and scope not in seen:
            seen.append(scope)
    return seen


def tracked_files(repo_root: Path) -> list[str]:
    output = run_git(repo_root, ["ls-files"], check=False)
    return [line.strip().replace("\\", "/") for line in output.splitlines() if line.strip()]


def rule_file_key(rel_path: str) -> str | None:
    lowered = rel_path.lower()
    basename = Path(rel_path).name.lower()
    for key, fixed_path in FIXED_RULE_FILES.items():
        if lowered == fixed_path.lower():
            return key

    commitlint_names = {
        ".commitlintrc",
        ".commitlintrc.json",
        ".commitlintrc.yml",
        ".commitlintrc.yaml",
        ".commitlintrc.js",
        ".commitlintrc.cjs",
        ".commitlintrc.mjs",
        ".commitlintrc.ts",
        "commitlint.config.js",
        "commitlint.config.cjs",
        "commitlint.config.mjs",
        "commitlint.config.ts",
    }
    if basename in commitlint_names:
        return "commitlint_config"
    if basename in {".gitmessage", ".gitmessage.txt", "gitmessage.txt"}:
        return "gitmessage_template"
    if basename == "package.json":
        return "package_json"
    if not lowered.endswith(RULE_TEXT_SUFFIXES):
        return None
    if any(token in lowered for token in ("commit", "conventional", "semantic-release", "gitmessage")):
        sanitized = re.sub(r"[^a-z0-9]+", "_", rel_path.lower()).strip("_")
        return f"extra_rule_file_{sanitized}"
    return None


def discover_rule_files(repo_root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    seen_paths: set[str] = set()
    for key, rel_path in FIXED_RULE_FILES.items():
        path = (repo_root / rel_path).resolve()
        if path.exists():
            normalized_path = str(path)
            result[key] = normalized_path
            seen_paths.add(normalized_path)
    for rel_path in tracked_files(repo_root):
        key = rule_file_key(rel_path)
        if key is None:
            continue
        normalized_path = str((repo_root / rel_path).resolve())
        if normalized_path in seen_paths:
            continue
        unique_key = key
        suffix = 2
        while unique_key in result:
            unique_key = f"{key}_{suffix}"
            suffix += 1
        result[unique_key] = normalized_path
        seen_paths.add(normalized_path)
    return result


def load_rule_texts(files: dict[str, str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for key, path_str in files.items():
        text = read_text_if_exists(Path(path_str))
        if text:
            result[key] = text
    return result


def infer_format_from_text(text: str | None) -> str | None:
    if not text:
        return None
    normalized = " ".join(text.split())
    if re.search(
        r"(?:<type>|type)\s*\(\s*(?:<scope>|scope)\s*\)\s*!?\s*:\s*(?:<subject>|subject)",
        normalized,
        flags=re.IGNORECASE,
    ):
        return "<type>(<scope>): <subject>"
    if re.search(
        r"(?:<type>|type)\s*!?\s*:\s*(?:<subject>|subject)",
        normalized,
        flags=re.IGNORECASE,
    ):
        return "<type>: <subject>"
    return None


def infer_format_from_recent_subjects(subjects: list[str]) -> str | None:
    parsed = [item for subject in subjects if (item := parse_subject_line(subject)) is not None]
    if len(parsed) < 3:
        return None
    if any(str(item.get("scope", "")) for item in parsed):
        return "<type>(<scope>): <subject>"
    return "<type>: <subject>"


def infer_allowed_types(types_block: str | None, texts: dict[str, str], subjects: list[str]) -> tuple[list[str], str | None]:
    explicit_tokens = normalize_token_list(extract_backtick_tokens(types_block))
    if explicit_tokens:
        return explicit_tokens, "commit_message_instructions"

    commitlint_pattern = re.compile(
        r"type-enum['\"]?\s*:\s*\[\s*\d+\s*,\s*['\"]always['\"]\s*,\s*\[(?P<body>.*?)\]\s*\]",
        flags=re.IGNORECASE | re.DOTALL,
    )
    for key, text in texts.items():
        match = commitlint_pattern.search(text)
        if not match:
            continue
        tokens = normalize_token_list(re.findall(r"['\"]([A-Za-z0-9-]+)['\"]", match.group("body")))
        if tokens:
            return tokens, key

    recent_types: list[str] = []
    for subject in subjects:
        parsed = parse_subject_line(subject)
        if not parsed:
            continue
        message_type = str(parsed["type"]).lower()
        if message_type not in recent_types:
            recent_types.append(message_type)
    return recent_types[:12], ("recent_subjects" if recent_types else None)


def infer_scope_requirement(
    format_block: str | None,
    scopes_block: str | None,
    texts: dict[str, str],
    subjects: list[str],
) -> tuple[bool | None, str | None]:
    explicit = explicit_scope_requirement(format_block, scopes_block)
    if explicit is not None:
        return explicit, "commit_message_instructions"

    for key, text in texts.items():
        required_match = re.search(
            r"scope-empty['\"]?\s*:\s*\[\s*\d+\s*,\s*['\"](?P<mode>always|never)['\"]",
            text,
            flags=re.IGNORECASE,
        )
        if required_match:
            return required_match.group("mode").lower() == "never", key

    parsed = [item for subject in subjects if (item := parse_subject_line(subject)) is not None]
    if len(parsed) >= 5:
        with_scope = sum(1 for item in parsed if str(item.get("scope", "")))
        if with_scope == len(parsed):
            return True, "recent_subjects"
        if with_scope == 0:
            return False, "recent_subjects"
    return None, None


def infer_subject_length_limit(subject_block: str | None, texts: dict[str, str]) -> tuple[int | None, str | None]:
    explicit = subject_length_limit(subject_block)
    if explicit is not None:
        return explicit, "commit_message_instructions"

    header_limit_pattern = re.compile(
        r"header-max-length['\"]?\s*:\s*\[\s*\d+\s*,\s*['\"]always['\"]\s*,\s*(?P<limit>\d+)\s*\]",
        flags=re.IGNORECASE,
    )
    prose_limit_pattern = re.compile(r"(?P<limit>\d+)\s+characters?\s+or\s+fewer", flags=re.IGNORECASE)
    for key, text in texts.items():
        config_match = header_limit_pattern.search(text)
        if config_match:
            return int(config_match.group("limit")), key
        prose_match = prose_limit_pattern.search(text)
        if prose_match:
            return int(prose_match.group("limit")), key
    return None, None


def derive_repo_defaults(type_selection_block: str | None, texts: dict[str, str]) -> tuple[list[str], str | None]:
    defaults = extract_bullets(type_selection_block)
    if defaults:
        return defaults, "commit_message_instructions"

    keywords = ("prefer ", "when uncertain", "default to ", "use `fix`", "use `feat`")
    derived: list[str] = []
    for key, text in texts.items():
        for line in commit_related_excerpt(text):
            lowered = line.lower()
            if any(keyword in lowered for keyword in keywords) and line not in derived:
                derived.append(line)
        if derived:
            return derived, key
    return [], None


def build_doc_mentions(texts: dict[str, str]) -> dict[str, list[str]]:
    return {
        key: commit_related_excerpt(text)
        for key, text in texts.items()
        if commit_related_excerpt(text)
    }


def build_rules(repo_root: Path) -> dict[str, object]:
    repo_root = Path(run_git(repo_root, ["rev-parse", "--show-toplevel"]).strip())
    files = discover_rule_files(repo_root)
    texts = load_rule_texts(files)

    instructions_text = texts.get("commit_message_instructions")
    blocks = parse_heading_blocks(instructions_text)
    format_block = find_block(blocks, "Format")
    types_block = find_block(blocks, "Types")
    type_selection_block = find_block(blocks, "Type Selection")
    scopes_block = find_block(blocks, "Scopes")
    subject_block = find_block(blocks, "Subject Rules")
    body_block = find_block(blocks, "Body Rules")
    refs_block = find_block(blocks, "References")

    subjects = recent_subjects(repo_root)
    recent_scope_words = recent_scopes(subjects)
    format_from_instructions = infer_format_from_text(format_block)
    inferred_format, format_source = (
        (format_from_instructions, "commit_message_instructions")
        if format_from_instructions
        else (None, None)
    )
    if inferred_format is None:
        for key, text in texts.items():
            if key == "commit_message_instructions":
                continue
            candidate = infer_format_from_text(text)
            if candidate:
                inferred_format = candidate
                format_source = key
                break
    if inferred_format is None:
        recent_format = infer_format_from_recent_subjects(subjects)
        inferred_format = recent_format or "<type>(<scope>): <subject>"
        format_source = "recent_subjects" if recent_format else "fallback_default"

    scope_suggestions = normalize_token_list(extract_backtick_tokens(scopes_block))
    for scope in recent_scope_words:
        if scope not in scope_suggestions:
            scope_suggestions.append(scope)

    allowed_types, allowed_types_source = infer_allowed_types(types_block, texts, subjects)
    scope_is_required, scope_required_source = infer_scope_requirement(
        format_block,
        scopes_block,
        texts,
        subjects,
    )
    subject_limit, subject_limit_source = infer_subject_length_limit(subject_block, texts)
    repo_defaults, repo_defaults_source = derive_repo_defaults(type_selection_block, texts)

    return {
        "repo_root": str(repo_root),
        "rule_files": files,
        "rules": {
            "format": inferred_format,
            "allowed_types": allowed_types,
            "scope_required": scope_is_required,
            "scope_suggestions": scope_suggestions,
            "subject_length_limit": subject_limit,
            "subject_rules": extract_bullets(subject_block),
            "body_rules": extract_bullets(body_block),
            "references_rules": extract_bullets(refs_block),
            "repo_defaults": repo_defaults,
        },
        "rule_derivation": {
            "format_source": format_source,
            "allowed_types_source": allowed_types_source,
            "scope_required_source": scope_required_source,
            "subject_length_limit_source": subject_limit_source,
            "repo_defaults_source": repo_defaults_source,
        },
        "recent_scope_vocabulary": recent_scope_words,
        "recent_subject_samples": subjects[:12],
        "instruction_snippets": {
            "format": format_block,
            "types": types_block,
            "type_selection": type_selection_block,
            "scopes": scopes_block,
            "subject_rules": subject_block,
            "body_rules": body_block,
            "references": refs_block,
        },
        "doc_mentions": build_doc_mentions(texts),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect repo-specific commit-message rules into JSON."
    )
    parser.add_argument(
        "--repo",
        type=Path,
        default=Path.cwd(),
        help="Repository path. Defaults to the current directory.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional path to write the JSON artifact. Prints JSON to stdout when omitted.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        payload = build_rules(args.repo)
    except Exception as exc:  # pragma: no cover - command-line error path
        print(f"collect_commit_rules.py: {exc}", file=sys.stderr)
        return 1

    serialized = json.dumps(payload, indent=2, ensure_ascii=True) + "\n"
    if args.output:
        args.output.write_text(serialized, encoding="utf-8")
        print(f"Wrote commit rules to {args.output}")
    else:
        sys.stdout.write(serialized)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
