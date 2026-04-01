#!/usr/bin/env python3
"""Build a conservative complete-phase plan for same-run outdated reconciliation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from thread_action_contract import context_fingerprint


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path | None, payload: dict[str, Any]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def packet_paths(packet_dir: Path) -> list[Path]:
    return sorted(path for path in packet_dir.glob("thread-*.json") if path.is_file())


def packet_lookup(packet_dir: Path) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for path in packet_paths(packet_dir):
        payload = load_json(path)
        thread = payload.get("thread") if isinstance(payload, dict) else None
        thread_id = str((thread or {}).get("thread_id") or "").strip()
        if thread_id:
            lookup[thread_id] = payload
    return lookup


def format_validation(commands: list[str]) -> str | None:
    normalized = [str(command).strip() for command in commands if str(command).strip()]
    if not normalized:
        return None
    return "; ".join(f"`{command}`" for command in normalized)


def completion_body(packet: dict[str, Any]) -> str:
    thread = packet.get("thread") or {}
    recheck = packet.get("outdated_recheck") or {}
    evidence = recheck.get("current_head_evidence") or {}
    validation = recheck.get("validation_provenance") or {}
    path = str(evidence.get("path") or thread.get("path") or "").strip()
    area = str(evidence.get("area") or "").strip()
    request_phrase = "requested wording change" if area == "docs" else "requested change"
    first_sentence = (
        f"Current HEAD already covers the {request_phrase} in `{path}`, "
        "and the thread became outdated after the accepted update was pushed."
    )
    validation_text = format_validation(list(validation.get("commands") or []))
    if not validation_text:
        return first_sentence
    return f"{first_sentence} Validation: {validation_text}."


def complete_reply_action(packet: dict[str, Any]) -> dict[str, Any]:
    complete_basis = ((packet.get("reply_update_basis") or {}).get("complete") or {})
    mode = str(complete_basis.get("mode") or "").strip()
    comment_id = str(complete_basis.get("comment_id") or "").strip()
    if mode == "update":
        action = {"complete_mode": "update"}
        if comment_id:
            action["complete_comment_id"] = comment_id
        return action
    return {"complete_mode": "add"}


def decision_for_thread(thread: dict[str, Any], packet: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
    thread_id = str(thread.get("thread_id") or "").strip()
    if not thread_id:
        raise RuntimeError("thread packet is missing thread_id")
    decision = "defer-outdated" if bool(thread.get("is_outdated")) else "defer"
    action: dict[str, Any] = {
        "thread_id": thread_id,
        "decision": decision,
        "complete_mode": "skip",
        "resolve_after_complete": False,
    }

    if not bool(packet.get("transitioned_to_outdated")):
        return action, None

    recheck = packet.get("outdated_recheck") or {}
    verdict = str(recheck.get("resolution_verdict") or "").strip()
    reason = str(recheck.get("verdict_reason") or "").strip()
    candidate = {
        "thread_id": thread_id,
        "resolution_verdict": verdict,
        "verdict_reason": reason,
        "path": str((recheck.get("current_head_evidence") or {}).get("path") or thread.get("path") or "").strip(),
        "validation_commands": list((recheck.get("validation_provenance") or {}).get("commands") or []),
    }

    if verdict == "auto-accept":
        action["decision"] = "accept"
        action.update(complete_reply_action(packet))
        action["complete_body"] = completion_body(packet)
        action["resolve_after_complete"] = True
        return action, candidate

    if verdict == "still-applies":
        action["decision"] = "defer"
        return action, candidate

    action["decision"] = "defer-outdated"
    return action, candidate


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context", type=Path, required=True, help="Path to post-push review-thread context JSON.")
    parser.add_argument("--packet-dir", type=Path, required=True, help="Directory containing thread packet JSON files.")
    parser.add_argument("--output", type=Path, help="Optional path to write the raw complete-phase plan JSON.")
    args = parser.parse_args()

    context = load_json(args.context)
    packets_by_thread = packet_lookup(args.packet_dir)
    thread_actions: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []

    for thread in context.get("threads", []):
        if not isinstance(thread, dict) or bool(thread.get("is_resolved")):
            continue
        thread_id = str(thread.get("thread_id") or "").strip()
        if not thread_id:
            raise RuntimeError("context thread is missing thread_id")
        packet = packets_by_thread.get(thread_id)
        if packet is None:
            raise RuntimeError(f"missing thread packet for {thread_id}")
        action, candidate = decision_for_thread(thread, packet)
        thread_actions.append(action)
        if candidate is not None:
            candidates.append(candidate)

    summary = {
        "outdated_transition_candidates": len(candidates),
        "outdated_auto_resolved": sum(1 for item in candidates if item["resolution_verdict"] == "auto-accept"),
        "outdated_recheck_ambiguous": sum(1 for item in candidates if item["resolution_verdict"] == "ambiguous"),
        "outdated_still_applicable": sum(1 for item in candidates if item["resolution_verdict"] == "still-applies"),
    }
    payload = {
        "context_fingerprint": context_fingerprint(context),
        "thread_actions": thread_actions,
        "reconciliation_summary": summary,
        "candidates": candidates,
    }
    write_json(args.output, payload)
    print(json.dumps(payload, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
