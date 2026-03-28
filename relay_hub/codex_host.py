from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_CODEX_HOME = Path.home() / ".codex"
THREAD_BOUND_MAIN_SESSION_PREFIX = "codex-main-thread-"


def resolve_codex_home(value: str | Path | None = None) -> Path:
    return Path(value).expanduser().resolve() if value else DEFAULT_CODEX_HOME


def state_db_path(codex_home: str | Path | None = None) -> Path:
    return resolve_codex_home(codex_home) / "state_5.sqlite"


def env_thread_id() -> str | None:
    value = os.environ.get("CODEX_THREAD_ID")
    return value.strip() if value else None


def thread_id_from_main_session_ref(main_session_ref: str | None) -> str | None:
    value = (main_session_ref or "").strip()
    if not value.startswith(THREAD_BOUND_MAIN_SESSION_PREFIX):
        return None
    thread_id = value.removeprefix(THREAD_BOUND_MAIN_SESSION_PREFIX).strip()
    return thread_id or None


def _compact_text(text: str, max_chars: int = 220) -> str:
    compact = " ".join((text or "").split())
    if len(compact) <= max_chars:
        return compact
    return compact[: max_chars - 1].rstrip() + "…"


def _normalize_command_text(text: str) -> str:
    lowered = (text or "").casefold()
    return "".join(ch for ch in lowered if ch.isalnum() or ("\u4e00" <= ch <= "\u9fff"))


def _is_relay_enable_command(text: str) -> bool:
    normalized = _normalize_command_text(text)
    return normalized in {"接入relayhub"}


def _flush_round(
    rounds: list[dict[str, str | None]],
    user_text: str | None,
    assistant_text: str | None,
) -> None:
    if not user_text and not assistant_text:
        return
    rounds.append(
        {
            "user": (user_text or "").rstrip(),
            "assistant": (assistant_text or "").rstrip() or None,
        }
    )


def _query_one(db_path: Path, sql: str, params: tuple[Any, ...]) -> dict[str, Any] | None:
    if not db_path.exists():
        return None
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(sql, params).fetchone()
    finally:
        conn.close()
    return dict(row) if row else None


