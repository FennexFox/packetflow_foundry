from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


TEST_DIR = Path(__file__).resolve().parent
SCRIPT_DIR = TEST_DIR.parent / "scripts"
for candidate in (str(TEST_DIR), str(SCRIPT_DIR)):
    while candidate in sys.path:
        sys.path.remove(candidate)
    sys.path.insert(0, candidate)

import apply_thread_action_plan as apply_plan  # type: ignore  # noqa: E402
import build_review_packets as build_packets  # type: ignore  # noqa: E402
import validate_thread_action_plan as validate_plan  # type: ignore  # noqa: E402
sys.modules.pop("write_evaluation_log", None)
import write_evaluation_log as eval_log  # type: ignore  # noqa: E402
from review_thread_test_support import context_with_threads, review_thread, write_json  # noqa: E402
from thread_action_contract import build_context_fingerprint  # type: ignore  # noqa: E402


class ReviewThreadWorkflowSmokeTests(unittest.TestCase):
    def test_end_to_end_dry_run_uses_stable_ordering(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            threads = [
                review_thread(thread_id="t-2", path="src/helper.py", line=20, reviewer_login="reviewer-b", reviewer_body="Please add a test."),
                review_thread(thread_id="t-1", path="src/app.py", line=10, reviewer_login="reviewer-a", reviewer_body="Please rename this."),
            ]
            context = context_with_threads(tmp, threads)
            context["context_fingerprint"] = build_context_fingerprint(context)

            context_path = tmp / "context.json"
            packet_dir = tmp / "packets"
            build_result_path = tmp / "build-result.json"
            raw_plan_path = tmp / "raw-plan.json"
            validated_path = tmp / "validated.json"
            dry_run_path = tmp / "dry-run.json"
            log_path = tmp / "eval-log.json"
            final_path = tmp / "final.json"
            write_json(context_path, context)
            write_json(
                raw_plan_path,
                {
                    "thread_actions": [
                        {
                            "thread_id": "t-2",
                            "decision": "defer",
                            "ack_mode": "skip",
                        },
                        {
                            "thread_id": "t-1",
                            "decision": "accept",
                            "ack_mode": "add",
                            "ack_body": "I will update the naming and rerun the relevant check.",
                        },
                    ]
                },
            )

            argv = [
                "build_review_packets.py",
                "--context",
                str(context_path),
                "--repo-root",
                context["repo_root"],
                "--output-dir",
                str(packet_dir),
                "--result-output",
                str(build_result_path),
            ]
            with patch.object(sys, "argv", argv):
                self.assertEqual(build_packets.main(), 0)

            argv = [
                "validate_thread_action_plan.py",
                "--context",
                str(context_path),
                "--plan",
                str(raw_plan_path),
                "--phase",
                "ack",
                "--output",
                str(validated_path),
            ]
            with patch.object(sys, "argv", argv):
                self.assertEqual(validate_plan.main(), 0)

            validated = json.loads(validated_path.read_text(encoding="utf-8"))
            self.assertEqual([item["thread_id"] for item in validated["normalized_thread_actions"]], ["t-1", "t-2"])

            argv = [
                "apply_thread_action_plan.py",
                "--context",
                str(context_path),
                "--plan",
                str(validated_path),
                "--phase",
                "ack",
                "--dry-run",
                "--result-output",
                str(dry_run_path),
            ]
            with patch.object(sys, "argv", argv):
                self.assertEqual(apply_plan.main(), 0)

            orchestrator_path = packet_dir / "orchestrator.json"
            init_payload = eval_log.build_base_log(
                Path(eval_log.__file__).resolve(),
                eval_log.load_json(context_path),
                eval_log.load_json(orchestrator_path),
                None,
            )
            eval_log.write_json(log_path, init_payload)
            log_payload = eval_log.load_json(log_path)
            eval_log.apply_phase_update(log_payload, "build", eval_log.load_json(build_result_path), None)
            eval_log.apply_phase_update(log_payload, "validate", validated, None)
            eval_log.apply_phase_update(log_payload, "apply", eval_log.load_json(dry_run_path), None)
            eval_log.write_json(log_path, log_payload)

            write_json(
                final_path,
                {
                    "quality": {
                        "first_pass_usable": True,
                        "human_post_edit_required": False,
                        "human_post_edit_severity": "none",
                    }
                },
            )
            finalized = eval_log.load_json(log_path)
            eval_log.finalize_log(finalized, eval_log.load_json(final_path))

            self.assertEqual(finalized["skill_specific"]["data"]["threads_accepted"], 1)
            self.assertTrue(finalized["skill_specific"]["data"]["common_path_sufficient"])
            self.assertIsNotNone(finalized["skill_specific"]["data"]["estimated_packet_tokens"])
            self.assertEqual(finalized["quality"]["result_status"], "dry-run")
            self.assertTrue(finalized["safety"]["fingerprint_match"])

    def test_stale_fingerprint_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            threads = [
                review_thread(thread_id="t-1", path="src/app.py", line=10, reviewer_login="reviewer-a", reviewer_body="Please rename this.")
            ]
            context = context_with_threads(tmp, threads)
            context["context_fingerprint"] = build_context_fingerprint(context)
            result = {
                "phase": "ack",
                "valid": True,
                "context_fingerprint": "stale",
                "normalized_thread_actions": [
                    {
                        "thread_id": "t-1",
                        "decision": "accept",
                        "ack_mode": "add",
                        "ack_body": "Will fix this.",
                    }
                ],
            }

            with self.assertRaises(RuntimeError):
                apply_plan.load_normalized_plan_envelope(context, result, "ack")


if __name__ == "__main__":
    unittest.main()
