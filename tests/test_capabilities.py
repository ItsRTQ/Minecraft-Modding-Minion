import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from mod_orchestra.state import Store
import mod_orchestra.workflow as workflow
from mod_orchestra.capabilities import CAPABILITIES, handoff, available_tasks

class TestCapabilities(unittest.TestCase):
    def test_task_handoff_is_bounded_and_grounded(self):
        with tempfile.TemporaryDirectory() as td, patch.object(workflow,"PROJECTS",Path(td)/"projects"):
            store=Store(Path(td)/"state.sqlite")
            workflow.new_project(store,name="Example",mod_id="example_mod",package="com.example.demo",idea="items: sun stone")
            workflow.plan_project(store,"example_mod")
            tasks=available_tasks(store,"example_mod")
            self.assertEqual(tasks[0]["role"],"interpreter")
            result=handoff(store,"example_mod","example_mod:SPEC")
            self.assertIn("items: sun stone",result)
            self.assertIn("No unapproved executable",result)
            self.assertLessEqual(len(result),5600)
            self.assertIn("world-builder",CAPABILITIES)
