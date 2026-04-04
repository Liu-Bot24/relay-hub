#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from relay_hub import RelayHub
from relay_hub.codex_host import (
    read_new_task_completions,
    resolve_active_reply_thread_record,
    resolve_rollout_record,
    thread_id_from_main_session_ref,
    thread_record,
)
from relay_hub.pickup import (
    load_pickup_state,
    pickup_capture_queue_dir,
    pickup_context_seed_path,
    save_pickup_state,
)

DEFAULT_ROOT = (PROJECT_ROOT.parent / "runtime") if PROJECT_ROOT.name == "app" else ((Path.home() / "Library" / "Application Support" / "RelayHub" / "runtime") if (Path.home() / "Library" / "Application Support" / "RelayHub" / "runtime").exists() else (PROJECT_ROOT / "runtime"))
DEFAULT_OPENCLAW_BRIDGE = PROJECT_ROOT / "scripts" / "relay_openclaw_bridge.py"
DEFAULT_AGENT_RELAY = PROJECT_ROOT / "scripts" / "agent_relay.py"

STOP_REQUESTED = False


def handle_stop(_signum: int, _frame: Any) -> None:
    global STOP_REQUESTED
    STOP_REQUESTED = True


def output(payload: object) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def notify_trace_path(root: Path, agent: str) -> Path:
    return root / "logs" / f"{agent}.notify-trace.jsonl"


def append_notify_trace(root: Path, agent: str, payload: dict[str, Any]) -> None:
    path = notify_trace_path(root, agent)
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "pid": os.getpid(),
        **payload,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def resolve_root(value: str | None) -> Path:
    return Path(value).expanduser().resolve() if value else DEFAULT_ROOT


def read_optional_text(body: str | None, body_file: str | None) -> str | None:
    if body is not None:
        return body
    if body_file is not None:
        return Path(body_file).read_text(encoding="utf-8")
    return None


def parse_backend_command_json(raw: str) -> list[str]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"--backend-command must be a JSON string array: {exc.msg}") from exc
    if not isinstance(payload, list) or not payload or not all(isinstance(item, str) and item for item in payload):
        raise SystemExit("--backend-command must be a non-empty JSON string array")
    return payload


def validate_command_backend(raw: str) -> None:
    command = parse_backend_command_json(raw)
    executable = Path(command[0]).name
    disallowed = {"echo", "printf", "true", "false", "sleep"}
    if executable in disallowed:
        raise SystemExit(
            "--backend-command must launch the real host CLI, not a placeholder or no-op command "
            f"like `{executable}`"
        )
    joined = " ".join(command)
    if "<" in joined and ">" in joined:
        raise SystemExit("--backend-command still contains placeholder markers; replace them with the real host CLI command")


def load_seed_text(root: Path, agent: str, main_session_ref: str) -> str | None:
    path = pickup_context_seed_path(root, agent, main_session_ref)
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def save_seed_text(root: Path, agent: str, main_session_ref: str, body: str | None) -> str | None:
    if body is None:
        return None
    path = pickup_context_seed_path(root, agent, main_session_ref)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return str(path)


