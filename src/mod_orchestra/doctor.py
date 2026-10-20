"""Non-invasive first-run diagnostics. Never install or run downloaded software."""
from __future__ import annotations
import os
import platform
import re
import shutil
import subprocess
from pathlib import Path
from .config import PROFILE


def _version(command: list[str]) -> str | None:
    try:
        p = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           text=True, timeout=8, check=False)
        return p.stdout.strip().splitlines()[0][:180] if p.stdout.strip() else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def inspect() -> dict:
    java = shutil.which("java")
    java_version = _version([java, "-version"]) if java else None
    major = None
    if java_version:
        m = re.search(r'"(?:1\.)?(\d+)', java_version)
        if m:
            major = int(m.group(1))
    gradle = shutil.which("gradle")
    git = shutil.which("git")
    blockbench = shutil.which("Blockbench") or shutil.which("blockbench")
    minecraft = Path(os.environ.get("APPDATA", "~/.minecraft")).expanduser() / ".minecraft" if os.name == "nt" and not os.environ.get("APPDATA", "").endswith(".minecraft") else Path.home() / ".minecraft"
    if os.name == "nt" and os.environ.get("APPDATA"):
        minecraft = Path(os.environ["APPDATA"]) / ".minecraft"
    return {
        "os": platform.system(), "machine": platform.machine(), "python": platform.python_version(),
        "profile": PROFILE, "java": {"executable": java, "version": java_version, "major": major,
                                    "compatible": major is not None and major >= PROFILE["gradle_jdk_major"],
                                    "note": f"JDK {PROFILE['gradle_jdk_major']}+ runs Gradle/Loom; sources compile with --release {PROFILE['java_major']}"},
        "gradle": {"executable": gradle, "version": _version([gradle, "--version"]) if gradle else None},
        "git": {"executable": git, "version": _version([git, "--version"]) if git else None},
        "blockbench": {"executable": blockbench, "note": "Optional for static item/block prototypes"},
        "minecraft": {"directory": str(minecraft), "launcher_files_found": minecraft.is_dir(),
                      "note": "Not required to generate Fabric source"},
        "notes": ["No dependencies were installed or changed.", "The toolchain has not been build-verified in this environment.",
                  "Gradle's wrapper may be generated locally using a trusted Gradle installation."],
    }
