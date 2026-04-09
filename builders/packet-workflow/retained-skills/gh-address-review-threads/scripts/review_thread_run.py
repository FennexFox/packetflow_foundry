from __future__ import annotations

import ast
import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


RUN_MANIFEST_KIND = "gh-address-review-threads-run-manifest"
RUN_MANIFEST_VERSION = 1
SKILL_NAME = "gh-address-review-threads"
RUNTIME_BASE_RELATIVE = Path(".codex/tmp/packet-workflow") / SKILL_NAME
LATEST_POINTER_NAME = "latest.json"
WORKTREE_STATUS_COMMAND = ["git", "status", "--porcelain=v1", "--untracked-files=all"]


def isoformat_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def safe_filename(value: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip())
    sanitized = sanitized.strip(".-")
    return sanitized or "run"


def read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"JSON document must be an object: {path.as_posix()}")
    return payload


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def copy_json_document(source_path: Path, target_path: Path) -> dict[str, Any]:
    payload = read_json(source_path)
    write_json(target_path, payload)
    return payload


def runtime_base_root(repo_root: Path) -> Path:
    return repo_root / RUNTIME_BASE_RELATIVE


def latest_pointer_path(repo_root: Path) -> Path:
    return runtime_base_root(repo_root) / LATEST_POINTER_NAME


def repo_head_sha(repo_root: Path) -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(repo_root),
        stdin=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def normalize_status_path(path: str) -> str:
    return path.replace("\\", "/").strip()


def decode_status_path_component(path: str) -> str:
    candidate = str(path).strip()
    if len(candidate) >= 2 and candidate[:1] == '"' and candidate[-1:] == '"':
        try:
            decoded = ast.literal_eval(candidate)
        except (SyntaxError, ValueError):
            decoded = candidate[1:-1]
        if isinstance(decoded, str):
            candidate = decoded
    return normalize_status_path(candidate)


def split_status_path_payload(payload: str) -> list[str]:
    remaining = str(payload).strip()
    parts: list[str] = []
    while remaining:
        if remaining[:1] == '"':
            index = 1
            escaped = False
            while index < len(remaining):
                char = remaining[index]
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    index += 1
                    break
                index += 1
            parts.append(remaining[:index])
            remaining = remaining[index:].lstrip()
        else:
            arrow_index = remaining.find(" -> ")
            if arrow_index < 0:
                parts.append(remaining)
                remaining = ""
            else:
                parts.append(remaining[:arrow_index])
                remaining = remaining[arrow_index + 4 :].lstrip()
        if remaining.startswith("-> "):
            remaining = remaining[3:].lstrip()
    decoded_parts: list[str] = []
    for part in parts:
        decoded = decode_status_path_component(part)
        if decoded:
            decoded_parts.append(decoded)
    return decoded_parts


def status_entry_paths(entry: str) -> list[str]:
    payload = str(entry)[3:].strip() if len(str(entry)) > 3 else str(entry).strip()
    if not payload:
        return []
    return split_status_path_payload(payload)


def canonicalize_status_entry(entry: str) -> str:
    text = str(entry)
    prefix = text[:2] if len(text) >= 2 else text.strip()
    paths = status_entry_paths(text)
    if not paths:
        return text.strip()
    return f"{prefix} {' -> '.join(paths)}"


def is_runtime_status_entry(entry: str) -> bool:
    paths = status_entry_paths(entry)
    return bool(paths) and all(path.startswith(".codex/tmp/") for path in paths)


