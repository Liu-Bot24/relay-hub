#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from relay_agent_daemon import enqueue_captured_main_output
from relay_hub import RelayHub


DEFAULT_ROOT = (
    Path.home() / "Library" / "Application Support" / "RelayHub" / "runtime"
    if (Path.home() / "Library" / "Application Support" / "RelayHub" / "runtime").exists()
    else (PROJECT_ROOT / "runtime")
)

DEFAULT_FIELDS = [
    "last_assistant_message",
    "assistant_message",
    "assistantMessage",
    "lastAssistantMessage",
    "final_output",
    "finalOutput",
    "output_text",
    "outputText",
    "response_text",
    "responseText",
    "message",
    "text",
]

TRANSCRIPT_PATH_FIELDS = [
    "transcript_path",
    "transcriptPath",
]


def output(payload: object) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def resolve_root(value: str | None) -> Path:
    return Path(value).expanduser().resolve() if value else DEFAULT_ROOT


def read_stdin_text() -> str:
    if sys.stdin.closed or sys.stdin.isatty():
        return ""
    return sys.stdin.read()


def stringify_content(value: Any) -> str | None:
    if isinstance(value, str):
        text = value.strip()
        return text or None
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            text = stringify_content(item)
            if text:
                parts.append(text)
        if not parts:
            return None
        return "\n".join(parts).strip()
    if isinstance(value, dict):
        item_type = str(value.get("type") or "").strip()
        if item_type == "text" and isinstance(value.get("text"), str):
            text = value["text"].strip()
            return text or None
        for key in ("text", "content", "message", "output_text", "outputText", "value"):
            if key in value:
                text = stringify_content(value[key])
                if text:
                    return text
    return None


def extract_last_assistant_text_from_transcript(path_value: Any) -> str | None:
    if not isinstance(path_value, str):
        return None
    path = Path(path_value).expanduser()
    if not path.exists() or not path.is_file():
        return None
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            obj = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if obj.get("role") != "assistant":
            continue
        message = obj.get("message")
        if isinstance(message, dict):
            text = stringify_content(message.get("content"))
            if text:
                return text
            text = stringify_content(message.get("text"))
            if text:
                return text
        text = stringify_content(obj.get("content"))
        if text:
            return text
        text = stringify_content(obj.get("text"))
        if text:
            return text
    return None


def extract_from_payload(payload: Any, candidate_fields: list[str]) -> tuple[str | None, str | None]:
    if isinstance(payload, str):
        return (payload.strip() or None), "stdin_text"
    if not isinstance(payload, dict):
        return None, None
    for field in candidate_fields:
        if field not in payload:
            continue
        text = stringify_content(payload[field])
        if text:
            return text, field
    for field in TRANSCRIPT_PATH_FIELDS:
        if field not in payload:
            continue
        text = extract_last_assistant_text_from_transcript(payload[field])
        if text:
            return text, field
    return None, None


def parse_payload(text: str) -> Any | None:
    stripped = text.strip()
    if not stripped:
        return None
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return stripped


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generic after-reply helper that extracts the exact final body from a host hook payload and queues it for Relay Hub mirroring"
    )
    parser.add_argument("--root", help="Relay root directory. Defaults to relay-hub/runtime.")
    parser.add_argument("--agent", required=True)
    parser.add_argument("--main-session-ref")
    parser.add_argument("--body")
    parser.add_argument("--body-file")
    parser.add_argument("--payload-file", help="Optional file containing the raw host hook payload.")
    parser.add_argument(
        "--field",
        action="append",
        help="Additional payload field to try before the built-in common field list.",
    )
    parser.add_argument("--source", default="host-after-reply-hook")
    return parser


def read_explicit_body(args: argparse.Namespace) -> str | None:
    if args.body is not None:
        text = args.body.strip()
        return text or None
    if args.body_file is not None:
        text = Path(args.body_file).read_text(encoding="utf-8").strip()
        return text or None
    return None


def read_payload_text(args: argparse.Namespace) -> str:
    if args.payload_file:
        return Path(args.payload_file).read_text(encoding="utf-8")
    return read_stdin_text()


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    hub = RelayHub(resolve_root(args.root))
    hub.init_layout()
    presence = hub.get_agent(args.agent)
    main_session_ref = args.main_session_ref or presence.get("current_main_session_ref")

    if presence.get("status") != "ready" or not main_session_ref:
        output(
            {
                "ok": True,
                "skipped": True,
                "reason": "relay_not_ready",
                "agent": args.agent,
                "main_session_ref": main_session_ref,
            }
        )
        return

    body = read_explicit_body(args)
    extracted_from = "explicit_body"
    if body is None:
        candidate_fields = list(args.field or []) + [field for field in DEFAULT_FIELDS if field not in (args.field or [])]
        payload = parse_payload(read_payload_text(args))
        body, extracted_from = extract_from_payload(payload, candidate_fields)

    if body is None:
        output(
            {
                "ok": True,
                "skipped": True,
                "reason": "no_final_body",
                "agent": args.agent,
                "main_session_ref": main_session_ref,
            }
        )
        return

    payload = enqueue_captured_main_output(
        root=hub.root,
        agent=args.agent,
        main_session_ref=main_session_ref,
        body=body,
        source=args.source,
        metadata={"extracted_from": extracted_from},
    )
    output(
        {
            "ok": True,
            "queued": payload,
            "agent": args.agent,
            "main_session_ref": main_session_ref,
            "extracted_from": extracted_from,
        }
    )


if __name__ == "__main__":
    main()
