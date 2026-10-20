"""Deterministic bounded diagnostics for Gradle and future Minecraft logs.

Diagnostic suggestions are hypotheses. A repair is only verified after rerunning tests.
"""
from __future__ import annotations
import re
from pathlib import Path
from .state import Store
from .build import tail_log, log_path

RULES = [
    ("JAVA_COMPILE", re.compile(r"(?:error: cannot find symbol|error: incompatible types|Compilation failed)", re.I), "Inspect pinned mappings/API signatures and compiler file:line before edits."),
    ("WRAPPER_DOWNLOAD", re.compile(r"(?:Downloading https://services\.gradle\.org.*\n(?:.*\n){0,3}?.*(?:UnknownHostException|failed|SocketTimeoutException|Verification of Gradle distribution failed|checksum))", re.I), "The Gradle wrapper could not fetch or verify the distribution: check network/proxy access to services.gradle.org, then retry; a checksum mismatch means the download was corrupted or tampered."),
    ("GRADLE_DEPENDENCY", re.compile(r"(?:Could not resolve|Could not find|Plugin .* was not found|No matching variant)", re.I), "Verify Loom plugin, Fabric Maven repository, dependency coordinates, Java and Gradle versions."),
    ("JAVA_TOOLCHAIN", re.compile(r"(?:Unsupported class file major version|invalid source release|No matching toolchains found)", re.I), "Compare Java major with locked Minecraft/toolchain profile."),
    ("MIXIN", re.compile(r"(?:MixinApplyError|InjectionError|MixinTransformerError)", re.I), "Inspect Mixin target and loader/mapper compatibility."),
    ("REGISTRY", re.compile(r"(?:Duplicate registration|Registry entry not found|Missing registry)", re.I), "Compare registry identifier, registration order and dynamic registry bootstrap."),
    ("RESOURCE", re.compile(r"(?:Unable to load model|Missing texture|FileNotFoundException.*\.json)", re.I), "Check asset model/texture namespaces and paths."),
    ("GECKOLIB", re.compile(r"(?:GeckoLib.*(?:error|exception)|Unknown bone|Missing animation)", re.I), "Validate exported bone/keyframe names, model paths and GeckoLib controller."),
    ("CRASH", re.compile(r"(?:Exception in thread|Caused by:|---- Minecraft Crash Report ----)", re.I), "Inspect the deepest causal stack and last project changes; do not guess at fixes."),
]


def diagnose(text: str, *, max_lines: int = 250) -> dict:
    # Never dump raw unlimited logs into a provider context.
    bounded = "\n".join(text.splitlines()[-max(1, min(max_lines, 500)):])[-32000:]
    findings = []
    for kind, pattern, guidance in RULES:
        match = pattern.search(bounded)
        if match:
            findings.append({"kind": kind, "symptom": match.group(0)[:140], "guidance": guidance, "confidence": "pattern_match_only"})
    return {"classifications": findings, "lines_reviewed": len(bounded.splitlines()),
            "raw_log_excerpt": bounded[-2500:], "status": "UNCLASSIFIED" if not findings else "CLASSIFIED_UNVERIFIED",
            "note": "Heuristic diagnostics; no fix or gameplay result is asserted."}


def project_diagnose(store: Store, pid: str) -> dict:
    root = Path(store.project(pid)["root"])
    if not log_path(root).is_file():
        return {"classifications": [], "lines_reviewed": 0, "raw_log_excerpt": "", "status": "NO_LOG",
                "note": "No build log exists yet; run an approved build first."}
    return diagnose(tail_log(store, pid, 250))
