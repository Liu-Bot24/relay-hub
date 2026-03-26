#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from relay_hub import RelayHub
from relay_hub.store import make_session_key

DEFAULT_ROOT = (PROJECT_ROOT.parent / "runtime") if PROJECT_ROOT.name == "app" else ((Path.home() / "Library" / "Application Support" / "RelayHub" / "runtime") if (Path.home() / "Library" / "Application Support" / "RelayHub" / "runtime").exists() else (PROJECT_ROOT / "runtime"))


def output(payload: object) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def resolve_root(value: str | None) -> Path:
    return Path(value).expanduser().resolve() if value else DEFAULT_ROOT


def read_optional_text(body: str | None, body_file: str | None) -> str | None:
    if body is not None:
        return body
    if body_file is not None:
        return Path(body_file).read_text(encoding="utf-8")
    return None


def add_session_locator(parser: argparse.ArgumentParser, required: bool = True) -> None:
    parser.set_defaults(_session_locator_required=required)
    parser.add_argument("--session")
    parser.add_argument("--channel")
    parser.add_argument("--target")


def resolve_session_arg(args: argparse.Namespace) -> str:
    if getattr(args, "session", None):
        return args.session
    channel = getattr(args, "channel", None)
    target = getattr(args, "target", None)
    if channel and target:
        return make_session_key(channel, target)
    if getattr(args, "_session_locator_required", False):
        raise SystemExit("either --session or both --channel and --target are required")
    if channel or target:
        raise SystemExit("when using channel lookup, both --channel and --target are required")
    raise SystemExit("either --session or both --channel and --target are required")


def build_open_message(branch: dict[str, Any], agent_status: str) -> str:
    web_url = branch["meta"]["web_url"]
    raw_channels = list((branch["meta"].get("default_delivery") or {}).get("channels") or [])
    channels = ", ".join(raw_channels) if raw_channels else "原始触发渠道"
    if agent_status == "ready":
        return (
            f"{branch['meta']['agent']} branch 已就绪。\n"
            f"网页入口：{web_url}\n"
            f"默认回传渠道：{channels}"
        )
    return (
        f"{branch['meta']['agent']} branch 入口已打开，但对象当前状态是 {agent_status}。\n"
        f"网页入口：{web_url}\n"
        f"默认回传渠道：{channels}"
    )


def build_status_message(session: dict[str, Any]) -> str:
    meta = session["meta"]
    state = session["state"]
    status = state.get("status") or "unknown"
    if status == "queued":
        status_text = "已排队，等待对象接手。"
    elif status == "processing":
        status_text = "对象正在处理中。"
    elif status == "awaiting_user":
        status_text = "当前等待你的下一步输入。"
    elif status == "input_open":
        status_text = "网页入口已打开，等待录入。"
    elif status == "error":
        status_text = "最近一次处理出错。"
    else:
        status_text = f"当前状态：{status}"
    return (
        f"当前对象：{meta.get('agent')}\n"
        f"{status_text}\n"
        f"最近录入消息：{state.get('last_committed_user_message_id') or '暂无'}\n"
        f"最近对象回复：{state.get('last_agent_message_id') or '暂无'}\n"
        f"网页入口：{meta.get('web_url')}"
    )


