#!/usr/bin/env python3
"""Create a release checklist issue with conservative project-add behavior."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


DEFAULT_PROJECT_TITLE = "Release Tracker"


def run_command(args: list[str], cwd: Path, check: bool = True) -> str:
    try:
        result = subprocess.run(
            args,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(f"{args[0]} not found") from exc
    if check and result.returncode != 0:
        stderr = result.stderr.strip()
        stdout = result.stdout.strip()
        detail = stderr or stdout or "command failed"
        raise RuntimeError(f"{' '.join(args)}: {detail}")
    return result.stdout


def write_json_output(path: Path | None, payload: dict[str, object]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def repo_slug(repo_root: Path) -> str | None:
    try:
        payload = json.loads(run_command(["gh", "repo", "view", "--json", "nameWithOwner"], cwd=repo_root))
    except Exception:
        return None
    slug = str(payload.get("nameWithOwner") or "").strip()
    return slug or None


def gh_repo_args(slug: str | None) -> list[str]:
    return ["--repo", slug] if slug else []


def find_existing_issue(repo_root: Path, slug: str | None, title: str) -> dict[str, object] | None:
    args = [
        "gh",
        "issue",
        "list",
        "--state",
        "open",
        "--label",
        "release",
        "--json",
        "number,title,url,state",
        *gh_repo_args(slug),
    ]
    try:
        payload = json.loads(run_command(args, cwd=repo_root, check=False) or "[]")
    except Exception:
        return None
    if not isinstance(payload, list):
        return None
    matches = [issue for issue in payload if str(issue.get("title") or "").strip() == title]
    if not matches:
        return None
    return max(matches, key=lambda issue: int(issue.get("number") or 0))


def build_create_command(
    slug: str | None,
    title: str,
    body_path: Path,
    use_project_flag: bool,
    project_title: str,
) -> list[str]:
    command = ["gh", "issue", "create", "--title", title, "--body-file", str(body_path), "--label", "release"]
    if slug:
        command.extend(["--repo", slug])
    if use_project_flag:
        command.extend(["--project", project_title])
    return command


def build_edit_command(
    slug: str | None,
    issue_number: object,
    title: str,
    body_path: Path,
    use_project_flag: bool,
    project_title: str,
) -> list[str]:
    command = ["gh", "issue", "edit", str(issue_number), "--title", title, "--body-file", str(body_path), "--add-label", "release"]
    if slug:
        command.extend(["--repo", slug])
    if use_project_flag:
        command.extend(["--add-project", project_title])
    return command


def has_project_scope(repo_root: Path) -> bool:
    try:
        status = run_command(["gh", "auth", "status"], cwd=repo_root, check=False)
    except RuntimeError:
        return False
    return "project" in status.lower()


def validate_input_contract(body_path: Path, sync_existing_body: bool, reuse_existing: bool) -> str | None:
    if not body_path.is_file():
        return f"create_release_issue.py: body file not found: {body_path}"
    if sync_existing_body and not reuse_existing:
        return "create_release_issue.py: --sync-existing-body requires --reuse-existing"
    return None


def execute_issue_action(
    *,
    title: str,
    body_path: Path,
    repo_root: Path,
    project_title: str,
    project_mode: str,
    local_release_helper_status: str,
    reuse_existing: bool,
    sync_existing_body: bool,
    dry_run: bool,
    result_output: Path | None = None,
) -> dict[str, object]:
    input_error = validate_input_contract(body_path, sync_existing_body, reuse_existing)
    if input_error:
        raise RuntimeError(input_error)

    project_scope_available = has_project_scope(repo_root)

    use_project_flag = False
    if project_mode == "require-scope":
        if not project_scope_available:
            raise RuntimeError(
                "create_release_issue.py: project scope is required but not available; run `gh auth refresh -s project` first"
            )
        use_project_flag = bool(project_title)
    elif project_mode == "auto-add-first":
        use_project_flag = bool(project_title and project_scope_available)

    slug = repo_slug(repo_root)
    existing_issue = find_existing_issue(repo_root, slug, title) if reuse_existing else None

    command = build_create_command(slug, title, body_path, use_project_flag, project_title)
    payload: dict[str, object] = {
        "repo_slug": slug,
        "checklist_issue_title": title,
        "project_mode": project_mode,
        "project_scope_available": project_scope_available,
        "project_flag_used": use_project_flag,
        "local_release_helper_handoff_available": local_release_helper_status == "present",
        "dry_run": dry_run,
        "mutation_type": "gh_issue_create",
        "command": command,
    }

    if existing_issue:
        payload.update(
            {
                "existing_issue_number": existing_issue.get("number"),
                "created_issue_url": str(existing_issue.get("url") or "").strip(),
            }
        )
        if sync_existing_body:
            edit_command = build_edit_command(
                slug,
                existing_issue.get("number"),
                title,
                body_path,
                use_project_flag,
                project_title,
            )
            payload.update(
                {
                    "mutation_type": "gh_issue_edit_existing",
                    "command": edit_command,
                }
            )
            if dry_run:
                payload["apply_succeeded"] = True
                write_json_output(result_output, payload)
                return payload
            run_command(edit_command, cwd=repo_root)
            payload["apply_succeeded"] = True
            write_json_output(result_output, payload)
            return payload

        payload.update(
            {
                "apply_succeeded": True,
                "mutation_type": "gh_issue_reuse_existing",
            }
        )
        write_json_output(result_output, payload)
        return payload

    if dry_run:
        payload["apply_succeeded"] = True
        write_json_output(result_output, payload)
        return payload

    output = run_command(command, cwd=repo_root)
    issue_url = output.strip().splitlines()[-1].strip() if output.strip() else ""
    payload["created_issue_url"] = issue_url
    payload["apply_succeeded"] = True
    write_json_output(result_output, payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create a release checklist issue with label `release`."
    )
    parser.add_argument("--title", required=True, help="Issue title")
    parser.add_argument("--body-file", required=True, help="Path to markdown body file")
    parser.add_argument("--repo-root", required=True, help="Repository root")
    parser.add_argument(
        "--project-title",
        default=DEFAULT_PROJECT_TITLE,
        help="Optional project title for explicit add when project scope is available",
    )
    parser.add_argument(
        "--project-mode",
        choices=("auto-add-first", "require-scope", "issue-only"),
        default="auto-add-first",
        help="Project add policy",
    )
    parser.add_argument(
        "--local-release-helper-status",
        default="unknown",
        help="Optional local helper status for result reporting",
    )
    parser.add_argument(
        "--result-output",
        type=Path,
        help="Optional path to write the JSON result payload.",
    )
    parser.add_argument(
        "--reuse-existing",
        action="store_true",
        help="Return an already-open release issue with the same title instead of creating a duplicate",
    )
    parser.add_argument(
        "--sync-existing-body",
        action="store_true",
        help="When reusing an existing open release issue, update its title/body from --body-file via `gh issue edit`",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print the planned gh command without creating the issue")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    body_path = Path(args.body_file).resolve()
    input_error = validate_input_contract(body_path, args.sync_existing_body, args.reuse_existing)
    if input_error:
        print(input_error, file=sys.stderr)
        return 1

    try:
        payload = execute_issue_action(
            title=args.title,
            body_path=body_path,
            repo_root=repo_root,
            project_title=args.project_title,
            project_mode=args.project_mode,
            local_release_helper_status=args.local_release_helper_status,
            reuse_existing=args.reuse_existing,
            sync_existing_body=args.sync_existing_body,
            dry_run=args.dry_run,
            result_output=args.result_output,
        )
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(json.dumps(payload, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
