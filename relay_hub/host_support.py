from __future__ import annotations

import os
import signal
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


WINDOWS = "windows"
MACOS = "macos"
LINUX = "linux"
DEFAULT_WINDOWS_TASK_NAME = "RelayHub Web"
MACOS_TEMP_PREFIXES = (
    Path("/private/tmp"),
    Path("/tmp"),
    Path("/var/folders"),
    Path("/private/var/folders"),
)


def current_platform() -> str:
    if sys.platform == "darwin":
        return MACOS
    if os.name == "nt":
        return WINDOWS
    return LINUX


def default_install_root() -> Path:
    platform_name = current_platform()
    if platform_name == WINDOWS:
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            return (Path(local_app_data) / "RelayHub").resolve()
        return (Path.home() / "AppData" / "Local" / "RelayHub").resolve()
    if platform_name == MACOS:
        return (Path.home() / "Library" / "Application Support" / "RelayHub").resolve()
    xdg_data_home = os.environ.get("XDG_DATA_HOME")
    if xdg_data_home:
        return (Path(xdg_data_home) / "RelayHub").expanduser().resolve()
    return (Path.home() / ".local" / "share" / "RelayHub").resolve()


def default_runtime_root() -> Path:
    return default_install_root() / "runtime"


def default_app_root() -> Path:
    return default_install_root() / "app"


def default_repo_runtime_root(project_root: Path) -> Path:
    project_root = project_root.resolve()
    if project_root.name == "app":
        return (project_root.parent / "runtime").resolve()
    installed_root = default_runtime_root()
    if installed_root.exists():
        return installed_root
    return (project_root / "runtime").resolve()


def default_openclaw_workspace() -> Path:
    return (Path.home() / ".openclaw" / "workspace").resolve()


def default_openclaw_logs_dir() -> Path:
    return (Path.home() / ".openclaw" / "logs").resolve()


def default_codex_home() -> Path:
    return (Path.home() / ".codex").resolve()


def default_windows_startup_dir() -> Path:
    app_data = os.environ.get("APPDATA")
    if app_data:
        return (Path(app_data) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup").resolve()
    return (Path.home() / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup").resolve()


def default_service_manager() -> str:
    platform_name = current_platform()
    if platform_name == MACOS:
        return "launchd"
    if platform_name == WINDOWS:
        return "windows-startup"
    return "manual"


def repo_root_forbidden_prefixes() -> tuple[Path, ...]:
    prefixes: list[Path] = []
    temp_root = Path(tempfile.gettempdir()).resolve()
    prefixes.append(temp_root)
    if current_platform() == MACOS:
        prefixes.extend(MACOS_TEMP_PREFIXES)
    deduped: list[Path] = []
    seen: set[str] = set()
    for item in prefixes:
        key = str(item)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return tuple(deduped)


def background_popen_kwargs() -> dict[str, Any]:
    if current_platform() != WINDOWS:
        return {"start_new_session": True}
    creationflags = 0
    for flag_name in ("CREATE_NEW_PROCESS_GROUP", "CREATE_NO_WINDOW"):
        creationflags |= int(getattr(subprocess, flag_name, 0))
    return {"creationflags": creationflags}


def terminate_process(pid: int, *, force: bool) -> None:
    if current_platform() == WINDOWS:
        cmd = ["taskkill", "/PID", str(pid), "/T"]
        if force:
            cmd.append("/F")
        try:
            subprocess.run(cmd, capture_output=True, text=True)  # noqa: S603
        except OSError:
            if force:
                os.kill(pid, signal.SIGTERM)
        return
    os.kill(pid, signal.SIGKILL if force else signal.SIGTERM)
