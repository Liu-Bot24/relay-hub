#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from relay_hub import RelayHub
from relay_hub.codex_host import (
    conversation_rounds,
    fallback_rounds_summary,
    format_rounds_snapshot,
    recent_conversation_snapshot,
    resolve_active_user_thread_record,
    resolve_rollout_record,
    rounds_before_last_relay_enable,
    thread_id_from_main_session_ref,
)
from relay_hub.pickup import (
    list_pickup_states,
    load_pickup_state,
    pickup_capture_queue_dir,
    pickup_context_seed_path,
    pickup_log_path,
    process_alive,
    save_pickup_state,
)
from relay_agent_daemon import enqueue_captured_main_output, run_codex_exec_backend

DEFAULT_ROOT = (Path.home() / "Library" / "Application Support" / "RelayHub" / "runtime") if (Path.home() / "Library" / "Application Support" / "RelayHub" / "runtime").exists() else (PROJECT_ROOT / "runtime")
DEFAULT_OPENCLAW_CONFIG = Path.home() / ".openclaw" / "workspace" / "data" / "relay_hub_openclaw.json"

CHANNEL_TOKEN_ALIASES = {
    "feishu": "feishu",
    "lark": "feishu",
    "飞书": "feishu",
    "weixin": "openclaw-weixin",
    "wechat": "openclaw-weixin",
    "wx": "openclaw-weixin",
    "微信": "openclaw-weixin",
    "openclaw-weixin": "openclaw-weixin",
    "telegram": "telegram",
    "tg": "telegram",
    "电报": "telegram",
    "discord": "discord",
    "slack": "slack",
}

CHANNEL_DISPLAY_NAMES = {
    "feishu": "飞书",
    "openclaw-weixin": "微信",
    "telegram": "Telegram",
    "discord": "Discord",
    "slack": "Slack",
}


def output(payload: object) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def fail(message: str, exit_code: int = 1) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(exit_code)


def resolve_root(value: str | None) -> Path:
    return Path(value).expanduser().resolve() if value else DEFAULT_ROOT


def read_body(body: str | None, body_file: str | None) -> str | None:
    if body is not None:
        return body
    if body_file is not None:
        return Path(body_file).read_text(encoding="utf-8")
    return None


def resolve_agent(value: str | None, default_agent: str | None) -> str:
    agent = value or default_agent or os.environ.get("RELAY_AGENT_ID")
    if agent:
        return agent
    raise SystemExit("agent is required: pass --agent or set RELAY_AGENT_ID")


def resolve_project_value(args: argparse.Namespace, presence: dict[str, Any], attr: str) -> str | None:
    direct = getattr(args, attr, None)
    if direct:
        return direct
    key = f"current_{attr}"
    return presence.get(key)


