from __future__ import annotations

import unittest
from pathlib import Path

from relay_hub.host_support import WINDOWS, current_platform


DOC_FILES = [
    "README.md",
    "RELAY_PROTOCOL.md",
    "docs/AI_INSTALL_PROMPT.md",
    "docs/COMPATIBILITY.md",
    "docs/GENERIC_HOST_BOOTSTRAP.md",
    "docs/GENERIC_HOST_RULE_TEMPLATE.md",
    "docs/HOST_EXAMPLES.md",
    "docs/INSTALL_PLAYBOOK.md",
    "docs/INTEGRATION_CONTRACT.md",
    "docs/OPENCLAW_INSTALL_PROMPT.md",
    "docs/OPENCLAW_INTEGRATION.md",
    "docs/OPENCLAW_RULE.md",
    "docs/RUNBOOK.md",
    "docs/UNINSTALL.md",
    "docs/AGENT_ENTRY_RULE.md",
    "docs/AGENT_WORKFLOW.md",
    "docs/HOST_EXAMPLES/codex.AGENTS.example.md",
    "docs/HOST_EXAMPLES/claude-code.CLAUDE.example.md",
    "docs/HOST_EXAMPLES/cursor-cli.relay-hub.example.mdc",
    "docs/HOST_EXAMPLES/gemini-cli.GEMINI.example.md",
]


@unittest.skipUnless(current_platform() == WINDOWS, "Windows-specific docs audit")
class WindowsDocsAuditTests(unittest.TestCase):
    repo_root = Path(__file__).resolve().parents[1]

    def read_text(self, relative_path: str) -> str:
        return (self.repo_root / relative_path).read_text(encoding="utf-8")

    def test_install_entry_docs_require_main_windows_git_source(self) -> None:
        for relative_path in [
            "README.md",
            "docs/AI_INSTALL_PROMPT.md",
            "docs/OPENCLAW_INSTALL_PROMPT.md",
            "docs/INSTALL_PLAYBOOK.md",
        ]:
            text = self.read_text(relative_path)
            self.assertIn("git clone -b main-Windows https://github.com/Liu-Bot24/relay-hub.git", text)
            self.assertIn("git switch main-Windows", text)
            self.assertNotIn("目标分支：", text, msg=f"{relative_path} still relies on natural-language branch selection")

    def test_install_entry_docs_reject_unverifiable_sources(self) -> None:
        banned_tokens = [
            "没有 `.git` 的包目录，也算有效安装源",
            "只要同时包含 `README.md`、`install.py`、`RELAY_PROTOCOL.md`，就直接使用它",
            "用户本地下载/解压出来的目录，只要同时包含 README.md、install.py、RELAY_PROTOCOL.md，就已经是有效安装源",
        ]
        for relative_path in [
            "README.md",
            "docs/AI_INSTALL_PROMPT.md",
            "docs/INSTALL_PLAYBOOK.md",
        ]:
            text = self.read_text(relative_path)
            for token in banned_tokens:
                self.assertNotIn(token, text, msg=f"{relative_path} still accepts unverifiable source token {token!r}")

    def test_windows_docs_avoid_posix_shell_and_old_bridge_surface(self) -> None:
        banned_tokens = [
            "```bash",
            "/path/to/relay-hub",
            "$HOME/AgentRelayHub",
            "~/.openclaw/",
            "scripts/openclaw_relay.py",
            "install-launchd",
            "uninstall-launchd",
            "--launchagents-dir",
            "launchd",
            "LaunchAgents",
            "python3",
            "<app_root>/",
            "alwaysApply: true",
        ]
        for relative_path in DOC_FILES:
            text = self.read_text(relative_path)
            for token in banned_tokens:
                self.assertNotIn(token, text, msg=f"{relative_path} still contains {token!r}")
            for line in text.splitlines():
                stripped = line.strip()
                self.assertFalse(
                    stripped.endswith("\\") and " " in stripped,
                    msg=f"{relative_path} still contains bash-style line continuation: {line!r}",
                )

    def test_merge_back_default_is_explicit_command(self) -> None:
        for relative_path in [
            "README.md",
            "RELAY_PROTOCOL.md",
            "docs/GENERIC_HOST_BOOTSTRAP.md",
            "docs/AGENT_ENTRY_RULE.md",
            "docs/AGENT_WORKFLOW.md",
        ]:
            text = self.read_text(relative_path)
            self.assertIn("合流上下文", text, msg=f"{relative_path} lost explicit merge-back command")
        self.assertNotIn(
            "用户回到主对话窗口并发送第一句话时，主窗口应先做一次 resume-main",
            self.read_text("RELAY_PROTOCOL.md"),
        )

    def test_openclaw_docs_use_installed_bridge_and_pump_deliveries(self) -> None:
        for relative_path in [
            "docs/OPENCLAW_INSTALL_PROMPT.md",
            "docs/OPENCLAW_INTEGRATION.md",
            "docs/OPENCLAW_RULE.md",
            "docs/RUNBOOK.md",
        ]:
            text = self.read_text(relative_path)
            self.assertIn("relay_openclaw_bridge.py", text, msg=f"{relative_path} should reference installed bridge")
            self.assertIn("pump-deliveries", text, msg=f"{relative_path} should use pump-deliveries")
            self.assertNotIn("pull-deliveries", text, msg=f"{relative_path} still documents stale pull-deliveries flow")
            self.assertNotIn("ack-delivery", text, msg=f"{relative_path} still documents stale ack-delivery flow")
            self.assertNotIn("scripts/openclaw_relay.py", text, msg=f"{relative_path} still references repo bridge")

    def test_docs_do_not_claim_windows_e2e_finished(self) -> None:
        self.assertNotIn("装完以后，正常流程是：", self.read_text("README.md"))
        self.assertIn("端到端目标流程", self.read_text("README.md"))
        self.assertIn("只有在真实 OpenClaw 实例、真实消息渠道", self.read_text("README.md"))
        self.assertNotIn("答案是：\n\n- 可以", self.read_text("docs/COMPATIBILITY.md"))
        self.assertNotIn("仓库已经安装到“可用状态”", self.read_text("docs/INSTALL_PLAYBOOK.md"))

    def test_host_side_docs_do_not_default_to_install_openclaw(self) -> None:
        readme = self.read_text("README.md")
        self.assertIn("这一步只应由 `OpenClaw` 执行，不是宿主侧默认步骤。", readme)
        ai_prompt = self.read_text("docs/AI_INSTALL_PROMPT.md")
        self.assertIn("不要执行 `install-openclaw`", ai_prompt)


if __name__ == "__main__":
    unittest.main()
