from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path


class RewordHeadCommitSmokeTests(unittest.TestCase):
    def test_smoke_helper_prints_stable_summary_shape(self) -> None:
        script_path = Path(__file__).resolve().parents[1] / "scripts" / "smoke_reword_head_commit.py"
        result = subprocess.run(
            [sys.executable, "-B", str(script_path)],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)
        payload = json.loads(result.stdout)
        self.assertEqual(
            set(payload.keys()),
            {"status", "force_push_likely", "new_head", "evaluation_log_path"},
        )
        self.assertEqual(payload["status"], "ok")
        self.assertFalse(payload["force_push_likely"])
        self.assertIsInstance(payload["new_head"], str)
        self.assertTrue(Path(payload["evaluation_log_path"]).is_file())


if __name__ == "__main__":
    unittest.main()
