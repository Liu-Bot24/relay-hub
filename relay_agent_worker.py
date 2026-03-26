#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from relay_hub import RelayHub


DEFAULT_ROOT = Path(__file__).resolve().parent / "runtime"
DEFAULT_WORKDIR = Path(__file__).resolve().parent.parent
DEFAULT_BRIDGE_SCRIPT = Path(__file__).resolve().parent / "relay_openclaw_bridge.py"
DEFAULT_BRIDGE_CONFIG = Path.home() / ".openclaw" / "workspace" / "data" / "relay_hub_openclaw.json"


def output(payload: object) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def resolve_root(value: str | None) -> Path:
    return Path(value).expanduser().resolve() if value else DEFAULT_ROOT


def resolve_workdir(value: str | None) -> Path:
    return Path(value).expanduser().resolve() if value else DEFAULT_WORKDIR


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Relay Hub worker for external coding agents")
    parser.add_argument("--root", help="Relay root directory. Defaults to relay-hub/runtime.")
    parser.add_argument("--agent", required=True, help="Relay agent id, e.g. claude-code")
    parser.add_argument(
        "--backend",
        default="claude-code",
        choices=["claude-code"],
        help="Runtime backend used to process queued relay sessions.",
    )
    parser.add_argument(
        "--workdir",
        help="Working directory passed to the backend CLI. Defaults to the parent directory of relay-hub.",
    )
    parser.add_argument(
        "--bridge-script",
        default=str(DEFAULT_BRIDGE_SCRIPT),
        help="OpenClaw relay bridge script used for delivery pumping.",
    )
    parser.add_argument(
        "--bridge-config",
        default=str(DEFAULT_BRIDGE_CONFIG),
        help="Path to relay_hub_openclaw.json used by the bridge script.",
    )
    parser.add_argument(
        "--poll-seconds",
        type=float,
        default=2.0,
        help="Polling interval for serve mode.",
    )
    parser.add_argument(
        "--idle-exit-after",
        type=int,
        default=0,
        help="If > 0, serve mode exits after this many idle polls with no queued work.",
    )
    parser.add_argument(
        "--verbose-idle",
        action="store_true",
        help="In serve mode, print idle polling results as JSON.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("once", help="Claim and process at most one queued session")
    subparsers.add_parser("serve", help="Keep polling and processing queued sessions")
    return parser


def run_backend_claude(prompt: str, workdir: Path) -> str:
    cmd = [
        "claude",
        "-p",
        prompt,
    ]
    result = subprocess.run(  # noqa: S603
        cmd,
        cwd=str(workdir),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        text = (result.stderr or result.stdout or "claude failed").strip()
        raise RuntimeError(text)
    answer = result.stdout.strip()
    if not answer:
        raise RuntimeError("claude returned empty output")
    return answer


def latest_user_message(context: dict[str, Any]) -> dict[str, Any] | None:
    state = context.get("state") or {}
    queued_id = state.get("last_queued_user_message_id") or state.get("last_committed_user_message_id")
    messages = context.get("branch_messages") or []
    for message in reversed(messages):
        if message.get("role") != "user":
            continue
        if queued_id and message.get("id") == queued_id:
            return message
    for message in reversed(messages):
        if message.get("role") == "user":
            return message
    return None


def format_branch_messages(messages: list[dict[str, Any]]) -> str:
    if not messages:
        return "(none)"
    lines: list[str] = []
    for message in messages:
        role = message.get("role") or "unknown"
        kind = message.get("kind") or role
        source = message.get("source") or ""
        created_at = message.get("created_at") or ""
        lines.append(f"[{message.get('id')}] {role}/{kind} source={source} created_at={created_at}")
        lines.append((message.get("body") or "").rstrip())
        lines.append("")
    return "\n".join(lines).rstrip()


def build_claude_prompt(agent: str, context: dict[str, Any]) -> str:
    meta = context.get("meta") or {}
    state = context.get("state") or {}
    main_context = (context.get("main_context") or {}).get("body") or "(none)"
    branch_messages = context.get("branch_messages") or []
    latest = latest_user_message(context)
    latest_body = latest.get("body") if latest else ""
    latest_id = latest.get("id") if latest else state.get("last_queued_user_message_id")
    transcript = format_branch_messages(branch_messages)
    return (
        "你正在作为 Relay Hub 的外部处理对象，处理一次来自 OpenClaw 渠道的 branch 请求。\n"
        "请直接回答用户当前这轮真正想要的内容。\n\n"
        "必须遵守：\n"
        "1. 只输出最终要发给用户的正文，不要输出分析过程。\n"
        "2. 不要提 Relay Hub、OpenClaw、session id、消息 id，除非用户明确问到。\n"
        "3. 默认使用中文，除非用户明确要求别的语言。\n"
        "4. 把最新这条用户消息视为当前主任务，之前消息只作为上下文。\n"
        "5. 如果上下文不足，就基于现有内容给出最合理、最直接的答复。\n\n"
        f"当前 agent: {agent}\n"
        f"session: {meta.get('session_key')}\n"
        f"branch 来源渠道: {meta.get('channel')} -> {meta.get('target')}\n\n"
        "主对话快照：\n"
        f"{main_context}\n\n"
        "branch 历史（按时间顺序）：\n"
        f"{transcript}\n\n"
        f"当前需要回复的最新用户消息 id: {latest_id}\n"
        "当前需要回复的最新用户消息正文：\n"
        f"{latest_body}\n\n"
        "现在请直接输出给用户的最终回复正文："
    )


def run_bridge_pump(bridge_script: Path, bridge_config: Path) -> dict[str, Any]:
    result = subprocess.run(  # noqa: S603
        [
            sys.executable,
            str(bridge_script),
            "--config",
            str(bridge_config),
            "--json",
            "pump-deliveries",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        text = (result.stderr or result.stdout or "delivery pump failed").strip()
        raise RuntimeError(text)
    return json.loads(result.stdout)


def process_one(
    hub: RelayHub,
    agent: str,
    backend: str,
    workdir: Path,
    bridge_script: Path,
    bridge_config: Path,
) -> dict[str, Any]:
    claim = hub.claim_next(agent)
    if not claim:
        return {"ok": True, "idle": True, "message": "no queued session"}

    session_key = claim["session_key"]
    queued_user = claim.get("last_user_message") or {}
    source_user_message_id = (queued_user.get("meta") or {}).get("id")

    hub.write_agent_message(
        session_key=session_key,
        agent=agent,
        kind="progress",
        body=f"{agent} 已确认接单，正在处理。",
        source_user_message_id=source_user_message_id,
        deliver_via_openclaw=False,
        append_web_url=False,
    )

    try:
        context = hub.build_context(session_key, limit=80)
        if backend == "claude-code":
            prompt = build_claude_prompt(agent, context)
            answer = run_backend_claude(prompt, workdir)
        else:
            raise RuntimeError(f"unsupported backend: {backend}")

        reply = hub.write_agent_message(
            session_key=session_key,
            agent=agent,
            kind="final",
            body=answer,
            source_user_message_id=source_user_message_id,
            deliver_via_openclaw=True,
            append_web_url=True,
        )
        pump = run_bridge_pump(bridge_script, bridge_config)
        return {
            "ok": True,
            "idle": False,
            "session_key": session_key,
            "claimed_user_message_id": source_user_message_id,
            "reply": reply,
            "delivery_pump": pump,
        }
    except Exception as exc:
        if hub.get_state(session_key).get("last_agent_message_id") and hub.message_by_id(session_key, hub.get_state(session_key).get("last_agent_message_id")):
            last_agent_id = hub.get_state(session_key).get("last_agent_message_id")
            last_agent_message = hub.message_by_id(session_key, last_agent_id)
            if (last_agent_message or {}).get("meta", {}).get("kind") == "final":
                return {
                    "ok": False,
                    "idle": False,
                    "session_key": session_key,
                    "claimed_user_message_id": source_user_message_id,
                    "error": str(exc),
                    "note": "final reply already exists; worker did not append an error reply",
                }
        error_reply = hub.write_agent_message(
            session_key=session_key,
            agent=agent,
            kind="error",
            body=f"{agent} 处理失败：{exc}",
            source_user_message_id=source_user_message_id,
            deliver_via_openclaw=True,
            append_web_url=True,
        )
        pump = None
        try:
            pump = run_bridge_pump(bridge_script, bridge_config)
        except Exception as pump_exc:  # noqa: BLE001
            pump = {"ok": False, "error": str(pump_exc)}
        return {
            "ok": False,
            "idle": False,
            "session_key": session_key,
            "claimed_user_message_id": source_user_message_id,
            "error": str(exc),
            "error_reply": error_reply,
            "delivery_pump": pump,
        }


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    root = resolve_root(args.root)
    workdir = resolve_workdir(args.workdir)
    bridge_script = Path(args.bridge_script).expanduser().resolve()
    bridge_config = Path(args.bridge_config).expanduser().resolve()
    hub = RelayHub(root)
    hub.init_layout()
    hub.set_agent(args.agent, "ready")

    if args.command == "once":
        output(process_one(hub, args.agent, args.backend, workdir, bridge_script, bridge_config))
        return

    idle_polls = 0
    while True:
        result = process_one(hub, args.agent, args.backend, workdir, bridge_script, bridge_config)
        if result.get("idle"):
            if args.verbose_idle:
                output(result)
            idle_polls += 1
            if args.idle_exit_after > 0 and idle_polls >= args.idle_exit_after:
                return
            time.sleep(args.poll_seconds)
            continue
        idle_polls = 0
        output(result)


if __name__ == "__main__":
    main()
