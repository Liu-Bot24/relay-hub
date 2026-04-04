#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import plistlib
import re
import shutil
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any

from relay_hub import RelayHub


REPO_ROOT = Path(__file__).resolve().parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
DEFAULT_INSTALL_ROOT = Path.home() / "Library" / "Application Support" / "RelayHub"
DEFAULT_RUNTIME_ROOT = DEFAULT_INSTALL_ROOT / "runtime"
DEFAULT_OPENCLAW_WORKSPACE = Path.home() / ".openclaw" / "workspace"
DEFAULT_LAUNCHAGENTS_DIR = Path.home() / "Library" / "LaunchAgents"
DEFAULT_APP_ROOT = DEFAULT_INSTALL_ROOT / "app"
DEFAULT_CODEX_HOME = Path.home() / ".codex"
FORBIDDEN_INSTALL_ROOT_PREFIXES = (
    Path("/private/tmp"),
    Path("/tmp"),
    Path("/var/folders"),
)
DEFAULT_PATH = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
DEFAULT_WEB_HOST = "0.0.0.0"
DEFAULT_WEB_PORT = 4317
VERSION = "0.1.0"
HEARTBEAT_BEGIN = "<!-- RELAY_HUB_BEGIN -->"
HEARTBEAT_END = "<!-- RELAY_HUB_END -->"
CODEX_AGENTS_BEGIN = "<!-- RELAY_HUB_CODEX_BEGIN -->"
CODEX_AGENTS_END = "<!-- RELAY_HUB_CODEX_END -->"
DEFAULT_OPENCLAW_LOGS_DIR = Path.home() / ".openclaw" / "logs"
DISCOVERY_LOG_TAIL_BYTES = 512 * 1024


def output(payload: object) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_text(path: Path, content: str) -> None:
    ensure_dir(path.parent)
    path.write_text(content, encoding="utf-8")


def write_json(path: Path, payload: Any) -> None:
    write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_path(raw: str | None, default: Path) -> Path:
    return Path(raw).expanduser().resolve() if raw else default


def repo_root_is_ephemeral(path: Path) -> bool:
    resolved = path.expanduser().resolve()
    return any(resolved == prefix or prefix in resolved.parents for prefix in FORBIDDEN_INSTALL_ROOT_PREFIXES)


def ensure_repo_root_allowed(command: str) -> None:
    if command not in {"install-host", "install-openclaw", "install-launchd", "full"}:
        return
    if repo_root_is_ephemeral(REPO_ROOT):
        raise SystemExit(
            "Relay Hub must not be installed from a temporary/cache checkout such as "
            f"`{REPO_ROOT}`. Re-run from a visible permanent local repo copy (for example the current "
            "workspace repo or `~/relay-hub`), and do not use `/tmp`, `/private/tmp`, or `/var/folders`."
        )


def default_web_base_url(port: int) -> str:
    return f"http://127.0.0.1:{port}"


def detect_lan_ipv4() -> str | None:
    probe_targets = [("10.255.255.255", 1), ("192.0.2.1", 1), ("8.8.8.8", 80)]
    for host, port in probe_targets:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.connect((host, port))
                ip = sock.getsockname()[0]
            if ip and not ip.startswith("127."):
                return ip
        except OSError:
            continue
    return None


def resolved_web_base_url(args: argparse.Namespace) -> str:
    if args.web_base_url:
        return args.web_base_url.rstrip("/")
    detected_ip = detect_lan_ipv4()
    if detected_ip:
        return f"http://{detected_ip}:{args.web_port}"
    return default_web_base_url(args.web_port)


