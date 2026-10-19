"""Version profiles must be explicit, pinned and tested before claiming compatibility."""
from __future__ import annotations
import json
import os
from pathlib import Path

HOME = Path(os.environ.get("CRAFTCTL_HOME", str(Path.home() / ".minecraft-mod-orchestra"))).expanduser()
PROJECTS = HOME / "projects"
SUPPORTED_PROFILE = "fabric-1.21.1-candidate"
PROFILE = {
    "id": SUPPORTED_PROFILE,
    "status": "UNVERIFIED_BUILD",  # Pinned artifact coordinates; full build needs network + Gradle/JDK.
    "minecraft": "1.21.1",
    "loader": "fabric",
    "java_major": 21,
    "loom": "1.10.5",
    "yarn": "1.21.1+build.3",
    "fabric_loader": "0.16.14",
    "fabric_api": "0.116.16+1.21.1",
    "gradle": "8.14.3",
    "source": "Fabric Maven and official Fabric docs; not yet validated by a successful runtime test",
}

def ensure_home() -> None:
    HOME.mkdir(parents=True, exist_ok=True)
    PROJECTS.mkdir(parents=True, exist_ok=True)
    try:
        HOME.chmod(0o700)
    except OSError:
        pass

def save_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temp, path)
