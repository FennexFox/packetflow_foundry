from __future__ import annotations

import io
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
script_dir = str(SCRIPT_DIR)
while script_dir in sys.path:
    sys.path.remove(script_dir)
sys.path.insert(0, script_dir)

sys.modules.pop("smoke_gh_create_pr", None)
import smoke_gh_create_pr as smoke  # noqa: E402


class SmokeGhCreatePrTests(unittest.TestCase):
    def test_smoke_reports_packet_sizing_path(self) -> None:
        buffer = io.StringIO()
        with patch("sys.stdout", buffer):
            exit_code = smoke.main()

        self.assertEqual(exit_code, 0)
        payload = json.loads(buffer.getvalue())
        self.assertIn("packet_sizing_path", payload)
        self.assertNotIn("packet_metrics_path", payload)
        self.assertTrue(payload["packet_sizing_path"].endswith("packet_sizing.json"))


if __name__ == "__main__":
    unittest.main()