def add_shared_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--runtime-root", help="Relay runtime root. Defaults to ~/Library/Application Support/RelayHub/runtime.")
    parser.add_argument("--openclaw-workspace", help="OpenClaw workspace path. Defaults to ~/.openclaw/workspace.")
    parser.add_argument("--app-root", help="Installed runtime app directory. Defaults to ~/Library/Application Support/RelayHub/app.")
    parser.add_argument("--web-host", default=DEFAULT_WEB_HOST)
    parser.add_argument("--web-port", type=int, default=DEFAULT_WEB_PORT)
    parser.add_argument("--web-base-url", help="Public base URL for Relay web.")
    parser.add_argument("--queue-ack-timeout", type=int, default=15)
    parser.add_argument("--codex-home", help="Codex home directory. Defaults to ~/.codex.")
    parser.add_argument(
        "--delivery-channel",
        action="append",
        help="Additional delivery target in channel=target form. Repeatable.",
    )
    parser.add_argument(
        "--delivery-account",
        action="append",
        help="Optional delivery account in channel=accountId form. Repeatable.",
    )
    parser.add_argument("--launchagents-dir", help="launchd plist destination. Defaults to ~/Library/LaunchAgents.")
    parser.add_argument("--load-services", action="store_true", help="Bootstrap launchd services after writing plists.")
    parser.add_argument(
        "--install-codex-host",
        action="store_true",
        help="Also install the optional Codex host enhancement into ~/.codex. Use only when the current AI host is Codex and the user explicitly wants it.",
    )
    parser.add_argument(
        "--uninstall-codex-host",
        action="store_true",
        help="Also remove the optional Codex host enhancement from ~/.codex. Only affects Relay Hub-managed Codex files.",
    )
    parser.add_argument("--skip-heartbeat-patch", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Relay Hub installer and service manager")
    subparsers = parser.add_subparsers(dest="command", required=True)

    full_parser = subparsers.add_parser("full", help="Operator-only combined install of shared layer, OpenClaw side, and launchd services")
    add_shared_args(full_parser)

    host_parser = subparsers.add_parser(
        "install-host",
        help="Install/update shared runtime and host-side services without touching OpenClaw workspace",
    )
    add_shared_args(host_parser)

    oc_parser = subparsers.add_parser("install-openclaw", help="Install/update OpenClaw-side bridge files")
    add_shared_args(oc_parser)

    svc_parser = subparsers.add_parser("install-launchd", help="Install/update launchd plist for Relay Hub web")
    add_shared_args(svc_parser)

    uninstall_parser = subparsers.add_parser(
        "uninstall",
        help="Operator-only combined uninstall of shared layer, OpenClaw side, and launchd services",
    )
    add_shared_args(uninstall_parser)

    uninstall_host_parser = subparsers.add_parser(
        "uninstall-host",
        help="Remove shared runtime and host-side services without touching OpenClaw workspace",
    )
    add_shared_args(uninstall_host_parser)

    uninstall_oc_parser = subparsers.add_parser(
        "uninstall-openclaw",
        help="Remove OpenClaw-side Relay Hub bridge files without touching shared runtime",
    )
    add_shared_args(uninstall_oc_parser)

    uninstall_launchd_parser = subparsers.add_parser(
        "uninstall-launchd",
        help="Unload and remove launchd plist for Relay Hub web",
    )
    add_shared_args(uninstall_launchd_parser)

    status_parser = subparsers.add_parser("status", help="Show current Relay Hub install status")
    add_shared_args(status_parser)

    doctor_parser = subparsers.add_parser("doctor", help="Check whether this machine is ready for Relay Hub installation")
    add_shared_args(doctor_parser)
    return parser


def delivery_channels(args: argparse.Namespace) -> dict[str, Any]:
    def parse_pairs(values: list[str] | None, flag_name: str) -> dict[str, str]:
        payload: dict[str, str] = {}
        for raw in values or []:
            if "=" not in raw:
                raise SystemExit(f"{flag_name} expects channel=value, got: {raw}")
            key, value = raw.split("=", 1)
            key = key.strip()
            value = value.strip()
            if not key or not value:
                raise SystemExit(f"{flag_name} expects channel=value, got: {raw}")
            payload[key] = value
        return payload

    channels: dict[str, Any] = {}
    generic_targets = parse_pairs(getattr(args, "delivery_channel", None), "--delivery-channel")
    generic_accounts = parse_pairs(getattr(args, "delivery_account", None), "--delivery-account")
    for channel, target in generic_targets.items():
        entry = channels.get(channel, {})
        entry["target"] = target
        if channel in generic_accounts:
            entry["accountId"] = generic_accounts[channel]
        channels[channel] = entry
    for channel, account_id in generic_accounts.items():
        entry = channels.get(channel, {})
        entry["accountId"] = account_id
        channels[channel] = entry
    for channel, entry in channels.items():
        if not entry.get("target"):
            raise SystemExit(f"delivery channel {channel} is missing a target")
    return channels


def clean_delivery_channels(payload: dict[str, Any] | None) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for channel, raw_entry in (payload or {}).items():
        entry = raw_entry or {}
        target = str(entry.get("target") or "").strip()
        if not target:
            continue
        normalized: dict[str, Any] = {"target": target}
        account_id = str(entry.get("accountId") or "").strip()
        if account_id:
            normalized["accountId"] = account_id
        cleaned[channel] = normalized
    return cleaned


def merge_delivery_channel_maps(*payloads: dict[str, Any] | None) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for payload in payloads:
        for channel, entry in clean_delivery_channels(payload).items():
            current = dict(merged.get(channel, {}))
            current.update(entry)
            current["target"] = entry["target"]
            merged[channel] = current
    return merged


def run_json_command(cmd: list[str]) -> Any | None:
    result = subprocess.run(cmd, capture_output=True, text=True)  # noqa: S603
    if result.returncode != 0:
        return None
    stdout = result.stdout.strip()
    if not stdout:
        return None
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        return None


def read_recent_log_text(path: Path, max_bytes: int = DISCOVERY_LOG_TAIL_BYTES) -> str:
    if not path.exists():
        return ""
    with path.open("rb") as handle:
        size = handle.seek(0, os.SEEK_END)
        handle.seek(max(0, size - max_bytes))
        return handle.read().decode("utf-8", errors="replace")


def discover_feishu_target_from_directory() -> str | None:
    payload = run_json_command(["openclaw", "directory", "peers", "list", "--channel", "feishu", "--json"])
    if not isinstance(payload, list):
        return None
    for item in payload:
        if not isinstance(item, dict):
            continue
        if item.get("kind") == "user" and item.get("id"):
            return str(item["id"]).strip()
    for item in payload:
        if not isinstance(item, dict):
            continue
        if item.get("id"):
            return str(item["id"]).strip()
    return None


def discover_channel_target_from_gateway_log(channel: str) -> str | None:
    text = read_recent_log_text(DEFAULT_OPENCLAW_LOGS_DIR / "gateway.log")
    if not text:
        return None
    patterns: list[re.Pattern[str]] = []
    if channel == "openclaw-weixin":
        patterns.append(re.compile(r"\[openclaw-weixin\] \[weixin\] config (?:cached|refreshed) for ([^\s]+)"))
    if channel == "feishu":
        patterns.append(re.compile(r"\[feishu\][^\n]*received message from ([^ ]+) in "))
    patterns.append(
        re.compile(
            rf'message params=\{{[^\n]*"channel":"{re.escape(channel)}"[^\n]*"target":"([^"]+)"'
        )
    )
    for pattern in patterns:
        matches = pattern.findall(text)
        if matches:
            return str(matches[-1]).strip()
    return None


def discover_channel_target(channel: str) -> str | None:
    if channel == "feishu":
        return discover_feishu_target_from_directory() or discover_channel_target_from_gateway_log(channel)
    return discover_channel_target_from_gateway_log(channel)


def channel_default_account_id(status_payload: dict[str, Any], channel: str) -> str | None:
    default_account = str(((status_payload.get("channelDefaultAccountId") or {}).get(channel)) or "").strip()
    if default_account:
        return default_account
    accounts = (status_payload.get("channelAccounts") or {}).get(channel) or []
    for account in accounts:
        if not isinstance(account, dict):
            continue
        if account.get("configured") and account.get("enabled") and account.get("accountId"):
            return str(account["accountId"]).strip()
    return None


def channel_can_deliver(status_payload: dict[str, Any], channel: str, account_id: str | None) -> bool:
    channel_state = ((status_payload.get("channels") or {}).get(channel)) or {}
    if not channel_state.get("configured"):
        return False
    accounts = (status_payload.get("channelAccounts") or {}).get(channel) or []
    if not accounts:
        return True
    for account in accounts:
        if not isinstance(account, dict):
            continue
        if account_id and str(account.get("accountId") or "").strip() != account_id:
            continue
        if account.get("configured") and account.get("enabled"):
            return True
    return False


def discover_openclaw_delivery_channels() -> tuple[dict[str, Any], list[str]]:
    payload = run_json_command(["openclaw", "channels", "status", "--json"])
    if not isinstance(payload, dict):
        return {}, []
    order = list(payload.get("channelOrder") or [])
    if not order:
        order = list((payload.get("channels") or {}).keys())
    discovered: dict[str, Any] = {}
    unresolved: list[str] = []
    for channel in order:
        account_id = channel_default_account_id(payload, channel)
        if not channel_can_deliver(payload, channel, account_id):
            continue
        target = discover_channel_target(channel)
        if not target:
            unresolved.append(channel)
            continue
        entry: dict[str, Any] = {"target": target}
        if account_id:
            entry["accountId"] = account_id
        discovered[str(channel)] = entry
    return discovered, unresolved


def resolved_delivery_channels(args: argparse.Namespace, openclaw_workspace: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    explicit = clean_delivery_channels(delivery_channels(args))
    existing = clean_delivery_channels(existing_delivery_channels(openclaw_workspace))
    auto_discovered, unresolved = discover_openclaw_delivery_channels()
    merged = merge_delivery_channel_maps(auto_discovered, existing, explicit)
    sources: list[str] = []
    if auto_discovered:
        sources.append("auto_discovered")
    if existing:
        sources.append("existing_config")
    if explicit:
        sources.append("explicit_args")
    return merged, {
        "source": "+".join(sources) if sources else "none",
        "auto_discovered_channels": auto_discovered,
        "existing_channels": existing,
        "explicit_channels": explicit,
        "unresolved_channels": unresolved,
    }


def bridge_script_repo_path() -> Path:
    return SCRIPTS_DIR / "relay_openclaw_bridge.py"


def bridge_script_workspace_path(openclaw_workspace: Path) -> Path:
    return openclaw_workspace / "scripts" / "relay_openclaw_bridge.py"


def openclaw_config_path(openclaw_workspace: Path) -> Path:
    return openclaw_workspace / "data" / "relay_hub_openclaw.json"


def existing_delivery_channels(openclaw_workspace: Path) -> dict[str, Any]:
    existing = load_json(openclaw_config_path(openclaw_workspace), {}) or {}
    return clean_delivery_channels((existing.get("delivery") or {}).get("channels") or {})


def alias_map_path(openclaw_workspace: Path) -> Path:
    return openclaw_workspace / "data" / "relay_hub_channel_aliases.json"


def heartbeat_path(openclaw_workspace: Path) -> Path:
    return openclaw_workspace / "HEARTBEAT.md"


def heartbeat_block_installed(openclaw_workspace: Path) -> bool:
    heartbeat_file = heartbeat_path(openclaw_workspace)
    if not heartbeat_file.exists():
        return False
    content = heartbeat_file.read_text(encoding="utf-8")
    return HEARTBEAT_BEGIN in content and HEARTBEAT_END in content


def skill_path(openclaw_workspace: Path) -> Path:
    return openclaw_workspace / "skills" / "relay-hub-openclaw" / "SKILL.md"


def codex_skill_path(codex_home: Path) -> Path:
    return codex_home / "skills" / "relay-hub" / "SKILL.md"


def codex_agents_path(codex_home: Path) -> Path:
    return codex_home / "AGENTS.md"


def stage_app_bundle(app_root: Path) -> dict[str, Any]:
    ensure_dir(app_root)
    scripts_root = app_root / "scripts"
    ensure_dir(scripts_root)
    stale_script = scripts_root / "relay_agent_worker.py"
    stale_script.unlink(missing_ok=True)
    scripts = [
        "agent_relay.py",
        "openclaw_relay.py",
        "relay_after_reply_hook.py",
        "relay_agent_daemon.py",
        "relay_openclaw_bridge.py",
        "relay_web.py",
        "relayctl.py",
    ]
    copied: list[str] = []
    for name in scripts:
        src = SCRIPTS_DIR / name
        dst = scripts_root / name
        shutil.copy2(src, dst)
        copied.append(str(dst))
    shutil.copytree(REPO_ROOT / "relay_hub", app_root / "relay_hub", dirs_exist_ok=True)
    return {
        "app_root": str(app_root),
        "scripts_root": str(scripts_root),
        "scripts": copied,
        "package_dir": str(app_root / "relay_hub"),
    }


def build_openclaw_config(
    args: argparse.Namespace,
    runtime_root: Path,
    openclaw_workspace: Path,
    app_root: Path,
    channels: dict[str, Any],
) -> dict[str, Any]:
    base_url = resolved_web_base_url(args)
    return {
        "version": 1,
        "relayHub": {
            "repoRoot": str(REPO_ROOT),
            "appRoot": str(app_root),
            "runtimeRoot": str(runtime_root),
            "openclawRelayScript": str(app_root / "scripts" / "openclaw_relay.py"),
            "relayWebScript": str(app_root / "scripts" / "relay_web.py"),
        },
        "aliases": {
            "path": str(alias_map_path(openclaw_workspace)),
        },
        "web": {
            "host": args.web_host,
            "port": args.web_port,
            "baseUrl": base_url,
            "startupWaitSeconds": 5,
            "pidPath": str(openclaw_workspace / "data" / "relay_hub_web.pid"),
            "logPath": str(openclaw_workspace / "log" / "relay_hub_web.log"),
        },
        "queueAckTimeoutSeconds": args.queue_ack_timeout,
        "delivery": {
            "defaultMode": "all",
            "channels": channels,
        },
    }


def build_skill_text(script_path: Path) -> str:
    return f"""---
name: relay-hub-openclaw
description: OpenClaw 的 Relay Hub 渠道路由技能。用于“打开 <agent> 入口”“已录入”“状态”“退出 relay”“relay help”这类请求，并把外部 agent 的回包优先发回当前会话来源渠道；首次从宿主侧开启时，默认提醒会发到当前已启用的 OpenClaw 渠道。
---

# relay-hub-openclaw

这个 skill 只负责 OpenClaw 侧的渠道网关动作，不负责外部 agent 的主上下文，也不要自己翻 Relay Hub 的底层文件。

必须遵守
- 只调用固定脚本：`python3 {script_path} ...`
- 不要自己读取 `routes.json`、`config.json`、`messages/*.md`。
- 对桥接脚本的返回内容，优先原样发给用户，不要总结，不要改写，不要脑补成功。
- 当前主对话窗口不在 OpenClaw 里。OpenClaw 只负责“开入口、收已录入、查状态、退出、relay help、发回包”。
- 网页链接发出去时只是入口已打开；用户第一次在网页里保存消息时，branch 才正式开始。
- 只有当当前实例已经为该渠道配置了默认 target 时，才能省略 `--target`；否则必须传当前渠道目标。
- 当前渠道和当前目标，默认必须从当前入站消息上下文里获取；如果宿主没有直接给出，再用宿主可查询的当前会话信息补取；只有真的拿不到时才回问用户。
- 不要使用文档示例值，不要沿用别的会话的渠道或目标。
- branch 回包始终优先发回原始触发渠道。
- 首次从 AI 宿主主窗口开启 Relay Hub 时，如果当前主会话还没有已绑定的 OpenClaw 来源对象，默认提醒应发送到当前 OpenClaw 已启用的所有默认消息渠道；后续用户可再通过主窗口命令关闭某些渠道提醒。
- 当你汇报安装结果或当前状态时，如果已经自动发现了默认提醒渠道，就直接如实列出；如果当前确实一个可用默认提醒渠道都没有，再说明“默认仍走原始触发渠道”，不要主动建议用户现在去加渠道。

对象名规则
- `--agent` 应传用户当前说到的对象名，或该对象稳定使用的 `agent_id`
- 常见别名例如：`codex`、`claude` / `claude-code`、`gemini` / `gemini-cli`、`cursor` / `cursor-cli`、`opencode`
- 未命中的对象名不要拒绝；桥接脚本会对常见别名做归一化，未知 `agent_id` 会原样透传

对象名映射由桥接脚本处理；只要把用户提到的对象名传给 `--agent` 即可。

## 1. 打开入口

```bash
python3 {script_path} open-entry --agent "<agent>" --channel "<当前渠道>" --target "<当前目标>"
```

如果脚本返回“请明确选择：回复‘复用入口’继续使用旧 branch，或回复‘新建入口’创建全新 branch”，必须先把这个问题发给用户，主动询问，不要替用户决定。并把这次的 `agent / channel / target` 视作当前待确认入口；等用户明确回答后再重试。用户只要明确表达“复用”或“新建”即可，不要求一字不差：

```bash
python3 {script_path} open-entry --agent "<agent>" --channel "<当前渠道>" --target "<当前目标>" --branch-mode reuse
```

或：

```bash
python3 {script_path} open-entry --agent "<agent>" --channel "<当前渠道>" --target "<当前目标>" --branch-mode new
```

## 2. 已录入

```bash
python3 {script_path} dispatch-input --channel "<当前渠道>" --target "<当前目标>" --wait-claim
```

## 3. 状态

```bash
python3 {script_path} session-status --channel "<当前渠道>" --target "<当前目标>"
```

## 4. 退出

```bash
python3 {script_path} exit-relay --channel "<当前渠道>" --target "<当前目标>"
```

## 5. relay help

```bash
python3 {script_path} relay-help --agent "<agent>"
```

## 6. 外部回包发送

外部 agent 的回包由 heartbeat 里的发送泵统一处理：

```bash
python3 {script_path} pump-deliveries
```
"""


def build_codex_skill_text(app_root: Path) -> str:
    script_path = app_root / "scripts" / "agent_relay.py"
    return f"""---
name: relay-hub
description: Use when the user says “接入 Relay Hub”, “Relay Hub 状态”, “合流上下文”, or “退出 Relay Hub”, or when a Relay Hub-enabled Codex conversation should mirror its replies to OpenClaw channels.
---

# relay-hub

This skill gives Codex a Relay Hub control surface for the current Codex conversation.

Use the installed script:

- `python3 {script_path} ...`

Treat these as product commands, not ordinary chat:

- `接入 Relay Hub`
- `Relay Hub 状态`
- `消息提醒状态`
- `开启<渠道>消息提醒`
- `关闭<渠道>消息提醒`
- `合流上下文`
- `退出 Relay Hub`

Current supported scope for Codex is simple:

1. Relay Hub is installed on this machine.
2. The user explicitly turns Relay Hub on once by saying `接入 Relay Hub` in a Codex conversation.
3. After that, Relay Hub stays enabled for Codex until the user says `退出 Relay Hub`, or the attached Codex conversation is closed / archived.
4. While Relay Hub remains enabled, the active main conversation follows the current Codex thread:
   - if the current thread already has Relay Hub history, reuse its existing `main_session_ref`
   - if the current thread has no Relay Hub history yet, start a new thread-bound `main_session_ref`
   - keep exactly one active main conversation at a time
5. This switch follows the current Codex conversation / thread, not `project_root`.

Do not monitor projects or guess future conversations. `project_root` only locates code, development log and workspace; the active main conversation follows the current Codex thread.

When the user says `接入 Relay Hub`:

1. Determine the current project root. Prefer the current workspace root unless the user clearly specifies another project.
2. Reuse an existing `DEVELOPMENT_LOG.md` for that project if present; otherwise create one at the project root.
3. Write a concise main-window snapshot before enabling Relay Hub.
   - Prefer the actual user task / topic immediately before `接入 Relay Hub`.
   - If there was already an ongoing discussion, summarize that discussion; do not make the snapshot mainly about “I am enabling Relay Hub”.
   - Only fall back to an enable-flow summary when there truly is no meaningful prior main-window topic.
4. Maintain one stable `main_session_ref` for this Codex main conversation:
   - Prefer a host-provided conversation/session/thread id if available.
   - Otherwise generate one once for this conversation and keep reusing it for later Relay Hub commands in the same conversation.
5. Run:

```bash
python3 {script_path} --agent codex enable-relay \\
  --project-root "<project_root>" \\
  --start-pickup
```

Notes:
- For Codex, `enable-relay --start-pickup` auto-resolves the current conversation's `main_session_ref` and auto-derives the current main-window snapshot from the rollout; only pass `--main-session-ref` or `--snapshot-body` if host auto-resolution is unavailable.
- `enable-relay` sends the startup OpenClaw reminder by default.
- For Codex host conversations, once pickup is running, normal main-window replies are mirrored to OpenClaw automatically from the current Codex rollout log. Do not manually regenerate or paraphrase a second copy for OpenClaw.
- For other hosts, use exact-body capture instead of regeneration: after the host has already produced the final reply, pass that exact body to `capture-main-output --body-file <exact final body file>` (preferred, daemon will mirror it) or `mirror-main-output --body-file <exact final body file>` if you need immediate direct notify.

Before a normal non-product reply while Relay Hub is already enabled, prepare the current Codex conversation for reply:

```bash
python3 {script_path} --agent codex prepare-main-reply
```

Notes:
- `prepare-main-reply` 会先对齐到当前 Codex 线程。
- 如果当前主会话下正好有 1 条待合流 branch，它会自动执行 `resume-main --keep-relay-open`，把 branch 增量并回主窗口，再继续正常回复。
- 如果当前主会话下有多条待合流 branch，它会返回 `resume_candidates`；此时不要猜，让用户明确选择要先合哪一条。
- 如果当前 Codex 线程没有 Relay Hub 历史，它会像 `sync-current-main` 一样创建/复用当前线程的 `main_session_ref` 和主线快照。

When the user says `Relay Hub 状态`:

First align Relay Hub to the current Codex conversation:

```bash
python3 {script_path} --agent codex sync-current-main
```

Then inspect agent status:

```bash
python3 {script_path} --agent codex agent-status
```

If you already know the current `main_session_ref`, also inspect that pickup:

```bash
python3 {script_path} --agent codex pickup-status --main-session-ref "<main_session_ref>"
```

If the status output shows `resume_candidates`, tell the user plainly that old branch context has not yet been merged back into the main conversation.

When the user says `消息提醒状态`:

```bash
python3 {script_path} --agent codex notification-status
```

When the user says `开启<渠道>消息提醒`:

```bash
python3 {script_path} --agent codex enable-notification-channel --channel "<channel>"
```

When the user says `关闭<渠道>消息提醒`:

```bash
python3 {script_path} --agent codex disable-notification-channel --channel "<channel>"
```

Accepted channel tokens include exact configured channel ids plus common aliases such as the examples below; if the configured channel id is different, pass that exact id through directly:
- `飞书` / `feishu`
- `微信` / `weixin` / `wechat` / `openclaw-weixin`
- `telegram` / `tg`

When the user says `合流上下文`:

1. First align Relay Hub to the current Codex conversation:

```bash
python3 {script_path} --agent codex sync-current-main
```

2. Reuse the current attached `main_session_ref`.
3. Run:

```bash
python3 {script_path} --agent codex resume-main --main-session-ref "<main_session_ref>"
```

4. If the script returns multiple `resume_candidates`, do not guess. Tell the user there are multiple old branches still waiting to be merged, and ask which one to merge.
5. If the script succeeds, continue the current main-window conversation on top of the merged result.

When the user says `退出 Relay Hub`:

```bash
python3 {script_path} --agent codex disable-relay
```

Rules:
- Do not read Relay Hub runtime files directly if the script can answer.
- Branch starts only when the user first saves a message in the webpage.
- OpenClaw remains the channel gateway; Codex remains the main conversation.
"""


def build_codex_agents_block(codex_home: Path, app_root: Path) -> str:
    skill = codex_skill_path(codex_home)
    script_path = app_root / "scripts" / "agent_relay.py"
    return f"""{CODEX_AGENTS_BEGIN}
When the user says `接入 Relay Hub`, `Relay Hub 状态`, `消息提醒状态`, `开启<渠道>消息提醒`, `关闭<渠道>消息提醒`, `合流上下文`, or `退出 Relay Hub`, treat those as Relay Hub product commands, not ordinary chat. Follow the installed Codex skill at:

- `{skill}`

If Relay Hub is already enabled for Codex, the active main conversation should follow the current Codex conversation / thread, not `project_root`. Before a normal main-window reply in this conversation, run:

- `python3 {script_path} --agent codex prepare-main-reply`

If this Codex conversation is attached to Relay Hub, normal main-window replies should by default be mirrored to OpenClaw channels unless the user explicitly says不要同步 or has already exited Relay Hub.
For Codex host conversations, this mirror must come from the exact final output captured by code, not from a second prompt-generated paraphrase or another model pass.
{CODEX_AGENTS_END}
"""


def merge_codex_agents(existing: str, block: str) -> str:
    existing = existing.rstrip() + "\n" if existing else ""
    if CODEX_AGENTS_BEGIN in existing and CODEX_AGENTS_END in existing:
        before, rest = existing.split(CODEX_AGENTS_BEGIN, 1)
        _, after = rest.split(CODEX_AGENTS_END, 1)
        merged = before.rstrip() + "\n\n" + block.rstrip() + "\n" + after.lstrip("\n")
        return merged.rstrip() + "\n"
    if not existing.strip():
        return block.rstrip() + "\n"
    return existing.rstrip() + "\n\n" + block.rstrip() + "\n"


def build_heartbeat_block(script_path: Path) -> str:
    return f"""{HEARTBEAT_BEGIN}
先运行：

- `python3 {script_path} pump-deliveries`

规则：

- 若输出为 `RELAY_PUMP_IDLE` 或以 `RELAY_PUMP_SENT:` 开头，继续执行下面的邮件通知检查。
- 若脚本非 0 退出、出现 traceback，或输出以 `RELAY_PUMP_FAILED:` 开头，则只回复该行，不要继续执行后续检查。
{HEARTBEAT_END}
"""


def merge_heartbeat(existing: str, block: str) -> str:
    existing = existing.rstrip() + "\n" if existing else ""
    if HEARTBEAT_BEGIN in existing and HEARTBEAT_END in existing:
        before, rest = existing.split(HEARTBEAT_BEGIN, 1)
        _, after = rest.split(HEARTBEAT_END, 1)
        merged = before.rstrip() + "\n\n" + block.rstrip() + "\n" + after.lstrip("\n")
        return merged.rstrip() + "\n"
    if "relay_openclaw_bridge.py pump-deliveries" in existing and "先检查目录 " in existing:
        prefix, suffix = existing.split("先检查目录 ", 1)
        if "规则：" in prefix:
            return block.rstrip() + "\n\n先检查目录 " + suffix.lstrip("\n")
    if not existing.strip():
        return block.rstrip() + "\n"
    return block.rstrip() + "\n\n" + existing


def remove_marked_block(existing: str, begin: str, end: str) -> tuple[str, bool]:
    if begin not in existing or end not in existing:
        return existing, False
    before, rest = existing.split(begin, 1)
    _, after = rest.split(end, 1)
    cleaned = before.rstrip("\n")
    suffix = after.lstrip("\n")
    if cleaned and suffix:
        result = cleaned + "\n\n" + suffix
    elif cleaned:
        result = cleaned + "\n"
    else:
        result = suffix
    return result.rstrip() + ("\n" if result.strip() else ""), True


def unlink_if_exists(path: Path) -> bool:
    if not path.exists():
        return False
    path.unlink()
    return True


def remove_tree_if_exists(path: Path) -> bool:
    if not path.exists():
        return False
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()
    return True


def prune_empty_parents(path: Path, stop_at: Path) -> None:
    current = path
    stop = stop_at.resolve()
    while current.exists() and current.is_dir():
        try:
            if current.resolve() == stop:
                return
        except FileNotFoundError:
            return
        try:
            current.rmdir()
        except OSError:
            return
        current = current.parent


def bootstrap_runtime(args: argparse.Namespace, runtime_root: Path) -> dict[str, Any]:
    hub = RelayHub(runtime_root)
    config = hub.init_layout(
        web_base_url=resolved_web_base_url(args),
        queue_ack_timeout_seconds=args.queue_ack_timeout,
        default_channels=list(delivery_channels(args).keys()),
    )
    return {"runtime_root": str(runtime_root), "config": config}


def app_bundle_installed(app_root: Path) -> bool:
    return (app_root / "scripts" / "relay_web.py").exists() and (app_root / "relay_hub").exists()


def ensure_shared_install_ready(runtime_root: Path, app_root: Path) -> None:
    missing: list[str] = []
    if not runtime_root.exists():
        missing.append(str(runtime_root))
    if not app_bundle_installed(app_root):
        missing.append(str(app_root))
    if missing:
        raise SystemExit(
            "OpenClaw-side install requires shared Relay Hub files to already exist. "
            "Please run `python3 install.py install-host --load-services` first. "
            f"Missing: {', '.join(missing)}"
        )


def install_openclaw(args: argparse.Namespace, runtime_root: Path, openclaw_workspace: Path, app_root: Path) -> dict[str, Any]:
    ensure_shared_install_ready(runtime_root, app_root)
    channels, channel_meta = resolved_delivery_channels(args, openclaw_workspace)
    unresolved_missing = [channel for channel in channel_meta["unresolved_channels"] if channel not in channels]
    if unresolved_missing:
        joined = ", ".join(unresolved_missing)
        raise SystemExit(
            "install-openclaw could not determine default targets for all enabled OpenClaw channels. "
            f"Unresolved channels: {joined}. "
            "Make those channels addressable in OpenClaw first, or pass explicit "
            "`--delivery-channel channel=target` / `--delivery-account channel=accountId` values."
        )
    config = build_openclaw_config(args, runtime_root, openclaw_workspace, app_root, channels)
    config_file = openclaw_config_path(openclaw_workspace)
    bridge_target = bridge_script_workspace_path(openclaw_workspace)
    ensure_dir(bridge_target.parent)
    shutil.copy2(bridge_script_repo_path(), bridge_target)
    write_json(config_file, config)
    write_text(skill_path(openclaw_workspace), build_skill_text(bridge_target))
    heartbeat_file = heartbeat_path(openclaw_workspace)
    heartbeat_existing = heartbeat_file.read_text(encoding="utf-8") if heartbeat_file.exists() else ""
    if not args.skip_heartbeat_patch:
        write_text(heartbeat_file, merge_heartbeat(heartbeat_existing, build_heartbeat_block(bridge_target)))
    return {
        "shared_install_verified": True,
        "bridge_script": str(bridge_target),
        "config_path": str(config_file),
        "skill_path": str(skill_path(openclaw_workspace)),
        "heartbeat_path": str(heartbeat_file),
        "configured_default_notification_channels": config["delivery"]["channels"],
        "delivery_channels_source": channel_meta["source"],
        "auto_discovered_notification_channels": channel_meta["auto_discovered_channels"],
        "unresolved_notification_channels": channel_meta["unresolved_channels"],
        "delivery_channels_note": (
            "Branch replies still default to the original trigger channel. "
            "When Relay Hub is first enabled from an AI host main window, startup reminders and host-opened entries "
            "fan out to every configured default notification channel unless the user later disables some of them."
        ),
    }


def install_codex(args: argparse.Namespace, codex_home: Path, app_root: Path) -> dict[str, Any]:
    skill_file = codex_skill_path(codex_home)
    write_text(skill_file, build_codex_skill_text(app_root))
    agents_file = codex_agents_path(codex_home)
    existing_agents = agents_file.read_text(encoding="utf-8") if agents_file.exists() else ""
    write_text(agents_file, merge_codex_agents(existing_agents, build_codex_agents_block(codex_home, app_root)))
    return {
        "codex_home": str(codex_home),
        "skill_path": str(skill_file),
        "agents_path": str(agents_file),
    }


def uninstall_codex(codex_home: Path) -> dict[str, Any]:
    skill_file = codex_skill_path(codex_home)
    agents_file = codex_agents_path(codex_home)
    skill_removed = unlink_if_exists(skill_file)
    prune_empty_parents(skill_file.parent, codex_home)
    agents_updated = False
    agents_removed = False
    if agents_file.exists():
        existing_agents = agents_file.read_text(encoding="utf-8")
        updated_agents, removed = remove_marked_block(existing_agents, CODEX_AGENTS_BEGIN, CODEX_AGENTS_END)
        if removed:
            agents_updated = True
            if updated_agents.strip():
                write_text(agents_file, updated_agents)
            else:
                agents_file.unlink(missing_ok=True)
                agents_removed = True
    return {
        "codex_home": str(codex_home),
        "skill_removed": skill_removed,
        "agents_updated": agents_updated,
        "agents_removed": agents_removed,
    }


def launchctl_domain() -> str:
    return f"gui/{os.getuid()}"


def launchctl_bootstrap(plist_path: Path, label: str) -> None:
    subprocess.run(["launchctl", "bootout", launchctl_domain(), str(plist_path)], capture_output=True, text=True)  # noqa: S603
    result = subprocess.run(["launchctl", "bootstrap", launchctl_domain(), str(plist_path)], capture_output=True, text=True)  # noqa: S603
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or f"launchctl bootstrap failed for {label}").strip())
    subprocess.run(["launchctl", "enable", f"{launchctl_domain()}/{label}"], capture_output=True, text=True)  # noqa: S603
    subprocess.run(["launchctl", "kickstart", "-k", f"{launchctl_domain()}/{label}"], capture_output=True, text=True)  # noqa: S603


