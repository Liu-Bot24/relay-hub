#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import socket
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

DEFAULT_CONFIG_PATH = Path.home() / ".openclaw" / "workspace" / "data" / "relay_hub_openclaw.json"
RECENT_SEND_DEDUPE_SECONDS = 2.0
RECENT_NOTIFY_DEDUPE_SECONDS = 60.0

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent


def bootstrap_import_paths() -> None:
    candidates: list[Path] = [PROJECT_ROOT]
    config_path = DEFAULT_CONFIG_PATH
    try:
        if config_path.exists():
            config = json.loads(config_path.read_text(encoding="utf-8"))
            app_root = Path(((config.get("relayHub") or {}).get("appRoot") or "")).expanduser()
            if app_root:
                candidates.append(app_root.resolve())
    except Exception:
        # Keep import bootstrapping best-effort; runtime argument validation will surface
        # any real configuration issues later.
        pass
    for candidate in candidates:
        text = str(candidate)
        if text and text not in sys.path:
            sys.path.insert(0, text)


bootstrap_import_paths()

from relay_hub import RelayHub
from relay_hub.message_text import delivery_footer, relay_help_text

AGENT_ALIASES = {
    "codex": "codex",
    "claude": "claude-code",
    "claude-code": "claude-code",
    "gemini": "gemini-cli",
    "gemini-cli": "gemini-cli",
    "cursor": "cursor-cli",
    "cursor-cli": "cursor-cli",
    "opencode": "opencode",
}

INVALID_MAIN_SESSION_REFS = {
    "main-current",
    "current-main",
    "current-session",
}


def load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def resolve_config_path(raw: str | None) -> Path:
    value = raw or os.environ.get("RELAY_HUB_OPENCLAW_CONFIG")
    return Path(value).expanduser().resolve() if value else DEFAULT_CONFIG_PATH


def load_config(config_path: Path) -> dict[str, Any]:
    config = load_json(config_path)
    if not config:
        raise SystemExit(f"missing config: {config_path}")
    return config


def relay_runtime_root(config: dict[str, Any]) -> Path:
    return Path(config["relayHub"]["runtimeRoot"]).expanduser().resolve()


def openclaw_relay_script(config: dict[str, Any]) -> Path:
    return Path(config["relayHub"]["openclawRelayScript"]).expanduser().resolve()


def relay_web_script(config: dict[str, Any]) -> Path:
    return Path(config["relayHub"]["relayWebScript"]).expanduser().resolve()


def alias_map_path(config: dict[str, Any]) -> Path:
    return Path(config["aliases"]["path"]).expanduser().resolve()


def send_trace_path(config: dict[str, Any]) -> Path:
    return alias_map_path(config).with_name("relay_hub_send_trace.jsonl")


def normalize_agent(raw: str) -> str:
    key = raw.strip().lower()
    return AGENT_ALIASES.get(key, key)