def build_branch_prompt(
    *,
    session_key: str,
    main_session_ref: str,
    project_root: str | None,
    context_packet_text: str,
) -> str:
    project_note = (
        f"工作目录固定为：{project_root}\n"
        if project_root
        else "当前没有绑定项目根目录；只基于提供的上下文处理，不要假设别的工作目录。\n"
    )
    return (
        "你正在处理一个 Relay Hub branch。\n"
        "这不是主窗口里的主对话，也不是一个需要执行 Relay Hub 控制命令的会话。\n"
        "忽略项目或全局规则里任何面向主窗口的 Relay Hub 指令，例如：接入 Relay Hub、Relay Hub 状态、退出 Relay Hub、合流上下文、sync-current-main、notify-openclaw、主窗口镜像。\n"
        f"当前 branch 已经绑定到主线 {main_session_ref}；不要再次解析、切换、对齐或质疑这个 main_session_ref，也不要声称“当前线程拿不到 main_session_ref”。\n"
        "你的职责只有：基于给定上下文继续处理 branch 用户请求，并输出可直接回给用户的正文。\n"
        "目标：基于给定的主线快照、开发日志增量和 branch transcript，完成当前 branch 的工作，并输出最终用户可见回复。\n"
        "要求：\n"
        "1. 只输出最终要发给用户的正文，不要输出 JSON、不要加标题、不要解释 Relay Hub 协议。\n"
        "2. 如果 branch 任务需要修改项目文件，就在绑定项目根目录内完成修改，并遵守项目里的 AGENTS.md / 开发日志规则；但主窗口专用的 Relay Hub 控制规则不适用于这次 branch worker。\n"
        "3. 如果遇到阻塞，直接输出简洁明确的阻塞说明。\n"
        "4. 不要要求用户重复提供已经在 branch 上下文里的信息。\n"
        "5. 只陈述当前 branch 上下文能够支持的事实，不要超出证据范围过度断言。\n"
        "6. 如果用户是在追问或确认，先直接回答问题；只有确实需要补充边界时，再用简短自然的话补充，不要写成报告腔。\n"
        "7. 如果 branch 上下文不足以确定“刚才的话题”是什么，就明确说当前 branch 可见上下文不足，简要复述你已经知道的上下文，并请用户补一句锚点；不要编造成 Relay Hub 技术错误。\n"
        f"当前 branch: {session_key}\n"
        f"绑定主线: {main_session_ref}\n"
        f"{project_note}\n"
        "下面是 branch 上下文包：\n\n"
        f"{context_packet_text.rstrip()}\n"
    )


