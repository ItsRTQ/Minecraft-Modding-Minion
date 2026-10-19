import unittest
from mod_orchestra.kb import search

class TestKB(unittest.TestCase):
    def test_retrieval_finds_source_note(self):
        entries=search("fabric loom profile",limit=5)
        self.assertTrue(entries)
        self.assertTrue(any("fabric" in x["path"] for x in entries))
    def test_empty_query_rejected(self):
        with self.assertRaises(ValueError):
            search("  ")
