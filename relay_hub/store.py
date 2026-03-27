from __future__ import annotations

import base64
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote


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


def make_session_key(channel: str, target: str) -> str:
    return f"{channel}__{encode_session_target(target)}"


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
        return config

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
            },
        )

    def set_agent(self, agent: str, status: str = "ready") -> dict[str, Any]:
        payload = self.get_agent(agent)
        payload["status"] = status
        payload["last_seen_at"] = now_iso()
        atomic_write_json(self.agent_path(agent), payload)
        return payload

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
    ) -> dict[str, Any]:
        config = self.config()
        session_key = make_session_key(channel, target)
        session_dir = self.session_dir(session_key)
        created = not session_dir.exists()
        ensure_dir(self.messages_dir(session_key))
        ensure_dir(self.attachments_dir(session_key))
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
            "created_at": self.get_meta(session_key).get("created_at", now_iso()),
            "web_url": self.web_url(session_key),
            "default_delivery": default_delivery,
        }
        state = {
            "session_key": session_key,
            "mode": "relay",
            "agent": agent,
            "status": "input_open",
            "dispatch_requested_at": None,
            "dispatch_ack_timeout_seconds": config["queue_ack_timeout_seconds"],
            "last_user_message_id": self.get_state(session_key).get("last_user_message_id"),
            "last_committed_user_message_id": self.get_state(session_key).get("last_committed_user_message_id"),
            "last_queued_user_message_id": self.get_state(session_key).get("last_queued_user_message_id"),
            "last_agent_message_id": self.get_state(session_key).get("last_agent_message_id"),
            "last_delivered_message_id": self.get_state(session_key).get("last_delivered_message_id"),
            "last_merged_back_message_id": self.get_state(session_key).get("last_merged_back_message_id"),
            "agent_claimed_at": self.get_state(session_key).get("agent_claimed_at"),
            "main_context_updated_at": self.get_state(session_key).get("main_context_updated_at"),
            "updated_at": now_iso(),
        }
        atomic_write_json(self.meta_path(session_key), meta)
        self.save_state(session_key, state)
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
                    "status": state.get("status"),
                    "mode": state.get("mode"),
                    "web_url": meta.get("web_url"),
                    "message_count": len(messages),
                    "route": routes.get(session_key),
                }
            )
        return sessions

    def get_session(self, session_key: str) -> dict[str, Any]:
        routes = self.routes().get("routes", {})
        return {
            "meta": self.get_meta(session_key),
            "state": self.get_state(session_key),
            "main_context": self.get_main_context(session_key),
            "route": routes.get(session_key),
            "messages": self.list_messages(session_key),
        }

    def build_context(self, session_key: str, limit: int = 50) -> dict[str, Any]:
        bundle = self.get_session(session_key)
        main_context = bundle["main_context"]
        messages = bundle["messages"]
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
        return {
            "session_key": session_key,
            "meta": bundle["meta"],
            "state": bundle["state"],
            "main_context": main_context,
            "main_context_present": bool(main_context.get("body")),
            "route": bundle["route"],
            "messages": branch_messages,
            "branch_messages": branch_messages,
        }

    def build_merge_back(self, session_key: str, since_message_id: str | None = None, limit: int = 100) -> dict[str, Any]:
        bundle = self.get_session(session_key)
        state = bundle["state"]
        floor = since_message_id or state.get("last_merged_back_message_id")
        floor_int = message_id_int(floor)
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
        merge_back_text = self._format_merge_back_text(session_key, branch_messages)
        return {
            "session_key": session_key,
            "meta": bundle["meta"],
            "state": bundle["state"],
            "main_context": bundle["main_context"],
            "since_message_id": floor,
            "branch_messages": branch_messages,
            "merge_back_text": merge_back_text,
        }

    def _format_merge_back_text(self, session_key: str, branch_messages: list[dict[str, Any]]) -> str:
        if not branch_messages:
            return f"[Relay branch merge-back: {session_key}]\n没有新的分支增量。"
        lines = [f"[Relay branch merge-back: {session_key}]"]
        lines.append("下面是需要并回主对话窗口的分支增量：")
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
                    delivery_text = f"{delivery_text}\n\n网页入口：{meta['web_url']}"
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
        state["status"] = "input_open"
        self.save_state(session_key, state)
        routes = self.routes()
        route = routes["routes"].get(session_key, {})
        route["last_user_commit_id"] = message_id
        route["status"] = state["status"]
        route["updated_at"] = now_iso()
        routes["routes"][session_key] = route
        self.save_routes(routes)
        return {"message_id": message_id, "path": str(file_path), "source": source}

    def dispatch_session(self, session_key: str) -> dict[str, Any]:
        state = self.get_state(session_key)
        if not state:
            raise FileNotFoundError(f"session {session_key} does not exist")
        if not is_relay_mode(state):
            raise ValueError("relay branch is closed; reopen it from OpenClaw before dispatching new input")
        committed_id = state.get("last_committed_user_message_id")
        if not committed_id:
            raise ValueError("no committed user message found")
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

    def claim_next(self, agent: str) -> dict[str, Any] | None:
        queued: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
        for session in self.list_sessions():
            if session.get("agent") != agent:
                continue
            state = self.get_state(session["session_key"])
            if state.get("status") != "queued":
                continue
            queued.append((session["session_key"], session, state))
        if not queued:
            return None
        queued.sort(key=lambda item: item[2].get("dispatch_requested_at") or "")
        session_key, _session, state = queued[0]
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
            self.save_state(session_key, state)
        return {
            "session_key": session_key,
            "last_merged_back_message_id": state.get("last_merged_back_message_id"),
        }

    def set_normal_mode(self, session_key: str) -> dict[str, Any]:
        state = self.get_state(session_key)
        if not state:
            raise FileNotFoundError(f"session {session_key} does not exist")
        state["mode"] = "normal"
        state["status"] = "awaiting_user"
        self.save_state(session_key, state)
        routes = self.routes()
        route = routes["routes"].get(session_key, {})
        route["mode"] = "normal"
        route["status"] = "awaiting_user"
        route["updated_at"] = now_iso()
        routes["routes"][session_key] = route
        self.save_routes(routes)
        return {"session_key": session_key, "mode": "normal", "status": "awaiting_user"}
