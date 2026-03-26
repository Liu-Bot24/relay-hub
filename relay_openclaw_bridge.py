#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_CONFIG_PATH = Path.home() / ".openclaw" / "workspace" / "data" / "relay_hub_openclaw.json"

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


def normalize_agent(raw: str) -> str:
    key = raw.strip().lower()
    return AGENT_ALIASES.get(key, key)


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


def requested_delivery_channels(delivery: dict[str, Any]) -> list[str]:
    default_delivery = delivery.get("default_delivery") or {}
    channels = list(default_delivery.get("channels") or [])
    if not channels:
        channels = [delivery["channel"]]
    seen: set[str] = set()
    ordered: list[str] = []
    for channel in channels:
        if channel not in seen:
            seen.add(channel)
            ordered.append(channel)
    return ordered


def resolve_delivery_destination(config: dict[str, Any], delivery: dict[str, Any], channel: str) -> tuple[str, str | None]:
    original_channel = delivery.get("channel")
    original_target = delivery.get("target")
    if channel == original_channel and original_target:
        return original_target, delivery_account_for_channel(config, channel)
    channel_config = (config.get("delivery") or {}).get("channels", {}).get(channel, {})
    target = channel_config.get("target")
    if not target:
        raise SystemExit(f"missing configured delivery target for channel {channel}")
    return target, channel_config.get("accountId")


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

    dispatch_parser = subparsers.add_parser("dispatch-input", help="Queue one relay branch after user input")
    add_locator_args(dispatch_parser)
    dispatch_parser.add_argument("--wait-claim", action="store_true")
    dispatch_parser.add_argument("--timeout-seconds", type=int, default=15)

    status_parser = subparsers.add_parser("session-status", help="Show relay branch status")
    add_locator_args(status_parser)

    exit_parser = subparsers.add_parser("exit-relay", help="Exit relay mode for one branch")
    add_locator_args(exit_parser)

    pump_parser = subparsers.add_parser("pump-deliveries", help="Send pending relay deliveries via OpenClaw channels")
    pump_parser.add_argument("--channel")
    pump_parser.add_argument("--target")

    return parser


def handle_open_entry(config: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    ensure_runtime_config(config)
    web_started = ensure_web_running(config)
    channel, target = resolve_channel_target(config, args.channel, args.target)
    payload = run_openclaw_relay(
        config,
        [
            "open-entry",
            "--agent",
            normalize_agent(args.agent),
            "--channel",
            channel,
            "--target",
            target,
        ],
    )
    payload["aliases"] = register_channel_aliases(
        config,
        session_key=payload["branch"]["session_key"],
        origin_channel=channel,
        origin_target=target,
        delivery_channels=list((payload["branch"]["meta"].get("default_delivery") or {}).get("channels") or []),
    )
    payload["resolved"] = {"channel": channel, "target": target}
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


def handle_exit(config: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    ensure_runtime_config(config)
    channel, target = resolve_channel_target(config, args.channel, args.target)
    aliased_session = resolve_session_alias(config, channel, target)
    relay_args = ["exit-relay"]
    if aliased_session:
        relay_args.extend(["--session", aliased_session])
    else:
        relay_args.extend(["--channel", channel, "--target", target])
    payload = run_openclaw_relay(config, relay_args)
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
    sent_count = 0
    sent_items: list[dict[str, Any]] = []
    for delivery in deliveries:
        used_channels = requested_delivery_channels(delivery)
        for delivery_channel in used_channels:
            target, account_id = resolve_delivery_destination(config, delivery, delivery_channel)
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
                "channels": used_channels,
            }
        )
    return {
        "ok": True,
        "message": f"RELAY_PUMP_SENT: {sent_count}",
        "sent_count": sent_count,
        "deliveries": sent_items,
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
        if args.command == "exit-relay":
            payload = handle_exit(config, args)
            output(payload, args.json)
            return
        if args.command == "pump-deliveries":
            payload = handle_pump(config, args)
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
