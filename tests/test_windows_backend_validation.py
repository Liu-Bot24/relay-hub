from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import relay_hub.openclaw_cli as openclaw_cli
from relay_hub.host_support import WINDOWS, current_platform


SCRIPTS_ROOT = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

import agent_relay as agent_relay_script
import relay_agent_daemon as relay_agent_daemon_script
import relay_openclaw_bridge as relay_openclaw_bridge_script


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

    def test_openclaw_cli_uses_cmd_wrapper_for_batch_launcher(self) -> None:
        def fake_which(name: str) -> str | None:
            mapping = {
                "openclaw": r"C:\Tools\openclaw.cmd",
                "cmd.exe": r"C:\Windows\System32\cmd.exe",
            }
            return mapping.get(name)

        with mock.patch.object(openclaw_cli.shutil, "which", side_effect=fake_which):
            prefix = openclaw_cli.openclaw_command_prefix()
        self.assertEqual(prefix[0].lower(), r"c:\windows\system32\cmd.exe")
        self.assertEqual(prefix[1:], ["/d", "/c", r"C:\Tools\openclaw.cmd"])

    def test_bridge_send_message_uses_openclaw_wrapper(self) -> None:
        completed = relay_openclaw_bridge_script.subprocess.CompletedProcess(
            args=["cmd.exe"],
            returncode=0,
            stdout="",
            stderr="",
        )
        with mock.patch.object(relay_openclaw_bridge_script, "run_openclaw_command", return_value=completed) as runner:
            relay_openclaw_bridge_script.send_message("feishu", "chat:oc_xxx", "relay-hub test", account_id="default")
        runner.assert_called_once_with(
            [
                "message",
                "send",
                "--channel",
                "feishu",
                "--target",
                "chat:oc_xxx",
                "--message",
                "relay-hub test",
                "--account",
                "default",
            ],
            capture_output=True,
            text=True,
        )

    def test_bridge_repairs_feishu_default_target_from_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "relay_hub_openclaw.json"
            config_path.write_text(
                """
{
  "delivery": {
    "channels": {
      "feishu": {
        "target": "default",
        "accountId": "default"
      }
    }
  }
}
""".strip()
                + "\n",
                encoding="utf-8",
            )
            config = relay_openclaw_bridge_script.load_config(config_path)
            with mock.patch.object(
                relay_openclaw_bridge_script,
                "run_openclaw_json",
                return_value=[{"kind": "user", "id": "ou_real_open_id"}],
            ):
                destinations = relay_openclaw_bridge_script.configured_delivery_channels(config)
            self.assertEqual(destinations, [("feishu", "user:ou_real_open_id", "default")])
            persisted = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertEqual(persisted["delivery"]["channels"]["feishu"]["target"], "user:ou_real_open_id")


if __name__ == "__main__":
    unittest.main()
