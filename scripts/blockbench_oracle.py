"""CI oracle (Linux runner only, never the owner's machine): build a six-bone critter with the vendored
blockbench-mcp-safe server, then run jasonjgardner/blockbench-mcp-plugin's validators on the .bbmodel and
compare its geometry export with ours bone-by-bone. Exit non-zero on any disagreement."""
import json, os, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAFE = ROOT / "tools/blockbench-mcp-safe/src/server.mjs"
UPSTREAM = "github:jasonjgardner/blockbench-mcp-plugin"  # audited at v1.10.1 / 16d3631c


class Client:
    def __init__(self, cmd):
        self.p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True); self.i = 0
        self.rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "oracle", "version": "0"}})
        self.p.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n"); self.p.stdin.flush()
    def rpc(self, method, params=None):
        self.i += 1; mid = self.i
        self.p.stdin.write(json.dumps({"jsonrpc": "2.0", "id": mid, "method": method, "params": params or {}}) + "\n"); self.p.stdin.flush()
        while True:
            line = self.p.stdout.readline()
            if not line: raise SystemExit(f"{method}: server closed stdout; stderr: {self.p.stderr.read()[-800:]}")
            try: r = json.loads(line)
            except Exception: continue
            if r.get("id") == mid: return r
    def call(self, name, args):
        res = self.rpc("tools/call", {"name": name, "arguments": args}).get("result", {})
        txt = "".join(c.get("text", "") for c in res.get("content", []) if c.get("type") == "text")
        if res.get("isError"): raise SystemExit(f"{name} failed: {txt[:400]}")
        try: return json.loads(txt)
        except Exception: return {"raw": txt}
    def close(self):
        self.p.stdin.close(); self.p.wait(timeout=30)


def main():
    work = Path(tempfile.mkdtemp(prefix="bb-oracle-"))
    safe = Client(["node", str(SAFE), "--root", str(work), "--allow-write"])
    rev = safe.call("bbmodel_geckolib_create", {"file": "critter.bbmodel", "name": "Critter", "identifier": "critter", "modid": "c_mod", "model_type": "Entity", "texture_width": 64, "texture_height": 32})["revision"]
    def edit(ops):
        nonlocal rev
        out = safe.call("bbmodel_edit", {"file": "critter.bbmodel", "expected_revision": rev, "operations": ops}); rev = out["revision"]; return out
    body = edit([{"op": "add_group", "name": "body", "origin": [0, 6, 0]}])["changes"][0]["uuid"]
    out = edit([{"op": "add_cube", "name": "body_cube", "group_uuid": body, "from": [-4, 6, -6], "to": [4, 12, 6], "uv_offset": [0, 0]},
                {"op": "add_group", "name": "head", "parent_group_uuid": body, "origin": [0, 12, -6]}])
    head = out["changes"][1]["uuid"]; edit([{"op": "add_cube", "name": "head_cube", "group_uuid": head, "from": [-3, 12, -10], "to": [3, 16, -6], "uv_offset": [0, 18]}])
    for i, (x, z) in enumerate([(-3, -4), (3, -4), (-3, 4), (3, 4)]):
        g = edit([{"op": "add_group", "name": f"leg{i}", "parent_group_uuid": body, "origin": [x, 6, z]}])["changes"][0]["uuid"]
        edit([{"op": "add_cube", "name": f"leg{i}_cube", "group_uuid": g, "from": [x - 1, 0, z - 1], "to": [x + 1, 6, z + 1], "uv_offset": [24 + i * 8, 0]}])
    walk = [{"bone": b, "channel": "rotation", "keyframes": [{"time": 0, "value": [20 * s, 0, 0]}, {"time": 0.5, "value": [-20 * s, 0, 0]}, {"time": 1, "value": [20 * s, 0, 0]}]} for b, s in (("leg0", 1), ("leg3", 1), ("leg1", -1), ("leg2", -1))]
    rev = safe.call("bbmodel_geckolib_upsert_animation", {"file": "critter.bbmodel", "expected_revision": rev, "name": "animation.critter.walk", "length": 1, "loop": "loop", "channels": walk})["revision"]
    rev = safe.call("bbmodel_geckolib_upsert_animation", {"file": "critter.bbmodel", "expected_revision": rev, "name": "animation.critter.idle", "length": 2, "loop": "loop", "channels": [{"bone": "head", "channel": "rotation", "keyframes": [{"time": 0, "value": [0, 0, 0]}, {"time": 1, "value": [3, 0, 0]}, {"time": 2, "value": [0, 0, 0]}]}]})["revision"]
    v = safe.call("bbmodel_geckolib_validate", {"file": "critter.bbmodel", "require_idle_walk": True})
    assert v["valid"], v
    safe.call("bbmodel_geckolib_export_geometry", {"file": "critter.bbmodel", "output_file": "critter.geo.json"})
    safe.call("bbmodel_geckolib_export_animations", {"file": "critter.bbmodel", "output_file": "critter.animation.json"})
    safe.close()
    print("safe: validate OK, exports written")

    up = Client(["npx", "-y", UPSTREAM, "--root", str(work)])
    a = up.call("bbmodel_validate", {"file": "critter.bbmodel"}); b = up.call("bbmodel_validate_animations", {"file": "critter.bbmodel"})
    assert a["summary"]["passed"] and a["summary"]["errors"] == 0, a["summary"]
    assert b["summary"]["passed"] and b["summary"]["errors"] == 0, b["summary"]
    up.call("bbmodel_export_bedrock_geometry", {"file": "critter.bbmodel", "output": "critter_upstream.geo.json", "identifier": "geometry.critter"})
    up.close()
    print("upstream: validate OK, validate_animations OK")

    norm = lambda g: [(x["name"], x.get("parent"), x.get("pivot"), [(c["origin"], c["size"], c["uv"]) for c in x.get("cubes", [])]) for x in g["bones"]]
    ours = json.loads((work / "critter.geo.json").read_text())["minecraft:geometry"][0]
    theirs = json.loads((work / "critter_upstream.geo.json").read_text())["minecraft:geometry"][0]
    if norm(ours) != norm(theirs):
        print("GEO MISMATCH"); print(json.dumps(norm(ours))); print(json.dumps(norm(theirs))); sys.exit(1)
    print("geo export identical to upstream (6 bones) — oracle PASS")


if __name__ == "__main__":
    main()