def build_web_plist(app_root: Path, runtime_root: Path, logs_dir: Path, host: str, port: int) -> bytes:
    payload = {
        "Label": "com.relayhub.web",
        "ProgramArguments": [
            sys.executable,
            str(app_root / "scripts" / "relay_web.py"),
            "--root",
            str(runtime_root),
            "--host",
            host,
            "--port",
            str(port),
        ],
        "WorkingDirectory": str(app_root),
        "RunAtLoad": True,
        "KeepAlive": True,
        "ProcessType": "Background",
        "EnvironmentVariables": {
            "PATH": DEFAULT_PATH,
        },
        "StandardOutPath": str(logs_dir / "launchd.web.out.log"),
        "StandardErrorPath": str(logs_dir / "launchd.web.err.log"),
    }
    return plistlib.dumps(payload)


def remove_legacy_agent_plists(launchagents_dir: Path) -> list[str]:
    removed: list[str] = []
    for plist in launchagents_dir.glob("com.relayhub.worker.*.plist"):
        subprocess.run(["launchctl", "bootout", launchctl_domain(), str(plist)], capture_output=True, text=True)  # noqa: S603
        plist.unlink(missing_ok=True)
        removed.append(str(plist))
    return removed


def install_launchd(args: argparse.Namespace, runtime_root: Path, launchagents_dir: Path, app_root: Path) -> dict[str, Any]:
    app_bundle = stage_app_bundle(app_root)
    ensure_dir(launchagents_dir)
    logs_dir = runtime_root / "logs"
    ensure_dir(logs_dir)
    web_plist = launchagents_dir / "com.relayhub.web.plist"
    web_plist.write_bytes(build_web_plist(app_root, runtime_root, logs_dir, args.web_host, args.web_port))
    removed_legacy_agent_plists = remove_legacy_agent_plists(launchagents_dir)
    if args.load_services:
        launchctl_bootstrap(web_plist, "com.relayhub.web")
    return {
        "app_bundle": app_bundle,
        "launchagents_dir": str(launchagents_dir),
        "web_plist": str(web_plist),
        "removed_legacy_agent_plists": removed_legacy_agent_plists,
        "loaded": bool(args.load_services),
    }