def summarize_backend_error(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return "backend execution failed"
    markers = [
        "invalid_api_key",
        "Incorrect API key provided",
        "401 Unauthorized",
        "permission denied",
        "No such file or directory",
    ]
    for marker in markers:
        for line in reversed(lines):
            if marker in line:
                return line
    for line in reversed(lines):
        if line.startswith("ERROR:"):
            return line.removeprefix("ERROR:").strip()
    return lines[-1]


def run_codex_exec_backend(project_root: str | None, prompt: str) -> tuple[str | None, str | None]:
    output_file = Path(tempfile.mkstemp(prefix="relayhub-codex-", suffix=".txt")[1])
    try:
        env = os.environ.copy()
        for key in (
            "OPENAI_API_KEY",
            "OPENAI_BASE_URL",
            "OPENAI_ORG_ID",
            "CODEX_API_KEY",
            "CODEX_THREAD_ID",
            "CODEX_INTERNAL_ORIGINATOR_OVERRIDE",
        ):
            env.pop(key, None)
        cmd = [
            "codex",
            "exec",
            "--ephemeral",
            "--skip-git-repo-check",
            "--dangerously-bypass-approvals-and-sandbox",
            "-o",
            str(output_file),
        ]
        if project_root:
            cmd.extend(["--cd", project_root])
        cmd.append("-")
        result = subprocess.run(  # noqa: S603
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            env=env,
        )
        if result.returncode != 0:
            detail = summarize_backend_error(result.stderr or result.stdout or "codex exec failed")
            return None, detail
        body = output_file.read_text(encoding="utf-8").strip() if output_file.exists() else ""
        if not body:
            body = (result.stdout or "").strip()
        if not body:
            return None, "codex exec returned empty output"
        return body, None
    finally:
        output_file.unlink(missing_ok=True)


def run_command_backend(
    command_json: str,
    env_updates: dict[str, str],
    prompt: str,
    *,
    cwd: str | None = None,
) -> tuple[str | None, str | None]:
    try:
        command = json.loads(command_json)
    except json.JSONDecodeError as exc:
        return None, f"invalid backend_command JSON: {exc}"
    if not isinstance(command, list) or not all(isinstance(item, str) for item in command):
        return None, "backend_command must be a JSON string array"
    output_file = Path(tempfile.mkstemp(prefix="relayhub-backend-", suffix=".txt")[1])
    env = os.environ.copy()
    env.update(env_updates)
    env["RELAY_OUTPUT_FILE"] = str(output_file)
    try:
        result = subprocess.run(  # noqa: S603
            command,
            input=prompt,
            capture_output=True,
            text=True,
            env=env,
            cwd=cwd or None,
        )
        if result.returncode != 0:
            detail = summarize_backend_error(result.stderr or result.stdout or "backend command failed")
            return None, detail
        body = output_file.read_text(encoding="utf-8").strip() if output_file.exists() else ""
        if not body:
            body = (result.stdout or "").strip()
        if not body:
            return None, "backend command returned empty output"
        return body, None
    finally:
        output_file.unlink(missing_ok=True)


def maybe_pump_deliveries(root: Path) -> str | None:
    if not DEFAULT_OPENCLAW_BRIDGE.exists():
        return None
    result = subprocess.run(  # noqa: S603
        [sys.executable, str(DEFAULT_OPENCLAW_BRIDGE), "pump-deliveries"],
        capture_output=True,
        text=True,
    )
    text = (result.stdout or result.stderr or "").strip()
    if result.returncode != 0:
        return f"pump_failed: {text or 'relay_openclaw_bridge.py pump-deliveries failed'}"
    return text or None


def notify_openclaw(
    root: Path,
    agent: str,
    body: str,
    *,
    main_session_ref: str | None = None,
    project_root: str | None = None,
    development_log_path: str | None = None,
) -> dict[str, Any]:
    body_sha256 = hashlib.sha256(body.encode("utf-8")).hexdigest()
    append_notify_trace(
        root,
        agent,
        {
            "event": "notify_openclaw_start",
            "main_session_ref": main_session_ref,
            "project_root": project_root,
            "development_log_path": development_log_path,
            "body_sha256": body_sha256,
            "body_preview": preview_text(body),
        },
    )
    cmd = [
        sys.executable,
        str(DEFAULT_OPENCLAW_BRIDGE),
        "--json",
        "notify",
        "--agent",
        agent,
        "--kind",
        "message",
        "--body",
        body,
    ]
    if main_session_ref:
        cmd.extend(["--main-session-ref", main_session_ref])
    if project_root:
        cmd.extend(["--project-root", project_root])
    if development_log_path:
        cmd.extend(["--development-log-path", development_log_path])
    result = subprocess.run(  # noqa: S603
        cmd,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        text = (result.stderr or result.stdout or "").strip() or "relay_openclaw_bridge notify failed"
        append_notify_trace(
            root,
            agent,
            {
                "event": "notify_openclaw_error",
                "main_session_ref": main_session_ref,
                "body_sha256": body_sha256,
                "error": text,
            },
        )
        return {
            "ok": False,
            "error": text,
        }
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        append_notify_trace(
            root,
            agent,
            {
                "event": "notify_openclaw_invalid_json",
                "main_session_ref": main_session_ref,
                "body_sha256": body_sha256,
                "stdout_preview": preview_text((result.stdout or "").strip()),
            },
        )
        return {
            "ok": False,
            "error": (result.stdout or "").strip() or "invalid notify JSON",
        }
    append_notify_trace(
        root,
        agent,
        {
            "event": "notify_openclaw_done",
            "main_session_ref": main_session_ref,
            "body_sha256": body_sha256,
            "notify_ok": payload.get("ok"),
            "notify_kind": payload.get("kind"),
        },
    )
    return payload


def handoff_to_thread(
    *,
    root: Path,
    agent: str,
    backend: str,
    backend_command: str | None,
    poll_interval_seconds: float,
    thread_id: str,
) -> dict[str, Any]:
    cmd = [
        sys.executable,
        str(DEFAULT_AGENT_RELAY),
        "--root",
        str(root),
        "--agent",
        agent,
        "sync-current-main",
        "--preferred-thread-id",
        thread_id,
        "--backend",
        backend,
        "--poll-interval-seconds",
        str(poll_interval_seconds),
    ]
    if backend_command:
        cmd.extend(["--backend-command", backend_command])
    result = subprocess.run(cmd, capture_output=True, text=True)  # noqa: S603
    if result.returncode != 0:
        return {
            "ok": False,
            "error": summarize_backend_error(result.stderr or result.stdout or "sync-current-main failed"),
        }
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        payload = {"ok": False, "error": "invalid sync-current-main JSON"}
    return payload


def preview_text(body: str, limit: int = 120) -> str:
    text = " ".join(body.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "..."


def enqueue_captured_main_output(
    *,
    root: Path,
    agent: str,
    main_session_ref: str,
    body: str,
    source: str = "host-exact-body",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    queue_dir = pickup_capture_queue_dir(root, agent, main_session_ref)
    queue_dir.mkdir(parents=True, exist_ok=True)
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    item_id = f"{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}"
    path = queue_dir / f"{item_id}.json"
    payload = {
        "id": item_id,
        "agent": agent,
        "main_session_ref": main_session_ref,
        "body": body,
        "source": source,
        "created_at": now,
        "metadata": metadata or {},
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "item_id": item_id,
        "path": str(path),
        "created_at": now,
    }


def drain_capture_queue_once(
    *,
    root: Path,
    agent: str,
    main_session_ref: str,
) -> dict[str, Any]:
    queue_dir = pickup_capture_queue_dir(root, agent, main_session_ref)
    if not queue_dir.exists():
        return {"mirrored": False, "reason": "no_capture_queue"}
    for path in sorted(queue_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {
                "mirrored": False,
                "reason": "invalid_capture_payload",
                "path": str(path),
            }
        body = str(payload.get("body") or "").strip()
        if not body:
            path.unlink(missing_ok=True)
            continue
        state = load_pickup_state(root, agent, main_session_ref)
        notify_result = notify_openclaw(
            root,
            agent,
            body,
            main_session_ref=main_session_ref,
            project_root=state.get("project_root"),
            development_log_path=state.get("development_log_path"),
        )
        if not notify_result.get("ok"):
            return {
                "mirrored": False,
                "reason": "notify_failed",
                "capture": payload,
                "notify": notify_result,
            }
        path.unlink(missing_ok=True)
        metadata = payload.get("metadata") or {}
        state.update(
            {
                "last_mirrored_turn_id": metadata.get("turn_id") or payload.get("id"),
                "last_mirrored_at": payload.get("created_at") or time.strftime("%Y-%m-%dT%H:%M:%S"),
                "last_mirrored_body_preview": preview_text(body),
                "last_error": None,
            }
        )
        save_pickup_state(root, agent, main_session_ref, state)
        return {
            "mirrored": True,
            "source": "capture-queue",
            "capture": payload,
            "notify": notify_result,
        }
    return {"mirrored": False, "reason": "no_new_capture"}


def ensure_codex_host_binding(
    root: Path,
    agent: str,
    main_session_ref: str,
    project_root: str | None,
) -> dict[str, Any]:
    state = load_pickup_state(root, agent, main_session_ref)
    if state.get("host_rollout_path") and Path(state["host_rollout_path"]).exists():
        return state
    if agent != "codex":
        return state
    thread_id = state.get("host_thread_id") or thread_id_from_main_session_ref(main_session_ref)
    if not thread_id:
        return state
    record = resolve_rollout_record(
        project_root=None,
        thread_id=thread_id,
    )
    if not record:
        return state
    rollout_path = Path(record["rollout_path"]).expanduser().resolve()
    mirror_offset = int(state.get("mirror_read_offset") or 0)
    if not mirror_offset and rollout_path.exists():
        mirror_offset = rollout_path.stat().st_size
    state.update(
        {
            "host_kind": "codex-rollout",
            "host_thread_id": record.get("id"),
            "host_rollout_path": str(rollout_path),
            "mirror_read_offset": mirror_offset,
        }
    )
    return save_pickup_state(root, agent, main_session_ref, state)


def codex_host_still_active(state: dict[str, Any]) -> tuple[bool, str | None]:
    thread_id = state.get("host_thread_id")
    if not thread_id:
        return True, None
    record = thread_record(str(thread_id), include_archived=True)
    if record is None:
        return False, "host_thread_missing"
    if record.get("archived"):
        return False, "host_thread_archived"
    return True, None


def mirror_main_output_once(
    *,
    hub: RelayHub,
    root: Path,
    agent: str,
    main_session_ref: str,
    carry: bytes,
) -> tuple[dict[str, Any], bytes]:
    state = load_pickup_state(root, agent, main_session_ref)
    state = ensure_codex_host_binding(root, agent, main_session_ref, state.get("project_root"))
    if state.get("host_kind") == "codex-rollout" and state.get("host_rollout_path"):
        events, next_offset, carry = read_new_task_completions(
            state["host_rollout_path"],
            int(state.get("mirror_read_offset") or 0),
            carry,
        )
        result: dict[str, Any] = {"mirrored": False, "reason": "no_new_task_complete"}
        state["mirror_read_offset"] = next_offset
        for event in events:
            if event["turn_id"] == state.get("last_mirrored_turn_id"):
                continue
            append_notify_trace(
                root,
                agent,
                {
                    "event": "mirror_task_complete",
                    "main_session_ref": main_session_ref,
                    "turn_id": event["turn_id"],
                    "turn_timestamp": event.get("timestamp"),
                    "body_sha256": hashlib.sha256(event["message"].encode("utf-8")).hexdigest(),
                    "body_preview": preview_text(event["message"]),
                },
            )
            notify_result = notify_openclaw(
                root,
                agent,
                event["message"],
                main_session_ref=main_session_ref,
                project_root=state.get("project_root"),
                development_log_path=state.get("development_log_path"),
            )
            if notify_result.get("ok"):
                state.update(
                    {
                        "last_mirrored_turn_id": event["turn_id"],
                        "last_mirrored_at": event.get("timestamp") or time.strftime("%Y-%m-%dT%H:%M:%S"),
                        "last_mirrored_body_preview": preview_text(event["message"]),
                        "last_error": None,
                    }
                )
                result = {
                    "mirrored": True,
                    "source": "codex-rollout",
                    "turn_id": event["turn_id"],
                    "notify": notify_result,
                }
            else:
                state["last_error"] = notify_result.get("error") or "notify failed"
                result = {
                    "mirrored": False,
                    "reason": "notify_failed",
                    "turn_id": event["turn_id"],
                    "notify": notify_result,
                }
        save_pickup_state(root, agent, main_session_ref, state)
        if result.get("mirrored"):
            return result, carry
    queue_result = drain_capture_queue_once(
        root=root,
        agent=agent,
        main_session_ref=main_session_ref,
    )
    return queue_result, carry


def update_pickup_state(
    root: Path,
    agent: str,
    main_session_ref: str,
    **updates: Any,
) -> dict[str, Any]:
    state = load_pickup_state(root, agent, main_session_ref)
    state.update(updates)
    return save_pickup_state(root, agent, main_session_ref, state)


def process_once(
    *,
    hub: RelayHub,
    root: Path,
    agent: str,
    main_session_ref: str,
    backend: str,
    backend_command: str | None,
) -> dict[str, Any]:
    claim = hub.claim_next(agent, main_session_ref=main_session_ref)
    if claim is None:
        return {"processed": False, "reason": "no_queued_branch"}
    session_key = claim["session_key"]
    meta = claim["meta"]
    seed_text = load_seed_text(root, agent, main_session_ref)
    attached_project = None
    attached_main_context = None
    if meta.get("project_root") or meta.get("development_log_path"):
        project_root = meta.get("project_root")
    else:
        pickup_state = load_pickup_state(root, agent, main_session_ref)
        project_root = pickup_state.get("project_root")
        development_log_path = pickup_state.get("development_log_path")
        if project_root or development_log_path:
            attached_project = hub.attach_project(
                session_key,
                project_root=project_root,
                development_log_path=development_log_path,
                snapshot_body=seed_text,
                author=agent,
            )
            meta = hub.get_meta(session_key)
    if not hub.get_main_context(session_key).get("body") and seed_text:
        attached_main_context = hub.set_main_context(session_key, seed_text, source="pickup-daemon")
    branch_context = hub.build_context(
        session_key,
        expected_main_session_ref=main_session_ref,
    )
    project_root = meta.get("project_root")
    prompt = build_branch_prompt(
        session_key=session_key,
        main_session_ref=main_session_ref,
        project_root=project_root,
        context_packet_text=branch_context["context_packet_text"],
    )
    if backend == "codex-exec":
        body, error = run_codex_exec_backend(project_root, prompt)
    elif backend == "command":
        env_updates = {
            "RELAY_SESSION_KEY": session_key,
            "RELAY_AGENT_ID": agent,
            "RELAY_MAIN_SESSION_REF": main_session_ref,
            "RELAY_PROJECT_ROOT": project_root or "",
            "RELAY_CONTEXT_TEXT": branch_context["context_packet_text"],
        }
        body, error = run_command_backend(backend_command or "", env_updates, prompt, cwd=project_root)
    else:
        raise ValueError(f"unsupported backend: {backend}")
    if error:
        reply = hub.write_agent_message(
            session_key=session_key,
            agent=agent,
            kind="error",
            body=f"Relay Hub 自动接单失败：{error}",
        )
        pump_result = maybe_pump_deliveries(root)
        return {
            "processed": True,
            "session_key": session_key,
            "attached_project": attached_project,
            "attached_main_context": attached_main_context,
            "branch_context": branch_context,
            "reply": reply,
            "error": error,
            "pump_result": pump_result,
        }
    reply = hub.write_agent_message(
        session_key=session_key,
        agent=agent,
        kind="final",
        body=body,
    )
    pump_result = maybe_pump_deliveries(root)
    return {
        "processed": True,
        "session_key": session_key,
        "attached_project": attached_project,
        "attached_main_context": attached_main_context,
        "branch_context": branch_context,
        "reply": reply,
        "pump_result": pump_result,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Relay Hub sustained pickup daemon")
    parser.add_argument("--root")
    parser.add_argument("--agent", required=True)
    parser.add_argument("--main-session-ref", required=True)
    parser.add_argument("--backend", choices=["codex-exec", "command"], required=True)
    parser.add_argument("--backend-command", help="JSON string array for backend=command")
    parser.add_argument("--poll-interval-seconds", type=float, default=2.0)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--main-context-body")
    parser.add_argument("--main-context-file")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.backend == "command" and not args.backend_command:
        raise SystemExit("--backend-command is required when --backend=command")
    if args.backend == "command" and args.backend_command:
        validate_command_backend(args.backend_command)
    root = resolve_root(args.root)
    hub = RelayHub(root)
    hub.init_layout()
    seed_text = read_optional_text(args.main_context_body, args.main_context_file)
    if seed_text is not None:
        save_seed_text(root, args.agent, args.main_session_ref, seed_text)

    signal.signal(signal.SIGTERM, handle_stop)
    signal.signal(signal.SIGINT, handle_stop)

    state = load_pickup_state(root, args.agent, args.main_session_ref)
    state = ensure_codex_host_binding(root, args.agent, args.main_session_ref, state.get("project_root"))
    if not state.get("created_at"):
        state["created_at"] = hub.config().get("created_at") or time.strftime("%Y-%m-%dT%H:%M:%S")
    state.update(
        {
            "backend": args.backend,
            "backend_command": args.backend_command,
            "status": "running",
            "pid": os.getpid(),
            "last_error": None,
        }
    )
    save_pickup_state(root, args.agent, args.main_session_ref, state)
    mirror_carry = b""

    if args.once:
        result = process_once(
            hub=hub,
            root=root,
            agent=args.agent,
            main_session_ref=args.main_session_ref,
            backend=args.backend,
            backend_command=args.backend_command,
        )
        mirror_result, _ = mirror_main_output_once(
            hub=hub,
            root=root,
            agent=args.agent,
            main_session_ref=args.main_session_ref,
            carry=mirror_carry,
        )
        update_pickup_state(
            root,
            args.agent,
            args.main_session_ref,
            last_heartbeat_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
            last_claimed_session_key=result.get("session_key") or state.get("last_claimed_session_key"),
            last_reply_message_id=((result.get("reply") or {}).get("message_id")) or state.get("last_reply_message_id"),
            last_error=result.get("error"),
            last_pump_result=result.get("pump_result"),
            status="running",
            pid=os.getpid(),
        )
        output({"ok": True, "result": result, "mirror": mirror_result})
        return

    while not STOP_REQUESTED:
        agent_state = hub.get_agent(args.agent)
        if agent_state.get("status") != "ready":
            update_pickup_state(
                root,
                args.agent,
                args.main_session_ref,
                status="stopped",
                pid=None,
                last_error=None,
            )
            return
        current_state = ensure_codex_host_binding(
            root,
            args.agent,
            args.main_session_ref,
            load_pickup_state(root, args.agent, args.main_session_ref).get("project_root"),
        )
        current_thread_id = str(
            current_state.get("host_thread_id")
            or thread_id_from_main_session_ref(args.main_session_ref)
            or ""
        )
        latest_reply_thread = resolve_active_reply_thread_record() if args.agent == "codex" else None
        if current_state.get("host_kind") == "codex-rollout":
            alive, reason = codex_host_still_active(current_state)
            if not alive:
                if (
                    latest_reply_thread is not None
                    and latest_reply_thread.get("id")
                    and str(latest_reply_thread["id"]) != current_thread_id
                    and agent_state.get("current_main_session_ref") == args.main_session_ref
                ):
                    handoff = handoff_to_thread(
                        root=root,
                        agent=args.agent,
                        backend=args.backend,
                        backend_command=args.backend_command,
                        poll_interval_seconds=args.poll_interval_seconds,
                        thread_id=str(latest_reply_thread["id"]),
                    )
                    update_pickup_state(
                        root,
                        args.agent,
                        args.main_session_ref,
                        status="stopped",
                        pid=None,
                        last_error=None if handoff.get("ok") else handoff.get("error"),
                    )
                    return
                if agent_state.get("current_main_session_ref") == args.main_session_ref:
                    hub.disable_agent(args.agent)
                update_pickup_state(
                    root,
                    args.agent,
                    args.main_session_ref,
                    status="stopped",
                    pid=None,
                    last_error=reason,
                )
                return
        if (
            latest_reply_thread is not None
            and latest_reply_thread.get("id")
            and str(latest_reply_thread["id"]) != current_thread_id
            and agent_state.get("current_main_session_ref") == args.main_session_ref
        ):
            handoff = handoff_to_thread(
                root=root,
                agent=args.agent,
                backend=args.backend,
                backend_command=args.backend_command,
                poll_interval_seconds=args.poll_interval_seconds,
                thread_id=str(latest_reply_thread["id"]),
            )
            update_pickup_state(
                root,
                args.agent,
                args.main_session_ref,
                status="stopped",
                pid=None,
                last_error=None if handoff.get("ok") else handoff.get("error"),
            )
            return
        result = process_once(
            hub=hub,
            root=root,
            agent=args.agent,
            main_session_ref=args.main_session_ref,
            backend=args.backend,
            backend_command=args.backend_command,
        )
        mirror_result, mirror_carry = mirror_main_output_once(
            hub=hub,
            root=root,
            agent=args.agent,
            main_session_ref=args.main_session_ref,
            carry=mirror_carry,
        )
        update_pickup_state(
            root,
            args.agent,
            args.main_session_ref,
            status="running",
            pid=os.getpid(),
            last_heartbeat_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
            last_claimed_session_key=result.get("session_key") or load_pickup_state(root, args.agent, args.main_session_ref).get("last_claimed_session_key"),
            last_reply_message_id=((result.get("reply") or {}).get("message_id")) or load_pickup_state(root, args.agent, args.main_session_ref).get("last_reply_message_id"),
            last_error=mirror_result.get("notify", {}).get("error") or result.get("error"),
            last_pump_result=result.get("pump_result"),
        )
        time.sleep(max(args.poll_interval_seconds, 0.5))

    update_pickup_state(
        root,
        args.agent,
        args.main_session_ref,
        status="stopped",
        pid=None,
        last_error=None,
    )


if __name__ == "__main__":
    main()
