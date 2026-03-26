#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import plistlib
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
DEFAULT_PATH = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
DEFAULT_WEB_HOST = "0.0.0.0"
DEFAULT_WEB_PORT = 4317
VERSION = "0.1.0"
HEARTBEAT_BEGIN = "<!-- RELAY_HUB_BEGIN -->"
HEARTBEAT_END = "<!-- RELAY_HUB_END -->"


def output(payload: object) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_text(path: Path, content: str) -> None:
    ensure_dir(path.parent)
    path.write_text(content, encoding="utf-8")


def write_json(path: Path, payload: Any) -> None:
    write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def resolve_path(raw: str | None, default: Path) -> Path:
    return Path(raw).expanduser().resolve() if raw else default


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
    parser.add_argument("--feishu-target")
    parser.add_argument("--weixin-target")
    parser.add_argument("--weixin-account-id")
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
    parser.add_argument("--worker-agent", default="claude-code")
    parser.add_argument(
        "--worker-backend",
        default="claude-code",
        choices=["claude-code", "manual"],
        help="Bundled background worker backend. Use claude-code for the packaged Claude worker, or manual for non-bundled agents.",
    )
    parser.add_argument("--worker-workdir", help="Worker working directory. Defaults to repo parent.")
    parser.add_argument("--worker-poll-seconds", type=float, default=2.0)
    parser.add_argument("--launchagents-dir", help="launchd plist destination. Defaults to ~/Library/LaunchAgents.")
    parser.add_argument("--load-services", action="store_true", help="Bootstrap launchd services after writing plists.")
    parser.add_argument("--skip-heartbeat-patch", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Relay Hub installer and service manager")
    subparsers = parser.add_subparsers(dest="command", required=True)

    full_parser = subparsers.add_parser("full", help="Bootstrap runtime, install OpenClaw bridge, and install launchd services")
    add_shared_args(full_parser)

    oc_parser = subparsers.add_parser("install-openclaw", help="Install/update OpenClaw-side bridge files")
    add_shared_args(oc_parser)

    svc_parser = subparsers.add_parser("install-launchd", help="Install/update launchd plists for web and one worker")
    add_shared_args(svc_parser)

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
    if args.feishu_target:
        channels["feishu"] = {"target": args.feishu_target}
    if args.weixin_target:
        entry: dict[str, Any] = {"target": args.weixin_target}
        if args.weixin_account_id:
            entry["accountId"] = args.weixin_account_id
        channels["openclaw-weixin"] = entry
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


def bridge_script_repo_path() -> Path:
    return SCRIPTS_DIR / "relay_openclaw_bridge.py"


def bridge_script_workspace_path(openclaw_workspace: Path) -> Path:
    return openclaw_workspace / "scripts" / "relay_openclaw_bridge.py"


def openclaw_config_path(openclaw_workspace: Path) -> Path:
    return openclaw_workspace / "data" / "relay_hub_openclaw.json"


def alias_map_path(openclaw_workspace: Path) -> Path:
    return openclaw_workspace / "data" / "relay_hub_channel_aliases.json"


def heartbeat_path(openclaw_workspace: Path) -> Path:
    return openclaw_workspace / "HEARTBEAT.md"


def skill_path(openclaw_workspace: Path) -> Path:
    return openclaw_workspace / "skills" / "relay-hub-openclaw" / "SKILL.md"


def stage_app_bundle(app_root: Path) -> dict[str, Any]:
    ensure_dir(app_root)
    scripts_root = app_root / "scripts"
    ensure_dir(scripts_root)
    scripts = [
        "agent_relay.py",
        "codex_relay.py",
        "openclaw_relay.py",
        "relay_agent_worker.py",
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


def build_openclaw_config(args: argparse.Namespace, runtime_root: Path, openclaw_workspace: Path, app_root: Path) -> dict[str, Any]:
    channels = delivery_channels(args)
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
description: OpenClaw 的 Relay Hub 渠道路由技能。用于“打开 codex/claude/gemini/cursor/opencode 入口”“已录入”“状态”“退出 relay”这类请求，并把外部 agent 的回包通过 OpenClaw 已配置消息渠道发回用户。
---

# relay-hub-openclaw

这个 skill 只负责 OpenClaw 侧的渠道网关动作，不负责外部 agent 的主上下文，也不要自己翻 Relay Hub 的底层文件。

必须遵守
- 只调用固定脚本：`python3 {script_path} ...`
- 不要自己读取 `routes.json`、`config.json`、`messages/*.md`。
- 对桥接脚本的返回内容，优先原样发给用户，不要总结，不要改写，不要脑补成功。
- 当前主对话窗口不在 OpenClaw 里。OpenClaw 只负责“开入口、收已录入、查状态、退出、发回包”。
- 若无法可靠取到当前渠道目标，可省略 `--target`，桥接脚本会按当前实例配置回落到默认目标。

支持的对象名
- `codex`
- `claude` / `claude-code`
- `gemini` / `gemini-cli`
- `cursor` / `cursor-cli`
- `opencode`

对象名映射由桥接脚本处理；只要把用户提到的对象名传给 `--agent` 即可。

## 1. 打开入口

```bash
python3 {script_path} open-entry --agent "<agent>" --channel "<当前渠道>" --target "<当前目标>"
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

## 5. 外部回包发送

外部 agent 的回包由 heartbeat 里的发送泵统一处理：

```bash
python3 {script_path} pump-deliveries
```
"""


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


def bootstrap_runtime(args: argparse.Namespace, runtime_root: Path) -> dict[str, Any]:
    hub = RelayHub(runtime_root)
    config = hub.init_layout(
        web_base_url=resolved_web_base_url(args),
        queue_ack_timeout_seconds=args.queue_ack_timeout,
        default_channels=list(delivery_channels(args).keys()),
    )
    return {"runtime_root": str(runtime_root), "config": config}


def install_openclaw(args: argparse.Namespace, runtime_root: Path, openclaw_workspace: Path, app_root: Path) -> dict[str, Any]:
    app_bundle = stage_app_bundle(app_root)
    config = build_openclaw_config(args, runtime_root, openclaw_workspace, app_root)
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
        "app_bundle": app_bundle,
        "bridge_script": str(bridge_target),
        "config_path": str(config_file),
        "skill_path": str(skill_path(openclaw_workspace)),
        "heartbeat_path": str(heartbeat_file),
        "delivery_channels": config["delivery"]["channels"],
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


def build_worker_plist(
    app_root: Path,
    runtime_root: Path,
    logs_dir: Path,
    agent: str,
    backend: str,
    workdir: Path,
    config_path: Path,
    poll_seconds: float,
) -> tuple[str, bytes]:
    label = f"com.relayhub.worker.{agent}"
    payload = {
        "Label": label,
        "ProgramArguments": [
            sys.executable,
            str(app_root / "scripts" / "relay_agent_worker.py"),
            "--root",
            str(runtime_root),
            "--agent",
            agent,
            "--backend",
            backend,
            "--workdir",
            str(workdir),
            "--bridge-config",
            str(config_path),
            "--poll-seconds",
            str(poll_seconds),
            "serve",
        ],
        "WorkingDirectory": str(app_root),
        "RunAtLoad": True,
        "KeepAlive": True,
        "ProcessType": "Background",
        "EnvironmentVariables": {
            "PATH": DEFAULT_PATH,
        },
        "StandardOutPath": str(logs_dir / f"launchd.worker.{agent}.out.log"),
        "StandardErrorPath": str(logs_dir / f"launchd.worker.{agent}.err.log"),
    }
    return label, plistlib.dumps(payload)


def install_launchd(args: argparse.Namespace, runtime_root: Path, openclaw_workspace: Path, launchagents_dir: Path, app_root: Path) -> dict[str, Any]:
    app_bundle = stage_app_bundle(app_root)
    ensure_dir(launchagents_dir)
    logs_dir = runtime_root / "logs"
    ensure_dir(logs_dir)
    web_plist = launchagents_dir / "com.relayhub.web.plist"
    worker_plist = launchagents_dir / f"com.relayhub.worker.{args.worker_agent}.plist"
    web_plist.write_bytes(build_web_plist(app_root, runtime_root, logs_dir, args.web_host, args.web_port))
    worker_label = f"com.relayhub.worker.{args.worker_agent}"
    worker_written = False
    if args.worker_backend == "claude-code":
        worker_label, worker_bytes = build_worker_plist(
            app_root=app_root,
            runtime_root=runtime_root,
            logs_dir=logs_dir,
            agent=args.worker_agent,
            backend=args.worker_backend,
            workdir=resolve_path(args.worker_workdir, REPO_ROOT.parent),
            config_path=openclaw_config_path(openclaw_workspace),
            poll_seconds=args.worker_poll_seconds,
        )
        worker_plist.write_bytes(worker_bytes)
        worker_written = True
    elif worker_plist.exists():
        worker_plist.unlink()
    if args.load_services:
        launchctl_bootstrap(web_plist, "com.relayhub.web")
        if worker_written:
            launchctl_bootstrap(worker_plist, worker_label)
    return {
        "app_bundle": app_bundle,
        "launchagents_dir": str(launchagents_dir),
        "web_plist": str(web_plist),
        "worker_plist": str(worker_plist) if worker_written else None,
        "worker_backend": args.worker_backend,
        "worker_installed": worker_written,
        "loaded": bool(args.load_services),
    }


def install_status(args: argparse.Namespace, runtime_root: Path, openclaw_workspace: Path, launchagents_dir: Path, app_root: Path) -> dict[str, Any]:
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
        "app_bundle_installed": (app_root / "scripts" / "relay_web.py").exists() and (app_root / "scripts" / "relay_agent_worker.py").exists() and (app_root / "relay_hub").exists(),
        "openclaw_workspace": str(openclaw_workspace),
        "bridge_script_installed": bridge_script_workspace_path(openclaw_workspace).exists(),
        "bridge_config_installed": bridge_config.exists(),
        "skill_installed": skill_path(openclaw_workspace).exists(),
        "heartbeat_installed": heartbeat_path(openclaw_workspace).exists(),
        "launchagents_dir": str(launchagents_dir),
        "web_plist_installed": (launchagents_dir / "com.relayhub.web.plist").exists(),
        "worker_plist_installed": (launchagents_dir / f"com.relayhub.worker.{args.worker_agent}.plist").exists(),
    }
    if bridge_config.exists():
        payload["bridge_config"] = json.loads(bridge_config.read_text(encoding="utf-8"))
    return payload


def backend_command(backend: str) -> str | None:
    if backend == "claude-code":
        return "claude"
    if backend == "manual":
        return None
    return None


def launchd_loaded(label: str) -> bool:
    result = subprocess.run(["launchctl", "print", f"{launchctl_domain()}/{label}"], capture_output=True, text=True)  # noqa: S603
    return result.returncode == 0


def claude_auth_ready() -> dict[str, Any]:
    cli = shutil.which("claude")
    if not cli:
        return {"ok": False, "detail": "claude not found"}
    result = subprocess.run(["claude", "auth", "status"], capture_output=True, text=True)  # noqa: S603
    text = (result.stdout or result.stderr or "").strip()
    logged_in = "loggedIn: true" in text or '"loggedIn": true' in text
    return {
        "ok": logged_in,
        "detail": "logged in" if logged_in else (text.splitlines()[-1] if text else "not logged in"),
    }


def install_doctor(args: argparse.Namespace, runtime_root: Path, openclaw_workspace: Path, launchagents_dir: Path, app_root: Path) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def add_check(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "ok": ok, "detail": detail})

    add_check("python3", True, sys.executable)

    openclaw_cli = shutil.which("openclaw")
    add_check("openclaw_cli", bool(openclaw_cli), openclaw_cli or "openclaw not found in PATH")

    backend_cli = backend_command(args.worker_backend)
    if backend_cli:
        backend_path = shutil.which(backend_cli)
        add_check(f"{backend_cli}_cli", bool(backend_path), backend_path or f"{backend_cli} not found in PATH")
        if backend_cli == "claude" and backend_path:
            auth = claude_auth_ready()
            add_check("claude_auth", auth["ok"], auth["detail"])
    else:
        add_check("worker_backend", True, f"{args.worker_backend} backend selected; no bundled worker CLI required")

    add_check("openclaw_workspace", openclaw_workspace.exists(), str(openclaw_workspace))
    add_check("launchagents_dir_parent", launchagents_dir.parent.exists(), str(launchagents_dir.parent))
    add_check("app_root_parent", app_root.parent.exists(), str(app_root.parent))
    add_check("repo_runtime_parent", runtime_root.parent.exists(), str(runtime_root.parent))

    status = install_status(args, runtime_root, openclaw_workspace, launchagents_dir, app_root)
    add_check("git_repo", status["repo_is_git"], "git initialized" if status["repo_is_git"] else "run `git init -b main` in relay-hub")
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
        else "no explicit delivery target provided; replies will default to the original trigger channel",
    )

    web_label = "com.relayhub.web"
    worker_label = f"com.relayhub.worker.{args.worker_agent}"
    add_check("launchd_web_loaded", launchd_loaded(web_label), web_label)
    if args.worker_backend == "manual":
        add_check("launchd_worker_loaded", True, "manual backend selected; no worker launchd service expected")
    else:
        add_check("launchd_worker_loaded", launchd_loaded(worker_label), worker_label)

    ok = all(check["ok"] for check in checks if check["name"] not in {"launchd_web_loaded", "launchd_worker_loaded"})
    return {
        "ok": ok,
        "version": VERSION,
        "checks": checks,
        "status": status,
    }


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    runtime_root = resolve_path(args.runtime_root, DEFAULT_RUNTIME_ROOT)
    openclaw_workspace = resolve_path(args.openclaw_workspace, DEFAULT_OPENCLAW_WORKSPACE)
    launchagents_dir = resolve_path(args.launchagents_dir, DEFAULT_LAUNCHAGENTS_DIR)
    app_root = resolve_path(args.app_root, DEFAULT_APP_ROOT)

    if args.command == "status":
        output(install_status(args, runtime_root, openclaw_workspace, launchagents_dir, app_root))
        return
    if args.command == "doctor":
        output(install_doctor(args, runtime_root, openclaw_workspace, launchagents_dir, app_root))
        return

    runtime_payload = bootstrap_runtime(args, runtime_root)
    payload: dict[str, Any] = {
        "ok": True,
        "runtime": runtime_payload,
    }

    if args.command in {"install-openclaw", "full"}:
        payload["openclaw"] = install_openclaw(args, runtime_root, openclaw_workspace, app_root)

    if args.command in {"install-launchd", "full"}:
        payload["launchd"] = install_launchd(args, runtime_root, openclaw_workspace, launchagents_dir, app_root)

    output(payload)


if __name__ == "__main__":
    main()
