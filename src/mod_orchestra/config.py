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
    "status": "UNVERIFIED_BUILD",  # Generator output not yet compiled; see template_evidence for what IS verified.
    "minecraft": "1.21.1",
    "loader": "fabric",
    "java_major": 21,          # compile target (options.release)
    "gradle_jdk_major": 25,    # JDK required to RUN Gradle + Loom 1.18 (official CI uses 25)
    "mappings": "mojang",      # loom.officialMojangMappings(); Yarn dropped to match upstream template
    "loom_plugin": "net.fabricmc.fabric-loom-remap",  # plugin id for obfuscated MC (<26.1)
    "loom": "1.18-SNAPSHOT",
    "fabric_loader": "0.19.5",
    "fabric_api": "0.116.17+1.21.1",
    "gradle": "9.7.1",
    "source": "FabricMC/fabric-example-mod branch 1.21.1 @ 684b581 (2026-09-26)",
    "template_evidence": "Upstream template compiled locally on Windows/JDK 25 (2026-10-19); generated output not yet compiled",
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
