from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any


DEVELOPMENT_LOG_FILENAME = "DEVELOPMENT_LOG.md"
DEVELOPMENT_LOG_HEADER = "# DEVELOPMENT_LOG.md\n\n"
ENTRY_HEADER_RE = re.compile(
    r"^## (?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) UTC(?P<offset>[+-]\d{2}:\d{2}) \| 作者: (?P<author>.+)$",
    re.MULTILINE,
)


def format_log_timestamp(dt: datetime | None = None) -> str:
    current = dt or datetime.now().astimezone()
    offset = current.strftime("%z")
    offset = f"{offset[:3]}:{offset[3:]}"
    return f"{current.strftime('%Y-%m-%d %H:%M:%S')} UTC{offset}"


def parse_log_timestamp(header_line: str) -> datetime | None:
    match = ENTRY_HEADER_RE.match(header_line.strip())
    if not match:
        return None
    raw = f"{match.group('ts')}{match.group('offset')}"
    return datetime.strptime(raw, "%Y-%m-%d %H:%M:%S%z")


def find_development_log(start: str | Path | None) -> Path | None:
    if not start:
        return None
    current = Path(start).expanduser().resolve()
    if current.is_file():
        if current.name == DEVELOPMENT_LOG_FILENAME:
            return current
        current = current.parent
    for candidate in (current, *current.parents):
        path = candidate / DEVELOPMENT_LOG_FILENAME
        if path.exists():
            return path
    return None


def ensure_development_log(path: str | Path) -> Path:
    log_path = Path(path).expanduser().resolve()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    if not log_path.exists():
        log_path.write_text(DEVELOPMENT_LOG_HEADER, encoding="utf-8")
        return log_path
    content = log_path.read_text(encoding="utf-8")
    if not content.startswith("# DEVELOPMENT_LOG.md"):
        if content.strip():
            log_path.write_text(DEVELOPMENT_LOG_HEADER + content, encoding="utf-8")
        else:
            log_path.write_text(DEVELOPMENT_LOG_HEADER, encoding="utf-8")
    return log_path


def prepend_log_entry(
    path: str | Path,
    *,
    author: str,
    goal: str,
    key_operations: list[str],
    changed_files: list[str],
    verification_results: list[str],
    next_steps: list[str] | None = None,
    snapshot_body: str | None = None,
) -> Path:
    log_path = ensure_development_log(path)
    current = log_path.read_text(encoding="utf-8")
    entry_lines = [
        f"## {format_log_timestamp()} | 作者: {author}",
        f"- 目标: {goal}",
        "- 关键操作:",
    ]
    for item in key_operations or ["无"]:
        entry_lines.append(f"  - {item}")
    entry_lines.append("- 变更文件:")
    for item in changed_files or ["无代码文件改动"]:
        entry_lines.append(f"  - {item}")
    entry_lines.append("- 验证结果:")
    for item in verification_results or ["未执行自动验证"]:
        entry_lines.append(f"  - {item}")
    entry_lines.append("- 后续事项:")
    for item in next_steps or ["无"]:
        entry_lines.append(f"  - {item}")
    if snapshot_body:
        entry_lines.append("- 主线快照:")
        for line in snapshot_body.rstrip().splitlines() or [""]:
            entry_lines.append(f"  {line}")
    entry_lines.append("")
    entry_text = "\n".join(entry_lines)
    if not current.startswith("# DEVELOPMENT_LOG.md"):
        current = DEVELOPMENT_LOG_HEADER + current
    remainder = current.split("\n", 2)
    if len(remainder) >= 3:
        new_content = remainder[0] + "\n\n" + entry_text + remainder[2].lstrip("\n")
    else:
        new_content = DEVELOPMENT_LOG_HEADER + entry_text
    log_path.write_text(new_content, encoding="utf-8")
    return log_path


def parse_log_entries(path: str | Path) -> list[dict[str, Any]]:
    log_path = Path(path).expanduser().resolve()
    if not log_path.exists():
        return []
    text = log_path.read_text(encoding="utf-8")
    matches = list(ENTRY_HEADER_RE.finditer(text))
    entries: list[dict[str, Any]] = []
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        raw = text[start:end].rstrip()
        header_line = raw.splitlines()[0] if raw else ""
        timestamp = parse_log_timestamp(header_line)
        entries.append(
            {
                "path": str(log_path),
                "timestamp": timestamp.isoformat() if timestamp else None,
                "author": match.group("author").strip(),
                "raw": raw,
            }
        )
    return entries


def log_entries_since(path: str | Path, since_iso: str | None, limit: int = 5) -> list[dict[str, Any]]:
    entries = parse_log_entries(path)
    if since_iso:
        floor = datetime.fromisoformat(since_iso)
        entries = [
            entry
            for entry in entries
            if entry.get("timestamp") and datetime.fromisoformat(entry["timestamp"]) >= floor
        ]
    return entries[: max(limit, 0)] if limit >= 0 else entries
