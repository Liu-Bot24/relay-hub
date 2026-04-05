from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

from relay_hub.host_support import WINDOWS, current_platform


SCRIPTS_ROOT = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

import agent_relay as agent_relay_script
import relay_agent_daemon as relay_agent_daemon_script


@unittest.skipUnless(current_platform() == WINDOWS, "Windows-specific backend tests")
class WindowsBackendValidationTests(unittest.TestCase):
    def test_agent_relay_rejects_direct_codex_command_backend(self) -> None:
        with self.assertRaisesRegex(SystemExit, "do not point --backend-command directly at `codex`"):
            agent_relay_script.validate_command_backend('["codex","exec","-"]')

    def test_daemon_rejects_direct_codex_command_backend(self) -> None:
        with self.assertRaisesRegex(SystemExit, "do not point --backend-command directly at `codex`"):
            relay_agent_daemon_script.validate_command_backend('["codex","exec","-"]')

    def test_daemon_run_command_backend_reports_spawn_failure(self) -> None:
        with mock.patch.object(relay_agent_daemon_script.subprocess, "run", side_effect=PermissionError("Access is denied")):
            body, error = relay_agent_daemon_script.run_command_backend('["python","-V"]', {}, "prompt")
        self.assertIsNone(body)
        self.assertIn("failed to start", error or "")

    def test_daemon_run_codex_exec_backend_reports_spawn_failure(self) -> None:
        with mock.patch.object(relay_agent_daemon_script.subprocess, "run", side_effect=PermissionError("Access is denied")):
            body, error = relay_agent_daemon_script.run_codex_exec_backend(None, "prompt")
        self.assertIsNone(body)
        self.assertIn("could not be started", error or "")


if __name__ == "__main__":
    unittest.main()
