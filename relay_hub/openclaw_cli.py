from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any


WINDOWS_BATCH_SUFFIXES = {".cmd", ".bat"}


def openclaw_cli_path() -> Path | None:
    for candidate in ("openclaw", "openclaw.cmd", "openclaw.bat", "openclaw.exe"):
        resolved = shutil.which(candidate)
        if resolved:
            return Path(resolved).resolve()
    return None


def openclaw_command_prefix() -> list[str]:
    cli_path = openclaw_cli_path()
    if cli_path is None:
        return ["openclaw"]
    if os.name == "nt" and cli_path.suffix.lower() in WINDOWS_BATCH_SUFFIXES:
        comspec = os.environ.get("COMSPEC") or shutil.which("cmd.exe") or "cmd.exe"
        return [comspec, "/d", "/c", str(cli_path)]
    return [str(cli_path)]


def run_openclaw_command(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
    return subprocess.run([*openclaw_command_prefix(), *args], **kwargs)  # noqa: S603
