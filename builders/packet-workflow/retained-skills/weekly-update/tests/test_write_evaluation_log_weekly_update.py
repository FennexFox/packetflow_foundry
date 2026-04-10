from __future__ import annotations

import sys
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
script_dir = str(SCRIPT_DIR)
while script_dir in sys.path:
    sys.path.remove(script_dir)
sys.path.insert(0, script_dir)

sys.modules.pop("write_evaluation_log", None)
import write_evaluation_log as eval_log  # noqa: E402


class WeeklyUpdateEvaluationLogTests(unittest.TestCase):
    @staticmethod
    def _planned_worker() -> dict:
        worker = {
            "name": "mapping-repo-mapper",
            "agent_type": "repo_mapper",
            "model": "gpt-5.4-mini",
            "reasoning_effort": "medium",
            "packets": ["mapping_packet.json"],
            "responsibility": "Map repo surfaces",
        }
        return {
            **worker,
            "worker_id": eval_log.common.planned_worker_id(worker),
        }

    def test_default_output_path_uses_repo_root(self) -> None:
        repo_root = Path("repo-root")

        resolved = eval_log.default_output_path(
            repo_root,
            "weekly-update",
            "2026-04-04T10:00:00Z__weekly-update__abc:def",
        )

        self.assertEqual(
            resolved,
            repo_root
            / ".codex"
            / "tmp"
            / "evaluation_logs"
            / "weekly-update"
            / "2026-04-04T10-00-00Z__weekly-update__abc-def.json",
        )

    def test_find_branch_and_head_sha_ignore_non_dict_analysis_ref(self) -> None:
        context = {
            "analysis_ref": "main",
            "current_branch": "develop",
            "head_sha": "abc1234",
            "pr": {
                "headRefName": "feature/fallback",
                "headRefOid": "deadbeef",
            },
        }

        self.assertEqual(eval_log.find_branch(context), "develop")
        self.assertEqual(eval_log.find_head_sha(context), "abc1234")

    def test_skill_specific_data_reads_weekly_update_contract_fields(self) -> None:
        context = {
            "reporting_window": {"start_utc": "2026-03-20T00:00:00Z", "end_utc": "2026-03-27T00:00:00Z"},
            "source_gaps": ["release notes may be truncated"],
            "candidate_inventory": [
                {"proposed_classification": "actual_incident", "raw_reread_reason": None},
                {"proposed_classification": "blocker_or_risk", "raw_reread_reason": "conflicting_signals"},
                {"proposed_classification": "artifact_only", "raw_reread_reason": None},
            ],
        }
        orchestrator = {
            "review_mode": "targeted-delegation",
            "selected_packets": ["mapping_packet", "changes_packet", "risks_packet"],
        }

        payload = eval_log.skill_specific_data("weekly-update", context, orchestrator, None)

        self.assertEqual(payload["review_mode"], "targeted-delegation")
        self.assertEqual(payload["selected_packets"], ["mapping_packet", "changes_packet", "risks_packet"])
        self.assertNotIn("worker_count", payload)
        self.assertNotIn("worker_mix", payload)
        self.assertEqual(payload["candidate_counts_by_proposed_classification"]["actual_incident"], 1)
        self.assertEqual(payload["candidate_counts_by_proposed_classification"]["blocker_or_risk"], 1)
        self.assertEqual(payload["raw_reread_reason_counts"], {"conflicting_signals": 1})
        self.assertEqual(payload["coverage_gap_count"], 1)
        self.assertFalse(payload["common_path_sufficient"])
        self.assertEqual(payload["raw_reread_count"], 1)

    def test_build_base_log_leaves_eval_only_worker_metadata_unset_for_lean_runtime_packets(self) -> None:
        context = {
            "repo_root": str(Path("repo-root")),
            "current_branch": "batch_3",
            "reporting_window": {"start_utc": "2026-03-20T00:00:00Z", "end_utc": "2026-03-27T00:00:00Z"},
        }
        orchestrator = {
            "review_mode": "targeted-delegation",
            "packet_files": ["global_packet.json", "mapping_packet.json", "orchestrator.json"],
            "shared_packet": "global_packet.json",
        }

        payload = eval_log.build_base_log(SCRIPT_DIR / "write_evaluation_log.py", context, orchestrator, None)

        self.assertEqual(payload["orchestration"]["planned_workers"]["count"], 0)
        self.assertEqual(payload["orchestration"]["planned_workers"]["roles"], [])
        self.assertEqual(payload["orchestration"]["actual_workers"]["summary"]["executed_count"], 0)
        self.assertEqual(payload["orchestration"]["override_signals"], [])
        self.assertNotIn("worker_count", payload["skill_specific"]["data"])
        self.assertNotIn("worker_mix", payload["skill_specific"]["data"])

    def test_build_phase_merges_packet_sizing_efficiency_and_common_path_signals(self) -> None:
        log = {
            "skill": {"name": "weekly-update"},
            "measurement": {},
            "baseline": {},
            "orchestration": {},
            "skill_specific": {"data": {}},
        }
        result = {
            "review_mode": "targeted-delegation",
            "planned_workers": {
                "count": 2,
                "roles": ["repo_mapper", "large_diff_auditor"],
                "workers": [
                    {
                        "name": "mapping-repo-mapper",
                        "agent_type": "repo_mapper",
                        "model": "gpt-5.4-mini",
                        "reasoning_effort": "medium",
                        "packets": ["mapping_packet.json"],
                        "responsibility": "Map repo surfaces",
                    },
                    {
                        "name": "risks-large-diff-auditor",
                        "agent_type": "large_diff_auditor",
                        "model": "gpt-5.4-mini",
                        "reasoning_effort": "medium",
                        "packets": ["risks_packet.json"],
                        "responsibility": "Audit risks",
                    },
                ],
            },
            "selected_packets": ["mapping_packet", "changes_packet", "risks_packet"],
            "candidate_counts_by_proposed_classification": {"actual_incident": 1, "blocker_or_risk": 2},
            "raw_reread_reason_counts": {"conflicting_signals": 1},
            "coverage_gap_count": 2,
            "common_path_sufficient": False,
            "raw_reread_count": 1,
            "packet_sizing": {
                "packet_count": 6,
                "packet_size_bytes": 4096,
                "largest_packet_bytes": 1024,
                "largest_two_packets_bytes": 1800,
            },
            "efficiency": {
                "packet_compaction": {
                    "local_only_tokens": 1200,
                    "packet_tokens": 400,
                    "savings_tokens": 800,
                    "main_model_input_cost_nanousd": 1000,
                    "provenance": "estimated",
                    "pricing_snapshot_id": "openai-2026-04-09",
                }
            },
        }

        eval_log.apply_phase_update(log, "build", result, 1.5)

        self.assertEqual(log["orchestration"]["review_mode"], "targeted-delegation")
        self.assertEqual(log["orchestration"]["planned_workers"]["count"], 0)
        self.assertEqual(len(log["orchestration"]["spawn_plan"]["workers"]), 2)
        self.assertEqual(log["skill_specific"]["data"]["selected_packets"], ["mapping_packet", "changes_packet", "risks_packet"])
        self.assertNotIn("packet_count", log["skill_specific"]["data"])
        self.assertNotIn("packet_tokens", log["skill_specific"]["data"])
        self.assertNotIn("savings_tokens", log["skill_specific"]["data"])
        self.assertFalse(log["skill_specific"]["data"]["common_path_sufficient"])
        self.assertTrue(log["orchestration"]["raw_reread_required"])
        self.assertEqual(log["packet_sizing"]["packet_count"], 6)
        self.assertEqual(log["packet_sizing"]["packet_size_bytes"], 4096)
        self.assertEqual(log["efficiency"]["packet_compaction"]["local_only_tokens"], 1200)
        self.assertEqual(log["efficiency"]["packet_compaction"]["savings_tokens"], 800)
        self.assertEqual(log["latency"]["packet_builder_seconds"], 1.5)

    def test_build_phase_preserves_legacy_recommended_worker_count_without_worker_list(self) -> None:
        log = {
            "skill": {"name": "weekly-update"},
            "measurement": {},
            "baseline": {},
            "orchestration": {},
            "skill_specific": {"data": {}},
        }
        result = {
            "review_mode": "targeted-delegation",
            "recommended_worker_count": 2,
            "recommended_workers": [],
            "packet_sizing": {
                "packet_count": 2,
                "packet_size_bytes": 512,
                "packet_size_breakdown": {
                    "orchestrator.json": 128,
                    "mapping_packet.json": 384,
                },
            },
        }

        eval_log.apply_phase_update(log, "build", result, None)

        self.assertEqual(log["orchestration"]["planned_workers"]["count"], 0)
        self.assertEqual(log["orchestration"]["spawn_plan"]["workers"], [])
        self.assertEqual(log["orchestration"]["planned_workers"]["workers"], [])
        self.assertEqual(log["orchestration"]["planned_workers"]["roles"], [])

    def test_execution_fidelity_scores_local_only_empty_run_as_one(self) -> None:
        score = eval_log.common.execution_fidelity_score(
            {
                "orchestration": {
                    "planned_workers": {"count": 0, "roles": [], "workers": []},
                    "actual_workers": {
                        "summary": {
                            "materialized_count": 0,
                            "executed_count": 0,
                            "completed_count": 0,
                            "failed_count": 0,
                            "cancelled_count": 0,
                            "planned_not_run_count": 0,
                            "unplanned_count": 0,
                            "capture_complete": True,
                            "capture_incomplete_reason": None,
                        },
                        "workers": [],
                    },
                }
            }
        )

        self.assertEqual(score, 1.0)

    def test_finalize_treats_unknown_planned_worker_id_as_unplanned_execution(self) -> None:
        log = {
            "skill": {"name": "weekly-update"},
            "measurement": {},
            "baseline": {},
            "orchestration": {
                "review_mode": "targeted-delegation",
                "planned_workers": {
                    "count": 1,
                    "roles": ["repo_mapper"],
                    "workers": [
                        {
                            "worker_id": "planned:mapping:repo_mapper:abc123",
                            "name": "mapping-repo-mapper",
                            "agent_type": "repo_mapper",
                            "model": "gpt-5.4-mini",
                            "reasoning_effort": "medium",
                            "packets": ["mapping_packet.json"],
                            "responsibility": "Map repo surfaces",
                        }
                    ],
                },
            },
            "quality": {},
            "safety": {},
            "skill_specific": {"data": {}},
        }

        eval_log.finalize_log(
            log,
            {
                "orchestration": {
                    "actual_workers": {
                        "summary": {"capture_complete": True},
                        "workers": [
                            {
                                "planned_worker_id": "planned:missing:repo_mapper:deadbeef",
                                "agent_type": "repo_mapper",
                                "model": "gpt-5.4-mini",
                                "reasoning_effort": "medium",
                                "status": "completed",
                            }
                        ],
                    }
                }
            },
        )

        actual_workers = log["orchestration"]["actual_workers"]
        self.assertEqual(actual_workers["summary"]["executed_count"], 1)
        self.assertEqual(actual_workers["summary"]["planned_not_run_count"], 1)
        self.assertEqual(actual_workers["summary"]["unplanned_row_count"], 1)
        self.assertEqual(actual_workers["workers"][0]["planned_worker_id"], None)
        self.assertEqual(actual_workers["workers"][0]["status"], "unplanned_completed")
        self.assertEqual(actual_workers["workers"][1]["status"], "planned_not_run")
        self.assertIn(
            "Unknown planned_worker_id in actual worker payload; recorded as unplanned execution.",
            log["notes"],
        )

    def test_legacy_optional_worker_entries_preserve_optional_execution_semantics(self) -> None:
        spawn_plan = eval_log.common.build_spawn_plan(
            review_mode="targeted-delegation",
            optional_workers=["repo_mapper"],
            common_path_sufficient=False,
        )

        self.assertEqual(len(spawn_plan["workers"]), 1)
        worker = spawn_plan["workers"][0]
        self.assertEqual(worker["execution_class"], "optional")
        self.assertEqual(worker["stage"], "initial_parallel")
        self.assertFalse(worker["default_spawn"])
        self.assertFalse(worker["blocking"])

    def test_spawn_plan_normalization_disables_default_spawn_when_blocked(self) -> None:
        worker = self._planned_worker()

        spawn_plan, warnings = eval_log.common.normalize_spawn_plan_payload(
            {
                "default_spawn_enabled": True,
                "default_spawn_blockers": ["common_path_sufficient=false"],
                "workers": [worker],
            },
            review_mode="targeted-delegation",
            common_path_sufficient=False,
        )

        self.assertFalse(spawn_plan["default_spawn_enabled"])
        self.assertEqual(
            spawn_plan["default_spawn_blockers"],
            ["common_path_sufficient=false"],
        )
        self.assertEqual(
            eval_log.common.default_planned_workers_from_spawn_plan(spawn_plan),
            {"count": 0, "roles": [], "workers": []},
        )
        self.assertIn(
            "default_spawn_enabled was disabled because default_spawn_blockers are present.",
            warnings,
        )

    def test_finalize_migrates_legacy_planned_workers_when_spawn_plan_is_empty(self) -> None:
        worker = self._planned_worker()
        log = {
            "skill": {"name": "weekly-update"},
            "measurement": {},
            "baseline": {},
            "orchestration": {
                "review_mode": "targeted-delegation",
                "spawn_plan": eval_log.common.empty_spawn_plan(),
            },
            "quality": {},
            "safety": {},
            "skill_specific": {"data": {}},
        }

        eval_log.finalize_log(
            log,
            {
                "orchestration": {
                    "planned_workers": {
                        "count": 1,
                        "roles": ["repo_mapper"],
                        "workers": [worker],
                    },
                    "actual_workers": {
                        "summary": {"capture_complete": True},
                        "workers": [
                            {
                                "planned_worker_id": worker["worker_id"],
                                "agent_type": "repo_mapper",
                                "model": "gpt-5.4-mini",
                                "reasoning_effort": "medium",
                                "status": "completed",
                            }
                        ],
                    },
                }
            },
        )

        self.assertEqual(len(log["orchestration"]["spawn_plan"]["workers"]), 1)
        self.assertEqual(log["orchestration"]["planned_workers"]["count"], 1)
        actual_workers = log["orchestration"]["actual_workers"]
        self.assertEqual(actual_workers["summary"]["planned_row_count"], 1)
        self.assertEqual(actual_workers["summary"]["planned_not_run_count"], 0)
        self.assertEqual(actual_workers["workers"][0]["row_kind"], "planned")
        self.assertEqual(actual_workers["workers"][0]["status"], "completed")

    def test_finalize_preserves_started_status_when_capture_is_incomplete(self) -> None:
        worker = self._planned_worker()
        log = {
            "skill": {"name": "weekly-update"},
            "measurement": {},
            "baseline": {},
            "orchestration": {
                "orchestrator_fingerprint": "sha256:expected",
                "planned_workers": {
                    "count": 1,
                    "roles": ["repo_mapper"],
                    "workers": [worker],
                },
            },
            "quality": {},
            "safety": {},
            "skill_specific": {"data": {}},
        }

        eval_log.finalize_log(
            log,
            {
                "orchestration": {
                    "actual_workers": {
                        "summary": {
                            "capture_complete": False,
                            "capture_incomplete_reason": "worker telemetry truncated",
                        },
                        "workers": [
                            {
                                "planned_worker_id": worker["worker_id"],
                                "agent_type": "repo_mapper",
                                "model": "gpt-5.4-mini",
                                "reasoning_effort": "medium",
                                "status": "started",
                                "orchestrator_fingerprint": "sha256:expected",
                            }
                        ],
                    }
                }
            },
        )

        actual_workers = log["orchestration"]["actual_workers"]
        self.assertFalse(actual_workers["summary"]["capture_complete"])
        self.assertEqual(actual_workers["summary"]["executed_count"], 0)
        self.assertEqual(actual_workers["workers"][0]["status"], "started")

    def test_finalize_rejects_started_status_when_capture_is_marked_complete(self) -> None:
        worker = self._planned_worker()
        log = {
            "skill": {"name": "weekly-update"},
            "measurement": {},
            "baseline": {},
            "orchestration": {
                "orchestrator_fingerprint": "sha256:expected",
                "planned_workers": {
                    "count": 1,
                    "roles": ["repo_mapper"],
                    "workers": [worker],
                },
            },
            "quality": {},
            "safety": {},
            "skill_specific": {"data": {}},
        }

        with self.assertRaisesRegex(
            ValueError,
            "capture_complete=true cannot include nonterminal actual worker statuses",
        ):
            eval_log.finalize_log(
                log,
                {
                    "orchestration": {
                        "actual_workers": {
                            "summary": {"capture_complete": True},
                            "workers": [
                                {
                                    "planned_worker_id": worker["worker_id"],
                                    "agent_type": "repo_mapper",
                                    "model": "gpt-5.4-mini",
                                    "reasoning_effort": "medium",
                                    "status": "started",
                                    "orchestrator_fingerprint": "sha256:expected",
                                }
                            ],
                        }
                    }
                },
            )

    def test_normalize_spawn_activation_materializes_rows_from_id_lists(self) -> None:
        required_worker = self._planned_worker()
        optional_worker = {
            **required_worker,
            "name": "qa-repo-mapper",
            "packets": ["qa_packet.json"],
            "worker_id": eval_log.common.planned_worker_id(
                {
                    "name": "qa-repo-mapper",
                    "agent_type": "repo_mapper",
                    "model": "gpt-5.4-mini",
                    "reasoning_effort": "medium",
                    "packets": ["qa_packet.json"],
                    "responsibility": "QA repo surfaces",
                }
            ),
        }
        skipped_worker = {
            **required_worker,
            "name": "risk-repo-mapper",
            "packets": ["risk_packet.json"],
            "worker_id": eval_log.common.planned_worker_id(
                {
                    "name": "risk-repo-mapper",
                    "agent_type": "repo_mapper",
                    "model": "gpt-5.4-mini",
                    "reasoning_effort": "medium",
                    "packets": ["risk_packet.json"],
                    "responsibility": "Review risk surfaces",
                }
            ),
        }
        log = {
            "orchestration": {
                "spawn_plan": eval_log.common.build_spawn_plan(
                    review_mode="targeted-delegation",
                    required_workers=[required_worker, optional_worker, skipped_worker],
                    common_path_sufficient=False,
                ),
                "spawn_activation": {
                    "activated_worker_ids": [optional_worker["worker_id"]],
                    "skipped_worker_ids": [skipped_worker["worker_id"]],
                    "local_fallback_worker_ids": [required_worker["worker_id"]],
                    "workers": [],
                },
            }
        }

        eval_log.common.normalize_spawn_activation(log)

        activation = log["orchestration"]["spawn_activation"]
        rows = {
            row["worker_id"]: row["resolved_as"]
            for row in activation["workers"]
        }
        self.assertEqual(rows[required_worker["worker_id"]], "local_fallback")
        self.assertEqual(rows[optional_worker["worker_id"]], "spawned")
        self.assertEqual(rows[skipped_worker["worker_id"]], "not_activated")
        self.assertEqual(activation["summary"]["attempted_count"], 2)
        self.assertEqual(activation["summary"]["succeeded_count"], 1)
        self.assertEqual(activation["summary"]["failed_count"], 1)
        self.assertEqual(activation["summary"]["local_fallback_count"], 1)
        self.assertEqual(activation["summary"]["not_activated_count"], 1)

    def test_normalize_spawn_activation_preserves_distinct_actual_worker_id(self) -> None:
        worker = self._planned_worker()
        log = {
            "orchestration": {
                "spawn_plan": eval_log.common.build_spawn_plan(
                    review_mode="targeted-delegation",
                    required_workers=[worker],
                    common_path_sufficient=True,
                ),
                "spawn_activation": {
                    "workers": [
                        {
                            "worker_id": "actual:spawn:repo_mapper:run-2",
                            "planned_worker_id": worker["worker_id"],
                            "resolved_as": "spawned",
                            "spawn_attempted": True,
                            "spawn_succeeded": True,
                        }
                    ],
                },
            }
        }

        eval_log.common.normalize_spawn_activation(log)

        activation_row = log["orchestration"]["spawn_activation"]["workers"][0]
        self.assertEqual(activation_row["worker_id"], "actual:spawn:repo_mapper:run-2")
        self.assertEqual(activation_row["planned_worker_id"], worker["worker_id"])
        self.assertEqual(activation_row["resolved_as"], "spawned")

    def test_normalize_spawn_activation_infers_attempt_from_resolved_row(self) -> None:
        worker = self._planned_worker()
        log = {
            "orchestration": {
                "spawn_plan": eval_log.common.build_spawn_plan(
                    review_mode="targeted-delegation",
                    required_workers=[worker],
                    common_path_sufficient=True,
                ),
                "spawn_activation": {
                    "workers": [
                        {
                            "planned_worker_id": worker["worker_id"],
                            "resolved_as": "spawned",
                        }
                    ],
                },
            }
        }

        eval_log.common.normalize_spawn_activation(log)

        activation = log["orchestration"]["spawn_activation"]
        activation_row = activation["workers"][0]
        self.assertTrue(activation_row["spawn_attempted"])
        self.assertEqual(activation_row["attempt_count"], 1)
        self.assertEqual(activation["summary"]["attempted_count"], 1)
        self.assertEqual(activation["summary"]["succeeded_count"], 1)

    def test_finalize_marks_list_only_local_fallback_as_spawn_failed(self) -> None:
        worker = self._planned_worker()
        log = {
            "skill": {"name": "weekly-update"},
            "measurement": {},
            "baseline": {},
            "orchestration": {
                "review_mode": "targeted-delegation",
                "spawn_plan": eval_log.common.build_spawn_plan(
                    review_mode="targeted-delegation",
                    required_workers=[worker],
                    common_path_sufficient=False,
                ),
            },
            "quality": {},
            "safety": {},
            "skill_specific": {"data": {}},
        }

        eval_log.finalize_log(
            log,
            {
                "orchestration": {
                    "spawn_activation": {
                        "local_fallback_worker_ids": [worker["worker_id"]],
                    }
                }
            },
        )

        activation = log["orchestration"]["spawn_activation"]
        actual_workers = log["orchestration"]["actual_workers"]
        self.assertEqual(activation["summary"]["attempted_count"], 1)
        self.assertEqual(activation["summary"]["failed_count"], 1)
        self.assertEqual(activation["workers"][0]["resolved_as"], "local_fallback")
        self.assertEqual(log["orchestration"]["planned_workers"]["count"], 1)
        self.assertEqual(actual_workers["summary"]["spawn_failed_count"], 1)
        self.assertEqual(actual_workers["summary"]["planned_not_run_count"], 0)
        self.assertEqual(actual_workers["workers"][0]["row_kind"], "planned")
        self.assertEqual(actual_workers["workers"][0]["status"], "spawn_failed")

    def test_finalize_marks_list_only_spawned_worker_as_started_when_capture_incomplete(self) -> None:
        worker = self._planned_worker()
        log = {
            "skill": {"name": "weekly-update"},
            "measurement": {},
            "baseline": {},
            "orchestration": {
                "review_mode": "targeted-delegation",
                "spawn_plan": eval_log.common.build_spawn_plan(
                    review_mode="targeted-delegation",
                    required_workers=[worker],
                    common_path_sufficient=True,
                ),
            },
            "quality": {},
            "safety": {},
            "skill_specific": {"data": {}},
        }

        eval_log.finalize_log(
            log,
            {
                "orchestration": {
                    "spawn_activation": {
                        "activated_worker_ids": [worker["worker_id"]],
                    },
                    "actual_workers": {
                        "summary": {
                            "capture_complete": False,
                            "capture_incomplete_reason": "worker telemetry pending",
                        },
                        "workers": [],
                    },
                }
            },
        )

        activation = log["orchestration"]["spawn_activation"]
        actual_workers = log["orchestration"]["actual_workers"]
        self.assertEqual(activation["summary"]["attempted_count"], 1)
        self.assertEqual(activation["summary"]["succeeded_count"], 1)
        self.assertEqual(activation["workers"][0]["resolved_as"], "spawned")
        self.assertFalse(actual_workers["summary"]["capture_complete"])
        self.assertEqual(actual_workers["summary"]["planned_not_run_count"], 0)
        self.assertEqual(actual_workers["workers"][0]["row_kind"], "planned")
        self.assertEqual(actual_workers["workers"][0]["status"], "started")

    def test_finalize_keeps_row_only_not_activated_as_planned_not_run(self) -> None:
        worker = self._planned_worker()
        log = {
            "skill": {"name": "weekly-update"},
            "measurement": {},
            "baseline": {},
            "orchestration": {
                "review_mode": "targeted-delegation",
                "spawn_plan": eval_log.common.build_spawn_plan(
                    review_mode="targeted-delegation",
                    required_workers=[worker],
                    common_path_sufficient=False,
                ),
            },
            "quality": {},
            "safety": {},
            "skill_specific": {"data": {}},
        }

        eval_log.finalize_log(
            log,
            {
                "orchestration": {
                    "spawn_activation": {
                        "workers": [
                            {
                                "planned_worker_id": worker["worker_id"],
                                "resolved_as": "not_activated",
                            }
                        ],
                    },
                }
            },
        )

        activation = log["orchestration"]["spawn_activation"]
        actual_workers = log["orchestration"]["actual_workers"]
        self.assertEqual(log["orchestration"]["planned_workers"]["count"], 1)
        self.assertEqual(activation["summary"]["attempted_count"], 0)
        self.assertEqual(activation["summary"]["not_activated_count"], 1)
        self.assertEqual(actual_workers["summary"]["planned_not_run_count"], 1)
        self.assertEqual(actual_workers["workers"][0]["row_kind"], "planned")
        self.assertEqual(actual_workers["workers"][0]["status"], "planned_not_run")

    def test_finalize_counts_default_spawn_worker_as_not_activated_without_activation_payload(
        self,
    ) -> None:
        worker = self._planned_worker()
        log = {
            "skill": {"name": "weekly-update"},
            "measurement": {},
            "baseline": {},
            "orchestration": {
                "review_mode": "targeted-delegation",
                "spawn_plan": eval_log.common.build_spawn_plan(
                    review_mode="targeted-delegation",
                    required_workers=[worker],
                    common_path_sufficient=True,
                ),
            },
            "quality": {},
            "safety": {},
            "skill_specific": {"data": {}},
        }

        eval_log.finalize_log(log, {"orchestration": {}})

        activation = log["orchestration"]["spawn_activation"]
        actual_workers = log["orchestration"]["actual_workers"]
        self.assertEqual(log["orchestration"]["planned_workers"]["count"], 1)
        self.assertEqual(activation["summary"]["not_activated_count"], 1)
        self.assertEqual(activation["workers"][0]["resolved_as"], "not_activated")
        self.assertEqual(actual_workers["summary"]["planned_not_run_count"], 1)
        self.assertEqual(actual_workers["workers"][0]["status"], "planned_not_run")

    def test_finalize_ignores_optional_worker_without_activation_payload(self) -> None:
        spawn_plan = eval_log.common.build_spawn_plan(
            review_mode="targeted-delegation",
            optional_workers=["repo_mapper"],
            common_path_sufficient=True,
        )
        log = {
            "skill": {"name": "weekly-update"},
            "measurement": {},
            "baseline": {},
            "orchestration": {
                "review_mode": "targeted-delegation",
                "spawn_plan": spawn_plan,
            },
            "quality": {},
            "safety": {},
            "skill_specific": {"data": {}},
        }

        eval_log.finalize_log(log, {"orchestration": {}})

        activation = log["orchestration"]["spawn_activation"]
        actual_workers = log["orchestration"]["actual_workers"]
        self.assertEqual(log["orchestration"]["planned_workers"]["count"], 0)
        self.assertEqual(activation["summary"]["not_activated_count"], 0)
        self.assertEqual(activation["workers"], [])
        self.assertEqual(actual_workers["summary"]["planned_not_run_count"], 0)
        self.assertEqual(actual_workers["workers"], [])

    def test_finalize_ignores_blocked_default_spawn_without_activation_payload(self) -> None:
        worker = self._planned_worker()
        log = {
            "skill": {"name": "weekly-update"},
            "measurement": {},
            "baseline": {},
            "orchestration": {
                "review_mode": "targeted-delegation",
                "spawn_plan": eval_log.common.build_spawn_plan(
                    review_mode="targeted-delegation",
                    required_workers=[worker],
                    common_path_sufficient=False,
                ),
            },
            "quality": {},
            "safety": {},
            "skill_specific": {"data": {}},
        }

        eval_log.finalize_log(log, {"orchestration": {}})

        activation = log["orchestration"]["spawn_activation"]
        actual_workers = log["orchestration"]["actual_workers"]
        self.assertEqual(log["orchestration"]["planned_workers"]["count"], 0)
        self.assertEqual(activation["summary"]["not_activated_count"], 0)
        self.assertEqual(activation["workers"], [])
        self.assertEqual(actual_workers["summary"]["planned_not_run_count"], 0)
        self.assertEqual(actual_workers["workers"], [])

    def test_finalize_does_not_fallback_match_unknown_planned_worker_id(
        self,
    ) -> None:
        worker = self._planned_worker()
        log = {
            "skill": {"name": "weekly-update"},
            "measurement": {},
            "baseline": {},
            "orchestration": {
                "review_mode": "targeted-delegation",
                "spawn_plan": eval_log.common.build_spawn_plan(
                    review_mode="targeted-delegation",
                    required_workers=[worker],
                    common_path_sufficient=False,
                ),
            },
            "quality": {},
            "safety": {},
            "skill_specific": {"data": {}},
        }

        eval_log.finalize_log(
            log,
            {
                "orchestration": {
                    "actual_workers": {
                        "summary": {"capture_complete": True},
                        "workers": [
                            {
                                **worker,
                                "planned_worker_id": "planned:stale-or-mistyped",
                                "status": "completed",
                            }
                        ],
                    }
                }
            },
        )

        actual_workers = log["orchestration"]["actual_workers"]
        self.assertEqual(log["orchestration"]["planned_workers"]["count"], 0)
        self.assertEqual(actual_workers["summary"]["unplanned_row_count"], 1)
        self.assertEqual(actual_workers["summary"]["planned_not_run_count"], 0)
        self.assertEqual(actual_workers["workers"][0]["row_kind"], "unplanned")
        self.assertIsNone(actual_workers["workers"][0]["planned_worker_id"])
        self.assertEqual(actual_workers["workers"][0]["status"], "unplanned_completed")

    def test_finalize_keeps_drifted_worker_row_unplanned_even_when_identity_matches(self) -> None:
        log = {
            "skill": {"name": "weekly-update"},
            "measurement": {},
            "baseline": {},
            "orchestration": {
                "orchestrator_fingerprint": "sha256:expected",
                "planned_workers": {
                    "count": 1,
                    "roles": ["repo_mapper"],
                    "workers": [
                        {
                            "worker_id": "planned:mapping:repo_mapper:abc123",
                            "name": "mapping-repo-mapper",
                            "agent_type": "repo_mapper",
                            "model": "gpt-5.4-mini",
                            "reasoning_effort": "medium",
                            "packets": ["mapping_packet.json"],
                            "responsibility": "Map repo surfaces",
                        }
                    ],
                },
            },
            "quality": {},
            "safety": {},
            "skill_specific": {"data": {}},
        }

        eval_log.finalize_log(
            log,
            {
                "orchestration": {
                    "actual_workers": {
                        "summary": {"capture_complete": True},
                        "workers": [
                            {
                                "name": "mapping-repo-mapper",
                                "agent_type": "repo_mapper",
                                "model": "gpt-5.4-mini",
                                "reasoning_effort": "medium",
                                "packets": ["mapping_packet.json"],
                                "status": "completed",
                                "orchestrator_fingerprint": "sha256:stale",
                            }
                        ],
                    }
                }
            },
        )

        actual_workers = log["orchestration"]["actual_workers"]
        self.assertEqual(actual_workers["summary"]["unplanned_row_count"], 1)
        self.assertEqual(actual_workers["summary"]["planned_not_run_count"], 1)
        self.assertEqual(actual_workers["workers"][0]["row_kind"], "unplanned")
        self.assertEqual(actual_workers["workers"][0]["status"], "unplanned_completed")
        self.assertEqual(actual_workers["workers"][1]["status"], "planned_not_run")
        self.assertEqual(
            log["orchestration"]["spawn_activation"]["drift_events"][0]["reason"],
            "orchestrator_fingerprint_mismatch",
        )

    def test_finalize_does_not_synthesize_missing_orchestrator_fingerprint(self) -> None:
        worker = self._planned_worker()
        log = {
            "skill": {"name": "weekly-update"},
            "measurement": {},
            "baseline": {},
            "orchestration": {
                "review_mode": "targeted-delegation",
                "spawn_plan": eval_log.common.build_spawn_plan(
                    review_mode="targeted-delegation",
                    required_workers=[worker],
                    common_path_sufficient=True,
                ),
            },
            "quality": {},
            "safety": {},
            "skill_specific": {"data": {}},
        }

        eval_log.finalize_log(
            log,
            {
                "orchestration": {
                    "actual_workers": {
                        "summary": {"capture_complete": True},
                        "workers": [
                            {
                                "planned_worker_id": worker["worker_id"],
                                "agent_type": "repo_mapper",
                                "model": "gpt-5.4-mini",
                                "reasoning_effort": "medium",
                                "status": "completed",
                                "orchestrator_fingerprint": "sha256:runtime",
                            }
                        ],
                    }
                }
            },
        )

        self.assertNotIn("orchestrator_fingerprint", log["orchestration"])
        self.assertEqual(
            log["orchestration"]["spawn_activation"]["drift_events"],
            [],
        )
        self.assertEqual(
            log["orchestration"]["spawn_activation"]["summary"]["not_activated_count"],
            0,
        )
        actual_workers = log["orchestration"]["actual_workers"]
        self.assertEqual(actual_workers["summary"]["planned_row_count"], 1)
        self.assertEqual(actual_workers["summary"]["unplanned_row_count"], 0)
        self.assertEqual(actual_workers["workers"][0]["row_kind"], "planned")

    def test_validate_and_apply_merge_plan_and_marker_fields(self) -> None:
        log = {
            "skill": {"name": "weekly-update"},
            "measurement": {},
            "orchestration": {},
            "safety": {},
            "quality": {},
            "outputs": {},
            "skill_specific": {"data": {}},
        }

        eval_log.apply_phase_update(
            log,
            "validate",
            {
                "valid": True,
                "overall_confidence": "medium",
                "allow_marker_update": False,
                "stop_reasons": ["allow_marker_update=false"],
            },
            None,
        )
        eval_log.apply_phase_update(
            log,
            "apply",
            {
                "dry_run": True,
                "apply_succeeded": True,
                "overall_confidence": "medium",
                "allow_marker_update": False,
                "marker_update_attempted": False,
                "marker_update_written": False,
                "stop_reasons": ["allow_marker_update=false"],
            },
            None,
        )

        self.assertTrue(log["safety"]["validation_run"])
        self.assertEqual(log["skill_specific"]["data"]["plan_overall_confidence"], "medium")
        self.assertFalse(log["skill_specific"]["data"]["allow_marker_update"])
        self.assertFalse(log["skill_specific"]["data"]["marker_update_attempted"])
        self.assertFalse(log["skill_specific"]["data"]["marker_update_written"])
        self.assertEqual(log["quality"]["result_status"], "dry-run")


if __name__ == "__main__":
    unittest.main()
