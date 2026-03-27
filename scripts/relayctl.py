#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from relay_hub import RelayHub

DEFAULT_ROOT = (PROJECT_ROOT.parent / "runtime") if PROJECT_ROOT.name == "app" else ((Path.home() / "Library" / "Application Support" / "RelayHub" / "runtime") if (Path.home() / "Library" / "Application Support" / "RelayHub" / "runtime").exists() else (PROJECT_ROOT / "runtime"))


def output(payload: object) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def fail(message: str, exit_code: int = 1) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(exit_code)


def resolve_root(value: str | None) -> Path:
    return Path(value).expanduser().resolve() if value else DEFAULT_ROOT


def read_body(args: argparse.Namespace) -> str:
    if args.body:
        return args.body
    if args.body_file:
        return Path(args.body_file).read_text(encoding="utf-8")
    raise SystemExit("body is required")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Relay Hub control CLI")
    parser.add_argument("--root", help="Relay root directory. Defaults to relay-hub/runtime.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Initialize a relay root")
    init_parser.add_argument("--web-base-url", default="http://127.0.0.1:4317")
    init_parser.add_argument("--ack-timeout", type=int, default=15)
    init_parser.add_argument(
        "--default-channels",
        nargs="+",
        default=[],
    )

    agent_parser = subparsers.add_parser("set-agent", help="Create or update agent presence")
    agent_parser.add_argument("--agent", required=True)
    agent_parser.add_argument("--status", default="ready")

    open_parser = subparsers.add_parser("open-session", help="Open or rebind a relay session")
    open_parser.add_argument("--agent", required=True)
    open_parser.add_argument("--channel", required=True)
    open_parser.add_argument("--target", required=True)
    open_parser.add_argument("--delivery-mode", choices=["all", "subset"])
    open_parser.add_argument("--delivery-channels", nargs="*")
    open_main_group = open_parser.add_mutually_exclusive_group()
    open_main_group.add_argument("--main-context-body")
    open_main_group.add_argument("--main-context-file")
    open_parser.add_argument("--main-context-source", default="main-chat")
    open_parser.add_argument("--main-session-ref")
    open_parser.add_argument("--main-session-ref-source", default="agent-session")

    subparsers.add_parser("list-sessions", help="List all sessions")

    show_parser = subparsers.add_parser("show-session", help="Show one session")
    show_parser.add_argument("--session", required=True)

    set_main_parser = subparsers.add_parser("set-main-context", help="Store the main-window context seed for one branch session")
    set_main_parser.add_argument("--session", required=True)
    set_main_parser.add_argument("--source", default="main-chat")
    set_main_group = set_main_parser.add_mutually_exclusive_group(required=True)
    set_main_group.add_argument("--body")
    set_main_group.add_argument("--body-file")

    set_main_session_parser = subparsers.add_parser(
        "set-main-session-ref",
        help="Bind one branch session to one specific main AI session reference",
    )
    set_main_session_parser.add_argument("--session", required=True)
    set_main_session_parser.add_argument("--main-session-ref", required=True)
    set_main_session_parser.add_argument("--source", default="agent-session")

    show_main_parser = subparsers.add_parser("show-main-context", help="Show the stored main-window context seed")
    show_main_parser.add_argument("--session", required=True)

    commit_parser = subparsers.add_parser("commit-user", help="Write a committed user message")
    commit_parser.add_argument("--session", required=True)
    commit_parser.add_argument("--source", default="web-ui")
    commit_group = commit_parser.add_mutually_exclusive_group(required=True)
    commit_group.add_argument("--body")
    commit_group.add_argument("--body-file")

    dispatch_parser = subparsers.add_parser("dispatch", help="Mark a session as queued")
    dispatch_parser.add_argument("--session", required=True)

    claim_parser = subparsers.add_parser("claim-next", help="Claim the next queued session for an agent")
    claim_parser.add_argument("--agent", required=True)
    claim_parser.add_argument("--main-session-ref")

    reply_parser = subparsers.add_parser("write-reply", help="Write a progress/final/error message")
    reply_parser.add_argument("--session", required=True)
    reply_parser.add_argument("--agent", required=True)
    reply_parser.add_argument("--kind", choices=["progress", "final", "error"], required=True)
    reply_group = reply_parser.add_mutually_exclusive_group(required=True)
    reply_group.add_argument("--body")
    reply_group.add_argument("--body-file")
    reply_parser.add_argument("--source-user-message-id")
    reply_parser.add_argument("--no-deliver-via-openclaw", action="store_true")
    reply_parser.add_argument("--no-append-web-url", action="store_true")

    context_parser = subparsers.add_parser(
        "build-context",
        help="Build the branch-processing context bundle from the main seed plus branch transcript",
    )
    context_parser.add_argument("--session", required=True)
    context_parser.add_argument("--limit", type=int, default=50)
    context_parser.add_argument("--main-session-ref")

    merge_parser = subparsers.add_parser(
        "build-merge-back",
        help="Build the branch increment that should be merged back into the main chat",
    )
    merge_parser.add_argument("--session", required=True)
    merge_parser.add_argument("--since-message-id")
    merge_parser.add_argument("--limit", type=int, default=100)
    merge_parser.add_argument("--main-session-ref")

    deliveries_parser = subparsers.add_parser(
        "list-pending-delivery",
        help="List assistant messages that still need to be sent via OpenClaw",
    )
    deliveries_parser.add_argument("--session")

    delivered_parser = subparsers.add_parser(
        "mark-delivered",
        help="Mark one assistant message as already delivered via OpenClaw",
    )
    delivered_parser.add_argument("--session", required=True)
    delivered_parser.add_argument("--message-id", required=True)

    merged_parser = subparsers.add_parser(
        "mark-merged-back",
        help="Mark branch messages up to one message id as already merged back into the main chat",
    )
    merged_parser.add_argument("--session", required=True)
    merged_parser.add_argument("--message-id", required=True)

    normal_parser = subparsers.add_parser("set-normal", help="Return a session to normal mode")
    normal_parser.add_argument("--session", required=True)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    hub = RelayHub(resolve_root(args.root))
    try:
        if args.command == "init":
            payload = hub.init_layout(
                web_base_url=args.web_base_url,
                queue_ack_timeout_seconds=args.ack_timeout,
                default_channels=args.default_channels,
            )
            output({"ok": True, "config": payload, "root": str(hub.root)})
            return

        hub.init_layout()

        if args.command == "set-agent":
            output({"ok": True, "agent": hub.set_agent(args.agent, args.status)})
            return
        if args.command == "open-session":
            main_context_body = args.main_context_body
            if args.main_context_file:
                main_context_body = Path(args.main_context_file).read_text(encoding="utf-8")
            payload = hub.open_session(
                args.agent,
                args.channel,
                args.target,
                delivery_mode=args.delivery_mode,
                delivery_channels=args.delivery_channels,
                main_context_body=main_context_body,
                main_context_source=args.main_context_source,
                main_session_ref=args.main_session_ref,
                main_session_ref_source=args.main_session_ref_source,
            )
            output({"ok": True, **payload})
            return
        if args.command == "list-sessions":
            output({"ok": True, "sessions": hub.list_sessions()})
            return
        if args.command == "show-session":
            output({"ok": True, "session": hub.get_session(args.session)})
            return
        if args.command == "set-main-context":
            output({"ok": True, "main_context": hub.set_main_context(args.session, read_body(args), source=args.source)})
            return
        if args.command == "set-main-session-ref":
            output(
                {
                    "ok": True,
                    "main_session": hub.set_main_session_ref(
                        args.session,
                        args.main_session_ref,
                        source=args.source,
                    ),
                }
            )
            return
        if args.command == "show-main-context":
            output({"ok": True, "main_context": hub.get_main_context(args.session)})
            return
        if args.command == "commit-user":
            output({"ok": True, **hub.commit_user_message(args.session, read_body(args), source=args.source)})
            return
        if args.command == "dispatch":
            output({"ok": True, **hub.dispatch_session(args.session)})
            return
        if args.command == "claim-next":
            payload = hub.claim_next(args.agent, main_session_ref=args.main_session_ref)
            output({"ok": payload is not None, "claim": payload})
            return
        if args.command == "write-reply":
            output(
                {
                    "ok": True,
                    **hub.write_agent_message(
                        args.session,
                        args.agent,
                        args.kind,
                        read_body(args),
                        source_user_message_id=args.source_user_message_id,
                        deliver_via_openclaw=not args.no_deliver_via_openclaw,
                        append_web_url=not args.no_append_web_url,
                    ),
                }
            )
            return
        if args.command == "build-context":
            output(
                {
                    "ok": True,
                    "context": hub.build_context(
                        args.session,
                        limit=args.limit,
                        expected_main_session_ref=args.main_session_ref,
                    ),
                }
            )
            return
        if args.command == "build-merge-back":
            output(
                {
                    "ok": True,
                    "merge_back": hub.build_merge_back(
                        args.session,
                        since_message_id=args.since_message_id,
                        limit=args.limit,
                        expected_main_session_ref=args.main_session_ref,
                        require_main_session_ref=bool(args.main_session_ref),
                    ),
                }
            )
            return
        if args.command == "list-pending-delivery":
            output({"ok": True, "deliveries": hub.pending_deliveries(session_key=args.session)})
            return
        if args.command == "mark-delivered":
            output({"ok": True, **hub.mark_delivered(args.session, args.message_id)})
            return
        if args.command == "mark-merged-back":
            output({"ok": True, **hub.mark_merged_back(args.session, args.message_id)})
            return
        if args.command == "set-normal":
            output({"ok": True, **hub.set_normal_mode(args.session)})
            return
    except (FileNotFoundError, ValueError) as exc:
        fail(str(exc))

    parser.error(f"unknown command: {args.command}")


if __name__ == "__main__":
    main()