def uninstall_launchd(launchagents_dir: Path) -> dict[str, Any]:
    web_plist = launchagents_dir / "com.relayhub.web.plist"
    unloaded_labels: list[str] = []
    if web_plist.exists():
        result = subprocess.run(  # noqa: S603
            ["launchctl", "bootout", launchctl_domain(), str(web_plist)],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            unloaded_labels.append("com.relayhub.web")
        web_plist.unlink(missing_ok=True)
    removed_legacy_agent_plists = remove_legacy_agent_plists(launchagents_dir)
    return {
        "launchagents_dir": str(launchagents_dir),
        "web_plist_removed": not web_plist.exists(),
        "unloaded_labels": unloaded_labels,
        "removed_legacy_agent_plists": removed_legacy_agent_plists,
    }


def uninstall_openclaw(openclaw_workspace: Path) -> dict[str, Any]:
    bridge_target = bridge_script_workspace_path(openclaw_workspace)
    config_file = openclaw_config_path(openclaw_workspace)
    alias_file = alias_map_path(openclaw_workspace)
    skill_dir = skill_path(openclaw_workspace).parent
    heartbeat_file = heartbeat_path(openclaw_workspace)
    relay_pid = openclaw_workspace / "data" / "relay_hub_web.pid"
    relay_log = openclaw_workspace / "log" / "relay_hub_web.log"

    bridge_removed = unlink_if_exists(bridge_target)
    config_removed = unlink_if_exists(config_file)
    alias_removed = unlink_if_exists(alias_file)
    pid_removed = unlink_if_exists(relay_pid)
    log_removed = unlink_if_exists(relay_log)
    skill_removed = remove_tree_if_exists(skill_dir)

    heartbeat_updated = False
    heartbeat_removed = False
    if heartbeat_file.exists():
        existing = heartbeat_file.read_text(encoding="utf-8")
        updated, removed = remove_marked_block(existing, HEARTBEAT_BEGIN, HEARTBEAT_END)
        if removed:
            heartbeat_updated = True
            if updated.strip():
                write_text(heartbeat_file, updated)
            else:
                heartbeat_file.unlink(missing_ok=True)
                heartbeat_removed = True

    prune_empty_parents(bridge_target.parent, openclaw_workspace / "scripts")
    prune_empty_parents(skill_dir, openclaw_workspace / "skills")
    prune_empty_parents(config_file.parent, openclaw_workspace / "data")
    prune_empty_parents(relay_log.parent, openclaw_workspace / "log")

    return {
        "openclaw_workspace": str(openclaw_workspace),
        "bridge_script_removed": bridge_removed,
        "config_removed": config_removed,
        "alias_map_removed": alias_removed,
        "skill_removed": skill_removed,
        "heartbeat_updated": heartbeat_updated,
        "heartbeat_removed": heartbeat_removed,
        "relay_pid_removed": pid_removed,
        "relay_log_removed": log_removed,
    }


def uninstall_host(runtime_root: Path, app_root: Path, launchagents_dir: Path) -> dict[str, Any]:
    launchd_payload = uninstall_launchd(launchagents_dir)
    app_removed = remove_tree_if_exists(app_root)
    runtime_removed = remove_tree_if_exists(runtime_root)
    return {
        "launchd": launchd_payload,
        "app_root": str(app_root),
        "app_removed": app_removed,
        "runtime_root": str(runtime_root),
        "runtime_removed": runtime_removed,
        "note": "OpenClaw workspace is untouched. Run uninstall-openclaw separately if you also want to remove channel-side Relay Hub files.",
    }


def install_status(
    args: argparse.Namespace,
    runtime_root: Path,
    openclaw_workspace: Path,
    launchagents_dir: Path,
    app_root: Path,
    codex_home: Path,
) -> dict[str, Any]:
    bridge_config = openclaw_config_path(openclaw_workspace)
    git_branch = None
    git_head = None
    repo_is_git = (REPO_ROOT / ".git").exists()
    if repo_is_git:
        branch_result = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=str(REPO_ROOT), capture_output=True, text=True)  # noqa: S603
        head_result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(REPO_ROOT), capture_output=True, text=True)  # noqa: S603
        if branch_result.returncode == 0:
            git_branch = branch_result.stdout.strip() or None
        if head_result.returncode == 0:
            git_head = head_result.stdout.strip() or None
    payload = {
        "version": VERSION,
        "repo_root": str(REPO_ROOT),
        "repo_is_git": repo_is_git,
        "git_branch": git_branch,
        "git_head": git_head,
        "python_executable": sys.executable,
        "python_version": sys.version.split()[0],
        "runtime_root": str(runtime_root),
        "runtime_exists": runtime_root.exists(),
        "app_root": str(app_root),
        "app_bundle_installed": app_bundle_installed(app_root),
        "openclaw_workspace": str(openclaw_workspace),
        "bridge_script_installed": bridge_script_workspace_path(openclaw_workspace).exists(),
        "bridge_config_installed": bridge_config.exists(),
        "skill_installed": skill_path(openclaw_workspace).exists(),
        "heartbeat_installed": heartbeat_block_installed(openclaw_workspace),
        "launchagents_dir": str(launchagents_dir),
        "web_plist_installed": (launchagents_dir / "com.relayhub.web.plist").exists(),
        "legacy_agent_plists_installed": sorted(str(path) for path in launchagents_dir.glob("com.relayhub.worker.*.plist")),
        "status_scope_note": "status only reports shared installation artifacts; current-host bootstrap must be judged from the installing AI's own completed host setup steps",
    }
    if bridge_config.exists():
        payload["bridge_config"] = json.loads(bridge_config.read_text(encoding="utf-8"))
    return payload