def wait_for_claim(hub: RelayHub, session_key: str, timeout_seconds: int, poll_interval_seconds: float) -> dict[str, Any]:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        session = hub.get_session(session_key)
        state = session["state"]
        if state.get("status") == "processing" and state.get("agent_claimed_at"):
            return {
                "claimed": True,
                "session": session,
                "message": f"{session['meta'].get('agent')} 已确认接单，正在处理。",
            }
        time.sleep(poll_interval_seconds)
    session = hub.get_session(session_key)
    return {
        "claimed": False,
        "session": session,
        "message": f"已录入，但 {session['meta'].get('agent')} 尚未确认接单。",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="OpenClaw-facing Relay Hub bridge")
    parser.add_argument("--root", help="Relay root directory. Defaults to relay-hub/runtime.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    open_parser = subparsers.add_parser("open-entry", help="Open or reuse a branch entry for one channel target")
    open_parser.add_argument("--agent", required=True)
    open_parser.add_argument("--channel", required=True)
    open_parser.add_argument("--target", required=True)
    open_parser.add_argument("--delivery-mode", choices=["all", "subset"])
    open_parser.add_argument("--delivery-channels", nargs="*")
    open_main_group = open_parser.add_mutually_exclusive_group()
    open_main_group.add_argument("--main-context-body")
    open_main_group.add_argument("--main-context-file")
    open_parser.add_argument("--main-context-source", default="main-chat")

    dispatch_parser = subparsers.add_parser("dispatch-input", help="Queue a branch after the user says 已录入")
    add_session_locator(dispatch_parser)
    dispatch_parser.add_argument("--wait-claim", action="store_true")
    dispatch_parser.add_argument("--timeout-seconds", type=int, default=15)
    dispatch_parser.add_argument("--poll-interval-seconds", type=float, default=0.5)

    status_parser = subparsers.add_parser("session-status", help="Return a user-facing branch status summary")
    add_session_locator(status_parser)

    deliveries_parser = subparsers.add_parser("pull-deliveries", help="List assistant messages that OpenClaw should send")
    add_session_locator(deliveries_parser, required=False)

    delivered_parser = subparsers.add_parser("ack-delivery", help="Mark one assistant message as delivered")
    add_session_locator(delivered_parser)
    delivered_parser.add_argument("--message-id", required=True)

    exit_parser = subparsers.add_parser("exit-relay", help="Return one branch session to normal mode")
    add_session_locator(exit_parser)

    resolve_parser = subparsers.add_parser("resolve-session", help="Resolve a channel target into the deterministic session key")
    resolve_parser.add_argument("--channel", required=True)
    resolve_parser.add_argument("--target", required=True)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    hub = RelayHub(resolve_root(args.root))
    hub.init_layout()

    if args.command == "open-entry":
        main_context_body = read_optional_text(args.main_context_body, args.main_context_file)
        branch = hub.open_session(
            agent=args.agent,
            channel=args.channel,
            target=args.target,
            delivery_mode=args.delivery_mode,
            delivery_channels=args.delivery_channels,
            main_context_body=main_context_body,
            main_context_source=args.main_context_source,
        )
        agent = hub.get_agent(args.agent)
        output(
            {
                "ok": True,
                "branch": branch,
                "agent_status": agent.get("status"),
                "user_message": build_open_message(branch, agent.get("status", "offline")),
            }
        )
        return

    if args.command == "dispatch-input":
        session_key = resolve_session_arg(args)
        queued = hub.dispatch_session(session_key)
        session = hub.get_session(session_key)
        payload: dict[str, Any] = {
            "ok": True,
            "queued": queued,
            "session": session,
            "user_message": f"已录入，已加入 {session['meta'].get('agent')} 的待处理队列。",
        }
        if args.wait_claim:
            payload["claim_wait"] = wait_for_claim(
                hub,
                session_key,
                timeout_seconds=args.timeout_seconds,
                poll_interval_seconds=args.poll_interval_seconds,
            )
            payload["user_message"] = payload["claim_wait"]["message"]
        output(payload)
        return

    if args.command == "session-status":
        session = hub.get_session(resolve_session_arg(args))
        output({"ok": True, "session": session, "user_message": build_status_message(session)})
        return

    if args.command == "pull-deliveries":
        session_key = None
        if args.session or (args.channel and args.target):
            session_key = resolve_session_arg(args)
        deliveries = hub.pending_deliveries(session_key=session_key)
        output({"ok": True, "deliveries": deliveries, "count": len(deliveries)})
        return

    if args.command == "ack-delivery":
        payload = hub.mark_delivered(resolve_session_arg(args), args.message_id)
        output({"ok": True, **payload})
        return

    if args.command == "exit-relay":
        session_key = resolve_session_arg(args)
        payload = hub.set_normal_mode(session_key)
        output(
            {
                "ok": True,
                **payload,
                "user_message": "已退出 Relay Hub，恢复 OpenClaw 正常模式。",
            }
        )
        return

    if args.command == "resolve-session":
        session_key = make_session_key(args.channel, args.target)
        exists = hub.session_dir(session_key).exists()
        output({"ok": True, "session_key": session_key, "exists": exists})
        return

    parser.error(f"unknown command: {args.command}")


if __name__ == "__main__":
    main()
