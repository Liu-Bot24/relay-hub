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


def last_branch_message_id(merge_back: dict[str, Any]) -> str | None:
    messages = merge_back.get("branch_messages") or []
    if not messages:
        return None
    return messages[-1].get("id")


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

    note_parser = subparsers.add_parser(
        "append-main-note",
        help="Append a main-chat note into an existing branch transcript",
    )
    note_parser.add_argument("--session", required=True)
    note_parser.add_argument("--source", default="direct-chat")
    note_group = note_parser.add_mutually_exclusive_group(required=True)
    note_group.add_argument("--body")
    note_group.add_argument("--body-file")

    claim_parser = subparsers.add_parser(
        "claim-next",
        help="Claim the next queued branch for this agent",
    )

    branch_parser = subparsers.add_parser(
        "branch-context",
        help="Build the branch-processing context from the main seed plus branch transcript",
    )
    branch_parser.add_argument("--session", required=True)
    branch_parser.add_argument("--limit", type=int, default=50)

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
    merge_parser.add_argument(
        "--mark-merged",
        action="store_true",
        help="After building the packet, mark its last branch message as merged back",
    )

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

    if args.command == "set-presence":
        agent = resolve_agent(args.agent, default_agent)
        output({"ok": True, "agent": hub.set_agent(agent, args.status)})
        return

    if args.command == "start-branch":
        agent = resolve_agent(args.agent, default_agent)
        main_context_body = read_body(args.main_context_body, args.main_context_file)
        payload = hub.open_session(
            agent=agent,
            channel=args.channel,
            target=args.target,
            delivery_mode=args.delivery_mode,
            delivery_channels=args.delivery_channels,
            main_context_body=main_context_body,
            main_context_source=args.main_context_source,
        )
        output(
            {
                "ok": True,
                "branch": payload,
                "next_steps": [
                    f"Open the web entry: {payload['meta']['web_url']}",
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

    if args.command == "claim-next":
        agent = resolve_agent(args.agent, default_agent)
        payload = hub.claim_next(agent)
        output({"ok": payload is not None, "claim": payload})
        return

    if args.command == "branch-context":
        payload = hub.build_context(args.session, limit=args.limit)
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
        )
        merged = None
        if args.mark_merged:
            last_id = last_branch_message_id(payload)
            if last_id:
                merged = hub.mark_merged_back(args.session, last_id)
        output({"ok": True, "merge_back": payload, "mark_merged_result": merged})
        return

    if args.command == "show-branch":
        output({"ok": True, "branch": hub.get_session(args.session)})
        return

    parser.error(f"unknown command: {args.command}")


if __name__ == "__main__":
    main()
