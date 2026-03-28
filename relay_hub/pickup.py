from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any


def now_iso() -> str:
    from datetime import datetime

    return datetime.now().astimezone().isoformat(timespec="seconds")


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_dir(path.parent)
    tmp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp_path, path)


def load_json(path: Path, default: dict[str, Any] | None = None) -> dict[str, Any]:
    if not path.exists():
        return json.loads(json.dumps(default or {}))
    return json.loads(path.read_text(encoding="utf-8"))


def pickup_token(main_session_ref: str) -> str:
    return hashlib.sha256(main_session_ref.encode("utf-8")).hexdigest()[:16]


def pickup_key(agent: str, main_session_ref: str) -> str:
    return f"{agent}__{pickup_token(main_session_ref)}"


def pickup_dir(root: str | Path) -> Path:
    return Path(root).expanduser().resolve() / "agents" / "pickups"


def pickup_state_path(root: str | Path, agent: str, main_session_ref: str) -> Path:
    return pickup_dir(root) / f"{pickup_key(agent, main_session_ref)}.json"


def pickup_context_seed_path(root: str | Path, agent: str, main_session_ref: str) -> Path:
    return pickup_dir(root) / f"{pickup_key(agent, main_session_ref)}.main_context.md"


def pickup_log_path(root: str | Path, agent: str, main_session_ref: str) -> Path:
    return Path(root).expanduser().resolve() / "logs" / f"{pickup_key(agent, main_session_ref)}.pickup.log"


def pickup_capture_queue_dir(root: str | Path, agent: str, main_session_ref: str) -> Path:
    return pickup_dir(root) / f"{pickup_key(agent, main_session_ref)}.capture-queue"


def load_pickup_state(root: str | Path, agent: str, main_session_ref: str) -> dict[str, Any]:
    return load_json(
        pickup_state_path(root, agent, main_session_ref),
        {
            "agent": agent,
            "main_session_ref": main_session_ref,
            "key": pickup_key(agent, main_session_ref),
            "backend": None,
            "backend_command": None,
            "project_root": None,
            "development_log_path": None,
            "status": "stopped",
            "pid": None,
            "created_at": None,
            "updated_at": None,
            "last_heartbeat_at": None,
            "last_claimed_session_key": None,
            "last_reply_message_id": None,
            "last_error": None,
            "last_pump_result": None,
            "host_kind": None,
            "host_thread_id": None,
            "host_rollout_path": None,
            "mirror_read_offset": 0,
            "last_mirrored_turn_id": None,
            "last_mirrored_at": None,
            "last_mirrored_body_preview": None,
        },
    )


def save_pickup_state(root: str | Path, agent: str, main_session_ref: str, payload: dict[str, Any]) -> dict[str, Any]:
    payload["agent"] = agent
    payload["main_session_ref"] = main_session_ref
    payload["key"] = pickup_key(agent, main_session_ref)
    payload["updated_at"] = now_iso()
    atomic_write_json(pickup_state_path(root, agent, main_session_ref), payload)
    return payload


def process_alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def list_pickup_states(root: str | Path, agent: str | None = None) -> list[dict[str, Any]]:
    directory = pickup_dir(root)
    if not directory.exists():
        return []
    states: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.json")):
        state = load_json(path, {})
        if agent and state.get("agent") != agent:
            continue
        state["state_path"] = str(path)
        state["alive"] = process_alive(state.get("pid"))
        states.append(state)
    states.sort(key=lambda item: item.get("updated_at") or "", reverse=True)
    return states
