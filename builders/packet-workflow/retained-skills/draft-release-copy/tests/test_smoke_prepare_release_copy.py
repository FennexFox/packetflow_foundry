from __future__ import annotations

import io
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


TEST_DIR = Path(__file__).resolve().parent
SCRIPT_DIR = TEST_DIR.parent / "scripts"
for candidate in (str(TEST_DIR), str(SCRIPT_DIR)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

import release_copy_plan_contract as contract  # noqa: E402
import smoke_prepare_release_copy as smoke  # noqa: E402


class SmokePrepareReleaseCopyTests(unittest.TestCase):
    def test_success_output_uses_reference_schema(self) -> None:
        with patch.object(sys, "argv", ["smoke_prepare_release_copy.py"]):
            buffer = io.StringIO()
            with patch("sys.stdout", buffer):
                self.assertEqual(smoke.main(), 0)

        payload = json.loads(buffer.getvalue())
        for key in contract.SMOKE_OUTPUT_FIELDS:
            self.assertIn(key, payload)
        self.assertEqual(payload["status"], "ok")
        self.assertIsNone(payload["reason"])
        self.assertEqual(payload["next_action"], "review_smoke_results")
        self.assertGreater(payload["estimated_delegation_savings"], 0)


if __name__ == "__main__":
    unittest.main()