def launchd_loaded(label: str) -> bool:
    result = subprocess.run(["launchctl", "print", f"{launchctl_domain()}/{label}"], capture_output=True, text=True)  # noqa: S603
    return result.returncode == 0


def install_doctor(
    args: argparse.Namespace,
    runtime_root: Path,
    openclaw_workspace: Path,
    launchagents_dir: Path,
    app_root: Path,
    codex_home: Path,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def add_check(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "ok": ok, "detail": detail})

    add_check("python3", True, sys.executable)

    openclaw_cli = shutil.which("openclaw")
    add_check("openclaw_cli", bool(openclaw_cli), openclaw_cli or "openclaw not found in PATH")

    add_check(
        "openclaw_workspace",
        True,
        f"{openclaw_workspace} (will be created if missing)",
    )
    add_check("launchagents_dir_parent", launchagents_dir.parent.exists(), str(launchagents_dir.parent))
    add_check("app_root_parent", app_root.parent.exists(), str(app_root.parent))
    add_check("repo_runtime_parent", runtime_root.parent.exists(), str(runtime_root.parent))

    status = install_status(args, runtime_root, openclaw_workspace, launchagents_dir, app_root, codex_home)
    add_check(
        "git_repo",
        True,
        "git initialized" if status["repo_is_git"] else "git metadata not present; package install mode is still supported",
    )
    add_check(
        "web_base_url",
        True,
        resolved_web_base_url(args),
    )
    configured_delivery_channels = delivery_channels(args)
    add_check(
        "delivery_target",
        True,
        "at least one explicit delivery target provided"
        if configured_delivery_channels
        else (
            "no explicit delivery target provided; install-openclaw will auto-discover enabled OpenClaw channels when possible, "
            "and branch replies still default to the original trigger channel"
        ),
    )

    web_label = "com.relayhub.web"
    add_check("launchd_web_loaded", launchd_loaded(web_label), web_label)

    ok = all(check["ok"] for check in checks if check["name"] not in {"launchd_web_loaded"})
    return {
        "ok": ok,
        "version": VERSION,
        "checks": checks,
        "status": status,
    }


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    ensure_repo_root_allowed(args.command)
    runtime_root = resolve_path(args.runtime_root, DEFAULT_RUNTIME_ROOT)
    openclaw_workspace = resolve_path(args.openclaw_workspace, DEFAULT_OPENCLAW_WORKSPACE)
    launchagents_dir = resolve_path(args.launchagents_dir, DEFAULT_LAUNCHAGENTS_DIR)
    app_root = resolve_path(args.app_root, DEFAULT_APP_ROOT)
    codex_home = resolve_path(args.codex_home, DEFAULT_CODEX_HOME)

    if args.command == "status":
        output(install_status(args, runtime_root, openclaw_workspace, launchagents_dir, app_root, codex_home))
        return
    if args.command == "doctor":
        output(install_doctor(args, runtime_root, openclaw_workspace, launchagents_dir, app_root, codex_home))
        return

    payload: dict[str, Any] = {"ok": True}

    if args.command in {"install-host", "full"}:
        payload["runtime"] = bootstrap_runtime(args, runtime_root)

    if args.command in {"install-openclaw", "full"}:
        payload["openclaw"] = install_openclaw(args, runtime_root, openclaw_workspace, app_root)

    if args.command in {"install-host", "full"} and args.install_codex_host:
        payload["codex"] = install_codex(args, codex_home, app_root)

    if args.command in {"install-host", "install-launchd", "full"}:
        payload["launchd"] = install_launchd(args, runtime_root, launchagents_dir, app_root)

    if args.command in {"uninstall-openclaw", "uninstall"}:
        payload["openclaw"] = uninstall_openclaw(openclaw_workspace)

    if args.command in {"uninstall-host", "uninstall"}:
        payload["host"] = uninstall_host(runtime_root, app_root, launchagents_dir)

    if args.command == "uninstall-launchd":
        payload["launchd"] = uninstall_launchd(launchagents_dir)

    if args.command in {"uninstall-host", "uninstall"} and args.uninstall_codex_host:
        payload["codex"] = uninstall_codex(codex_home)

    output(payload)


if __name__ == "__main__":
    main()
