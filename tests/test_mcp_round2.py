"""Regression tests for pilot testing round 2 (docs/TESTING_LOG.md M1-M5, M8)."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mod_orchestra import workflow
from mod_orchestra.mcp import handle, TOOLS, SUPPORTED_PROTOCOLS
from mod_orchestra.state import Store



class McpProtocol(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.store = Store(base / "footprint.sqlite")
        p = patch.object(workflow, "PROJECTS", base / "projects"); p.start(); self.addCleanup(p.stop)
        (base / "projects").mkdir()
        workflow.new_project(self.store, name="M", mod_id="m_mod", package="com.x.m", idea="items: gem")

    def rpc(self, method, params=None, mid=1):
        msg = {"jsonrpc": "2.0", "id": mid, "method": method}
        if params is not None: msg["params"] = params
        return handle(self.store, msg)

    def call(self, name, args):
        return self.rpc("tools/call", {"name": name, "arguments": args})

    def test_initialize_echoes_supported_client_version(self):  # M1
        r = self.rpc("initialize", {"protocolVersion": "2025-06-18"})
        self.assertEqual(r["result"]["protocolVersion"], "2025-06-18")
        r = self.rpc("initialize", {"protocolVersion": "1999-01-01"})
        self.assertEqual(r["result"]["protocolVersion"], SUPPORTED_PROTOCOLS[0])

    def test_initialize_carries_instructions_naming_user_only_steps(self):  # M8
        text = self.rpc("initialize", {})["result"]["instructions"]
        for needle in ("approve-spec", "request-build", "decide", "NO tool"):
            self.assertIn(needle, text)

    def test_mcp_module_never_reaches_user_only_operations(self):
        import inspect, mod_orchestra.mcp as mcp
        src = inspect.getsource(mcp)
        for symbol in ("consume_approval", "decide_approval", "request_approval", "build_project", "new_project", "approve_spec"):
            self.assertNotIn(symbol, src, f"MCP must not be able to call {symbol}")

    def test_validate_before_generate_is_a_clean_state_error(self):  # M2
        r = self.call("orchestra_validate_source", {"project": "m_mod"})
        self.assertTrue(r["result"]["isError"])
        text = r["result"]["content"][0]["text"]
        self.assertIn("StateError", text)
        self.assertNotIn("FileNotFoundError", text)
        self.assertNotIn(self.tmp.name, text, "must not leak filesystem paths")

    def test_argument_types_are_enforced(self):  # M3
        r = self.call("orchestra_project_status", {"project": 123})
        self.assertTrue(r["result"]["isError"])
        self.assertIn("must be a string", r["result"]["content"][0]["text"])

    def test_knowledge_search_returns_relative_paths(self):  # M5
        r = self.call("orchestra_knowledge_search", {"query": "fabric profile"})
        hits = __import__("json").loads(r["result"]["content"][0]["text"])
        self.assertTrue(hits)
        for hit in hits:
            self.assertRegex(hit["path"], r"^(repo|home):")
            self.assertFalse(Path(hit["path"].split(":", 1)[1]).is_absolute())

    def test_notifications_get_no_reply(self):
        self.assertIsNone(handle(self.store, {"jsonrpc": "2.0", "method": "notifications/initialized"}))


if __name__ == "__main__":
    unittest.main()
