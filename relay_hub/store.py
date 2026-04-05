from __future__ import annotations

import base64
import json
import os
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

try:
    import fcntl
except ImportError:
    fcntl = None

try:
    import msvcrt
except ImportError:
    msvcrt = None

from .devlog import ensure_development_log, log_entries_since, prepend_log_entry
from .message_text import delivery_footer


DEFAULT_CONFIG = {
    "version": 1,
    "web_base_url": "http://127.0.0.1:4317",
    "default_delivery": {
        "mode": "all",
        "channels": [],
    },
    "queue_ack_timeout_seconds": 15,
}
def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def atomic_write_text(path: Path, content: str) -> None:
    ensure_dir(path.parent)
    tmp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp_path.write_text(content, encoding="utf-8")
    os.replace(tmp_path, path)


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def load_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return json.loads(json.dumps(default))
    return json.loads(path.read_text(encoding="utf-8"))


def encode_session_target(target: str) -> str:
    return quote(target, safe="@._-")


def make_session_key(channel: str, target: str, branch_ref: str | None = None) -> str:
    base = f"{channel}__{encode_session_target(target)}"
    if not branch_ref:
        return base
    return f"{base}__branch__{encode_session_target(branch_ref)}"


def session_public_token(session_key: str) -> str:
    return base64.urlsafe_b64encode(session_key.encode("utf-8")).decode("ascii").rstrip("=")


def session_key_from_public_token(token: str) -> str:
    padding = "=" * (-len(token) % 4)
    return base64.urlsafe_b64decode((token + padding).encode("ascii")).decode("utf-8")


def yaml_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(str(value), ensure_ascii=False)


def format_front_matter(meta: dict[str, Any], body: str) -> str:
    lines = ["---"]
    for key, value in meta.items():
        lines.append(f"{key}: {yaml_scalar(value)}")
    lines.append("---")
    lines.append(body.rstrip())
    lines.append("")
    return "\n".join(lines)


def parse_front_matter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---\n"):
        return {}, text
    lines = text.splitlines()
    meta: dict[str, Any] = {}
    idx = 1
    while idx < len(lines):
        line = lines[idx]
        if line == "---":
            body = "\n".join(lines[idx + 1 :]).rstrip("\n")
            return meta, body
        key, _, raw_value = line.partition(":")
        value = raw_value.strip()
        if value.startswith('"') and value.endswith('"'):
            parsed: Any = json.loads(value)
        elif value == "true":
            parsed = True
        elif value == "false":
            parsed = False
        elif value == "null":
            parsed = None
        else:
            try:
                parsed = int(value)
            except ValueError:
                parsed = value
        meta[key.strip()] = parsed
        idx += 1
    return {}, text


def message_id_int(message_id: str | None) -> int:
    try:
        return int(message_id or 0)
    except (TypeError, ValueError):
        return 0


def is_relay_mode(state: dict[str, Any]) -> bool:
    return state.get("mode") == "relay"


def main_session_ref_matches(bound_ref: str | None, expected_ref: str | None) -> bool:
    if expected_ref is None:
        return True
    return bound_ref == expected_ref


def parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


def normalize_notification_channel_overrides(raw: Any) -> dict[str, bool]:
    if not isinstance(raw, dict):
        return {}
    normalized: dict[str, bool] = {}
    for key, value in raw.items():
        channel = str(key).strip()
        if not channel:
            continue
        normalized[channel] = bool(value)
    return normalized


def acquire_file_lock(handle: Any) -> None:
    if fcntl is not None:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        return
    if msvcrt is None:
        raise RuntimeError("no supported file locking backend available on this platform")
    handle.seek(0)
    if handle.tell() == 0 and handle.read(1) == "":
        handle.write("\0")
        handle.flush()
    handle.seek(0)
    while True:
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            return
        except OSError:
            time.sleep(0.05)


def release_file_lock(handle: Any) -> None:
    if fcntl is not None:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        return
    if msvcrt is None:
        return
    handle.seek(0)
    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