def _query_all(db_path: Path, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    if not db_path.exists():
        return []
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()
    return [dict(row) for row in rows]


def thread_record(
    thread_id: str,
    *,
    codex_home: str | Path | None = None,
    include_archived: bool = True,
) -> dict[str, Any] | None:
    db_path = state_db_path(codex_home)
    record = _query_one(
        db_path,
        "select id, rollout_path, cwd, updated_at, archived from threads where id = ? limit 1",
        (thread_id,),
    )
    if record is None:
        return None
    if not include_archived and record.get("archived"):
        return None
    return record


def resolve_rollout_record(
    *,
    project_root: str | None = None,
    thread_id: str | None = None,
    codex_home: str | Path | None = None,
) -> dict[str, Any] | None:
    db_path = state_db_path(codex_home)
    resolved_project = str(Path(project_root).expanduser().resolve()) if project_root else None
    explicit = thread_id or env_thread_id()

    if explicit:
        record = _query_one(
            db_path,
            "select id, rollout_path, cwd, updated_at, archived from threads where id = ? limit 1",
            (explicit,),
        )
        if record and not record.get("archived"):
            record["resolved_by"] = "thread_id"
            if not resolved_project or record.get("cwd") == resolved_project:
                return record

    if resolved_project:
        record = _query_one(
            db_path,
            "select id, rollout_path, cwd, updated_at, archived from threads "
            "where archived = 0 and cwd = ? order by updated_at desc limit 1",
            (resolved_project,),
        )
        if record:
            record["resolved_by"] = "cwd"
            return record

    if explicit:
        record = _query_one(
            db_path,
            "select id, rollout_path, cwd, updated_at, archived from threads where id = ? limit 1",
            (explicit,),
        )
        if record and not record.get("archived"):
            record["resolved_by"] = "thread_id_fallback"
            return record

    return None


def _last_user_message_timestamp(rollout_path: str | Path) -> str | None:
    path = Path(rollout_path).expanduser().resolve()
    if not path.exists():
        return None
    last_timestamp: str | None = None
    with path.open("r", encoding="utf-8") as handle:
        for raw in handle:
            try:
                item = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if item.get("type") != "event_msg":
                continue
            payload = item.get("payload") or {}
            if payload.get("type") != "user_message":
                continue
            timestamp = item.get("timestamp")
            if isinstance(timestamp, str):
                last_timestamp = timestamp
    return last_timestamp


def resolve_active_user_thread_record(
    *,
    codex_home: str | Path | None = None,
    limit: int = 12,
) -> dict[str, Any] | None:
    db_path = state_db_path(codex_home)
    candidates = _query_all(
        db_path,
        "select id, rollout_path, cwd, updated_at, archived from threads "
        "where archived = 0 order by updated_at desc limit ?",
        (limit,),
    )
    best: dict[str, Any] | None = None
    best_key: tuple[datetime, int] | None = None
    for record in candidates:
        last_user_timestamp = _last_user_message_timestamp(record["rollout_path"])
        if last_user_timestamp is None:
            continue
        try:
            parsed = datetime.fromisoformat(last_user_timestamp.replace("Z", "+00:00"))
        except ValueError:
            continue
        record["last_user_message_at"] = last_user_timestamp
        key = (parsed, int(record.get("updated_at") or 0))
        if best_key is None or key > best_key:
            best = record
            best_key = key
    if best is not None:
        best["resolved_by"] = "latest_user_message"
        return best
    return None


def conversation_rounds(
    *,
    project_root: str | None = None,
    thread_id: str | None = None,
    codex_home: str | Path | None = None,
    trim_trailing_relay_enable: bool = False,
) -> list[dict[str, str | None]]:
    record = resolve_rollout_record(
        project_root=project_root,
        thread_id=thread_id,
        codex_home=codex_home,
    )
    if record is None:
        return []
    path = Path(record["rollout_path"]).expanduser().resolve()
    if not path.exists():
        return []
    rounds: list[dict[str, str | None]] = []
    pending_user: str | None = None
    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        for raw in handle:
            try:
                item = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if item.get("type") != "event_msg":
                continue
            payload = item.get("payload") or {}
            payload_type = payload.get("type")
            if payload_type == "user_message":
                body = str(payload.get("message") or "").strip()
                if not body:
                    continue
                if pending_user is not None:
                    _flush_round(rounds, pending_user, None)
                pending_user = body
                continue
            if payload_type == "task_complete":
                body = str(payload.get("last_agent_message") or "").strip()
                if not body:
                    continue
                if pending_user is not None:
                    _flush_round(rounds, pending_user, body)
                    pending_user = None
    if pending_user is not None:
        _flush_round(rounds, pending_user, None)
    if trim_trailing_relay_enable:
        while rounds:
            tail = rounds[-1]
            if not _is_relay_enable_command(tail.get("user") or ""):
                break
            rounds.pop()
    return rounds


def fallback_rounds_summary(
    rounds: list[dict[str, str | None]],
    *,
    max_rounds: int = 6,
    max_chars_per_role: int = 160,
) -> str:
    if not rounds:
        return "（无额外对话）"
    chosen = rounds[-max(max_rounds, 1) :]
    parts: list[str] = []
    for idx, round_item in enumerate(chosen, start=1):
        user_text = _compact_text(round_item.get("user") or "", max_chars=max_chars_per_role)
        assistant_text = _compact_text(round_item.get("assistant") or "", max_chars=max_chars_per_role)
        if assistant_text:
            parts.append(f"第{idx}轮：用户提到「{user_text}」；助手回应「{assistant_text}」")
        else:
            parts.append(f"第{idx}轮：用户提到「{user_text}」；助手尚未完成回复")
    return "\n".join(parts)


def rounds_before_last_relay_enable(
    rounds: list[dict[str, str | None]],
) -> list[dict[str, str | None]]:
    for index in range(len(rounds) - 1, -1, -1):
        if _is_relay_enable_command(rounds[index].get("user") or ""):
            return rounds[:index]
    return rounds


def format_rounds_snapshot(
    rounds: list[dict[str, str | None]],
    *,
    heading: str,
    preserve_rounds: int = 3,
    raw_round_limit: int = 5,
    summary_heading: str = "其余对话摘要：",
    summary_text: str | None = None,
) -> str | None:
    if not rounds:
        return None
    lines = [heading]
    if len(rounds) <= raw_round_limit:
        source_rounds = rounds
        title = "原文对话："
        lines.append(title)
        for index, round_item in enumerate(source_rounds, start=1):
            lines.append(f"第{index}轮")
            lines.append("用户：")
            lines.extend((round_item.get("user") or "").splitlines() or [""])
            assistant_text = round_item.get("assistant")
            if assistant_text:
                lines.append("助手：")
                lines.extend(assistant_text.splitlines())
        return "\n".join(lines).rstrip()
    preserved = rounds[: max(preserve_rounds, 0)]
    remaining = rounds[max(preserve_rounds, 0) :]
    lines.append(summary_heading)
    lines.extend((summary_text or fallback_rounds_summary(remaining)).splitlines())
    if preserved:
        lines.append("")
        lines.append(f"前三轮原文：")
        for index, round_item in enumerate(preserved, start=1):
            lines.append(f"第{index}轮")
            lines.append("用户：")
            lines.extend((round_item.get("user") or "").splitlines() or [""])
            assistant_text = round_item.get("assistant")
            if assistant_text:
                lines.append("助手：")
                lines.extend(assistant_text.splitlines())
    return "\n".join(lines).rstrip()


def recent_conversation_snapshot(
    *,
    project_root: str | None = None,
    thread_id: str | None = None,
    codex_home: str | Path | None = None,
    trim_trailing_relay_enable: bool = False,
    heading: str = "最近主线对话：",
    preserve_rounds: int = 3,
    raw_round_limit: int = 5,
    summary_text: str | None = None,
) -> str | None:
    rounds = conversation_rounds(
        project_root=project_root,
        thread_id=thread_id,
        codex_home=codex_home,
        trim_trailing_relay_enable=trim_trailing_relay_enable,
    )
    return format_rounds_snapshot(
        rounds,
        heading=heading,
        preserve_rounds=preserve_rounds,
        raw_round_limit=raw_round_limit,
        summary_text=summary_text,
    )


def read_new_task_completions(
    rollout_path: str | Path,
    offset: int,
    carry: bytes,
) -> tuple[list[dict[str, Any]], int, bytes]:
    path = Path(rollout_path).expanduser().resolve()
    if not path.exists():
        return [], offset, carry
    size = path.stat().st_size
    if offset > size:
        offset = 0
        carry = b""
    with path.open("rb") as handle:
        handle.seek(offset)
        chunk = handle.read()
        next_offset = handle.tell()
    if not chunk and not carry:
        return [], next_offset, carry
    payload = carry + chunk
    lines = payload.split(b"\n")
    if payload and not payload.endswith(b"\n"):
        carry = lines.pop()
    else:
        carry = b""
    events: list[dict[str, Any]] = []
    for raw in lines:
        if not raw:
            continue
        try:
            item = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if item.get("type") != "event_msg":
            continue
        event_payload = item.get("payload") or {}
        if event_payload.get("type") != "task_complete":
            continue
        message = (event_payload.get("last_agent_message") or "").strip()
        turn_id = event_payload.get("turn_id")
        if not message or not turn_id:
            continue
        events.append(
            {
                "turn_id": turn_id,
                "message": message,
                "timestamp": item.get("timestamp"),
            }
        )
    return events, next_offset, carry
