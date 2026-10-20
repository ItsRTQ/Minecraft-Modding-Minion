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
    "status": "BUILD_VERIFIED",  # Generator output compiled, client+server booted, content verified 2026-10-20; see evidence.
    "minecraft": "1.21.1",
    "loader": "fabric",
    "java_major": 21,          # compile target (options.release)
    "gradle_jdk_major": 25,    # JDK required to RUN Gradle + Loom 1.18 (official CI uses 25)
    "mappings": "mojang",      # loom.officialMojangMappings(); Yarn dropped to match upstream template
    "loom_plugin": "net.fabricmc.fabric-loom-remap",  # plugin id for obfuscated MC (<26.1)
    "loom": "1.18.4",  # pinned: 1.18-SNAPSHOT resolved to 1.18.4 in the verified build
    "fabric_loader": "0.19.5",
    "fabric_api": "0.116.17+1.21.1",
    "gradle": "9.7.1",
    "source": "FabricMC/fabric-example-mod branch 1.21.1 @ 684b581 (2026-09-26)",
    "evidence": "2026-10-20: examples/crystal_example built (JAR sha256 6de89b8cebde3bac596c504489d07fad9c6c858eaffa97e99414f24cf4b857f1), "
                "client loaded 'crystal_example 1.0.0', dedicated server booted, items/block placeable and block drops in survival. "
                "Windows, JDK 25, Loom 1.18.4, Gradle 9.7.1. See examples/crystal_example/EVIDENCE.md.",
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
