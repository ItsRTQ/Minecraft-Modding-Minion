"""Simple version-aware Markdown knowledge search (no cloud or embeddings)."""
from __future__ import annotations
import re
from pathlib import Path
from .config import HOME

REPO_KB = Path(__file__).resolve().parents[2] / "knowledge"
TOKENS = re.compile(r"[a-z0-9_+.\-]{2,}", re.I)


def search(query: str, profile: str | None = None, *, limit: int = 8) -> list[dict]:
    if not query.strip() or len(query) > 300:
        raise ValueError("Provide a short search query (1-300 characters)")
    query_terms = {t.lower() for t in TOKENS.findall(query)}
    results = []
    for root in (REPO_KB, HOME / "knowledge"):
        if not root.is_dir():
            continue
        for path in root.rglob("*.md"):
            # Never follow injected symlink files into sensitive locations.
            if path.is_symlink():
                continue
            try:
                if path.stat().st_size > 128 * 1024:
                    continue
                contents = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if profile and ("minecraft:" in contents[:1000]) and not (
                profile in contents[:1500] or profile.removeprefix("fabric-").split("-")[0] in contents[:1500]):
                continue
            words = {t.lower() for t in TOKENS.findall(contents[:10000] + " " + path.name)}
            match = query_terms.intersection(words)
            if not match:
                continue
            score = len(match) * 10 + sum(contents.lower().count(t) for t in query_terms)
            source = "repo" if root == REPO_KB else "home"
            results.append({"path": f"{source}:{path.relative_to(root).as_posix()}", "title": path.stem, "score": score,
                            "excerpt": " ".join(contents[:750].split())[:500]})
    return sorted(results, key=lambda x: (-x["score"], x["path"]))[:max(1, min(30, limit))]