class RelayHub:
    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser().resolve()

    @property
    def config_path(self) -> Path:
        return self.root / "config.json"

    @property
    def routes_path(self) -> Path:
        return self.root / "routes.json"

    @property
    def agents_dir(self) -> Path:
        return self.root / "agents"

    @property
    def sessions_dir(self) -> Path:
        return self.root / "sessions"

    @property
    def logs_dir(self) -> Path:
        return self.root / "logs"

    def init_layout(
        self,
        web_base_url: str = DEFAULT_CONFIG["web_base_url"],
        queue_ack_timeout_seconds: int = DEFAULT_CONFIG["queue_ack_timeout_seconds"],
        default_channels: list[str] | None = None,
    ) -> dict[str, Any]:
        ensure_dir(self.root)
        ensure_dir(self.agents_dir)
        ensure_dir(self.sessions_dir)
        ensure_dir(self.logs_dir)
        channels = default_channels or list(DEFAULT_CONFIG["default_delivery"]["channels"])
        config = {
            "version": 1,
            "relay_root": str(self.root),
            "web_base_url": web_base_url.rstrip("/"),
            "default_delivery": {
                "mode": "all",
                "channels": channels,
            },
            "queue_ack_timeout_seconds": queue_ack_timeout_seconds,
        }
        if not self.config_path.exists():
            atomic_write_json(self.config_path, config)
        if not self.routes_path.exists():
            atomic_write_json(
                self.routes_path,
                {"version": 1, "updated_at": now_iso(), "routes": {}},
            )
        return self.config()

    def config(self) -> dict[str, Any]:
        default = {
            "version": 1,
            "relay_root": str(self.root),
            **DEFAULT_CONFIG,
        }
        return load_json(self.config_path, default)

    def routes(self) -> dict[str, Any]:
        return load_json(self.routes_path, {"version": 1, "updated_at": now_iso(), "routes": {}})

    def save_routes(self, routes: dict[str, Any]) -> None:
        routes["updated_at"] = now_iso()
        atomic_write_json(self.routes_path, routes)

    def agent_path(self, agent: str) -> Path:
        return self.agents_dir / f"{agent}.json"

    def get_agent(self, agent: str) -> dict[str, Any]:
        return load_json(
            self.agent_path(agent),
            {
                "agent": agent,
                "status": "offline",
                "adapter_version": "1",
                "last_seen_at": None,
                "capabilities": {
                    "read_messages": True,
                    "write_progress": True,
                    "write_final": True,
                    "write_error": True,
                },
                "relay_enabled_at": None,
                "current_main_session_ref": None,
                "current_project_root": None,
                "current_development_log_path": None,
                "last_snapshot_at": None,
                "notification_channel_overrides": {},
            },
        )

    def set_agent(self, agent: str, status: str = "ready") -> dict[str, Any]:
        payload = self.get_agent(agent)
        payload["status"] = status
        payload["last_seen_at"] = now_iso()
        payload["notification_channel_overrides"] = normalize_notification_channel_overrides(
            payload.get("notification_channel_overrides")
        )
        atomic_write_json(self.agent_path(agent), payload)
        return payload

    def set_active_main_session(
        self,
        agent: str,
        main_session_ref: str | None,
        *,
        project_root: str | Path | None = None,
        development_log_path: str | Path | None = None,
    ) -> dict[str, Any]:
        payload = self.get_agent(agent)
        payload["current_main_session_ref"] = main_session_ref
        if project_root is not None:
            payload["current_project_root"] = str(Path(project_root).expanduser().resolve())
        if development_log_path is not None:
            payload["current_development_log_path"] = str(Path(development_log_path).expanduser().resolve())
        payload["last_seen_at"] = now_iso()
        payload["notification_channel_overrides"] = normalize_notification_channel_overrides(
            payload.get("notification_channel_overrides")
        )
        atomic_write_json(self.agent_path(agent), payload)
        return payload

    def disable_agent(self, agent: str) -> dict[str, Any]:
        payload = self.get_agent(agent)
        payload["status"] = "offline"
        payload["last_seen_at"] = now_iso()
        payload["current_main_session_ref"] = None
        payload["current_project_root"] = None
        payload["current_development_log_path"] = None
        payload["notification_channel_overrides"] = normalize_notification_channel_overrides(
            payload.get("notification_channel_overrides")
        )
        atomic_write_json(self.agent_path(agent), payload)
        return payload

    def notification_channel_status(
        self,
        agent: str,
        configured_channels: list[str],
    ) -> dict[str, Any]:
        payload = self.get_agent(agent)
        overrides = normalize_notification_channel_overrides(payload.get("notification_channel_overrides"))
        channels: list[dict[str, Any]] = []
        enabled_channels: list[str] = []
        disabled_channels: list[str] = []
        for channel in configured_channels:
            enabled = overrides.get(channel, True)
            channels.append(
                {
                    "channel": channel,
                    "enabled": enabled,
                    "source": "override" if channel in overrides else "default",
                }
            )
            if enabled:
                enabled_channels.append(channel)
            else:
                disabled_channels.append(channel)
        return {
            "channels": channels,
            "enabled_channels": enabled_channels,
            "disabled_channels": disabled_channels,
            "all_enabled": bool(channels) and not disabled_channels,
            "all_disabled": bool(channels) and not enabled_channels,
            "overrides": overrides,
        }

    def effective_notification_channels(
        self,
        agent: str,
        configured_channels: list[str],
    ) -> list[str]:
        status = self.notification_channel_status(agent, configured_channels)
        return list(status["enabled_channels"])

    def set_notification_channel_enabled(
        self,
        agent: str,
        channel: str,
        enabled: bool,
    ) -> dict[str, Any]:
        payload = self.get_agent(agent)
        overrides = normalize_notification_channel_overrides(payload.get("notification_channel_overrides"))
        overrides[channel] = enabled
        payload["notification_channel_overrides"] = overrides
        payload["last_seen_at"] = now_iso()
        atomic_write_json(self.agent_path(agent), payload)
        return {
            "agent": payload,
            "channel": channel,
            "enabled": enabled,
            "status": self.notification_channel_status(agent, [channel]),
        }

    def _resolve_development_log(
        self,
        *,
        project_root: str | Path | None = None,
        development_log_path: str | Path | None = None,
    ) -> tuple[Path, Path, bool]:
        explicit_path = Path(development_log_path).expanduser().resolve() if development_log_path else None
        if project_root is not None:
            project_path = Path(project_root).expanduser().resolve()
        elif explicit_path is not None:
            project_path = explicit_path.parent
        else:
            raise ValueError("project_root is required unless development_log_path is provided")
        if explicit_path is not None:
            created = not explicit_path.exists()
            ensure_development_log(explicit_path)
            return project_path, explicit_path, created
        project_log_path = project_path / "DEVELOPMENT_LOG.md"
        created = not project_log_path.exists()
        ensure_development_log(project_log_path)
        return project_path, project_log_path, created

    def _write_main_session_snapshot(
        self,
        log_path: Path,
        *,
        author: str,
        goal: str,
        key_operations: list[str],
        verification_results: list[str],
        next_steps: list[str],
        snapshot_body: str,
    ) -> None:
        prepend_log_entry(
            log_path,
            author=author,
            goal=goal,
            key_operations=key_operations,
            changed_files=["无代码文件变更，记录主线状态快照。"],
            verification_results=verification_results,
            next_steps=next_steps,
            snapshot_body=snapshot_body,
        )

    def enable_agent(
        self,
        *,
        agent: str,
        project_root: str | Path,
        snapshot_body: str,
        development_log_path: str | Path | None = None,
        main_session_ref: str | None = None,
        author: str | None = None,
    ) -> dict[str, Any]:
        project_path, log_path, created = self._resolve_development_log(
            project_root=project_root,
            development_log_path=development_log_path,
        )
        self._write_main_session_snapshot(
            log_path,
            author=author or agent,
            goal="Relay Hub 主线快照",
            key_operations=[
                "开启 Relay Hub 能力并记录当前主对话窗口摘要。",
                "后续 branch 处理与主线合流优先参考开发日志。",
            ],
            verification_results=["开发日志已更新，可供后续 branch 上下文和合流参考。"],
            next_steps=["继续在主线工作时，按项目规则持续更新开发日志。"],
            snapshot_body=snapshot_body,
        )
        payload = self.get_agent(agent)
        enabled_at = now_iso()
        payload["status"] = "ready"
        payload["last_seen_at"] = enabled_at
        payload["relay_enabled_at"] = enabled_at
        payload["current_main_session_ref"] = main_session_ref
        payload["current_project_root"] = str(project_path)
        payload["current_development_log_path"] = str(log_path)
        payload["last_snapshot_at"] = enabled_at
        atomic_write_json(self.agent_path(agent), payload)
        return {
            "agent": payload,
            "project_root": str(project_path),
            "development_log_path": str(log_path),
            "development_log_created": created,
            "snapshot_written": True,
        }

    def switch_active_main_session(
        self,
        *,
        agent: str,
        project_root: str | Path,
        main_session_ref: str,
        development_log_path: str | Path | None = None,
        snapshot_body: str | None = None,
        author: str | None = None,
    ) -> dict[str, Any]:
        project_path, log_path, created = self._resolve_development_log(
            project_root=project_root,
            development_log_path=development_log_path,
        )
        snapshot_written = False
        if snapshot_body is not None:
            self._write_main_session_snapshot(
                log_path,
                author=author or agent,
                goal="Relay Hub 主线切换快照",
                key_operations=[
                    "切换到当前活跃主会话，并记录这条主会话的当前窗口摘要。",
                    "如果这条主会话此前没有 Relay Hub 历史，就从这里开始作为主线快照。",
                ],
                verification_results=["当前主会话的开发日志上下文已就位，可供 branch 和 merge-back 继续使用。"],
                next_steps=["继续在当前主会话工作时，按项目规则持续更新开发日志。"],
                snapshot_body=snapshot_body,
            )
            snapshot_written = True
        payload = self.get_agent(agent)
        switched_at = now_iso()
        payload["status"] = "ready"
        payload["last_seen_at"] = switched_at
        payload["relay_enabled_at"] = payload.get("relay_enabled_at") or switched_at
        payload["current_main_session_ref"] = main_session_ref
        payload["current_project_root"] = str(project_path)
        payload["current_development_log_path"] = str(log_path)
        if snapshot_written:
            payload["last_snapshot_at"] = switched_at
        atomic_write_json(self.agent_path(agent), payload)
        return {
            "agent": payload,
            "project_root": str(project_path),
            "development_log_path": str(log_path),
            "development_log_created": created,
            "snapshot_written": snapshot_written,
        }

    def attach_project(
        self,
        session_key: str,
        *,
        project_root: str | Path | None = None,
        development_log_path: str | Path | None = None,
        snapshot_body: str | None = None,
        author: str | None = None,
    ) -> dict[str, Any]:
        meta = self.get_meta(session_key)
        if not meta:
            raise FileNotFoundError(f"session {session_key} does not exist")
        project_path, log_path, created = self._resolve_development_log(
            project_root=project_root,
            development_log_path=development_log_path,
        )
        meta["project_root"] = str(project_path)
        meta["development_log_path"] = str(log_path)
        meta["development_log_attached_at"] = now_iso()
        atomic_write_json(self.meta_path(session_key), meta)
        snapshot_written = False
        if snapshot_body:
            prepend_log_entry(
                log_path,
                author=author or meta.get("agent") or "relay-hub",
                goal=f"Relay Hub branch {session_key} 主线快照",
                key_operations=[
                    "在 branch 正式处理前记录当前主线摘要。",
                    "供 branch 处理和后续 merge-back 使用。",
                ],
                changed_files=["无代码文件变更，记录 branch 对应的主线快照。"],
                verification_results=["开发日志已附加 branch 主线快照。"],
                next_steps=["branch 期间的重要主线进展继续按项目规则写入开发日志。"],
                snapshot_body=snapshot_body,
            )
            snapshot_written = True
            state = self.get_state(session_key)
            state["development_log_snapshot_at"] = now_iso()
            self.save_state(session_key, state)
        return {
            "session_key": session_key,
            "project_root": str(project_path),
            "development_log_path": str(log_path),
            "development_log_created": created,
            "snapshot_written": snapshot_written,
        }

    def session_dir(self, session_key: str) -> Path:
        return self.sessions_dir / session_key

    def meta_path(self, session_key: str) -> Path:
        return self.session_dir(session_key) / "meta.json"

    def state_path(self, session_key: str) -> Path:
        return self.session_dir(session_key) / "state.json"

    def messages_dir(self, session_key: str) -> Path:
        return self.session_dir(session_key) / "messages"

    def attachments_dir(self, session_key: str) -> Path:
        return self.session_dir(session_key) / "attachments"

    def main_context_path(self, session_key: str) -> Path:
        return self.session_dir(session_key) / "main_context.md"

    def session_lock_path(self, session_key: str) -> Path:
        return self.session_dir(session_key) / ".session.lock"

    @contextmanager
    def _lock_session(self, session_key: str):
        ensure_dir(self.session_dir(session_key))
        lock_path = self.session_lock_path(session_key)
        handle = lock_path.open("a+", encoding="utf-8")
        acquire_file_lock(handle)
        try:
            yield handle
        finally:
            release_file_lock(handle)
            handle.close()

    def get_meta(self, session_key: str) -> dict[str, Any]:
        return load_json(self.meta_path(session_key), {})

    def get_state(self, session_key: str) -> dict[str, Any]:
        return load_json(self.state_path(session_key), {})

    def save_state(self, session_key: str, state: dict[str, Any]) -> None:
        state["updated_at"] = now_iso()
        atomic_write_json(self.state_path(session_key), state)

    def get_main_context(self, session_key: str) -> dict[str, Any]:
        path = self.main_context_path(session_key)
        if not path.exists():
            return {}
        meta, body = parse_front_matter(path.read_text(encoding="utf-8"))
        return {"path": str(path), "meta": meta, "body": body}

    def set_main_session_ref(self, session_key: str, main_session_ref: str, source: str = "agent-session") -> dict[str, Any]:
        meta = self.get_meta(session_key)
        if not meta:
            raise FileNotFoundError(f"session {session_key} does not exist")
        existing = meta.get("main_session_ref")
        if existing and existing != main_session_ref:
            raise ValueError(
                f"session {session_key} is already bound to main session {existing}; "
                f"refusing to switch silently to {main_session_ref}"
            )
        if not existing:
            bound_at = now_iso()
            meta["main_session_ref"] = main_session_ref
            meta["main_session_ref_source"] = source
            meta["main_session_ref_bound_at"] = bound_at
            atomic_write_json(self.meta_path(session_key), meta)
            state = self.get_state(session_key)
            state["main_session_ref_updated_at"] = bound_at
            self.save_state(session_key, state)
        return {
            "session_key": session_key,
            "main_session_ref": meta.get("main_session_ref"),
            "main_session_ref_source": meta.get("main_session_ref_source"),
            "main_session_ref_bound_at": meta.get("main_session_ref_bound_at"),
        }

    def set_main_context(self, session_key: str, body: str, source: str = "main-chat") -> dict[str, Any]:
        meta = self.get_meta(session_key)
        if not meta:
            raise FileNotFoundError(f"session {session_key} does not exist")
        payload = {
            "kind": "main_context_seed",
            "source": source,
            "captured_at": now_iso(),
            "session_key": session_key,
            "agent": meta.get("agent"),
        }
        path = self.main_context_path(session_key)
        atomic_write_text(path, format_front_matter(payload, body))
        state = self.get_state(session_key)
        state["main_context_updated_at"] = payload["captured_at"]
        self.save_state(session_key, state)
        return {"path": str(path), "meta": payload, "body": body}

    def _current_max_message_id(self, session_key: str) -> str | None:
        messages = self.list_messages(session_key)
        if not messages:
            return None
        return str(messages[-1]["meta"].get("id") or "")

    def _current_cycle_floor_id(self, state: dict[str, Any]) -> int:
        return message_id_int(state.get("cycle_floor_message_id"))

    def _development_log_bundle(
        self,
        meta: dict[str, Any],
        state: dict[str, Any],
        *,
        purpose: str,
        limit: int = 5,
    ) -> dict[str, Any]:
        log_path = meta.get("development_log_path")
        if not log_path:
            return {
                "attached": False,
                "path": None,
                "since": None,
                "entries": [],
            }
        if purpose == "context":
            candidates = [
                parse_iso_datetime(state.get("main_context_updated_at")),
                parse_iso_datetime(state.get("entry_opened_at")),
                parse_iso_datetime(meta.get("created_at")),
            ]
        else:
            candidates = [
                parse_iso_datetime(state.get("last_merged_back_at")),
                parse_iso_datetime(state.get("branch_started_at")),
                parse_iso_datetime(state.get("entry_opened_at")),
                parse_iso_datetime(meta.get("created_at")),
            ]
        valid_candidates = [candidate for candidate in candidates if candidate is not None]
        since_iso = max(valid_candidates).isoformat() if valid_candidates else None
        try:
            entries = log_entries_since(log_path, since_iso, limit=limit)
            readable = True
            error = None
        except OSError as exc:
            entries = []
            readable = False
            error = f"{type(exc).__name__}: {exc}"
        return {
            "attached": True,
            "path": log_path,
            "since": since_iso,
            "entries": entries,
            "readable": readable,
            "error": error,
        }

    def _format_context_packet_text(
        self,
        session_key: str,
        main_context: dict[str, Any],
        development_log: dict[str, Any],
        branch_messages: list[dict[str, Any]],
    ) -> str:
        lines = [f"[Relay branch context: {session_key}]"]
        lines.append("")
        if main_context.get("body"):
            lines.append("主对话快照：")
            lines.append(main_context["body"].rstrip())
        else:
            lines.append("主对话快照：当前缺失。")
        if development_log.get("attached"):
            lines.append("")
            lines.append(f"开发日志参考：{development_log.get('path')}")
            entries = development_log.get("entries") or []
            if entries:
                for entry in entries:
                    lines.append("")
                    lines.append(entry.get("raw", "").rstrip())
            else:
                lines.append("自参考时间点以来没有新的开发日志条目。")
        else:
            lines.append("")
            lines.append("开发日志参考：当前未附加开发日志。")
        lines.append("")
        lines.append("branch 消息：")
        if not branch_messages:
            lines.append("当前还没有 branch 消息。")
        else:
            for message in branch_messages:
                lines.append("")
                lines.append(
                    f"{message.get('role')}/{message.get('kind')} id={message.get('id')} "
                    f"source={message.get('source')} created_at={message.get('created_at')}"
                )
                lines.append((message.get("body") or "").rstrip())
        return "\n".join(lines).rstrip()

    def web_url(self, session_key: str) -> str:
        return f"{self.config()['web_base_url']}/s/{session_public_token(session_key)}"

    def open_session(
        self,
        agent: str,
        channel: str,
        target: str,
        delivery_mode: str | None = None,
        delivery_channels: list[str] | None = None,
        main_context_body: str | None = None,
        main_context_source: str = "main-chat",
        main_session_ref: str | None = None,
        main_session_ref_source: str = "agent-session",
        session_key_override: str | None = None,
        branch_ref: str | None = None,
    ) -> dict[str, Any]:
        config = self.config()
        session_key = session_key_override or make_session_key(channel, target, branch_ref=branch_ref)
        session_dir = self.session_dir(session_key)
        created = not session_dir.exists()
        previous_state = self.get_state(session_key)
        ensure_dir(self.messages_dir(session_key))
        ensure_dir(self.attachments_dir(session_key))
        existing_meta = self.get_meta(session_key)
        if existing_meta.get("agent") and existing_meta.get("agent") != agent:
            raise ValueError(
                f"session {session_key} already belongs to {existing_meta.get('agent')}; "
                f"reuse it with the same agent or create a new branch"
            )
        default_delivery = {
            "mode": delivery_mode or config["default_delivery"]["mode"],
            "channels": delivery_channels or config["default_delivery"]["channels"],
        }
        meta = {
            "session_key": session_key,
            "channel": channel,
            "target": target,
            "agent": agent,
            "session_role": "branch",
            "branch_parent": "main-chat",
            "created_at": existing_meta.get("created_at", now_iso()),
            "web_url": self.web_url(session_key),
            "default_delivery": default_delivery,
        }
        if existing_meta.get("main_session_ref"):
            meta["main_session_ref"] = existing_meta.get("main_session_ref")
            meta["main_session_ref_source"] = existing_meta.get("main_session_ref_source")
            meta["main_session_ref_bound_at"] = existing_meta.get("main_session_ref_bound_at")
        if existing_meta.get("project_root"):
            meta["project_root"] = existing_meta.get("project_root")
        if existing_meta.get("development_log_path"):
            meta["development_log_path"] = existing_meta.get("development_log_path")
            meta["development_log_attached_at"] = existing_meta.get("development_log_attached_at")
        existing_relay = is_relay_mode(previous_state)
        current_max_message_id = self._current_max_message_id(session_key)
        if existing_relay:
            status = previous_state.get("status") or "entry_open"
            entry_opened_at = previous_state.get("entry_opened_at") or now_iso()
            branch_started_at = previous_state.get("branch_started_at")
            if "cycle_floor_message_id" in previous_state:
                cycle_floor_message_id = previous_state.get("cycle_floor_message_id")
            else:
                cycle_floor_message_id = current_max_message_id
        else:
            status = "entry_open"
            entry_opened_at = now_iso()
            branch_started_at = None
            cycle_floor_message_id = current_max_message_id
        state = {
            "session_key": session_key,
            "mode": "relay",
            "agent": agent,
            "status": status,
            "entry_opened_at": entry_opened_at,
            "branch_started_at": branch_started_at,
            "cycle_floor_message_id": cycle_floor_message_id,
            "dispatch_requested_at": previous_state.get("dispatch_requested_at") if existing_relay else None,
            "dispatch_ack_timeout_seconds": config["queue_ack_timeout_seconds"],
            "last_user_message_id": previous_state.get("last_user_message_id"),
            "last_committed_user_message_id": previous_state.get("last_committed_user_message_id"),
            "last_branch_user_message_id": previous_state.get("last_branch_user_message_id") if existing_relay else None,
            "last_queued_user_message_id": previous_state.get("last_queued_user_message_id"),
            "last_agent_message_id": previous_state.get("last_agent_message_id"),
            "last_delivered_message_id": previous_state.get("last_delivered_message_id"),
            "last_merged_back_message_id": previous_state.get("last_merged_back_message_id"),
            "last_merged_back_at": previous_state.get("last_merged_back_at"),
            "agent_claimed_at": previous_state.get("agent_claimed_at") if existing_relay else None,
            "main_context_updated_at": previous_state.get("main_context_updated_at"),
            "main_session_ref_updated_at": previous_state.get("main_session_ref_updated_at"),
            "development_log_snapshot_at": previous_state.get("development_log_snapshot_at"),
            "updated_at": now_iso(),
        }
        atomic_write_json(self.meta_path(session_key), meta)
        self.save_state(session_key, state)
        if main_session_ref is not None:
            self.set_main_session_ref(
                session_key,
                main_session_ref,
                source=main_session_ref_source,
            )
            meta = self.get_meta(session_key)
        main_context = self.get_main_context(session_key)
        if main_context_body is not None:
            main_context = self.set_main_context(session_key, main_context_body, source=main_context_source)
        state = self.get_state(session_key)
        routes = self.routes()
        routes["routes"][session_key] = {
            "mode": "relay",
            "agent": agent,
            "status": state["status"],
            "web_url": meta["web_url"],
            "default_delivery": default_delivery,
            "last_user_commit_id": state["last_committed_user_message_id"],
            "last_agent_message_id": state["last_agent_message_id"],
            "updated_at": now_iso(),
        }
        self.save_routes(routes)
        return {
            "created": created,
            "session_key": session_key,
            "meta": meta,
            "state": state,
            "main_context": main_context,
            "route": routes["routes"][session_key],
        }

    def list_sessions(self) -> list[dict[str, Any]]:
        sessions = []
        routes = self.routes().get("routes", {})
        for session_dir in sorted(self.sessions_dir.iterdir()) if self.sessions_dir.exists() else []:
            if not session_dir.is_dir():
                continue
            session_key = session_dir.name
            meta = self.get_meta(session_key)
            state = self.get_state(session_key)
            messages = self.list_messages(session_key)
            sessions.append(
                {
                    "session_key": session_key,
                    "agent": meta.get("agent"),
                    "channel": meta.get("channel"),
                    "target": meta.get("target"),
                    "main_session_ref": meta.get("main_session_ref"),
                    "project_root": meta.get("project_root"),
                    "development_log_path": meta.get("development_log_path"),
                    "status": state.get("status"),
                    "mode": state.get("mode"),
                    "entry_opened_at": state.get("entry_opened_at"),
                    "branch_started_at": state.get("branch_started_at"),
                    "last_merged_back_at": state.get("last_merged_back_at"),
                    "web_url": meta.get("web_url"),
                    "message_count": len(messages),
                    "route": routes.get(session_key),
                }
            )
        return sessions

    def get_session(self, session_key: str) -> dict[str, Any]:
        routes = self.routes().get("routes", {})
        meta = self.get_meta(session_key)
        state = self.get_state(session_key)
        return {
            "meta": meta,
            "state": state,
            "main_context": self.get_main_context(session_key),
            "development_log": self._development_log_bundle(meta, state, purpose="context"),
            "route": routes.get(session_key),
            "messages": self.list_messages(session_key),
        }

    def build_context(
        self,
        session_key: str,
        limit: int = 50,
        expected_main_session_ref: str | None = None,
    ) -> dict[str, Any]:
        bundle = self.get_session(session_key)
        bound_main_session_ref = bundle["meta"].get("main_session_ref")
        if expected_main_session_ref and not main_session_ref_matches(bound_main_session_ref, expected_main_session_ref):
            raise ValueError(
                f"session {session_key} belongs to main session {bound_main_session_ref or 'UNBOUND'}, "
                f"not {expected_main_session_ref}"
            )
        main_context = bundle["main_context"]
        state = bundle["state"]
        floor_int = self._current_cycle_floor_id(state)
        messages = [
            message
            for message in bundle["messages"]
            if message_id_int(str(message["meta"].get("id") or "")) > floor_int
        ]
        if limit > 0:
            messages = messages[-limit:]
        branch_messages = []
        for message in messages:
            meta = message["meta"]
            branch_messages.append(
                {
                    "id": meta.get("id"),
                    "role": meta.get("role"),
                    "kind": meta.get("kind", meta.get("role")),
                    "source": meta.get("source"),
                    "agent": meta.get("agent"),
                    "created_at": meta.get("created_at"),
                    "body": message["body"],
                }
            )
        development_log = self._development_log_bundle(
            bundle["meta"],
            state,
            purpose="context",
        )
        return {
            "session_key": session_key,
            "meta": bundle["meta"],
            "state": state,
            "main_context": main_context,
            "main_context_present": bool(main_context.get("body")),
            "main_session_ref": bound_main_session_ref,
            "development_log": development_log,
            "route": bundle["route"],
            "messages": branch_messages,
            "branch_messages": branch_messages,
            "context_packet_text": self._format_context_packet_text(
                session_key,
                main_context,
                development_log,
                branch_messages,
            ),
        }

    def build_merge_back(
        self,
        session_key: str,
        since_message_id: str | None = None,
        limit: int = 100,
        expected_main_session_ref: str | None = None,
        require_main_session_ref: bool = False,
    ) -> dict[str, Any]:
        bundle = self.get_session(session_key)
        bound_main_session_ref = bundle["meta"].get("main_session_ref")
        if require_main_session_ref and not bound_main_session_ref:
            raise ValueError(
                f"session {session_key} is not bound to any main session yet; "
                "bind it before merging branch increments back"
            )
        if expected_main_session_ref and not main_session_ref_matches(bound_main_session_ref, expected_main_session_ref):
            raise ValueError(
                f"session {session_key} belongs to main session {bound_main_session_ref or 'UNBOUND'}, "
                f"not {expected_main_session_ref}"
            )
        state = bundle["state"]
        floor = since_message_id or state.get("last_merged_back_message_id")
        floor_int = max(message_id_int(floor), self._current_cycle_floor_id(state))
        branch_messages = []
        for message in bundle["messages"]:
            meta = message["meta"]
            current_id = str(meta.get("id") or "")
            if message_id_int(current_id) <= floor_int:
                continue
            if meta.get("role") == "user" and meta.get("source") in {"main-chat", "direct-chat"}:
                continue
            branch_messages.append(
                {
                    "id": current_id,
                    "role": meta.get("role"),
                    "kind": meta.get("kind", meta.get("role")),
                    "source": meta.get("source"),
                    "agent": meta.get("agent"),
                    "created_at": meta.get("created_at"),
                    "body": message["body"],
                }
            )
        if limit > 0:
            branch_messages = branch_messages[-limit:]
        development_log = self._development_log_bundle(
            bundle["meta"],
            state,
            purpose="merge",
        )
        merge_back_text = self._format_merge_back_text(session_key, development_log, branch_messages)
        return {
            "session_key": session_key,
            "meta": bundle["meta"],
            "state": state,
            "main_context": bundle["main_context"],
            "main_session_ref": bound_main_session_ref,
            "development_log": development_log,
            "since_message_id": floor,
            "branch_messages": branch_messages,
            "merge_back_text": merge_back_text,
        }

    def _format_merge_back_text(
        self,
        session_key: str,
        development_log: dict[str, Any],
        branch_messages: list[dict[str, Any]],
    ) -> str:
        lines = [
            f"[Relay merge-back: {session_key}]",
            "下面这些内容发生在你当前主会话窗口最后一句已知消息之后、以及你现在要回复的这条新输入之前。",
            "请先按顺序吸收并合并进当前主会话的统一上下文，再继续回答用户当前输入。",
            "不要把下面内容当成新的独立用户消息，也不要原样转述这段说明。",
        ]
        if development_log.get("attached"):
            lines.append("")
            lines.append("先补充自上次合流以来的开发日志增量：")
            entries = development_log.get("entries") or []
            if entries:
                for entry in entries:
                    lines.append("")
                    lines.append(entry.get("raw", "").rstrip())
            else:
                lines.append("（这段时间没有新的开发日志条目）")
        else:
            lines.append("")
            lines.append("当前没有附加开发日志。")
        if not branch_messages:
            lines.append("")
            lines.append("这次没有新的 branch 增量需要并回。")
            return "\n".join(lines).rstrip()
        lines.append("")
        lines.append("下面是按发生顺序需要并回主会话的 branch 增量：")
        for message in branch_messages:
            role = message.get("role") or "unknown"
            kind = message.get("kind") or role
            source = message.get("source") or ""
            created_at = message.get("created_at") or ""
            lines.append("")
            lines.append(
                f"{role}/{kind} id={message.get('id')} source={source} created_at={created_at}"
            )
            lines.append(message.get("body", "").rstrip())
        return "\n".join(lines).rstrip()

    def _next_message_id(self, session_key: str) -> str:
        current_max = 0
        for path in self.messages_dir(session_key).glob("*.md"):
            try:
                current_max = max(current_max, int(path.name.split(".", 1)[0]))
            except ValueError:
                continue
        return f"{current_max + 1:06d}"

    def list_messages(self, session_key: str) -> list[dict[str, Any]]:
        if not self.messages_dir(session_key).exists():
            return []
        messages = []
        for path in sorted(self.messages_dir(session_key).glob("*.md")):
            meta, body = parse_front_matter(path.read_text(encoding="utf-8"))
            messages.append(
                {
                    "path": str(path),
                    "filename": path.name,
                    "meta": meta,
                    "body": body,
                }
            )
        return messages

    def pending_deliveries(self, session_key: str | None = None) -> list[dict[str, Any]]:
        session_keys = [session_key] if session_key else [session["session_key"] for session in self.list_sessions()]
        deliveries: list[dict[str, Any]] = []
        for current_session_key in session_keys:
            meta = self.get_meta(current_session_key)
            state = self.get_state(current_session_key)
            if not meta or not state:
                continue
            last_delivered = message_id_int(state.get("last_delivered_message_id"))
            for message in self.list_messages(current_session_key):
                message_meta = message["meta"]
                message_id = str(message_meta.get("id") or "")
                if message_meta.get("role") != "assistant":
                    continue
                if not message_meta.get("deliver_via_openclaw"):
                    continue
                if message_id_int(message_id) <= last_delivered:
                    continue
                delivery_text = message["body"].rstrip()
                if message_meta.get("append_web_url") and meta.get("web_url"):
                    delivery_text = f"{delivery_text}\n\n{delivery_footer(meta['web_url'], meta.get('agent'))}"
                deliveries.append(
                    {
                        "session_key": current_session_key,
                        "message_id": message_id,
                        "kind": message_meta.get("kind"),
                        "agent": message_meta.get("agent"),
                        "channel": meta.get("channel"),
                        "target": meta.get("target"),
                        "web_url": meta.get("web_url"),
                        "default_delivery": meta.get("default_delivery"),
                        "created_at": message_meta.get("created_at"),
                        "delivery_text": delivery_text,
                        "message": message,
                    }
                )
        deliveries.sort(key=lambda item: (item.get("created_at") or "", item["session_key"], item["message_id"]))
        return deliveries

    def commit_user_message(self, session_key: str, body: str, source: str = "web-ui") -> dict[str, Any]:
        with self._lock_session(session_key):
            meta = self.get_meta(session_key)
            if not meta:
                raise FileNotFoundError(f"session {session_key} does not exist")
            state = self.get_state(session_key)
            if not is_relay_mode(state):
                raise ValueError("relay branch is closed; reopen it from OpenClaw before writing new branch input")
            message_id = self._next_message_id(session_key)
            created_at = now_iso()
            payload = {
                "id": message_id,
                "role": "user",
                "source": source,
                "status": "committed",
                "agent": meta["agent"],
                "created_at": created_at,
                "committed_at": created_at,
                "reply_expected": True,
            }
            file_path = self.messages_dir(session_key) / f"{message_id}.user.md"
            atomic_write_text(file_path, format_front_matter(payload, body))
            state["last_user_message_id"] = message_id
            state["last_committed_user_message_id"] = message_id
            branch_started_now = False
            if source == "web-ui" and not state.get("branch_started_at"):
                state["branch_started_at"] = created_at
                branch_started_now = True
            if source == "web-ui":
                state["last_branch_user_message_id"] = message_id
            state["status"] = "input_open" if state.get("branch_started_at") else "entry_open"
            self.save_state(session_key, state)
            routes = self.routes()
            route = routes["routes"].get(session_key, {})
            route["last_user_commit_id"] = message_id
            route["status"] = state["status"]
            route["updated_at"] = now_iso()
            routes["routes"][session_key] = route
            self.save_routes(routes)
            return {
                "message_id": message_id,
                "path": str(file_path),
                "source": source,
                "branch_started_now": branch_started_now,
                "branch_started_at": state.get("branch_started_at"),
            }

    def dispatch_session(self, session_key: str) -> dict[str, Any]:
        state = self.get_state(session_key)
        if not state:
            raise FileNotFoundError(f"session {session_key} does not exist")
        if not is_relay_mode(state):
            raise ValueError("relay branch is closed; reopen it from OpenClaw before dispatching new input")
        committed_id = state.get("last_branch_user_message_id")
        if not committed_id:
            raise ValueError("还没有网页录入内容；先在网页里保存第一条消息，branch 才会正式开始")
        if message_id_int(committed_id) <= self._current_cycle_floor_id(state):
            raise ValueError("当前 cycle 还没有新的网页录入内容")
        if committed_id == state.get("last_queued_user_message_id") and state.get("status") in {"queued", "processing"}:
            return {"session_key": session_key, "status": state["status"], "queued_message_id": committed_id}
        state["status"] = "queued"
        state["dispatch_requested_at"] = now_iso()
        state["dispatch_ack_timeout_seconds"] = self.config()["queue_ack_timeout_seconds"]
        state["last_queued_user_message_id"] = committed_id
        self.save_state(session_key, state)
        routes = self.routes()
        route = routes["routes"].get(session_key, {})
        route["status"] = "queued"
        route["last_user_commit_id"] = committed_id
        route["updated_at"] = now_iso()
        routes["routes"][session_key] = route
        self.save_routes(routes)
        return {"session_key": session_key, "status": state["status"], "queued_message_id": committed_id}

    def claim_next(self, agent: str, main_session_ref: str | None = None) -> dict[str, Any] | None:
        queued: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
        for session in self.list_sessions():
            if session.get("agent") != agent:
                continue
            state = self.get_state(session["session_key"])
            if state.get("status") != "queued":
                continue
            bound_main_session_ref = session.get("main_session_ref")
            if main_session_ref and bound_main_session_ref and bound_main_session_ref != main_session_ref:
                continue
            queued.append((session["session_key"], session, state))
        if not queued:
            return None
        queued.sort(key=lambda item: item[2].get("dispatch_requested_at") or "")
        session_key, _session, state = queued[0]
        if main_session_ref:
            self.set_main_session_ref(session_key, main_session_ref, source="agent-claim")
            state = self.get_state(session_key)
        state["status"] = "processing"
        state["agent_claimed_at"] = now_iso()
        self.save_state(session_key, state)
        routes = self.routes()
        route = routes["routes"].get(session_key, {})
        route["status"] = "processing"
        route["updated_at"] = now_iso()
        routes["routes"][session_key] = route
        self.save_routes(routes)
        last_message = self.message_by_id(session_key, state.get("last_queued_user_message_id"))
        return {
            "session_key": session_key,
            "state": state,
            "last_user_message": last_message,
            "meta": self.get_meta(session_key),
            "main_context_present": bool(self.get_main_context(session_key).get("body")),
            "main_session_ref": self.get_meta(session_key).get("main_session_ref"),
        }

    def _sessions_for_main_session(self, agent: str, main_session_ref: str) -> list[dict[str, Any]]:
        sessions: list[dict[str, Any]] = []
        for session in self.list_sessions():
            if session.get("agent") != agent:
                continue
            if session.get("main_session_ref") != main_session_ref:
                continue
            if session.get("mode") != "relay":
                continue
            state = self.get_state(session["session_key"])
            max_message_id = message_id_int(self._current_max_message_id(session["session_key"]))
            merge_floor = max(
                self._current_cycle_floor_id(state),
                message_id_int(state.get("last_merged_back_message_id")),
            )
            has_unmerged_increment = max_message_id > merge_floor
            if state.get("status") == "entry_open" and not has_unmerged_increment:
                continue
            sessions.append(session)
        sessions.sort(
            key=lambda session: (
                parse_iso_datetime(session.get("branch_started_at"))
                or parse_iso_datetime(session.get("entry_opened_at"))
                or parse_iso_datetime((self.get_state(session["session_key"]) or {}).get("updated_at"))
                or datetime.fromtimestamp(0).astimezone()
            ),
            reverse=True,
        )
        return sessions

    def resume_candidates(self, agent: str, main_session_ref: str) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        for session in self._sessions_for_main_session(agent, main_session_ref):
            session_key = session["session_key"]
            state = self.get_state(session_key)
            max_message_id = message_id_int(self._current_max_message_id(session_key))
            merge_floor = max(
                self._current_cycle_floor_id(state),
                message_id_int(state.get("last_merged_back_message_id")),
            )
            branch_messages = self.list_messages(session_key)
            pending_messages = [
                message
                for message in branch_messages
                if message_id_int(message["meta"].get("id")) > merge_floor
            ]
            last_pending = pending_messages[-1]["meta"].get("id") if pending_messages else None
            candidates.append(
                {
                    "session_key": session_key,
                    "status": state.get("status"),
                    "web_url": session.get("web_url"),
                    "entry_opened_at": state.get("entry_opened_at"),
                    "branch_started_at": state.get("branch_started_at"),
                    "last_merged_back_message_id": state.get("last_merged_back_message_id"),
                    "pending_message_count": len(pending_messages),
                    "last_pending_message_id": last_pending,
                }
            )
        return candidates

    def resume_main(
        self,
        *,
        agent: str,
        main_session_ref: str,
        session_key: str | None = None,
        limit: int = 100,
        close_relay: bool = True,
    ) -> dict[str, Any] | None:
        if session_key is not None:
            session = self.get_session(session_key)
            if session["meta"].get("agent") != agent:
                raise ValueError(f"session {session_key} belongs to {session['meta'].get('agent')}, not {agent}")
            target_session_key = session_key
        else:
            candidates = self._sessions_for_main_session(agent, main_session_ref)
            if not candidates:
                return None
            if len(candidates) > 1:
                raise ValueError(
                    "multiple relay branches are still bound to this main session; "
                    "pass --session to resume the correct one explicitly"
                )
            target_session_key = candidates[0]["session_key"]
        merge_back = self.build_merge_back(
            target_session_key,
            limit=limit,
            expected_main_session_ref=main_session_ref,
            require_main_session_ref=True,
        )
        last_branch_message_id = None
        if merge_back["branch_messages"]:
            last_branch_message_id = merge_back["branch_messages"][-1]["id"]
            self.mark_merged_back(target_session_key, last_branch_message_id)
        if close_relay:
            self.set_normal_mode(target_session_key)
        return {
            "session_key": target_session_key,
            "main_session_ref": main_session_ref,
            "merge_back": merge_back,
            "last_merged_message_id": last_branch_message_id,
            "closed": close_relay,
        }

    def message_by_id(self, session_key: str, message_id: str | None) -> dict[str, Any] | None:
        if not message_id:
            return None
        for message in self.list_messages(session_key):
            if message["meta"].get("id") == message_id:
                return message
        return None

    def write_agent_message(
        self,
        session_key: str,
        agent: str,
        kind: str,
        body: str,
        source_user_message_id: str | None = None,
        deliver_via_openclaw: bool = True,
        append_web_url: bool = True,
    ) -> dict[str, Any]:
        with self._lock_session(session_key):
            meta = self.get_meta(session_key)
            if not meta:
                raise FileNotFoundError(f"session {session_key} does not exist")
            if agent != meta.get("agent"):
                raise ValueError(f"session {session_key} belongs to {meta.get('agent')}, not {agent}")
            if kind not in {"progress", "final", "error"}:
                raise ValueError(f"unsupported kind: {kind}")
            state = self.get_state(session_key)
            source_id = source_user_message_id or state.get("last_queued_user_message_id") or state.get("last_committed_user_message_id")
            message_id = self._next_message_id(session_key)
            created_at = now_iso()
            payload = {
                "id": message_id,
                "role": "assistant",
                "kind": kind,
                "agent": agent,
                "source_user_message_id": source_id,
                "created_at": created_at,
                "deliver_via_openclaw": deliver_via_openclaw,
                "append_web_url": append_web_url,
            }
            file_path = self.messages_dir(session_key) / f"{message_id}.{kind}.{agent}.md"
            atomic_write_text(file_path, format_front_matter(payload, body))
            state["last_agent_message_id"] = message_id
            if kind == "progress":
                state["status"] = "processing"
            elif kind == "final":
                state["status"] = "awaiting_user"
            else:
                state["status"] = "error"
            self.save_state(session_key, state)
            routes = self.routes()
            route = routes["routes"].get(session_key, {})
            route["status"] = state["status"]
            route["last_agent_message_id"] = message_id
            route["updated_at"] = now_iso()
            routes["routes"][session_key] = route
            self.save_routes(routes)
            return {
                "message_id": message_id,
                "path": str(file_path),
                "status": state["status"],
                "deliver_via_openclaw": deliver_via_openclaw,
                "append_web_url": append_web_url,
            }

    def mark_delivered(self, session_key: str, message_id: str) -> dict[str, Any]:
        state = self.get_state(session_key)
        if not state:
            raise FileNotFoundError(f"session {session_key} does not exist")
        if not self.message_by_id(session_key, message_id):
            raise FileNotFoundError(f"message {message_id} does not exist in session {session_key}")
        current_last = message_id_int(state.get("last_delivered_message_id"))
        target = message_id_int(message_id)
        if target >= current_last:
            state["last_delivered_message_id"] = message_id
            self.save_state(session_key, state)
        return {
            "session_key": session_key,
            "last_delivered_message_id": state.get("last_delivered_message_id"),
        }

    def mark_merged_back(self, session_key: str, message_id: str) -> dict[str, Any]:
        state = self.get_state(session_key)
        if not state:
            raise FileNotFoundError(f"session {session_key} does not exist")
        if not self.message_by_id(session_key, message_id):
            raise FileNotFoundError(f"message {message_id} does not exist in session {session_key}")
        current_last = message_id_int(state.get("last_merged_back_message_id"))
        target = message_id_int(message_id)
        if target >= current_last:
            state["last_merged_back_message_id"] = message_id
            state["last_merged_back_at"] = now_iso()
            self.save_state(session_key, state)
        return {
            "session_key": session_key,
            "last_merged_back_message_id": state.get("last_merged_back_message_id"),
            "last_merged_back_at": state.get("last_merged_back_at"),
        }

    def set_normal_mode(self, session_key: str) -> dict[str, Any]:
        state = self.get_state(session_key)
        if not state:
            raise FileNotFoundError(f"session {session_key} does not exist")
        state["mode"] = "normal"
        state["status"] = "awaiting_user"
        state["branch_closed_at"] = now_iso()
        self.save_state(session_key, state)
        routes = self.routes()
        route = routes["routes"].get(session_key, {})
        route["mode"] = "normal"
        route["status"] = "awaiting_user"
        route["updated_at"] = now_iso()
        routes["routes"][session_key] = route
        self.save_routes(routes)
        return {"session_key": session_key, "mode": "normal", "status": "awaiting_user"}