def load_openclaw_delivery_channels() -> dict[str, Any]:
    if not DEFAULT_OPENCLAW_CONFIG.exists():
        return {}
    try:
        payload = json.loads(DEFAULT_OPENCLAW_CONFIG.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return ((payload.get("delivery") or {}).get("channels") or {})


def display_channel_name(channel: str) -> str:
    return CHANNEL_DISPLAY_NAMES.get(channel, channel)


def resolve_channel_token(token: str, configured_channels: list[str]) -> str:
    normalized = token.strip()
    if not normalized:
        raise SystemExit("channel token is required")
    lowered = normalized.lower()
    if normalized in configured_channels:
        return normalized
    if lowered in configured_channels:
        return lowered
    alias = CHANNEL_TOKEN_ALIASES.get(lowered) or CHANNEL_TOKEN_ALIASES.get(normalized)
    if alias and alias in configured_channels:
        return alias
    available = " / ".join(configured_channels) if configured_channels else "无"
    raise SystemExit(f"unknown delivery channel: {token}; configured channels: {available}")


def build_notification_status_payload(hub: RelayHub, agent: str) -> dict[str, Any]:
    delivery_channels = load_openclaw_delivery_channels()
    configured_channels = list(delivery_channels.keys())
    status = hub.notification_channel_status(agent, configured_channels)
    channel_rows: list[dict[str, Any]] = []
    for item in status["channels"]:
        channel = item["channel"]
        channel_config = delivery_channels.get(channel, {}) or {}
        channel_rows.append(
            {
                **item,
                "display_name": display_channel_name(channel),
                "target": channel_config.get("target"),
                "account_id": channel_config.get("accountId"),
            }
        )
    if not configured_channels:
        user_message = "当前还没有配置任何 OpenClaw 消息渠道。"
    elif status["all_enabled"]:
        user_message = "当前 OpenClaw 消息提醒：全部开启。"
    elif status["all_disabled"]:
        user_message = "当前 OpenClaw 消息提醒：全部关闭。"
    elif len(status["enabled_channels"]) == 1:
        user_message = f"当前 OpenClaw 消息提醒：仅开启 {display_channel_name(status['enabled_channels'][0])}。"
    else:
        enabled_names = "、".join(display_channel_name(channel) for channel in status["enabled_channels"])
        disabled_names = "、".join(display_channel_name(channel) for channel in status["disabled_channels"])
        if disabled_names:
            user_message = f"当前 OpenClaw 消息提醒：已开启 {enabled_names}；已关闭 {disabled_names}。"
        else:
            user_message = f"当前 OpenClaw 消息提醒：已开启 {enabled_names}。"
    return {
        "ok": True,
        "agent": agent,
        "configured_channels": configured_channels,
        "status": {
            **status,
            "channels": channel_rows,
        },
        "user_message": user_message,
    }


def last_branch_message_id(merge_back: dict[str, Any]) -> str | None:
    messages = merge_back.get("branch_messages") or []
    if not messages:
        return None
    return messages[-1].get("id")


def build_agent_status(hub: RelayHub, agent: str) -> dict[str, Any]:
    presence = hub.get_agent(agent)
    sessions = [session for session in hub.list_sessions() if session.get("agent") == agent]
    queued = [session for session in sessions if session.get("status") == "queued"]
    processing = [session for session in sessions if session.get("status") == "processing"]
    awaiting_user = [session for session in sessions if session.get("status") == "awaiting_user"]
    input_open = [session for session in sessions if session.get("status") == "input_open"]
    entry_open = [session for session in sessions if session.get("status") == "entry_open"]
    error = [session for session in sessions if session.get("status") == "error"]
    pickup_states = list_pickup_states(hub.root, agent=agent)
    active_pickups = [state for state in pickup_states if state.get("alive")]
    current_main_session_ref = presence.get("current_main_session_ref")
    resume_candidates = (
        hub.resume_candidates(agent, current_main_session_ref) if current_main_session_ref else []
    )
    return {
        "agent": presence,
        "summary": {
            "ready": presence.get("status") == "ready",
            "current_main_session_ref": current_main_session_ref,
            "session_count": len(sessions),
            "queued_count": len(queued),
            "processing_count": len(processing),
            "awaiting_user_count": len(awaiting_user),
            "input_open_count": len(input_open),
            "entry_open_count": len(entry_open),
            "error_count": len(error),
            "has_pending_branch": bool(queued or processing),
            "unmerged_branch_count": len(resume_candidates),
            "pickup_count": len(pickup_states),
            "active_pickup_count": len(active_pickups),
        },
        "pickup": pickup_states,
        "resume_candidates": resume_candidates,
        "sessions": sessions,
    }


def pick_backend(value: str | None, agent: str) -> str:
    if value:
        return value
    if agent == "codex":
        return "codex-exec"
    raise SystemExit("backend is required; for generic CLI 接入优先使用 command，codex 可省略并默认使用 codex-exec")


def pickup_for_host_thread(root: Path, agent: str, thread_id: str) -> dict[str, Any] | None:
    for pickup in list_pickup_states(root, agent=agent):
        if pickup.get("host_thread_id") == thread_id:
            return pickup
    return None


def resolve_codex_conversation_binding(
    root: Path,
    agent: str,
    *,
    project_root: str | None = None,
    explicit_main_session_ref: str | None = None,
    preferred_thread_id: str | None = None,
    use_latest_user_thread: bool = False,
) -> dict[str, Any]:
    record = None
    candidate_thread_id = preferred_thread_id or thread_id_from_main_session_ref(explicit_main_session_ref)
    if candidate_thread_id:
        record = resolve_rollout_record(project_root=None, thread_id=candidate_thread_id)
    if record is None and use_latest_user_thread:
        record = resolve_active_user_thread_record()
    if record is None:
        record = resolve_rollout_record(project_root=None, thread_id=os.environ.get("CODEX_THREAD_ID"))
    if record is None:
        raise SystemExit("current Codex conversation could not be resolved; pass --main-session-ref explicitly")
    thread_id = str(record["id"])
    existing_pickup = pickup_for_host_thread(root, agent, thread_id)
    resolved_project_root = project_root or record.get("cwd")
    if resolved_project_root:
        resolved_project_root = str(Path(resolved_project_root).expanduser().resolve())
    return {
        "record": record,
        "thread_id": thread_id,
        "pickup": existing_pickup,
        "project_root": resolved_project_root,
        "main_session_ref": explicit_main_session_ref
        or (existing_pickup.get("main_session_ref") if existing_pickup else f"codex-main-thread-{thread_id}"),
    }


def auto_switch_snapshot_body(project_root: str | None, thread_id: str) -> str:
    recent = build_codex_snapshot_body(
        project_root=project_root,
        thread_id=thread_id,
        trim_trailing_relay_enable=False,
        heading="当前主线最近对话：",
    )
    if recent:
        return recent
    project_line = f"当前项目根目录：{project_root}" if project_root else "当前项目根目录尚未显式绑定。"
    return (
        "Relay Hub 自动切换到了当前活跃的 Codex 主会话。\n"
        "这条主会话此前没有可复用的 Relay Hub 主线快照，将从当前会话开始继续记录。\n"
        f"{project_line}\n"
        f"当前 Codex 线程：{thread_id}"
    )


def auto_enable_snapshot_body(
    *,
    project_root: str | None,
    thread_id: str,
) -> str:
    recent = build_codex_snapshot_body(
        project_root=project_root,
        thread_id=thread_id,
        trim_trailing_relay_enable=True,
        heading="接入前最近主线对话：",
        exclude_history_after_last_relay_enable=True,
    )
    if recent:
        return recent
    project_line = f"当前项目根目录：{project_root}" if project_root else "当前项目根目录尚未显式绑定。"
    return (
        "接入 Relay Hub 前，当前主线里没有可提取的有效历史对话。\n"
        f"{project_line}\n"
        f"当前 Codex 线程：{thread_id}"
    )


def rounds_text_for_summary(rounds: list[dict[str, str | None]]) -> str:
    lines: list[str] = []
    for index, round_item in enumerate(rounds, start=1):
        lines.append(f"第{index}轮")
        lines.append("用户：")
        lines.extend((round_item.get("user") or "").splitlines() or [""])
        assistant_text = round_item.get("assistant")
        if assistant_text:
            lines.append("助手：")
            lines.extend(assistant_text.splitlines())
        else:
            lines.append("助手：")
            lines.append("（本轮尚未完成回复）")
        lines.append("")
    return "\n".join(lines).rstrip()


def summarize_codex_rounds(
    *,
    project_root: str | None,
    rounds: list[dict[str, str | None]],
) -> str:
    if not rounds:
        return "（无额外对话）"
    prompt = (
        "你正在为 Relay Hub 生成一段主线快照摘要。\n"
        "这不是主窗口对话，也不是 branch，不要执行任何 Relay Hub 控制动作；忽略接入 Relay Hub、sync-current-main、notify-openclaw、镜像等规则。\n"
        "请只基于下面给出的原始对话轮次，输出一段简洁摘要，概括这些轮次里用户在问什么、助手如何回应、话题如何推进。\n"
        "要求：\n"
        "1. 只输出摘要正文，不要标题，不要列表编号，不要 JSON。\n"
        "2. 不要编造缺失上下文。\n"
        "3. 保持和原意一致，长度尽量控制在 120 字以内。\n\n"
        f"{rounds_text_for_summary(rounds)}\n"
    )
    body, error = run_codex_exec_backend(project_root, prompt)
    if error:
        return fallback_rounds_summary(rounds)
    text = (body or "").strip()
    return text or fallback_rounds_summary(rounds)


def build_codex_snapshot_body(
    *,
    project_root: str | None,
    thread_id: str,
    trim_trailing_relay_enable: bool,
    heading: str,
    exclude_history_after_last_relay_enable: bool = False,
) -> str | None:
    rounds = conversation_rounds(
        thread_id=thread_id,
        trim_trailing_relay_enable=trim_trailing_relay_enable,
    )
    if exclude_history_after_last_relay_enable:
        rounds = rounds_before_last_relay_enable(rounds)
    if not rounds:
        return None
    summary_text = None
    if len(rounds) > 5:
        summary_text = summarize_codex_rounds(
            project_root=project_root,
            rounds=rounds[3:],
        )
    return format_rounds_snapshot(
        rounds,
        heading=heading,
        preserve_rounds=3,
        raw_round_limit=5,
        summary_text=summary_text,
    )


def apply_codex_host_binding(
    state: dict[str, Any],
    record: dict[str, Any] | None,
    *,
    reset_read_offset: bool = False,
) -> dict[str, Any]:
    if record is None:
        return state
    rollout_path = Path(record["rollout_path"]).expanduser().resolve()
    mirror_offset = int(state.get("mirror_read_offset") or 0)
    if rollout_path.exists() and (reset_read_offset or not mirror_offset):
        mirror_offset = rollout_path.stat().st_size
    state.update(
        {
            "host_kind": "codex-rollout",
            "host_thread_id": str(record.get("id") or ""),
            "host_rollout_path": str(rollout_path),
            "mirror_read_offset": mirror_offset,
        }
    )
    return state


def sync_codex_main_session(
    *,
    hub: RelayHub,
    agent: str,
    project_root: str | None = None,
    development_log_path: str | None = None,
    snapshot_body: str | None = None,
    author: str | None = None,
    backend: str | None = None,
    backend_command: str | None = None,
    poll_interval_seconds: float = 2.0,
    preferred_thread_id: str | None = None,
    use_latest_user_thread: bool = False,
) -> dict[str, Any]:
    presence = hub.get_agent(agent)
    if presence.get("status") != "ready":
        return {
            "ok": True,
            "relay_active": False,
            "switched": False,
            "reason": "agent_not_ready",
            "agent": presence,
        }
    if agent != "codex":
        raise SystemExit("sync-current-main currently supports codex only")
    binding = resolve_codex_conversation_binding(
        hub.root,
        agent,
        project_root=project_root,
        preferred_thread_id=preferred_thread_id,
        use_latest_user_thread=use_latest_user_thread,
    )
    main_session_ref = str(binding["main_session_ref"])
    existing_pickup = load_pickup_state(hub.root, agent, main_session_ref)
    seed_path = pickup_context_seed_path(hub.root, agent, main_session_ref)
    seed_exists = seed_path.exists()
    bootstrap_needed = not seed_exists
    target_project_root = (
        existing_pickup.get("project_root")
        or binding.get("project_root")
        or presence.get("current_project_root")
        or project_root
    )
    if not target_project_root:
        raise SystemExit("sync-current-main could not determine the current project root")
    target_log_path = (
        existing_pickup.get("development_log_path")
        or development_log_path
        or (
            presence.get("current_development_log_path")
            if presence.get("current_project_root") == target_project_root
            else None
        )
        or str(Path(target_project_root).expanduser().resolve() / "DEVELOPMENT_LOG.md")
    )
    snapshot_seed = snapshot_body
    if bootstrap_needed and snapshot_seed is None:
        snapshot_seed = auto_switch_snapshot_body(target_project_root, str(binding["thread_id"]))
    context_payload = hub.switch_active_main_session(
        agent=agent,
        project_root=target_project_root,
        development_log_path=target_log_path,
        main_session_ref=main_session_ref,
        snapshot_body=snapshot_seed if bootstrap_needed else None,
        author=author or agent,
    )
    stopped_pickups = stop_other_pickups(hub.root, agent, keep_main_session_ref=main_session_ref)
    pickup = start_pickup_process(
        hub=hub,
        root=hub.root,
        agent=agent,
        main_session_ref=main_session_ref,
        backend=pick_backend(backend, agent),
        backend_command=backend_command,
        poll_interval_seconds=poll_interval_seconds,
        main_context_body=snapshot_seed if bootstrap_needed and not seed_exists else None,
    )
    return {
        "ok": True,
        "relay_active": True,
        "switched": presence.get("current_main_session_ref") != main_session_ref,
        "bootstrap_needed": bootstrap_needed,
        "main_session_ref": main_session_ref,
        "thread_id": binding["thread_id"],
        "project_root": context_payload["project_root"],
        "development_log_path": context_payload["development_log_path"],
        "pickup": pickup,
        "stopped_pickups": stopped_pickups,
    }


def prepare_codex_main_reply(
    *,
    hub: RelayHub,
    agent: str,
    project_root: str | None = None,
    development_log_path: str | None = None,
    snapshot_body: str | None = None,
    author: str | None = None,
    backend: str | None = None,
    backend_command: str | None = None,
    poll_interval_seconds: float = 2.0,
    preferred_thread_id: str | None = None,
) -> dict[str, Any]:
    sync_result = sync_codex_main_session(
        hub=hub,
        agent=agent,
        project_root=project_root,
        development_log_path=development_log_path,
        snapshot_body=snapshot_body,
        author=author,
        backend=backend,
        backend_command=backend_command,
        poll_interval_seconds=poll_interval_seconds,
        preferred_thread_id=preferred_thread_id,
    )
    if not sync_result.get("relay_active"):
        return {
            "ok": True,
            "relay_active": False,
            "sync_current_main": sync_result,
            "resume_main": None,
            "resume_candidates": [],
        }
    main_session_ref = str(sync_result["main_session_ref"])
    resume_candidates = hub.resume_candidates(agent, main_session_ref)
    if len(resume_candidates) > 1:
        return {
            "ok": False,
            "relay_active": True,
            "main_session_ref": main_session_ref,
            "sync_current_main": sync_result,
            "resume_main": None,
            "resume_candidates": resume_candidates,
            "user_message": "当前主会话下有多条未合流的旧 branch，请先明确要合流哪一条。",
        }
    resume_payload = None
    if len(resume_candidates) == 1:
        resume_payload = hub.resume_main(
            agent=agent,
            main_session_ref=main_session_ref,
            session_key=resume_candidates[0]["session_key"],
            close_relay=False,
        )
    return {
        "ok": True,
        "relay_active": True,
        "main_session_ref": main_session_ref,
        "sync_current_main": sync_result,
        "resume_main": resume_payload,
        "resume_candidates": resume_candidates,
    }


def resolve_codex_notify_binding(
    *,
    hub: RelayHub,
    agent: str,
) -> dict[str, Any]:
    if agent != "codex":
        return {
            "main_session_ref": None,
            "project_root": None,
            "development_log_path": None,
            "thread_id": None,
        }
    presence = hub.get_agent(agent)
    binding = resolve_codex_conversation_binding(hub.root, agent)
    main_session_ref = str(binding["main_session_ref"])
    pickup = binding.get("pickup") or load_pickup_state(hub.root, agent, main_session_ref)
    project_root = (
        pickup.get("project_root")
        or binding.get("project_root")
        or (
            presence.get("current_project_root")
            if presence.get("current_main_session_ref") == main_session_ref
            else None
        )
    )
    development_log_path = (
        pickup.get("development_log_path")
        or (
            presence.get("current_development_log_path")
            if presence.get("current_main_session_ref") == main_session_ref
            else None
        )
        or (str(Path(project_root).expanduser().resolve() / "DEVELOPMENT_LOG.md") if project_root else None)
    )
    return {
        "main_session_ref": main_session_ref,
        "project_root": project_root,
        "development_log_path": development_log_path,
        "thread_id": str(binding["thread_id"]),
    }


def auto_main_session_ref(root: Path, agent: str, project_root: str, explicit: str | None) -> str:
    if explicit:
        return explicit
    if agent == "codex":
        binding = resolve_codex_conversation_binding(
            root,
            agent,
            project_root=project_root,
            explicit_main_session_ref=explicit,
        )
        return str(binding["main_session_ref"])
    raise SystemExit("main_session_ref is required for this host; pass --main-session-ref explicitly")


def daemon_script_path() -> Path:
    return SCRIPT_DIR / "relay_agent_daemon.py"


def openclaw_bridge_script_path() -> Path:
    return SCRIPT_DIR / "relay_openclaw_bridge.py"


def run_openclaw_bridge(args: list[str]) -> dict[str, Any]:
    cmd = [
        sys.executable,
        str(openclaw_bridge_script_path()),
        "--json",
        *args,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)  # noqa: S603
    if result.returncode != 0:
        text = result.stderr or result.stdout or "relay_openclaw_bridge failed"
        fail(text.strip())
    return json.loads(result.stdout)


def start_pickup_process(
    *,
    hub: RelayHub,
    root: Path,
    agent: str,
    main_session_ref: str,
    backend: str,
    backend_command: str | None,
    poll_interval_seconds: float,
    main_context_body: str | None,
) -> dict[str, Any]:
    presence = hub.get_agent(agent)
    if presence.get("status") != "ready":
        raise SystemExit(f"{agent} is not ready; run enable-relay first")
    if backend == "command" and not backend_command:
        raise SystemExit("--backend-command is required when backend=command")
    existing = load_pickup_state(root, agent, main_session_ref)
    existing_pid = existing.get("pid")
    if process_alive(existing_pid):
        return existing
    if main_context_body is not None:
        seed_path = pickup_context_seed_path(root, agent, main_session_ref)
        seed_path.parent.mkdir(parents=True, exist_ok=True)
        seed_path.write_text(main_context_body, encoding="utf-8")
    log_path = pickup_log_path(root, agent, main_session_ref)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        str(daemon_script_path()),
        "--root",
        str(root),
        "--agent",
        agent,
        "--main-session-ref",
        main_session_ref,
        "--backend",
        backend,
        "--poll-interval-seconds",
        str(poll_interval_seconds),
    ]
    if backend_command:
        cmd.extend(["--backend-command", backend_command])
    if main_context_body is not None:
        cmd.extend(["--main-context-body", main_context_body])
    with log_path.open("ab") as handle:
        proc = subprocess.Popen(  # noqa: S603
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    existing.update(
        {
            "backend": backend,
            "backend_command": backend_command,
            "project_root": presence.get("current_project_root"),
            "development_log_path": presence.get("current_development_log_path"),
            "status": "starting",
            "pid": proc.pid,
            "log_path": str(log_path),
        }
    )
    if agent == "codex":
        host_thread_id = (
            existing.get("host_thread_id")
            or thread_id_from_main_session_ref(main_session_ref)
            or os.environ.get("CODEX_THREAD_ID")
        )
        record = resolve_rollout_record(project_root=None, thread_id=host_thread_id)
        if record is not None:
            existing = apply_codex_host_binding(
                existing,
                record,
                reset_read_offset=True,
            )
    return save_pickup_state(root, agent, main_session_ref, existing)


def stop_pickup_process(root: Path, agent: str, main_session_ref: str) -> dict[str, Any]:
    state = load_pickup_state(root, agent, main_session_ref)
    pid = state.get("pid")
    if process_alive(pid):
        os.kill(pid, signal.SIGTERM)
        deadline = time.monotonic() + 3.0
        while process_alive(pid) and time.monotonic() < deadline:
            time.sleep(0.1)
        if process_alive(pid):
            os.kill(pid, signal.SIGKILL)
            deadline = time.monotonic() + 1.0
            while process_alive(pid) and time.monotonic() < deadline:
                time.sleep(0.05)
    state["status"] = "stopped"
    state["pid"] = None
    return save_pickup_state(root, agent, main_session_ref, state)


def stop_other_pickups(root: Path, agent: str, keep_main_session_ref: str | None = None) -> list[dict[str, Any]]:
    stopped: list[dict[str, Any]] = []
    for pickup in list_pickup_states(root, agent=agent):
        main_session_ref = pickup.get("main_session_ref")
        if not main_session_ref:
            continue
        if keep_main_session_ref and main_session_ref == keep_main_session_ref:
            continue
        if process_alive(pickup.get("pid")):
            stopped.append(stop_pickup_process(root, agent, main_session_ref))
    return stopped


def build_parser(label: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=f"{label}-facing Relay Hub helper")
    parser.add_argument("--root", help="Relay root directory. Defaults to relay-hub/runtime.")
    parser.add_argument("--agent", help="Agent identity. Falls back to RELAY_AGENT_ID if omitted.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    presence_parser = subparsers.add_parser(
        "set-presence",
        help="Create or update this agent's presence record",
    )
    presence_parser.add_argument("--status", default="ready")

    subparsers.add_parser(
        "agent-status",
        help="Show this agent's current ready/offline state and branch summary",
    )

    sync_parser = subparsers.add_parser(
        "sync-current-main",
        help="When Relay Hub is already enabled, switch the active main session to the current Codex conversation",
    )
    sync_parser.add_argument("--project-root")
    sync_parser.add_argument("--development-log-path")
    sync_group = sync_parser.add_mutually_exclusive_group()
    sync_group.add_argument("--snapshot-body")
    sync_group.add_argument("--snapshot-file")
    sync_parser.add_argument("--preferred-thread-id")
    sync_parser.add_argument("--use-latest-user-thread", action="store_true")
    sync_parser.add_argument("--author")
    sync_parser.add_argument("--backend", choices=["codex-exec", "command"])
    sync_parser.add_argument("--backend-command")
    sync_parser.add_argument("--poll-interval-seconds", type=float, default=2.0)

    prepare_parser = subparsers.add_parser(
        "prepare-main-reply",
        help="Before a normal main-window reply, align to the current Codex conversation and auto-resume one pending branch if needed",
    )
    prepare_parser.add_argument("--project-root")
    prepare_parser.add_argument("--development-log-path")
    prepare_group = prepare_parser.add_mutually_exclusive_group()
    prepare_group.add_argument("--snapshot-body")
    prepare_group.add_argument("--snapshot-file")
    prepare_parser.add_argument("--preferred-thread-id")
    prepare_parser.add_argument("--author")
    prepare_parser.add_argument("--backend", choices=["codex-exec", "command"])
    prepare_parser.add_argument("--backend-command")
    prepare_parser.add_argument("--poll-interval-seconds", type=float, default=2.0)

    enable_parser = subparsers.add_parser(
        "enable-relay",
        help="Mark this agent as ready and attach/create a development log for the current project",
    )
    enable_parser.add_argument("--project-root", required=True)
    enable_parser.add_argument("--development-log-path")
    enable_parser.add_argument("--main-session-ref")
    enable_group = enable_parser.add_mutually_exclusive_group()
    enable_group.add_argument("--snapshot-body")
    enable_group.add_argument("--snapshot-file")
    enable_parser.add_argument("--author")
    enable_parser.add_argument("--start-pickup", action="store_true")
    enable_parser.add_argument("--backend", choices=["codex-exec", "command"])
    enable_parser.add_argument("--backend-command")
    enable_parser.add_argument("--poll-interval-seconds", type=float, default=2.0)
    enable_parser.add_argument(
        "--no-notify-openclaw",
        action="store_true",
        help="Disable the default startup reminder sent via OpenClaw after enable-relay",
    )

    disable_parser = subparsers.add_parser(
        "disable-relay",
        help="Mark this agent as offline for Relay Hub and stop the current attached conversation",
    )
    disable_parser.add_argument("--main-session-ref")

    notification_status_parser = subparsers.add_parser(
        "notification-status",
        help="Show the current OpenClaw reminder channel status for this agent",
    )

    notification_enable_parser = subparsers.add_parser(
        "enable-notification-channel",
        help="Enable one OpenClaw reminder channel for this agent",
    )
    notification_enable_parser.add_argument("--channel", required=True)

    notification_disable_parser = subparsers.add_parser(
        "disable-notification-channel",
        help="Disable one OpenClaw reminder channel for this agent",
    )
    notification_disable_parser.add_argument("--channel", required=True)

    pickup_start_parser = subparsers.add_parser(
        "start-pickup",
        help="Start the sustained pickup loop for one bound main session",
    )
    pickup_start_parser.add_argument("--main-session-ref", required=True)
    pickup_start_parser.add_argument("--backend", choices=["codex-exec", "command"])
    pickup_start_parser.add_argument("--backend-command")
    pickup_main_group = pickup_start_parser.add_mutually_exclusive_group()
    pickup_main_group.add_argument("--main-context-body")
    pickup_main_group.add_argument("--main-context-file")
    pickup_start_parser.add_argument("--poll-interval-seconds", type=float, default=2.0)

    pickup_stop_parser = subparsers.add_parser(
        "stop-pickup",
        help="Stop the sustained pickup loop for one main session",
    )
    pickup_stop_parser.add_argument("--main-session-ref", required=True)

    pickup_status_parser = subparsers.add_parser(
        "pickup-status",
        help="Show sustained pickup status for one or all main sessions of this agent",
    )
    pickup_status_parser.add_argument("--main-session-ref")

    notify_parser = subparsers.add_parser(
        "notify-openclaw",
        help="Send a reminder-only message via configured OpenClaw channels",
    )
    notify_parser.add_argument("--kind", choices=["startup", "message", "shutdown"], default="message")
    notify_group = notify_parser.add_mutually_exclusive_group()
    notify_group.add_argument("--body")
    notify_group.add_argument("--body-file")

    mirror_parser = subparsers.add_parser(
        "mirror-main-output",
        help="Mirror one already-produced main-window output to OpenClaw without re-generating it",
    )
    mirror_group = mirror_parser.add_mutually_exclusive_group(required=True)
    mirror_group.add_argument("--body")
    mirror_group.add_argument("--body-file")

    capture_parser = subparsers.add_parser(
        "capture-main-output",
        help="Queue one already-produced main-window output for exact code-level mirroring by the pickup daemon",
    )
    capture_parser.add_argument("--main-session-ref")
    capture_parser.add_argument("--source", default="host-exact-body")
    capture_group = capture_parser.add_mutually_exclusive_group(required=True)
    capture_group.add_argument("--body")
    capture_group.add_argument("--body-file")

    start_parser = subparsers.add_parser(
        "start-branch",
        help="Open a branch session and optionally seed it with main-chat context",
    )
    start_parser.add_argument("--channel", required=True)
    start_parser.add_argument("--target", required=True)
    start_parser.add_argument("--delivery-mode", choices=["all", "subset"])
    start_parser.add_argument("--delivery-channels", nargs="*")
    start_main_group = start_parser.add_mutually_exclusive_group()
    start_main_group.add_argument("--main-context-body")
    start_main_group.add_argument("--main-context-file")
    start_parser.add_argument("--main-context-source", default="main-chat")
    start_parser.add_argument("--main-session-ref")
    start_parser.add_argument("--main-session-ref-source", default="agent-session")
    start_parser.add_argument("--project-root")
    start_parser.add_argument("--development-log-path")

    note_parser = subparsers.add_parser(
        "append-main-note",
        help="Append a main-chat note into an existing branch transcript",
    )
    note_parser.add_argument("--session", required=True)
    note_parser.add_argument("--source", default="direct-chat")
    note_group = note_parser.add_mutually_exclusive_group(required=True)
    note_group.add_argument("--body")
    note_group.add_argument("--body-file")

    bind_parser = subparsers.add_parser(
        "bind-main-session",
        help="Bind one existing branch to the current main AI session reference",
    )
    bind_parser.add_argument("--session", required=True)
    bind_parser.add_argument("--main-session-ref", required=True)
    bind_parser.add_argument("--source", default="agent-session")

    claim_parser = subparsers.add_parser(
        "claim-next",
        help="Claim the next queued branch for this agent",
    )
    claim_parser.add_argument("--main-session-ref", required=True)
    claim_main_group = claim_parser.add_mutually_exclusive_group()
    claim_main_group.add_argument("--main-context-body")
    claim_main_group.add_argument("--main-context-file")
    claim_parser.add_argument("--main-context-source", default="main-chat")
    claim_parser.add_argument("--project-root")
    claim_parser.add_argument("--development-log-path")

    branch_parser = subparsers.add_parser(
        "branch-context",
        help="Build the branch-processing context from the main seed plus branch transcript",
    )
    branch_parser.add_argument("--session", required=True)
    branch_parser.add_argument("--limit", type=int, default=50)
    branch_parser.add_argument("--main-session-ref", required=True)

    reply_parser = subparsers.add_parser(
        "reply",
        help="Write a progress/final/error message for one branch",
    )
    reply_parser.add_argument("--session", required=True)
    reply_parser.add_argument("--kind", choices=["progress", "final", "error"], required=True)
    reply_group = reply_parser.add_mutually_exclusive_group(required=True)
    reply_group.add_argument("--body")
    reply_group.add_argument("--body-file")
    reply_parser.add_argument("--source-user-message-id")
    reply_parser.add_argument("--no-deliver-via-openclaw", action="store_true")
    reply_parser.add_argument("--no-append-web-url", action="store_true")

    merge_parser = subparsers.add_parser(
        "merge-back",
        help="Build the branch increment that should be merged back into the main chat",
    )
    merge_parser.add_argument("--session", required=True)
    merge_parser.add_argument("--since-message-id")
    merge_parser.add_argument("--limit", type=int, default=100)
    merge_parser.add_argument("--main-session-ref", required=True)
    merge_parser.add_argument(
        "--mark-merged",
        action="store_true",
        help="After building the packet, mark its last branch message as merged back",
    )

    resume_parser = subparsers.add_parser(
        "resume-main",
        help="On the first main-window message after a branch, merge the latest bound branch back and optionally close relay",
    )
    resume_parser.add_argument("--main-session-ref", required=True)
    resume_parser.add_argument("--session")
    resume_parser.add_argument("--limit", type=int, default=100)
    resume_parser.add_argument("--keep-relay-open", action="store_true")

    show_parser = subparsers.add_parser(
        "show-branch",
        help="Show one branch session with main context and transcript",
    )
    show_parser.add_argument("--session", required=True)

    return parser


def main(default_agent: str | None = None, label: str = "Agent") -> None:
    parser = build_parser(label)
    args = parser.parse_args()
    hub = RelayHub(resolve_root(args.root))
    hub.init_layout()
    try:
        if args.command == "set-presence":
            agent = resolve_agent(args.agent, default_agent)
            output({"ok": True, "agent": hub.set_agent(agent, args.status)})
            return

        if args.command == "agent-status":
            agent = resolve_agent(args.agent, default_agent)
            output({"ok": True, "status": build_agent_status(hub, agent)})
            return

        if args.command == "sync-current-main":
            output(
                sync_codex_main_session(
                    hub=hub,
                    agent=resolve_agent(args.agent, default_agent),
                    project_root=args.project_root,
                    development_log_path=args.development_log_path,
                    snapshot_body=read_body(args.snapshot_body, args.snapshot_file),
                    author=args.author,
                    backend=args.backend,
                    backend_command=args.backend_command,
                    poll_interval_seconds=args.poll_interval_seconds,
                    preferred_thread_id=args.preferred_thread_id,
                    use_latest_user_thread=args.use_latest_user_thread,
                )
            )
            return

        if args.command == "prepare-main-reply":
            output(
                prepare_codex_main_reply(
                    hub=hub,
                    agent=resolve_agent(args.agent, default_agent),
                    project_root=args.project_root,
                    development_log_path=args.development_log_path,
                    snapshot_body=read_body(args.snapshot_body, args.snapshot_file),
                    author=args.author,
                    backend=args.backend,
                    backend_command=args.backend_command,
                    poll_interval_seconds=args.poll_interval_seconds,
                    preferred_thread_id=args.preferred_thread_id,
                )
            )
            return

        if args.command == "enable-relay":
            agent = resolve_agent(args.agent, default_agent)
            snapshot_body = read_body(args.snapshot_body, args.snapshot_file)
            binding = None
            if snapshot_body is None and agent == "codex":
                binding = resolve_codex_conversation_binding(
                    hub.root,
                    agent,
                    project_root=args.project_root,
                    explicit_main_session_ref=args.main_session_ref,
                )
                snapshot_body = auto_enable_snapshot_body(
                    project_root=binding.get("project_root") or args.project_root,
                    thread_id=str(binding["thread_id"]),
                )
            if snapshot_body is None:
                fail("enable-relay requires --snapshot-body or --snapshot-file; codex can omit them only when the current conversation is resolvable")
            main_session_ref = auto_main_session_ref(hub.root, agent, args.project_root, args.main_session_ref) if args.start_pickup else args.main_session_ref
            payload = hub.enable_agent(
                agent=agent,
                project_root=args.project_root,
                development_log_path=args.development_log_path,
                snapshot_body=snapshot_body,
                main_session_ref=main_session_ref,
                author=args.author or agent,
            )
            pickup = None
            stopped_pickups: list[dict[str, Any]] = []
            if args.start_pickup:
                stopped_pickups = stop_other_pickups(hub.root, agent, keep_main_session_ref=main_session_ref)
                pickup = start_pickup_process(
                    hub=hub,
                    root=hub.root,
                    agent=agent,
                    main_session_ref=main_session_ref,
                    backend=pick_backend(args.backend, agent),
                    backend_command=args.backend_command,
                    poll_interval_seconds=args.poll_interval_seconds,
                    main_context_body=snapshot_body,
                )
                hub.set_active_main_session(
                    agent,
                    main_session_ref,
                    project_root=args.project_root,
                    development_log_path=payload["development_log_path"],
                )
            resume_candidates = hub.resume_candidates(agent, main_session_ref) if main_session_ref else []
            notification = None
            if not args.no_notify_openclaw:
                startup_note = None
                if resume_candidates:
                    count = len(resume_candidates)
                    if count == 1:
                        startup_note = (
                            "检测到 1 条未合流的旧 branch。"
                            "如果你要先把它接回主窗口，可回主窗口说“合流上下文”；"
                            "如果你只是继续远程处理，也可以直接点下方网页入口。"
                        )
                    else:
                        startup_note = (
                            f"检测到 {count} 条未合流的旧 branch。"
                            "如果你要先把其中一条接回主窗口，可回主窗口说“合流上下文”；"
                            "如果你只是继续远程处理，也可以直接点下方网页入口。"
                        )
                relay_args = [
                    "notify",
                    "--agent",
                    agent,
                    "--kind",
                    "startup",
                ]
                if startup_note:
                    relay_args.extend(["--body", startup_note])
                notification = run_openclaw_bridge(
                    relay_args
                )
            output(
                {
                    "ok": True,
                    "relay_enabled": payload,
                    "main_session_ref": main_session_ref,
                    "pickup": pickup,
                    "stopped_pickups": stopped_pickups,
                    "resume_candidates": resume_candidates,
                    "notification": notification,
                }
            )
            return

        if args.command == "disable-relay":
            agent = resolve_agent(args.agent, default_agent)
            presence = hub.get_agent(agent)
            main_session_ref = args.main_session_ref or presence.get("current_main_session_ref")
            disabled_agent = hub.disable_agent(agent)
            stopped_pickups = stop_other_pickups(hub.root, agent, keep_main_session_ref=None)
            notification = run_openclaw_bridge(
                [
                    "notify",
                    "--agent",
                    agent,
                    "--kind",
                    "shutdown",
                ]
            )
            output(
                {
                    "ok": True,
                    "disabled_agent": disabled_agent,
                    "stopped_pickups": stopped_pickups,
                    "main_session_ref": main_session_ref,
                    "notification": notification,
                }
            )
            return

        if args.command == "notification-status":
            agent = resolve_agent(args.agent, default_agent)
            output(build_notification_status_payload(hub, agent))
            return

        if args.command in {"enable-notification-channel", "disable-notification-channel"}:
            agent = resolve_agent(args.agent, default_agent)
            delivery_channels = load_openclaw_delivery_channels()
            configured_channels = list(delivery_channels.keys())
            if not configured_channels:
                fail("当前还没有配置任何 OpenClaw 消息渠道。")
            channel = resolve_channel_token(args.channel, configured_channels)
            enabled = args.command == "enable-notification-channel"
            payload = hub.set_notification_channel_enabled(agent, channel, enabled)
            status_payload = build_notification_status_payload(hub, agent)
            status_payload["changed_channel"] = channel
            status_payload["changed_display_name"] = display_channel_name(channel)
            status_payload["changed_enabled"] = enabled
            action_text = "开启" if enabled else "关闭"
            status_payload["user_message"] = (
                f"已{action_text}{display_channel_name(channel)}消息提醒。"
                f"\n{status_payload['user_message']}"
            )
            status_payload["agent_state"] = payload["agent"]
            output(status_payload)
            return

        if args.command == "start-pickup":
            agent = resolve_agent(args.agent, default_agent)
            payload = start_pickup_process(
                hub=hub,
                root=hub.root,
                agent=agent,
                main_session_ref=args.main_session_ref,
                backend=pick_backend(args.backend, agent),
                backend_command=args.backend_command,
                poll_interval_seconds=args.poll_interval_seconds,
                main_context_body=read_body(args.main_context_body, args.main_context_file),
            )
            output({"ok": True, "pickup": payload})
            return

        if args.command == "stop-pickup":
            agent = resolve_agent(args.agent, default_agent)
            payload = stop_pickup_process(hub.root, agent, args.main_session_ref)
            output({"ok": True, "pickup": payload})
            return

        if args.command == "pickup-status":
            agent = resolve_agent(args.agent, default_agent)
            if args.main_session_ref:
                payload = load_pickup_state(hub.root, agent, args.main_session_ref)
                payload["alive"] = process_alive(payload.get("pid"))
                output({"ok": True, "pickup": payload})
                return
            output({"ok": True, "pickup": list_pickup_states(hub.root, agent=agent)})
            return

        if args.command == "notify-openclaw":
            agent = resolve_agent(args.agent, default_agent)
            preferred_main_session_ref = None
            preferred_project_root = None
            preferred_development_log_path = None
            if agent == "codex":
                notify_binding = resolve_codex_notify_binding(
                    hub=hub,
                    agent=agent,
                )
                preferred_main_session_ref = notify_binding.get("main_session_ref")
                preferred_project_root = notify_binding.get("project_root")
                preferred_development_log_path = notify_binding.get("development_log_path")
            body = read_body(args.body, args.body_file)
            relay_args = [
                "notify",
                "--agent",
                agent,
                "--kind",
                args.kind,
            ]
            if preferred_main_session_ref:
                relay_args.extend(["--main-session-ref", preferred_main_session_ref])
            if preferred_project_root:
                relay_args.extend(["--project-root", preferred_project_root])
            if preferred_development_log_path:
                relay_args.extend(["--development-log-path", preferred_development_log_path])
            if body is not None:
                relay_args.extend(["--body", body])
            payload = run_openclaw_bridge(relay_args)
            output(payload)
            return

        if args.command == "mirror-main-output":
            agent = resolve_agent(args.agent, default_agent)
            body = read_body(args.body, args.body_file)
            if body is None:
                fail("mirror-main-output requires --body or --body-file")
            output(
                run_openclaw_bridge(
                    [
                        "notify",
                        "--agent",
                        agent,
                        "--kind",
                        "message",
                        "--body",
                        body,
                    ]
                )
            )
            return

        if args.command == "capture-main-output":
            agent = resolve_agent(args.agent, default_agent)
            body = read_body(args.body, args.body_file)
            if body is None:
                fail("capture-main-output requires --body or --body-file")
            presence = hub.get_agent(agent)
            main_session_ref = args.main_session_ref or presence.get("current_main_session_ref")
            if not main_session_ref:
                fail("capture-main-output requires --main-session-ref or an attached current_main_session_ref")
            payload = enqueue_captured_main_output(
                root=hub.root,
                agent=agent,
                main_session_ref=main_session_ref,
                body=body,
                source=args.source,
            )
            output(
                {
                    "ok": True,
                    "capture": payload,
                    "queue_dir": str(pickup_capture_queue_dir(hub.root, agent, main_session_ref)),
                }
            )
            return

        if args.command == "start-branch":
            agent = resolve_agent(args.agent, default_agent)
            presence = hub.get_agent(agent)
            main_context_body = read_body(args.main_context_body, args.main_context_file)
            payload = hub.open_session(
                agent=agent,
                channel=args.channel,
                target=args.target,
                delivery_mode=args.delivery_mode,
                delivery_channels=args.delivery_channels,
                main_context_body=main_context_body,
                main_context_source=args.main_context_source,
                main_session_ref=args.main_session_ref,
                main_session_ref_source=args.main_session_ref_source,
            )
            project_root = resolve_project_value(args, presence, "project_root")
            development_log_path = resolve_project_value(args, presence, "development_log_path")
            attached_project = None
            if project_root or development_log_path:
                attached_project = hub.attach_project(
                    payload["session_key"],
                    project_root=project_root or presence.get("current_project_root"),
                    development_log_path=development_log_path,
                    snapshot_body=main_context_body,
                    author=agent,
                )
            output(
                {
                    "ok": True,
                    "branch": payload,
                    "attached_project": attached_project,
                    "next_steps": [
                        f"Open the web entry: {payload['meta']['web_url']}",
                        "The branch is only considered started after the first web message is saved.",
                        f"When branch input is done, dispatch session: {payload['session_key']}",
                        f"Before {agent} processes the branch, read branch-context.",
                    ],
                }
            )
            return

        if args.command == "append-main-note":
            payload = hub.commit_user_message(
                session_key=args.session,
                body=read_body(args.body, args.body_file) or "",
                source=args.source,
            )
            output({"ok": True, "note": payload})
            return

        if args.command == "bind-main-session":
            payload = hub.set_main_session_ref(
                args.session,
                args.main_session_ref,
                source=args.source,
            )
            output({"ok": True, "main_session": payload})
            return

        if args.command == "claim-next":
            agent = resolve_agent(args.agent, default_agent)
            presence = hub.get_agent(agent)
            main_context_body = read_body(args.main_context_body, args.main_context_file)
            payload = hub.claim_next(agent, main_session_ref=args.main_session_ref)
            attached_project = None
            attached_main_context = None
            if payload is not None:
                project_root = resolve_project_value(args, presence, "project_root")
                development_log_path = resolve_project_value(args, presence, "development_log_path")
                if project_root or development_log_path:
                    attached_project = hub.attach_project(
                        payload["session_key"],
                        project_root=project_root or presence.get("current_project_root"),
                        development_log_path=development_log_path,
                        snapshot_body=main_context_body,
                        author=agent,
                    )
                if main_context_body is not None:
                    attached_main_context = hub.set_main_context(
                        payload["session_key"],
                        main_context_body,
                        source=args.main_context_source,
                    )
            output(
                {
                    "ok": payload is not None,
                    "claim": payload,
                    "attached_project": attached_project,
                    "attached_main_context": attached_main_context,
                }
            )
            return

        if args.command == "branch-context":
            payload = hub.build_context(
                args.session,
                limit=args.limit,
                expected_main_session_ref=args.main_session_ref,
            )
            output({"ok": True, "branch_context": payload})
            return

        if args.command == "reply":
            agent = resolve_agent(args.agent, default_agent)
            payload = hub.write_agent_message(
                session_key=args.session,
                agent=agent,
                kind=args.kind,
                body=read_body(args.body, args.body_file) or "",
                source_user_message_id=args.source_user_message_id,
                deliver_via_openclaw=not args.no_deliver_via_openclaw,
                append_web_url=not args.no_append_web_url,
            )
            output({"ok": True, "reply": payload})
            return

        if args.command == "merge-back":
            payload = hub.build_merge_back(
                args.session,
                since_message_id=args.since_message_id,
                limit=args.limit,
                expected_main_session_ref=args.main_session_ref,
                require_main_session_ref=bool(args.main_session_ref),
            )
            merged = None
            if args.mark_merged:
                last_id = last_branch_message_id(payload)
                if last_id:
                    merged = hub.mark_merged_back(args.session, last_id)
            output({"ok": True, "merge_back": payload, "mark_merged_result": merged})
            return

        if args.command == "resume-main":
            agent = resolve_agent(args.agent, default_agent)
            try:
                payload = hub.resume_main(
                    agent=agent,
                    main_session_ref=args.main_session_ref,
                    session_key=args.session,
                    limit=args.limit,
                    close_relay=not args.keep_relay_open,
                )
            except ValueError as exc:
                if "multiple relay branches are still bound to this main session" not in str(exc):
                    raise
                output(
                    {
                        "ok": False,
                        "resume_main": None,
                        "user_message": "当前主会话下有多条未合流的旧 branch，请先明确要合流哪一条。",
                        "resume_candidates": hub.resume_candidates(agent, args.main_session_ref),
                    }
                )
                return
            output({"ok": payload is not None, "resume_main": payload})
            return

        if args.command == "show-branch":
            output({"ok": True, "branch": hub.get_session(args.session)})
            return
    except (FileNotFoundError, ValueError) as exc:
        fail(str(exc))

    parser.error(f"unknown command: {args.command}")


if __name__ == "__main__":
    main()
