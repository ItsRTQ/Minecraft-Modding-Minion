"""SEC-002: the only place the controller spawns an external process.

- Minimal, explicit environment (no os.environ passthrough).
- Own process group/session so a timeout kills Gradle *and* its children (daemons, javac).
- Output goes to a file, never into memory unbounded.
- Returns a record (pid, duration, exit code, killed) for the Footprint.
"""
from __future__ import annotations
import os
import signal
import subprocess
import time
from pathlib import Path

DEFAULT_TIMEOUT = int(os.environ.get("CRAFTCTL_BUILD_TIMEOUT", "1800"))  # first build downloads Gradle + Minecraft

# Environment variables forwarded to child processes. Everything else is dropped.
ENV_ALLOWLIST_COMMON = ("PATH", "JAVA_HOME", "GRADLE_USER_HOME", "GRADLE_OPTS", "LANG", "LC_ALL", "TZ",
                        "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "no_proxy")
ENV_ALLOWLIST_POSIX = ("HOME", "USER", "TMPDIR", "SHELL", "DISPLAY")
ENV_ALLOWLIST_WINDOWS = ("USERPROFILE", "HOMEDRIVE", "HOMEPATH", "APPDATA", "LOCALAPPDATA", "TEMP", "TMP",
                         "SystemRoot", "SystemDrive", "ComSpec", "PATHEXT", "ProgramFiles", "ProgramData",
                         "USERNAME", "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE")


def controlled_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    names = ENV_ALLOWLIST_COMMON + (ENV_ALLOWLIST_WINDOWS if os.name == "nt" else ENV_ALLOWLIST_POSIX)
    env = {k: os.environ[k] for k in names if k in os.environ}
    env["JAVA_TOOL_OPTIONS"] = (os.environ.get("JAVA_TOOL_OPTIONS", "") + " -Dfile.encoding=UTF-8").strip()
    if extra:
        env.update(extra)
    return env


def _kill_tree(proc: subprocess.Popen) -> None:
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True, check=False)
        else:
            os.killpg(proc.pid, signal.SIGKILL)
    except Exception:
        pass
    try:
        proc.kill()
    except Exception:
        pass


def run_logged(cmd: list[str], *, cwd: Path, log: Path, timeout: int = DEFAULT_TIMEOUT,
               env: dict[str, str] | None = None) -> dict:
    """Run cmd with stdout+stderr appended to `log`. Never raises on process failure."""
    env = env or controlled_env()
    popen_kwargs: dict = {}
    if os.name == "nt":
        popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        popen_kwargs["start_new_session"] = True
    log.parent.mkdir(parents=True, exist_ok=True)
    started = time.time()
    killed = False
    with log.open("wb") as f:
        f.write(f"$ {' '.join(cmd)}\n".encode())
        proc = subprocess.Popen(cmd, cwd=str(cwd), stdout=f, stderr=subprocess.STDOUT, env=env, **popen_kwargs)
        try:
            code = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            _kill_tree(proc)
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                pass
            killed = True
            code = 124
            f.write(f"\n[craftctl] timeout after {timeout}s; process tree killed\n".encode())
    return {"pid": proc.pid, "exit_code": code, "killed": killed, "timeout_s": timeout,
            "duration_s": round(time.time() - started, 1), "cmd": cmd}