def sha256_hexdigest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def path_content_token(path: Path) -> str:
    try:
        if not path.exists():
            return "missing"
        if path.is_symlink():
            return f"symlink:{path.readlink().as_posix()}"
        if path.is_file():
            return f"file:sha256:{sha256_hexdigest(path.read_bytes())}"
        if path.is_dir():
            child_names = sorted(child.name for child in path.iterdir())
            encoded = json.dumps(child_names, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
            return f"dir:sha256:{sha256_hexdigest(encoded)}"
        stat = path.stat()
        return f"other:{stat.st_mode}:{stat.st_size}"
    except OSError as exc:
        return f"error:{type(exc).__name__}:{exc}"


def worktree_content_fingerprint(repo_root: Path, entries: list[str]) -> str:
    states: list[dict[str, str]] = []
    seen_paths: set[str] = set()
    for entry in entries:
        for rel_path in status_entry_paths(entry):
            if not rel_path or rel_path in seen_paths:
                continue
            seen_paths.add(rel_path)
            states.append(
                {
                    "path": rel_path,
                    "token": path_content_token(repo_root / Path(rel_path)),
                }
            )
    encoded = json.dumps(
        sorted(states, key=lambda item: item["path"]),
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return f"sha256:{sha256_hexdigest(encoded)}"


def repo_worktree_snapshot(repo_root: Path) -> dict[str, Any]:
    result = subprocess.run(
        WORKTREE_STATUS_COMMAND,
        cwd=str(repo_root),
        stdin=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "git status failed"
        return {
            "available": False,
            "status_command": " ".join(WORKTREE_STATUS_COMMAND),
            "entries": [],
            "error": detail,
        }
    entries = [
        line.rstrip("\n")
        for line in result.stdout.splitlines()
        if line.strip() and not is_runtime_status_entry(line)
    ]
    return {
        "available": True,
        "status_command": " ".join(WORKTREE_STATUS_COMMAND),
        "entries": entries,
        "content_fingerprint": worktree_content_fingerprint(repo_root, entries),
    }


def pre_ack_worktree_snapshot(repo_root: Path) -> dict[str, Any]:
    return repo_worktree_snapshot(repo_root)


def summarize_worktree_entries(entries: list[str], limit: int = 4) -> str:
    sample = [str(entry) for entry in entries[:limit] if str(entry).strip()]
    if not sample:
        return "<clean>"
    if len(entries) > limit:
        sample.append(f"... (+{len(entries) - limit} more)")
    return "; ".join(sample)


def resolved_head_identity(repo_root: Path, context: dict[str, Any]) -> str:
    pr = context.get("pr")
    if not isinstance(pr, dict):
        pr = {}
    return (
        repo_head_sha(repo_root)
        or str(pr.get("headRefName") or "").strip()
        or str(context.get("context_fingerprint") or "").strip()
        or "nohead"
    )


def default_evaluation_log_path(repo_root: Path, run_id: str) -> Path:
    return repo_root / ".codex" / "tmp" / "evaluation_logs" / SKILL_NAME / f"{safe_filename(run_id)}.json"


def build_run_id(pr_number: int | str, head_sha: str, *, created_at: str | None = None) -> str:
    timestamp = created_at or isoformat_utc()
    compact_timestamp = timestamp.replace("-", "").replace(":", "")
    compact_timestamp = compact_timestamp.replace("T", "T").replace("Z", "Z")
    return "-".join(
        [
            f"pr-{safe_filename(str(pr_number))}",
            safe_filename(head_sha[:12] or "nohead"),
            safe_filename(compact_timestamp),
        ]
    )


def build_run_layout(run_root: Path) -> dict[str, Any]:
    return {
        "run_root": run_root.as_posix(),
        "manifest": (run_root / "manifest.json").as_posix(),
        "pre": {
            "context": (run_root / "pre" / "context.json").as_posix(),
            "packet_dir": (run_root / "pre" / "packets").as_posix(),
            "build_result": (run_root / "pre" / "build-result.json").as_posix(),
        },
        "ack": {
            "raw_plan": (run_root / "ack" / "plan-raw.json").as_posix(),
            "validated_plan": (run_root / "ack" / "plan.json").as_posix(),
            "result": (run_root / "ack" / "apply.json").as_posix(),
        },
        "post": {
            "context": (run_root / "post" / "context.json").as_posix(),
            "packet_dir": (run_root / "post" / "packets").as_posix(),
            "build_result": (run_root / "post" / "build-result.json").as_posix(),
            "reconciliation_input": (run_root / "post" / "reconciliation-input.json").as_posix(),
        },
        "complete": {
            "raw_plan": (run_root / "complete" / "plan-raw.json").as_posix(),
            "validated_plan": (run_root / "complete" / "plan.json").as_posix(),
            "result": (run_root / "complete" / "apply.json").as_posix(),
        },
        "evaluation": {
            "final": (run_root / "evaluation" / "final-eval.json").as_posix(),
        },
    }


def initialize_run_manifest(
    repo_root: Path,
    context: dict[str, Any],
    *,
    run_id: str | None = None,
    created_at: str | None = None,
    evaluation_log_path: Path | None = None,
) -> dict[str, Any]:
    pr = context.get("pr")
    if not isinstance(pr, dict) or not pr.get("number"):
        raise RuntimeError("Review-thread context must include `pr.number`.")

    created_timestamp = created_at or isoformat_utc()
    head_sha = resolved_head_identity(repo_root, context)
    resolved_run_id = run_id or build_run_id(pr["number"], head_sha, created_at=created_timestamp)
    run_root = runtime_base_root(repo_root) / resolved_run_id
    paths = build_run_layout(run_root)
    eval_path = evaluation_log_path or default_evaluation_log_path(repo_root, resolved_run_id)

    return {
        "kind": RUN_MANIFEST_KIND,
        "version": RUN_MANIFEST_VERSION,
        "skill_name": SKILL_NAME,
        "run_id": resolved_run_id,
        "created_at": created_timestamp,
        "updated_at": created_timestamp,
        "repo_root": repo_root.as_posix(),
        "pr": {
            "number": pr.get("number"),
            "url": pr.get("url"),
            "title": pr.get("title"),
            "head_ref": pr.get("headRefName"),
            "base_ref": pr.get("baseRefName"),
        },
        "git": {
            "pre_push_head_sha": head_sha,
            "post_push_head_sha": None,
        },
        "paths": {
            **paths,
            "evaluation_log": eval_path.resolve().as_posix(),
        },
        "state": {
            # This field is the run-local ack-applied accepted set. Same-run
            # post-push reconciliation turns it into explicit accepted
            # provenance together with validation commands and HEAD SHAs.
            "accepted_threads": [],
            "validation_commands": [],
            # Freeze the run-start worktree until ack is both posted and
            # recorded so accepted changes cannot start ahead of ack-applied.
            "pre_ack_worktree": pre_ack_worktree_snapshot(repo_root),
            "latest_context_fingerprint": context.get("context_fingerprint"),
            "phase_apply_results": {},
            "last_completed_phase": "start",
        },
    }


def validate_manifest(payload: dict[str, Any]) -> None:
    if payload.get("kind") != RUN_MANIFEST_KIND or payload.get("version") != RUN_MANIFEST_VERSION:
        raise RuntimeError("Unsupported review-thread run manifest.")
    if not isinstance(payload.get("paths"), dict):
        raise RuntimeError("Malformed review-thread run manifest: missing paths.")
    if not isinstance(payload.get("state"), dict):
        raise RuntimeError("Malformed review-thread run manifest: missing state.")


def load_manifest(path: Path) -> dict[str, Any]:
    payload = read_json(path)
    validate_manifest(payload)
    return payload


def write_manifest(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    payload["updated_at"] = isoformat_utc()
    write_json(path, payload)
    return payload


def write_latest_pointer(repo_root: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    pointer = {
        "kind": "gh-address-review-threads-run-pointer",
        "version": 1,
        "run_id": manifest["run_id"],
        "manifest_path": manifest["paths"]["manifest"],
        "repo_root": manifest["repo_root"],
        "pr_number": manifest["pr"]["number"],
        "pre_push_head_sha": manifest["git"]["pre_push_head_sha"],
        "post_push_head_sha": manifest["git"]["post_push_head_sha"],
        "updated_at": manifest["updated_at"],
    }
    write_json(latest_pointer_path(repo_root), pointer)
    return pointer


def last_completed_phase(manifest: dict[str, Any]) -> str:
    state = manifest.get("state")
    if not isinstance(state, dict):
        return ""
    return str(state.get("last_completed_phase") or "").strip()


def require_last_completed_phase(
    manifest: dict[str, Any],
    *,
    action_label: str,
    allowed: set[str],
) -> None:
    current = last_completed_phase(manifest)
    if current in allowed:
        return
    allowed_text = ", ".join(sorted(allowed))
    raise RuntimeError(
        f"{action_label} requires manifest state in {{{allowed_text}}}, got `{current or 'unknown'}`"
    )


def require_post_push_validation_provenance(manifest: dict[str, Any]) -> None:
    state = manifest.get("state")
    if not isinstance(state, dict):
        raise RuntimeError("Malformed review-thread run manifest: missing state.")
    accepted_threads = [str(item).strip() for item in state.get("accepted_threads") or [] if str(item).strip()]
    validation_commands = [str(item).strip() for item in state.get("validation_commands") or [] if str(item).strip()]
    if accepted_threads and not validation_commands:
        raise RuntimeError(
            "post-push requires recorded validation commands when accepted threads are present"
        )


def require_pre_ack_worktree_unchanged(
    manifest: dict[str, Any],
    *,
    action_label: str,
) -> None:
    state = manifest.get("state")
    if not isinstance(state, dict):
        raise RuntimeError("Malformed review-thread run manifest: missing state.")
    snapshot = state.get("pre_ack_worktree")
    if not isinstance(snapshot, dict):
        raise RuntimeError(
            f"{action_label} requires a run-start pre-ack worktree snapshot; start a new run"
        )
    baseline_entries = snapshot.get("entries")
    if not isinstance(baseline_entries, list):
        raise RuntimeError(
            f"{action_label} requires a valid run-start pre-ack worktree snapshot; start a new run"
        )
    if snapshot.get("available") is not True:
        return
    repo_root = Path(str(manifest.get("repo_root") or ".")).resolve()
    current_snapshot = repo_worktree_snapshot(repo_root)
    if current_snapshot.get("available") is not True:
        detail = str(current_snapshot.get("error") or "git status failed").strip()
        raise RuntimeError(f"{action_label} could not refresh the git worktree status: {detail}")
    current_entries = [str(entry) for entry in current_snapshot.get("entries", []) if str(entry).strip()]
    normalized_baseline = [str(entry) for entry in baseline_entries if str(entry).strip()]
    current_canonical_entries = sorted(canonicalize_status_entry(entry) for entry in current_entries)
    baseline_canonical_entries = sorted(canonicalize_status_entry(entry) for entry in normalized_baseline)
    baseline_content_fingerprint = str(snapshot.get("content_fingerprint") or "").strip()
    current_content_fingerprint = str(current_snapshot.get("content_fingerprint") or "").strip()
    if current_canonical_entries == baseline_canonical_entries and (
        not baseline_content_fingerprint or current_content_fingerprint == baseline_content_fingerprint
    ):
        return
    detail_parts = [
        f"baseline={summarize_worktree_entries(baseline_canonical_entries)}",
        f"current={summarize_worktree_entries(current_canonical_entries)}",
    ]
    if current_canonical_entries == baseline_canonical_entries:
        detail_parts.append("content-sensitive comparison detected additional edits to already-dirty paths")
        detail_parts.append(f"baseline_content={baseline_content_fingerprint or '<unknown>'}")
        detail_parts.append(f"current_content={current_content_fingerprint or '<unknown>'}")
    raise RuntimeError(
        f"{action_label} blocked because the git worktree changed after run start and before ack-applied; "
        + "; ".join(detail_parts)
    )


def create_run(
    repo_root: Path,
    context_source_path: Path,
    *,
    run_id: str | None = None,
    evaluation_log_path: Path | None = None,
) -> dict[str, Any]:
    context = read_json(context_source_path)
    manifest = initialize_run_manifest(
        repo_root,
        context,
        run_id=run_id,
        evaluation_log_path=evaluation_log_path,
    )
    manifest_path = Path(manifest["paths"]["manifest"])
    pre_context_path = Path(manifest["paths"]["pre"]["context"])
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    copy_json_document(context_source_path, pre_context_path)
    write_manifest(manifest_path, manifest)
    write_latest_pointer(repo_root, manifest)
    return manifest


def copy_context_into_manifest(manifest: dict[str, Any], *, phase: str, source_path: Path) -> dict[str, Any]:
    phase_paths = manifest["paths"].get(phase)
    if not isinstance(phase_paths, dict) or "context" not in phase_paths:
        raise RuntimeError(f"Manifest does not define a `{phase}` context path.")
    payload = copy_json_document(source_path, Path(phase_paths["context"]))
    manifest["state"]["latest_context_fingerprint"] = payload.get("context_fingerprint")
    if phase == "post":
        manifest["git"]["post_push_head_sha"] = (
            repo_head_sha(Path(manifest["repo_root"])) or manifest["git"]["pre_push_head_sha"]
        )
    return payload


def copy_validated_plan_into_manifest(
    manifest: dict[str, Any],
    *,
    phase: str,
    source_path: Path,
) -> dict[str, Any]:
    phase_paths = manifest["paths"].get(phase)
    if not isinstance(phase_paths, dict) or "validated_plan" not in phase_paths:
        raise RuntimeError(f"Manifest does not define a `{phase}` validated plan path.")
    payload = copy_json_document(source_path, Path(phase_paths["validated_plan"]))
    manifest["state"]["last_completed_phase"] = f"{phase}-validated"
    return payload


def copy_apply_result_into_manifest(
    manifest: dict[str, Any],
    *,
    phase: str,
    source_path: Path,
    allow_dry_run: bool = False,
) -> dict[str, Any]:
    phase_paths = manifest["paths"].get(phase)
    if not isinstance(phase_paths, dict) or "result" not in phase_paths:
        raise RuntimeError(f"Manifest does not define a `{phase}` apply-result path.")
    payload = copy_json_document(source_path, Path(phase_paths["result"]))
    result_phase = str(payload.get("phase") or "").strip()
    if result_phase and result_phase != phase:
        raise RuntimeError(
            f"apply result phase `{result_phase}` does not match manifest phase `{phase}`"
        )
    if payload.get("apply_succeeded") is not True:
        raise RuntimeError(f"{phase} apply result must report apply_succeeded=true")
    if payload.get("fingerprint_match") is not True:
        raise RuntimeError(f"{phase} apply result must report fingerprint_match=true")
    dry_run = bool(payload.get("dry_run"))
    if dry_run and not allow_dry_run:
        raise RuntimeError(
            f"{phase} apply result must be non-dry-run to advance the live run state"
        )
    mutation_count = len(payload.get("mutations") or []) if isinstance(payload.get("mutations"), list) else 0
    phase_results = manifest["state"].setdefault("phase_apply_results", {})
    phase_results[phase] = {
        "dry_run": dry_run,
        "apply_succeeded": True,
        "fingerprint_match": True,
        "mutation_type": payload.get("mutation_type"),
        "mutation_count": mutation_count,
        "result_path": phase_paths["result"],
    }
    fingerprint = str(payload.get("context_fingerprint") or "").strip()
    if fingerprint:
        manifest["state"]["latest_context_fingerprint"] = fingerprint
    if phase == "ack":
        actions = payload.get("normalized_thread_actions")
        accepted = sorted(
            {
                str(item.get("thread_id") or "").strip()
                for item in actions or []
                if isinstance(item, dict) and str(item.get("decision") or "").strip() == "accept"
            }
        )
        manifest["state"]["accepted_threads"] = [thread_id for thread_id in accepted if thread_id]
    manifest["state"]["last_completed_phase"] = f"{phase}-applied"
    return payload


def set_validation_commands(
    manifest: dict[str, Any],
    commands: list[str],
) -> dict[str, Any]:
    manifest["state"]["validation_commands"] = [command.strip() for command in commands if command.strip()]
    return manifest


def set_accepted_threads(
    manifest: dict[str, Any],
    thread_ids: list[str],
) -> dict[str, Any]:
    # This is a manual escape hatch for the run-local ack-applied accepted set.
    manifest["state"]["accepted_threads"] = sorted({thread_id.strip() for thread_id in thread_ids if thread_id.strip()})
    return manifest


def build_reconciliation_input(manifest: dict[str, Any]) -> dict[str, Any]:
    validation_commands = list(manifest["state"].get("validation_commands") or [])
    accepted_threads = [
        {
            "thread_id": thread_id,
            "validation_commands": validation_commands,
        }
        for thread_id in manifest["state"].get("accepted_threads") or []
        if str(thread_id).strip()
    ]
    return {
        "pre_push_head_sha": str(manifest["git"].get("pre_push_head_sha") or "").strip() or None,
        "post_push_head_sha": str(manifest["git"].get("post_push_head_sha") or "").strip() or None,
        "default_validation_commands": validation_commands,
        "accepted_threads": accepted_threads,
    }


def write_reconciliation_input(manifest: dict[str, Any]) -> dict[str, Any]:
    path = Path(manifest["paths"]["post"]["reconciliation_input"])
    payload = build_reconciliation_input(manifest)
    write_json(path, payload)
    manifest["state"]["last_completed_phase"] = "post-prepared"
    return payload
