"""v1 criterion 1 runner: ten prompts through the real interpreter, scored against expectations."""
from __future__ import annotations
import json
import time
from pathlib import Path

from .dispatch import dispatch
from .provider import AgentProvider
from .state import Store
from . import workflow

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "tests" / "v1" / "prompts"


def score(expect: dict, spec: dict, handoff: dict, questions: list[str]) -> list[str]:
    fails = []
    items = [f for f in spec.get("features", []) if f["kind"] == "item"]
    blocks = [f for f in spec.get("features", []) if f["kind"] == "block"]
    if len(items) < expect.get("min_items", 0): fails.append(f"items {len(items)} < {expect['min_items']}")
    if len(blocks) < expect.get("min_blocks", 0): fails.append(f"blocks {len(blocks)} < {expect['min_blocks']}")
    if len(spec.get("recipes", [])) < expect.get("recipes_min", 0): fails.append(f"recipes {len(spec.get('recipes', []))} < {expect['recipes_min']}")
    if len(spec.get("drops", [])) < expect.get("drops_min", 0): fails.append(f"drops {len(spec.get('drops', []))} < {expect['drops_min']}")
    if expect.get("tab") and not spec.get("tab"): fails.append("no tab")
    if len(questions) > expect.get("max_questions", 3): fails.append(f"questions {len(questions)} > {expect['max_questions']}")
    if expect.get("vanilla_ingredient"):
        blob = json.dumps(spec.get("recipes", []))
        if expect["vanilla_ingredient"] not in blob: fails.append(f"missing ingredient {expect['vanilla_ingredient']}")
    if expect.get("unknown_mentions"):
        if expect["unknown_mentions"] not in json.dumps(handoff.get("unknowns", []) + questions).lower():
            fails.append(f"'{expect['unknown_mentions']}' not surfaced in unknowns/questions")
        if expect["unknown_mentions"] in json.dumps([f["identifier"] for f in spec.get("features", []) if f["kind"] == "block"]):
            pass  # a dragon block is acceptable; a dragon "mob" cannot exist as a feature anyway
    return fails


def run_suite(store: Store, *, provider: AgentProvider | None = None, prompts_dir: Path = PROMPTS_DIR, limit: int | None = None) -> dict:
    files = sorted(prompts_dir.glob("*.json"))[: (limit or None)]
    results, cost = [], 0.0
    stamp = time.strftime("%Y%m%d-%H%M%S")
    for f in files:
        case = json.loads(f.read_text(encoding="utf8"))
        pid = f"v1q1_{case['name'][:12].replace('-', '_')}_{stamp[-6:]}"
        workflow.new_project(store, name=f"Suite {case['name']}", mod_id=pid, package=f"com.suite.p{case['name'].split('_')[0]}", idea=case["idea"])
        out = dispatch(store, pid, task_id=f"{pid}:SPEC", provider=provider)
        spec = store.project(pid)["spec"]
        questions = spec.get("questions", [])
        fails = score(case["expect"], spec, out.get("handoff") or {}, questions) if out["task_state"] == "WAITING_USER" else [f"run {out['task_state']}: {out.get('error')}"]
        cost += float(out.get("cost_usd") or 0)
        results.append({"prompt": case["name"], "project": pid, "pass": not fails, "fails": fails, "questions": questions,
                        "features": [f"{x['kind']}:{x['identifier']}" for x in spec.get("features", [])], "recipes": [r["id"] for r in spec.get("recipes", [])],
                        "drops": len(spec.get("drops", [])), "tab": spec.get("tab"), "cost_usd": out.get("cost_usd"), "duration_s": out.get("duration_s")})
    summary = {"date": stamp, "passed": sum(r["pass"] for r in results), "total": len(results), "total_cost_usd": round(cost, 4), "results": results}
    out_dir = prompts_dir.parent / "results"; out_dir.mkdir(exist_ok=True)
    (out_dir / f"{stamp}.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf8")
    summary["written"] = str(out_dir / f"{stamp}.json")
    return summary
