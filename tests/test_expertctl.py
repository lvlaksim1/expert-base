from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from installer.expertctl import copy_overlay


class ExpertCtlTests(unittest.TestCase):
    def test_overlay_requires_service_agent(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(RuntimeError):
                copy_overlay(Path(td), "test-expert", "Test", False)

    def test_overlay_preserves_service_agent_and_creates_expert_identity(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            contract = root / ".context" / "service-agent" / "CONTRACT.md"
            contract.parent.mkdir(parents=True)
            contract.write_text("service-agent-contract\n", encoding="utf-8")
            entrypoint = root / ".context" / "ENTRYPOINT.md"
            entrypoint.write_text("# Base entrypoint\n", encoding="utf-8")

            copy_overlay(root, "ios-expert", "iOS", False)

            self.assertEqual(contract.read_text(encoding="utf-8"), "service-agent-contract\n")
            identity = json.loads((root / ".context" / "expert" / "identity.json").read_text(encoding="utf-8"))
            self.assertEqual(identity["expert_id"], "ios-expert")
            self.assertEqual(identity["specialization"], "iOS")
            self.assertIn(".context/expert/ENTRYPOINT.md", entrypoint.read_text(encoding="utf-8"))
            profile = (root / ".context" / "expert" / "PROFILE.md").read_text(encoding="utf-8")
            self.assertIn("ios-expert", profile)
            self.assertIn("iOS", profile)


if __name__ == "__main__":
    unittest.main()