def sanitize_main_session_ref(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    if text.lower() in INVALID_MAIN_SESSION_REFS:
        return None
    return text


def output(payload: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    if "user_message" in payload:
        print(payload["user_message"])
        return
    if "message" in payload:
        print(payload["message"])
        return
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def fail(message: str, as_json: bool = False, exit_code: int = 1) -> None:
    payload = {"ok": False, "user_message": message}
    output(payload, as_json)
    raise SystemExit(exit_code)


def resolve_channel_target(
    config: dict[str, Any],
    channel: str,
    target: str | None,
) -> tuple[str, str]:
    channel_key = channel.strip()
    channel_config = (config.get("delivery") or {}).get("channels", {}).get(channel_key, {})
    resolved_target = target or channel_config.get("target")
    if not resolved_target:
        raise SystemExit(f"missing target for channel {channel_key}")
    return channel_key, resolved_target


def read_optional_text(body: str | None, body_file: str | None) -> str | None:
    if body is not None:
        return body
    if body_file is not None:
        return Path(body_file).read_text(encoding="utf-8")
    return None


def delivery_account_for_channel(config: dict[str, Any], channel: str) -> str | None:
    return ((config.get("delivery") or {}).get("channels", {}).get(channel, {}) or {}).get("accountId")


def ensure_runtime_config(config: dict[str, Any]) -> None:
    runtime_root = relay_runtime_root(config)
    runtime_root.mkdir(parents=True, exist_ok=True)
    config_path = runtime_root / "config.json"
    existing = load_json(config_path, {}) or {}
    desired = {
        "version": existing.get("version", 1),
        "relay_root": str(runtime_root),
        "web_base_url": str(config["web"]["baseUrl"]).rstrip("/"),
        "default_delivery": {
            "mode": config.get("delivery", {}).get("defaultMode", "all"),
            "channels": list((config.get("delivery", {}).get("channels") or {}).keys()),
        },
        "queue_ack_timeout_seconds": config.get("queueAckTimeoutSeconds", 15),
    }
    if existing != desired:
        atomic_write_json(config_path, desired)


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def new_branch_ref() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(2)


def alias_key(channel: str, target: str) -> str:
    return f"{channel}::{target}"


def load_alias_map(config: dict[str, Any]) -> dict[str, Any]:
    return load_json(alias_map_path(config), {"version": 1, "updated_at": None, "aliases": {}}) or {
        "version": 1,
        "updated_at": None,
        "aliases": {},
    }


def save_alias_map(config: dict[str, Any], payload: dict[str, Any]) -> None:
    payload["updated_at"] = now_iso()
    atomic_write_json(alias_map_path(config), payload)


def append_send_trace(config: dict[str, Any], payload: dict[str, Any]) -> None:
    path = send_trace_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "recorded_at": now_iso(),
        "pid": os.getpid(),
        "ppid": os.getppid(),
        "argv": sys.argv,
        **payload,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def register_channel_aliases(
    config: dict[str, Any],
    session_key: str,
    origin_channel: str,
    origin_target: str,
    delivery_channels: list[str],
) -> dict[str, Any]:
    alias_map = load_alias_map(config)
    aliases = alias_map.setdefault("aliases", {})
    registered: list[dict[str, str]] = []
    candidates: list[tuple[str, str]] = [(origin_channel, origin_target)]
    for channel in delivery_channels:
        channel_config = (config.get("delivery") or {}).get("channels", {}).get(channel, {})
        target = channel_config.get("target")
        if target:
            candidates.append((channel, target))
    candidate_keys = {alias_key(channel, target) for channel, target in candidates}
    stale_keys = [
        key
        for key, record in aliases.items()
        if record.get("session_key") == session_key and key not in candidate_keys
    ]
    for key in stale_keys:
        aliases.pop(key, None)
    seen: set[str] = set()
    for channel, target in candidates:
        key = alias_key(channel, target)
        if key in seen:
            continue
        seen.add(key)
        aliases[key] = {
            "session_key": session_key,
            "channel": channel,
            "target": target,
            "updated_at": now_iso(),
        }
        registered.append({"channel": channel, "target": target})
    save_alias_map(config, alias_map)
    return {"session_key": session_key, "registered": registered}


def resolve_session_alias(config: dict[str, Any], channel: str, target: str) -> str | None:
    alias_map = load_alias_map(config)
    record = (alias_map.get("aliases") or {}).get(alias_key(channel, target))
    if not record:
        return None
    return record.get("session_key")


def can_connect(host: str, port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def ensure_web_running(config: dict[str, Any]) -> bool:
    host = str(config["web"].get("host", "127.0.0.1"))
    port = int(config["web"].get("port", 4317))
    if can_connect("127.0.0.1", port):
        return False
    log_path = Path(config["web"]["logPath"]).expanduser().resolve()
    pid_path = Path(config["web"]["pidPath"]).expanduser().resolve()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        str(relay_web_script(config)),
        "--root",
        str(relay_runtime_root(config)),
        "--host",
        host,
        "--port",
        str(port),
    ]
    with log_path.open("ab") as handle:
        proc = subprocess.Popen(  # noqa: S603
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    pid_path.write_text(str(proc.pid), encoding="utf-8")
    deadline = time.time() + float(config["web"].get("startupWaitSeconds", 5))
    while time.time() < deadline:
        if can_connect("127.0.0.1", port):
            return True
        time.sleep(0.2)
    raise SystemExit(f"relay web did not start on port {port}")


def run_command(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True)  # noqa: S603


def summarize_error_text(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict):
            for key in ("user_message", "message", "error"):
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return "command failed"
    last = lines[-1]
    for prefix in ("FileNotFoundError: ", "ValueError: ", "RuntimeError: "):
        if last.startswith(prefix):
            return last.removeprefix(prefix)
    return last


def run_openclaw_relay(config: dict[str, Any], args: list[str]) -> dict[str, Any]:
    cmd = [
        sys.executable,
        str(openclaw_relay_script(config)),
        "--root",
        str(relay_runtime_root(config)),
        *args,
    ]
    result = run_command(cmd)
    if result.returncode != 0:
        text = result.stderr or result.stdout or "openclaw_relay failed"
        raise SystemExit(summarize_error_text(text))
    return json.loads(result.stdout)


def extract_openclaw_error(result: subprocess.CompletedProcess[str]) -> str:
    lines = [line.strip() for line in (result.stderr + "\n" + result.stdout).splitlines() if line.strip()]
    return lines[-1] if lines else "openclaw message send failed"


def send_message(channel: str, target: str, message: str, account_id: str | None = None) -> None:
    cmd = [
        "openclaw",
        "message",
        "send",
        "--channel",
        channel,
        "--target",
        target,
        "--message",
        message,
    ]
    if account_id:
        cmd.extend(["--account", account_id])
    result = run_command(cmd)
    if result.returncode != 0:
        raise SystemExit(extract_openclaw_error(result))


def build_notify_text(agent: str, kind: str, body: str | None = None) -> str:
    raise RuntimeError("build_notify_text requires an ensured entry and should not be called directly")


def build_notify_text_without_entry(agent: str, kind: str, body: str | None = None) -> str:
    if kind != "shutdown":
        raise RuntimeError("build_notify_text_without_entry only supports shutdown")
    lines = [
        f"{agent} 已退出 Relay Hub。",
        "当前主窗口回复不再同步到 OpenClaw。",
        "如需重新接入，请回主窗口说：接入 Relay Hub。",
    ]
    if body:
        lines.extend(
            [
                "",
                body.rstrip(),
            ]
        )
    return "\n".join(lines)


def build_notify_text_with_entry(agent: str, web_url: str, kind: str, body: str | None = None) -> str:
    if kind == "startup":
        lines = [
            f"{agent} 已接入 Relay Hub。",
            "当前主窗口会继续正常对话；如果你暂时离开电脑，直接点下面网页录入即可。",
        ]
        if body:
            lines.extend(
                [
                    "",
                    body.rstrip(),
                ]
            )
        lines.extend(
            [
            delivery_footer(web_url, agent),
            "第一次在网页里保存消息时，branch 才正式开始。",
            ]
        )
        return "\n".join(lines)
    lines = [
        (body or "").rstrip(),
        "",
        delivery_footer(web_url, agent),
    ]
    return "\n".join(lines).strip()


def configured_delivery_channels(
    config: dict[str, Any],
    *,
    exclude_origin_channel: str | None = None,
    exclude_origin_target: str | None = None,
) -> list[tuple[str, str, str | None]]:
    results: list[tuple[str, str, str | None]] = []
    channels_config = (config.get("delivery") or {}).get("channels") or {}
    for channel, channel_config in channels_config.items():
        channel_key = str(channel or "").strip()
        target = str(channel_config.get("target") or "").strip()
        if not channel_key or not target:
            continue
        if (
            exclude_origin_channel
            and exclude_origin_target
            and channel_key == exclude_origin_channel
            and target == exclude_origin_target
        ):
            continue
        results.append((channel_key, target, channel_config.get("accountId")))
    return results


def configured_delivery_channel_names(
    config: dict[str, Any],
    *,
    exclude_origin_channel: str | None = None,
    exclude_origin_target: str | None = None,
) -> list[str]:
    return [
        channel
        for channel, _target, _account_id in configured_delivery_channels(
            config,
            exclude_origin_channel=exclude_origin_channel,
            exclude_origin_target=exclude_origin_target,
        )
    ]


def notify_entry_strategy(
    config: dict[str, Any],
    agent: str,
    channel: str,
    target: str,
    aliased_session: str | None,
    *,
    preferred_main_session_ref: str | None = None,
) -> dict[str, Any]:
    hub = RelayHub(relay_runtime_root(config))
    hub.init_layout()
    current_main_session_ref = sanitize_main_session_ref(preferred_main_session_ref) or sanitize_main_session_ref((hub.get_agent(agent) or {}).get("current_main_session_ref"))
    if not aliased_session:
        return {
            "current_main_session_ref": current_main_session_ref,
            "reuse_session_key": None,
            "branch_ref": new_branch_ref() if current_main_session_ref else None,
            "reason": "no_existing_alias",
        }
    session = hub.get_session(aliased_session)
    existing_main_session_ref = ((session.get("meta") or {}).get("main_session_ref"))
    if current_main_session_ref and existing_main_session_ref and existing_main_session_ref != current_main_session_ref:
        return {
            "current_main_session_ref": current_main_session_ref,
            "reuse_session_key": None,
            "branch_ref": new_branch_ref(),
            "reason": "alias_bound_to_different_main_session",
            "previous_session_key": aliased_session,
            "previous_main_session_ref": existing_main_session_ref,
        }
    return {
        "current_main_session_ref": current_main_session_ref,
        "reuse_session_key": aliased_session,
        "branch_ref": None,
        "reason": "reuse_existing_alias",
        "previous_session_key": aliased_session,
        "previous_main_session_ref": existing_main_session_ref,
    }


def ensure_notify_entry(
    config: dict[str, Any],
    agent: str,
    *,
    main_session_ref: str | None = None,
    project_root: str | None = None,
    development_log_path: str | None = None,
) -> dict[str, Any]:
    ensure_runtime_config(config)
    web_started = ensure_web_running(config)
    origin = resolve_notify_origin(
        config,
        agent=agent,
        preferred_main_session_ref=main_session_ref,
    )
    channel = str(origin.get("channel") or "").strip()
    target = str(origin.get("target") or "").strip()
    if not channel or not target:
        return {
            "ok": True,
            "skipped": True,
            "reason": "no_notify_origin",
            "notify_origin": origin,
            "user_message": "当前还没有可复用的 OpenClaw 渠道对象，也没有配置默认提醒渠道，已跳过提醒发送。",
        }
    relay_args = [
        "open-entry",
        "--agent",
        agent,
        "--channel",
        channel,
        "--target",
        target,
    ]
    configured_channels = configured_delivery_channel_names(
        config,
        exclude_origin_channel=channel,
        exclude_origin_target=target,
    )
    if configured_channels:
        relay_args.extend(["--delivery-mode", "all", "--delivery-channels", *configured_channels])
    if origin.get("reuse_session_key"):
        strategy = {
            "current_main_session_ref": origin.get("current_main_session_ref"),
            "reuse_session_key": origin.get("reuse_session_key"),
            "branch_ref": None,
            "reason": origin.get("source"),
        }
        relay_args.extend(["--session-key", str(origin["reuse_session_key"])])
    else:
        aliased_session = resolve_session_alias(config, channel, target)
        strategy = notify_entry_strategy(
            config,
            agent,
            channel,
            target,
            aliased_session,
            preferred_main_session_ref=main_session_ref,
        )
        if strategy.get("reuse_session_key"):
            relay_args.extend(["--session-key", str(strategy["reuse_session_key"])])
        elif strategy.get("branch_ref"):
            relay_args.extend(["--branch-ref", str(strategy["branch_ref"])])
    if strategy.get("current_main_session_ref"):
        main_session_ref_source = "notify-explicit-session" if main_session_ref else "agent-active-session"
        relay_args.extend(
            [
                "--main-session-ref",
                str(strategy["current_main_session_ref"]),
                "--main-session-ref-source",
                main_session_ref_source,
            ]
        )
    if project_root:
        relay_args.extend(["--project-root", project_root])
    if development_log_path:
        relay_args.extend(["--development-log-path", development_log_path])
    payload = run_openclaw_relay(config, relay_args)
    payload["aliases"] = register_channel_aliases(
        config,
        session_key=payload["branch"]["session_key"],
        origin_channel=channel,
        origin_target=target,
        delivery_channels=list((payload["branch"]["meta"].get("default_delivery") or {}).get("channels") or []),
    )
    payload["resolved"] = {"channel": channel, "target": target}
    if origin.get("session") and origin["session"].get("session_key"):
        payload["resolved"]["previous_session"] = origin["session"]["session_key"]
    payload["notify_entry_strategy"] = strategy
    payload["notify_origin"] = origin
    payload["web_started"] = web_started
    return payload


def original_delivery_destination(
    config: dict[str, Any],
    delivery: dict[str, Any],
) -> tuple[str, str, str | None] | None:
    channel = str(delivery.get("channel") or "").strip()
    target = str(delivery.get("target") or "").strip()
    if not channel or not target:
        return None
    return channel, target, delivery_account_for_channel(config, channel)


def configured_mirror_destinations(
    config: dict[str, Any],
    delivery: dict[str, Any],
) -> list[tuple[str, str, str | None]]:
    default_delivery = delivery.get("default_delivery") or {}
    destinations: list[tuple[str, str, str | None]] = []
    for channel in default_delivery.get("channels") or []:
        channel_key = str(channel or "").strip()
        if not channel_key:
            continue
        channel_config = (config.get("delivery") or {}).get("channels", {}).get(channel_key, {})
        target = str(channel_config.get("target") or "").strip()
        if not target:
            continue
        destinations.append((channel_key, target, channel_config.get("accountId")))
    return destinations


def dedupe_delivery_destinations(
    destinations: list[tuple[str, str, str | None]],
) -> list[tuple[str, str, str | None]]:
    ordered: list[tuple[str, str, str | None]] = []
    seen: set[tuple[str, str, str | None]] = set()
    for destination in destinations:
        if destination in seen:
            continue
        seen.add(destination)
        ordered.append(destination)
    return ordered


def parse_timestamp(value: Any) -> datetime:
    text = str(value or "").strip()
    if not text:
        return datetime.fromtimestamp(0).astimezone()
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return datetime.fromtimestamp(0).astimezone()


def sessions_for_main_session(
    hub: RelayHub,
    *,
    agent: str,
    main_session_ref: str,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for session in hub.list_sessions():
        if session.get("agent") != agent:
            continue
        if session.get("main_session_ref") != main_session_ref:
            continue
        if not session.get("channel") or not session.get("target"):
            continue
        candidates.append(session)
    candidates.sort(
        key=lambda session: (
            1 if session.get("mode") == "relay" else 0,
            parse_timestamp((session.get("route") or {}).get("updated_at")),
            parse_timestamp(session.get("last_merged_back_at")),
            parse_timestamp(session.get("branch_started_at")),
            parse_timestamp(session.get("entry_opened_at")),
        ),
        reverse=True,
    )
    return candidates


def resolve_notify_origin(
    config: dict[str, Any],
    *,
    agent: str,
    preferred_main_session_ref: str | None = None,
) -> dict[str, Any]:
    hub = RelayHub(relay_runtime_root(config))
    hub.init_layout()
    current_main_session_ref = sanitize_main_session_ref(preferred_main_session_ref) or sanitize_main_session_ref(
        (hub.get_agent(agent) or {}).get("current_main_session_ref")
    )
    if current_main_session_ref:
        sessions = sessions_for_main_session(
            hub,
            agent=agent,
            main_session_ref=current_main_session_ref,
        )
        if sessions:
            chosen = sessions[0]
            return {
                "source": "main_session_session",
                "current_main_session_ref": current_main_session_ref,
                "channel": chosen.get("channel"),
                "target": chosen.get("target"),
                "reuse_session_key": chosen.get("session_key"),
                "session": chosen,
            }
    configured = configured_delivery_channels(config)
    if configured:
        channel, target, _account_id = configured[0]
        return {
            "source": "configured_fallback",
            "current_main_session_ref": current_main_session_ref,
            "channel": channel,
            "target": target,
            "reuse_session_key": None,
            "session": None,
        }
    return {
        "source": "unavailable",
        "current_main_session_ref": current_main_session_ref,
        "channel": None,
        "target": None,
        "reuse_session_key": None,
        "session": None,
    }


def notify_destinations(
    config: dict[str, Any],
    *,
    agent: str,
    origin_channel: str | None,
    origin_target: str | None,
) -> list[tuple[str, str, str | None]]:
    hub = RelayHub(relay_runtime_root(config))
    hub.init_layout()
    configured = configured_delivery_channels(config)
    channels_to_check: list[str] = []
    if origin_channel:
        channels_to_check.append(origin_channel)
    channels_to_check.extend(channel for channel, _target, _account_id in configured if channel not in channels_to_check)
    enabled = set(hub.effective_notification_channels(agent, channels_to_check))
    destinations: list[tuple[str, str, str | None]] = []
    if origin_channel and origin_target and origin_channel in enabled:
        destinations.append(
            (
                origin_channel,
                origin_target,
                delivery_account_for_channel(config, origin_channel),
            )
        )
    destinations.extend(
        (channel, target, account_id)
        for channel, target, account_id in configured
        if channel in enabled
    )
    return dedupe_delivery_destinations(destinations)


def add_locator_args(parser: argparse.ArgumentParser, require_channel: bool = True) -> None:
    parser.add_argument("--channel", required=require_channel)
    parser.add_argument("--target")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="OpenClaw Relay Hub bridge")
    parser.add_argument(
        "--config",
        help="Path to relay_hub_openclaw.json. Defaults to ~/.openclaw/workspace/data/relay_hub_openclaw.json or RELAY_HUB_OPENCLAW_CONFIG.",
    )
    parser.add_argument("--json", action="store_true", help="Output JSON instead of plain text")
    subparsers = parser.add_subparsers(dest="command", required=True)

    open_parser = subparsers.add_parser("open-entry", help="Open or reuse one relay branch for OpenClaw")
    open_parser.add_argument("--agent", required=True)
    add_locator_args(open_parser)
    open_parser.add_argument("--branch-mode", choices=["reuse", "new"])

    dispatch_parser = subparsers.add_parser("dispatch-input", help="Queue one relay branch after user input")
    add_locator_args(dispatch_parser)
    dispatch_parser.add_argument("--wait-claim", action="store_true")
    dispatch_parser.add_argument("--timeout-seconds", type=int, default=15)

    status_parser = subparsers.add_parser("session-status", help="Show relay branch status")
    add_locator_args(status_parser)

    pump_parser = subparsers.add_parser("pump-deliveries", help="Send pending relay deliveries via OpenClaw channels")
    pump_parser.add_argument("--channel")
    pump_parser.add_argument("--target")

    notify_parser = subparsers.add_parser("notify", help="Send a reminder-only message via configured OpenClaw channels")
    notify_parser.add_argument("--agent", required=True)
    notify_parser.add_argument("--kind", choices=["startup", "message", "shutdown"], default="message")
    notify_parser.add_argument("--main-session-ref")
    notify_parser.add_argument("--project-root")
    notify_parser.add_argument("--development-log-path")
    notify_group = notify_parser.add_mutually_exclusive_group()
    notify_group.add_argument("--body")
    notify_group.add_argument("--body-file")

    help_parser = subparsers.add_parser("relay-help", help="Return the fixed Relay Hub command catalog")
    help_parser.add_argument("--agent")

    return parser


def handle_open_entry(config: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    ensure_runtime_config(config)
    web_started = ensure_web_running(config)
    channel, target = resolve_channel_target(config, args.channel, args.target)
    aliased_session = resolve_session_alias(config, channel, target)
    if aliased_session and not args.branch_mode:
        existing_payload = run_openclaw_relay(
            config,
            [
                "session-status",
                "--session",
                aliased_session,
            ],
        )
        existing_session = existing_payload.get("session") or {}
        existing_meta = existing_session.get("meta") or {}
        existing_state = existing_session.get("state") or {}
        return {
            "ok": False,
            "needs_branch_mode_choice": True,
            "resolved": {
                "channel": channel,
                "target": target,
                "session": aliased_session,
            },
            "existing_branch": {
                "session_key": aliased_session,
                "agent": existing_meta.get("agent"),
                "status": existing_state.get("status"),
                "web_url": existing_meta.get("web_url"),
            },
            "user_message": (
                f"当前渠道对象已经有一个 branch：{aliased_session}\n"
                f"当前对象：{existing_meta.get('agent') or '未知'}，状态：{existing_state.get('status') or '未知'}\n"
                "请明确选择：回复“复用入口”继续使用旧 branch，或回复“新建入口”创建全新 branch。"
            ),
        }
    relay_args = [
        "open-entry",
        "--agent",
        normalize_agent(args.agent),
        "--channel",
        channel,
        "--target",
        target,
    ]
    configured_channels = configured_delivery_channel_names(
        config,
        exclude_origin_channel=channel,
        exclude_origin_target=target,
    )
    if configured_channels:
        relay_args.extend(["--delivery-mode", "all", "--delivery-channels", *configured_channels])
    if aliased_session and args.branch_mode == "reuse":
        relay_args.extend(["--session-key", aliased_session])
    elif args.branch_mode == "new":
        relay_args.extend(["--branch-ref", new_branch_ref()])
    payload = run_openclaw_relay(config, relay_args)
    payload["aliases"] = register_channel_aliases(
        config,
        session_key=payload["branch"]["session_key"],
        origin_channel=channel,
        origin_target=target,
        delivery_channels=list((payload["branch"]["meta"].get("default_delivery") or {}).get("channels") or []),
    )
    payload["resolved"] = {"channel": channel, "target": target}
    if aliased_session:
        payload["resolved"]["previous_session"] = aliased_session
    payload["web_started"] = web_started
    return payload


def handle_dispatch(config: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    ensure_runtime_config(config)
    channel, target = resolve_channel_target(config, args.channel, args.target)
    aliased_session = resolve_session_alias(config, channel, target)
    relay_args = ["dispatch-input"]
    if aliased_session:
        relay_args.extend(["--session", aliased_session])
    else:
        relay_args.extend(["--channel", channel, "--target", target])
    if args.wait_claim:
        relay_args.extend(
            [
                "--wait-claim",
                "--timeout-seconds",
                str(args.timeout_seconds),
            ]
        )
    payload = run_openclaw_relay(config, relay_args)
    payload["resolved"] = {"channel": channel, "target": target}
    if aliased_session:
        payload["resolved"]["session"] = aliased_session
    return payload


def handle_status(config: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    ensure_runtime_config(config)
    channel, target = resolve_channel_target(config, args.channel, args.target)
    aliased_session = resolve_session_alias(config, channel, target)
    relay_args = ["session-status"]
    if aliased_session:
        relay_args.extend(["--session", aliased_session])
    else:
        relay_args.extend(["--channel", channel, "--target", target])
    payload = run_openclaw_relay(config, relay_args)
    session = payload.get("session") or {}
    meta = session.get("meta") or {}
    if not meta.get("session_key"):
        raise SystemExit(f"session {channel}__{target} does not exist")
    payload["resolved"] = {"channel": channel, "target": target}
    if aliased_session:
        payload["resolved"]["session"] = aliased_session
    return payload


def handle_pump(config: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    ensure_runtime_config(config)
    relay_args = ["pull-deliveries"]
    if args.channel:
        channel, target = resolve_channel_target(config, args.channel, args.target)
        relay_args.extend(["--channel", channel, "--target", target])
    deliveries_payload = run_openclaw_relay(config, relay_args)
    deliveries = deliveries_payload.get("deliveries") or []
    if not deliveries:
        return {"ok": True, "message": "RELAY_PUMP_IDLE", "sent_count": 0, "deliveries": []}
    hub = RelayHub(relay_runtime_root(config))
    hub.init_layout()
    sent_count = 0
    sent_items: list[dict[str, Any]] = []
    for delivery in deliveries:
        mirror_destinations = configured_mirror_destinations(config, delivery)
        allowed_mirror_channels = set(
            hub.effective_notification_channels(
                delivery["agent"],
                [channel for channel, _target, _account_id in mirror_destinations],
            )
        )
        destinations: list[tuple[str, str, str | None]] = []
        original_destination = original_delivery_destination(config, delivery)
        if original_destination is not None:
            # The original trigger channel is the minimum guaranteed return path.
            destinations.append(original_destination)
        destinations.extend(
            destination
            for destination in mirror_destinations
            if destination[0] in allowed_mirror_channels
        )
        destinations = dedupe_delivery_destinations(destinations)
        if not destinations:
            raise SystemExit(
                "no delivery destination available for this branch message; "
                "the original trigger channel is missing and all mirror channels are disabled"
            )
        for delivery_channel, target, account_id in destinations:
            append_send_trace(
                config,
                {
                    "event": "pump_send",
                    "channel": delivery_channel,
                    "target": target,
                    "account_id": account_id,
                    "session_key": delivery["session_key"],
                    "message_id": delivery["message_id"],
                },
            )
            send_message(
                channel=delivery_channel,
                target=target,
                message=delivery["delivery_text"],
                account_id=account_id,
            )
        run_openclaw_relay(
            config,
            [
                "ack-delivery",
                "--session",
                delivery["session_key"],
                "--message-id",
                delivery["message_id"],
            ],
        )
        sent_count += 1
        sent_items.append(
            {
                "session_key": delivery["session_key"],
                "message_id": delivery["message_id"],
                "channels": [channel for channel, _target, _account_id in destinations],
                "destinations": [
                    {
                        "channel": channel,
                        "target": target,
                        "account_id": account_id,
                    }
                    for channel, target, account_id in destinations
                ],
                "requested_mirror_channels": [channel for channel, _target, _account_id in mirror_destinations],
            }
        )
    return {
        "ok": True,
        "message": f"RELAY_PUMP_SENT: {sent_count}",
        "sent_count": sent_count,
        "deliveries": sent_items,
    }


def handle_notify(config: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    agent = normalize_agent(args.agent)
    body = read_optional_text(getattr(args, "body", None), getattr(args, "body_file", None))
    if args.kind == "shutdown":
        origin = resolve_notify_origin(
            config,
            agent=agent,
            preferred_main_session_ref=args.main_session_ref,
        )
        destinations = notify_destinations(
            config,
            agent=agent,
            origin_channel=str(origin.get("channel") or "").strip() or None,
            origin_target=str(origin.get("target") or "").strip() or None,
        )
        if not destinations:
            return {
                "ok": True,
                "kind": args.kind,
                "agent": agent,
                "skipped": True,
                "reason": "no_enabled_notification_destinations",
                "notify_origin": origin,
                "user_message": "当前没有可用的 OpenClaw 消息提醒渠道，已跳过提醒发送。",
            }
        message = build_notify_text_without_entry(agent, args.kind, body=body)
        sent: list[dict[str, Any]] = []
        for channel, target, account_id in destinations:
            append_send_trace(
                config,
                {
                    "event": "notify_send",
                    "agent": agent,
                    "kind": args.kind,
                    "main_session_ref": args.main_session_ref,
                    "channel": channel,
                    "target": target,
                    "account_id": account_id,
                    "body_sha256": hashlib.sha256(message.encode("utf-8")).hexdigest(),
                },
            )
            send_message(
                channel=channel,
                target=target,
                message=message,
                account_id=account_id,
            )
            sent.append({"channel": channel, "target": target})
        return {
            "ok": True,
            "kind": args.kind,
            "agent": agent,
            "entry_session_key": None,
            "web_url": None,
            "sent_count": len(sent),
            "deliveries": sent,
            "delivery_text": message,
            "notify_origin": origin,
            "user_message": f"已通过 OpenClaw 渠道发送 {agent} 的退出提醒。",
        }
    entry = ensure_notify_entry(
        config,
        agent,
        main_session_ref=args.main_session_ref,
        project_root=args.project_root,
        development_log_path=args.development_log_path,
    )
    if entry.get("skipped"):
        return {
            "ok": True,
            "kind": args.kind,
            "agent": agent,
            **entry,
        }
    web_url = ((entry.get("branch") or {}).get("meta") or {}).get("web_url")
    if not web_url:
        raise SystemExit("failed to prepare relay web entry")
    if args.kind == "message" and not body:
        raise SystemExit("--body or --body-file is required when kind=message")
    destinations = notify_destinations(
        config,
        agent=agent,
        origin_channel=((entry.get("branch") or {}).get("meta") or {}).get("channel"),
        origin_target=((entry.get("branch") or {}).get("meta") or {}).get("target"),
    )
    if not destinations:
        return {
            "ok": True,
            "kind": args.kind,
            "agent": agent,
            "skipped": True,
            "reason": "no_enabled_notification_destinations",
            "entry_session_key": (entry.get("branch") or {}).get("session_key"),
            "web_url": web_url,
            "notify_origin": entry.get("notify_origin"),
            "user_message": "当前所有 OpenClaw 消息提醒渠道都已关闭，已跳过提醒发送。",
        }
    message = build_notify_text_with_entry(agent, web_url, args.kind, body=body)
    sent: list[dict[str, Any]] = []
    for channel, target, account_id in destinations:
        append_send_trace(
            config,
            {
                "event": "notify_send",
                "agent": agent,
                "kind": args.kind,
                "main_session_ref": args.main_session_ref,
                "channel": channel,
                "target": target,
                "account_id": account_id,
                "body_sha256": hashlib.sha256(message.encode("utf-8")).hexdigest(),
            },
        )
        send_message(
            channel=channel,
            target=target,
            message=message,
            account_id=account_id,
        )
        sent.append({"channel": channel, "target": target})
    return {
        "ok": True,
        "kind": args.kind,
        "agent": agent,
        "entry_session_key": (entry.get("branch") or {}).get("session_key"),
        "web_url": web_url,
        "sent_count": len(sent),
        "deliveries": sent,
        "delivery_text": message,
        "notify_origin": entry.get("notify_origin"),
        "user_message": f"已通过 OpenClaw 渠道发送 {agent} 的提醒消息。",
    }


def handle_relay_help(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "ok": True,
        "agent": normalize_agent(args.agent) if args.agent else None,
        "user_message": relay_help_text(normalize_agent(args.agent) if args.agent else None),
    }


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    config = load_config(resolve_config_path(args.config))
    try:
        if args.command == "open-entry":
            payload = handle_open_entry(config, args)
            output(payload, args.json)
            return
        if args.command == "dispatch-input":
            payload = handle_dispatch(config, args)
            output(payload, args.json)
            return
        if args.command == "session-status":
            payload = handle_status(config, args)
            output(payload, args.json)
            return
        if args.command == "pump-deliveries":
            payload = handle_pump(config, args)
            output(payload, args.json)
            return
        if args.command == "notify":
            payload = handle_notify(config, args)
            output(payload, args.json)
            return
        if args.command == "relay-help":
            payload = handle_relay_help(args)
            output(payload, args.json)
            return
    except SystemExit as exc:
        message = str(exc) or "relay bridge failed"
        if args.command == "pump-deliveries":
            fail(f"RELAY_PUMP_FAILED: {message}", as_json=args.json)
        fail(message, as_json=args.json)
    parser.error(f"unknown command: {args.command}")


if __name__ == "__main__":
    main()
