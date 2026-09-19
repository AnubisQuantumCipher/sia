"""Pinned Bun JUnit selection is distinct from unselected skipped cases."""

from pathlib import Path
import tempfile
import unittest

from tests import mutation_raw_vector_adapter as harness


class SelectedBunReport(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "report.xml"
        self.spec = harness.MUTATIONS[0]

    def _case(self, *, name=None, suite=None, file=None, assertions="5", child=""):
        return ('<testcase name="' + (name or self.spec.test)
                + '" classname="' + (suite or self.spec.suite)
                + '" file="' + (file or self.spec.test_path)
                + '" assertions="' + assertions + '">' + child + '</testcase>')

    def _read(self, cases):
        self.path.write_text('<testsuites><testsuite>' + cases
                             + '</testsuite></testsuites>')
        return harness._junit(self.path, self.spec)

    def test_selected_green_accepts_only_strict_unselected_skips(self):
        report = self._read(self._case()
                            + self._case(name="unselected", assertions="0", child="<skipped />"))
        self.assertFalse(report["assertion_failure"])
        self.assertEqual(report["test"]["name"], self.spec.test)

    def test_selected_skip_is_never_evidence(self):
        with self.assertRaises(RuntimeError):
            self._read(self._case(assertions="0", child="<skipped />"))

    def test_extra_executed_case_refuses(self):
        with self.assertRaises(RuntimeError):
            self._read(self._case() + self._case(name="unselected"))

    def test_duplicate_selection_refuses(self):
        with self.assertRaises(RuntimeError):
            self._read(self._case() + self._case())

    def test_wrong_source_or_suite_refuses(self):
        for overrides in ({"file": "different.test.ts"}, {"suite": "different suite"}):
            with self.subTest(overrides=overrides), self.assertRaises(RuntimeError):
                self._read(self._case(**overrides))

    def test_unselected_skip_must_have_no_execution_evidence(self):
        for child, assertions in (("<skipped /><failure>expect(x).toBe(y)</failure>", "0"),
                                  ("<skipped />", "5"), ("<skipped /><error />", "0")):
            with self.subTest(child=child, assertions=assertions), self.assertRaises(RuntimeError):
                self._read(self._case() + self._case(name="unselected", child=child,
                                                    assertions=assertions))

    def test_no_assertions_cannot_establish_green_control(self):
        with self.assertRaises(RuntimeError):
            self._read(self._case(assertions="0"))

    def test_assertion_failure_is_classified_but_runtime_error_is_not(self):
        result = self._read(self._case(child="<failure>error: expect(x).toBe(y)</failure>"))
        self.assertTrue(result["assertion_failure"])
        for text in ("TypeError: bad", "Cannot find module", "error: Expected a value"):
            with self.subTest(text=text):
                result = self._read(self._case(child="<failure>" + text + "</failure>"))
                self.assertFalse(result["assertion_failure"])


if __name__ == "__main__":
    unittest.main()
