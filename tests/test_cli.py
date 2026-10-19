from __future__ import annotations
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class TestCLI(unittest.TestCase):
    def test_command_line_end_to_end(self):
        with tempfile.TemporaryDirectory() as temp:
            env = os.environ.copy()
            env["CRAFTCTL_HOME"] = temp
            env["PYTHONPATH"] = str(ROOT / "src")
            def run(*args):
                p = subprocess.run([sys.executable, "-m", "mod_orchestra.cli", *args], cwd=ROOT,
                                   env=env, capture_output=True, text=True)
                self.assertEqual(p.returncode, 0, p.stderr)
                return json.loads(p.stdout)
            self.assertEqual(run("doctor")["profile"]["minecraft"], "1.21.1")
            run("new", "--name", "Test", "--id", "cli_test", "--package", "com.example.cli", "--idea", "items: sapphire")
            run("plan", "cli_test")
            run("approve-spec", "cli_test")
            gen = run("generate", "cli_test")
            self.assertEqual(gen["static_validation"]["status"], "PASS")
            self.assertEqual(run("status", "cli_test")["status"], "SOURCE_GENERATED_UNVERIFIED")
            self.assertEqual(run("validate", "cli_test")["status"], "PASS")

if __name__ == "__main__":
    unittest.main()
