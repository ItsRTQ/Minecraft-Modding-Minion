import unittest
from mod_orchestra.diagnostics import diagnose

class TestDiagnostics(unittest.TestCase):
    def test_classification_is_honest(self):
        d=diagnose("error: cannot find symbol\n Caused by: java.lang.NoSuchMethodError")
        kinds={x["kind"] for x in d["classifications"]}
        self.assertIn("JAVA_COMPILE",kinds)
        self.assertIn("CRASH",kinds)
        self.assertEqual(d["status"],"CLASSIFIED_UNVERIFIED")
    def test_truncation_and_empty_logs(self):
        self.assertLessEqual(diagnose("X\n"*10000)["lines_reviewed"],250)
        self.assertEqual(diagnose("")["status"],"UNCLASSIFIED")
