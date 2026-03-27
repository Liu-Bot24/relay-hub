#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from relay_hub import RelayHub

DEFAULT_ROOT = (Path.home() / "Library" / "Application Support" / "RelayHub" / "runtime") if (Path.home() / "Library" / "Application Support" / "RelayHub" / "runtime").exists() else (PROJECT_ROOT / "runtime")


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
    return {
        "agent": presence,
        "summary": {
            "ready": presence.get("status") == "ready",
            "session_count": len(sessions),
            "queued_count": len(queued),
            "processing_count": len(processing),
            "awaiting_user_count": len(awaiting_user),
            "input_open_count": len(input_open),
            "entry_open_count": len(entry_open),
            "error_count": len(error),
            "has_pending_branch": bool(queued or processing),
        },
        "sessions": sessions,
    }


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

    enable_parser = subparsers.add_parser(
        "enable-relay",
        help="Mark this agent as ready and attach/create a development log for the current project",
    )
    enable_parser.add_argument("--project-root", required=True)
    enable_parser.add_argument("--development-log-path")
    enable_group = enable_parser.add_mutually_exclusive_group(required=True)
    enable_group.add_argument("--snapshot-body")
    enable_group.add_argument("--snapshot-file")
    enable_parser.add_argument("--author")

    subparsers.add_parser(
        "disable-relay",
        help="Mark this agent as offline for Relay Hub without removing project bindings",
    )

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

        if args.command == "enable-relay":
            agent = resolve_agent(args.agent, default_agent)
            payload = hub.enable_agent(
                agent=agent,
                project_root=args.project_root,
                development_log_path=args.development_log_path,
                snapshot_body=read_body(args.snapshot_body, args.snapshot_file) or "",
                author=args.author or agent,
            )
            output({"ok": True, "relay_enabled": payload})
            return

        if args.command == "disable-relay":
            agent = resolve_agent(args.agent, default_agent)
            output({"ok": True, "agent": hub.set_agent(agent, "offline")})
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
            payload = hub.resume_main(
                agent=agent,
                main_session_ref=args.main_session_ref,
                session_key=args.session,
                limit=args.limit,
                close_relay=not args.keep_relay_open,
            )
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
