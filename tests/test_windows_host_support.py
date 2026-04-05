from __future__ import annotations

import os
import shutil
import unittest
import uuid
from pathlib import Path
from unittest import mock

import install
from relay_hub.host_support import WINDOWS, current_platform, default_install_root
from relay_hub.store import RelayHub


@unittest.skipUnless(current_platform() == WINDOWS, "Windows-specific host tests")
class WindowsHostSupportTests(unittest.TestCase):
    def make_temp_dir(self) -> Path:
        tests_root = Path(__file__).resolve().parents[1] / ".tmp-tests"
        tests_root.mkdir(exist_ok=True)
        temp_dir = tests_root / f"relay-hub-{uuid.uuid4().hex}"
        temp_dir.mkdir()
        return temp_dir

    def read_repo_text(self, relative_path: str) -> str:
        return (Path(__file__).resolve().parents[1] / relative_path).read_text(encoding="utf-8")

    def test_default_install_root_prefers_localappdata(self) -> None:
        with mock.patch.dict(os.environ, {"LOCALAPPDATA": r"C:\RelayHubLocal"}, clear=False):
            self.assertEqual(default_install_root(), Path(r"C:\RelayHubLocal\RelayHub"))

    def test_store_init_layout_works_without_fcntl(self) -> None:
        tests_root = Path(__file__).resolve().parents[1] / ".tmp-tests"
        temp_dir = self.make_temp_dir()
        try:
            hub = RelayHub(temp_dir / "runtime")
            payload = hub.init_layout()
            self.assertEqual(payload["relay_root"], str((temp_dir / "runtime").resolve()))
            self.assertTrue((temp_dir / "runtime" / "config.json").exists())
            self.assertTrue((temp_dir / "runtime" / "routes.json").exists())
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
            if tests_root.exists() and not any(tests_root.iterdir()):
                tests_root.rmdir()

    def test_windows_web_launcher_quotes_paths_with_spaces(self) -> None:
        app_root = Path(r"D:\path with space\relay-hub\app")
        runtime_root = Path(r"D:\path with space\relay-hub\runtime")
        logs_dir = runtime_root / "logs"
        script = install.build_windows_web_launcher(app_root, runtime_root, logs_dir, "0.0.0.0", 4517)
        self.assertIn('"D:\\path with space\\relay-hub\\app\\scripts\\relay_web.py"', script)
        self.assertIn('--root "D:\\path with space\\relay-hub\\runtime"', script)
        self.assertIn("Start-Process", script)

    def test_generated_openclaw_skill_uses_windows_python_command_and_quotes_path(self) -> None:
        script_path = Path(r"D:\path with space\relay-hub\app\scripts\relay_openclaw_bridge.py")
        text = install.build_skill_text(script_path)
        self.assertIn('`py -3 "D:\\path with space\\relay-hub\\app\\scripts\\relay_openclaw_bridge.py" ...`', text)
        self.assertIn('py -3 "D:\\path with space\\relay-hub\\app\\scripts\\relay_openclaw_bridge.py" pump-deliveries', text)

    def test_generated_codex_skill_uses_windows_python_command_and_quotes_path(self) -> None:
        app_root = Path(r"D:\path with space\relay-hub\app")
        text = install.build_codex_skill_text(app_root)
        self.assertIn('`py -3 "D:\\path with space\\relay-hub\\app\\scripts\\agent_relay.py" ...`', text)
        self.assertIn('py -3 "D:\\path with space\\relay-hub\\app\\scripts\\agent_relay.py" --agent codex enable-relay --project-root "<project_root>" --start-pickup', text)

    def test_cli_help_hides_launchd_surface(self) -> None:
        parser = install.build_parser()
        root_help = parser.format_help()
        subparsers = next(action for action in parser._actions if action.dest == "command")
        install_host_help = subparsers.choices["install-host"].format_help()
        uninstall_service_help = subparsers.choices["uninstall-service"].format_help()

        for text in (root_help, install_host_help, uninstall_service_help):
            self.assertNotIn("install-launchd", text)
            self.assertNotIn("uninstall-launchd", text)
            self.assertNotIn("--launchagents-dir", text)
            self.assertNotIn("launchd", text)

    def test_windows_only_install_surface_docs_hide_posix_and_direct_codex_backend(self) -> None:
        banned_tokens = {
            "README.md": ["macOS", "launchd", "LaunchAgents", "python3"],
            "docs/AI_INSTALL_PROMPT.md": ["~/relay-hub", "/tmp", "/private/tmp", "/var/folders", "python3"],
            "docs/INSTALL_PLAYBOOK.md": ["~/relay-hub", "/path/to/relay-hub", "python3"],
            "docs/COMPATIBILITY.md": ["macOS", "launchd", "LaunchAgents", "python3"],
            "docs/HOST_EXAMPLES/codex.AGENTS.example.md": ['["codex","exec"', "python3", "launchd", "macOS"],
            "docs/HOST_EXAMPLES/claude-code.CLAUDE.example.md": ["python3", "launchd", "macOS"],
            "docs/HOST_EXAMPLES/gemini-cli.GEMINI.example.md": ["python3", '["bash","-lc"', "mktemp", "launchd", "macOS"],
            "docs/HOST_EXAMPLES/cursor-cli.relay-hub.example.mdc": ["python3", '["bash","-lc"', "mktemp", "launchd", "macOS"],
        }
        for relative_path, tokens in banned_tokens.items():
            text = self.read_repo_text(relative_path)
            for token in tokens:
                self.assertNotIn(token, text, msg=f"{relative_path} still contains {token!r}")

    def test_explicit_openclaw_delivery_channels_skip_auto_discovery(self) -> None:
        temp_dir = self.make_temp_dir()
        openclaw_workspace = temp_dir / "openclaw"
        args = mock.Mock()
        args.delivery_channel = ["openclaw-weixin=test-user"]
        args.delivery_account = ["openclaw-weixin=test-account"]
        try:
            with mock.patch.object(install, "discover_openclaw_delivery_channels", side_effect=AssertionError("auto-discovery should not run")):
                channels, meta = install.resolved_delivery_channels(args, openclaw_workspace)
            self.assertEqual(
                channels,
                {"openclaw-weixin": {"target": "test-user", "accountId": "test-account"}},
            )
            self.assertEqual(meta["source"], "explicit_args")
            self.assertEqual(meta["auto_discovered_channels"], {})
            self.assertEqual(meta["unresolved_channels"], [])
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_doctor_reports_windows_python_launcher(self) -> None:
        temp_dir = self.make_temp_dir()
        runtime_root = temp_dir / "runtime"
        openclaw_workspace = temp_dir / "openclaw"
        app_root = temp_dir / "app"
        codex_home = temp_dir / ".codex"
        args = mock.Mock()
        args.web_port = 4517
        args.web_base_url = "http://127.0.0.1:4517"
        args.delivery_channel = None
        args.delivery_account = None
        try:
            def which_side_effect(name: str) -> str | None:
                mapping = {
                    "py.exe": r"C:\Windows\py.exe",
                    "py": r"C:\Windows\py.exe",
                    "powershell.exe": r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
                    "powershell": r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
                }
                return mapping.get(name)

            with (
                mock.patch.object(install, "service_loaded", return_value=False),
                mock.patch.object(install, "windows_relay_web_running", return_value=False),
                mock.patch.object(install, "REPO_ROOT", temp_dir),
                mock.patch("install.shutil.which", side_effect=which_side_effect),
            ):
                status_payload = install.install_status(args, runtime_root, openclaw_workspace, app_root, codex_home)
                self.assertNotIn("launchagents_dir", status_payload)
                self.assertNotIn("web_plist_installed", status_payload)
                self.assertNotIn("legacy_agent_plists_installed", status_payload)
                self.assertNotIn("launchagents_dir", status_payload["service"])
                payload = install.install_doctor(args, runtime_root, openclaw_workspace, app_root, codex_home)
            python_check = next(check for check in payload["checks"] if check["name"] == "python")
            self.assertEqual(python_check["detail"], f"py -3 (C:\\Windows\\py.exe) -> {install.sys.executable}")
            self.assertFalse(any(check["name"] == "launchagents_dir_parent" for check in payload["checks"]))
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_install_windows_service_succeeds_and_reports_loaded(self) -> None:
        temp_dir = self.make_temp_dir()
        runtime_root = temp_dir / "runtime"
        app_root = temp_dir / "app"
        args = mock.Mock()
        args.web_host = "127.0.0.1"
        args.web_port = 4518
        args.load_services = True
        args.windows_startup_name = "Relay Hub Test"
        startup_entry = temp_dir / "startup.cmd"
        try:
            with (
                mock.patch.object(install, "stage_app_bundle", return_value={"installed": True}),
                mock.patch.object(install, "windows_startup_entry_path", return_value=startup_entry),
                mock.patch.object(install, "can_connect_local_web", side_effect=[False, False]),
                mock.patch.object(install, "start_windows_web_now", return_value=123),
                mock.patch.object(install, "wait_for_local_web", return_value=True),
                mock.patch.object(install, "windows_relay_web_running", return_value=True),
            ):
                payload = install.install_windows_service(args, runtime_root, app_root)
            self.assertTrue(payload["running"])
            self.assertTrue(payload["loaded"])
            self.assertTrue(startup_entry.exists())
            self.assertTrue(install.windows_web_launcher_path(runtime_root).exists())
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_install_windows_service_rolls_back_on_foreign_listener(self) -> None:
        temp_dir = self.make_temp_dir()
        runtime_root = temp_dir / "runtime"
        app_root = temp_dir / "app"
        args = mock.Mock()
        args.web_host = "127.0.0.1"
        args.web_port = 4517
        args.load_services = True
        args.windows_startup_name = "Relay Hub Test"
        startup_entry = temp_dir / "startup.cmd"
        launcher_path = install.windows_web_launcher_path(runtime_root)
        try:
            with (
                mock.patch.object(install, "stage_app_bundle", return_value={"installed": True}),
                mock.patch.object(install, "windows_startup_entry_path", return_value=startup_entry),
                mock.patch.object(install, "can_connect_local_web", return_value=True),
                mock.patch.object(install, "windows_relay_web_running", return_value=False),
            ):
                with self.assertRaisesRegex(RuntimeError, "port 4517 is already in use"):
                    install.install_windows_service(args, runtime_root, app_root)
            self.assertFalse(startup_entry.exists())
            self.assertFalse(launcher_path.exists())
            self.assertFalse(install.windows_web_pid_path(runtime_root).exists())
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_install_windows_service_rolls_back_started_process_after_failed_verification(self) -> None:
        temp_dir = self.make_temp_dir()
        runtime_root = temp_dir / "runtime"
        app_root = temp_dir / "app"
        args = mock.Mock()
        args.web_host = "127.0.0.1"
        args.web_port = 4519
        args.load_services = True
        args.windows_startup_name = "Relay Hub Test"
        startup_entry = temp_dir / "startup.cmd"
        launcher_path = install.windows_web_launcher_path(runtime_root)
        pid_path = install.windows_web_pid_path(runtime_root)

        def fake_start(*_args: object, **_kwargs: object) -> int:
            install.write_windows_web_pid_info(runtime_root, {"pid": 222, "port": 4519})
            return 222

        try:
            with (
                mock.patch.object(install, "stage_app_bundle", return_value={"installed": True}),
                mock.patch.object(install, "windows_startup_entry_path", return_value=startup_entry),
                mock.patch.object(install, "can_connect_local_web", side_effect=[False, False, False]),
                mock.patch.object(install, "start_windows_web_now", side_effect=fake_start),
                mock.patch.object(install, "wait_for_local_web", return_value=True),
                mock.patch.object(install, "windows_relay_web_running", return_value=False),
                mock.patch.object(install, "terminate_process") as terminate_process,
            ):
                with self.assertRaisesRegex(RuntimeError, "relay web did not start"):
                    install.install_windows_service(args, runtime_root, app_root)
            terminate_process.assert_called_once_with(222, force=False)
            self.assertFalse(startup_entry.exists())
            self.assertFalse(launcher_path.exists())
            self.assertFalse(pid_path.exists())
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_windows_relay_web_running_requires_verified_process(self) -> None:
        runtime_root = Path(r"D:\relay-hub\runtime")
        app_root = Path(r"D:\relay-hub\app")
        with (
            mock.patch.object(install, "can_connect_local_web", return_value=True),
            mock.patch.object(install, "load_windows_web_pid_info", return_value={"pid": 321}),
            mock.patch.object(install, "windows_process_matches_relay_web", return_value=False) as matches,
        ):
            self.assertFalse(install.windows_relay_web_running(runtime_root, app_root, 4517))
            matches.assert_called_once_with(321, runtime_root, app_root, 4517)

    def test_uninstall_windows_service_skips_unverified_pid(self) -> None:
        temp_dir = self.make_temp_dir()
        runtime_root = temp_dir / "runtime"
        app_root = temp_dir / "app"
        runtime_root.mkdir()
        startup_entry = temp_dir / "startup.cmd"
        launcher_path = install.windows_web_launcher_path(runtime_root)
        launcher_path.parent.mkdir(parents=True, exist_ok=True)
        launcher_path.write_text("echo off\n", encoding="utf-8")
        startup_entry.write_text("echo off\n", encoding="utf-8")
        install.write_windows_web_pid_info(runtime_root, {"pid": 456, "port": 4517})
        args = mock.Mock()
        args.web_port = 4517
        args.windows_startup_name = "Relay Hub Test"
        try:
            with (
                mock.patch.object(install, "windows_startup_entry_path", return_value=startup_entry),
                mock.patch.object(install, "windows_process_matches_relay_web", return_value=False),
                mock.patch.object(install, "terminate_process") as terminate_process,
            ):
                payload = install.uninstall_windows_service(args, runtime_root, app_root)
            terminate_process.assert_not_called()
            self.assertFalse(payload["process_verified"])
            self.assertFalse(install.windows_web_pid_path(runtime_root).exists())
            self.assertFalse(startup_entry.exists())
            self.assertFalse(launcher_path.exists())
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_uninstall_windows_service_terminates_verified_pid(self) -> None:
        temp_dir = self.make_temp_dir()
        runtime_root = temp_dir / "runtime"
        app_root = temp_dir / "app"
        runtime_root.mkdir()
        startup_entry = temp_dir / "startup.cmd"
        launcher_path = install.windows_web_launcher_path(runtime_root)
        launcher_path.parent.mkdir(parents=True, exist_ok=True)
        launcher_path.write_text("echo off\n", encoding="utf-8")
        startup_entry.write_text("echo off\n", encoding="utf-8")
        install.write_windows_web_pid_info(runtime_root, {"pid": 654, "port": 4517})
        args = mock.Mock()
        args.web_port = 4517
        args.windows_startup_name = "Relay Hub Test"
        try:
            with (
                mock.patch.object(install, "windows_startup_entry_path", return_value=startup_entry),
                mock.patch.object(install, "windows_process_matches_relay_web", return_value=True),
                mock.patch.object(install, "can_connect_local_web", return_value=False),
                mock.patch.object(install, "terminate_process") as terminate_process,
            ):
                payload = install.uninstall_windows_service(args, runtime_root, app_root)
            terminate_process.assert_called_once_with(654, force=False)
            self.assertTrue(payload["process_verified"])
            self.assertFalse(install.windows_web_pid_path(runtime_root).exists())
            self.assertFalse(startup_entry.exists())
            self.assertFalse(launcher_path.exists())
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
