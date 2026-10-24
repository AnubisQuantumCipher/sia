"""Synthetic report-shape controls; these fixtures are not proof evidence."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location(
    "sia_proof_summary", Path(__file__).parents[1] / "check-proof-summary.py")
CHECKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKER)
REPORT = """SPARK Analysis results Total Flow Provers Justified   Unproved
Total 2 2 . . .
in unit a, 1 subprograms and packages out of 1 analyzed
  A at a.adb:1 flow analyzed (0 errors, 0 checks, 0 warnings and 0 pragma Assume statements) and proved (0 checks)
in unit b, 1 subprograms and packages out of 1 analyzed
  B at b.adb:1 flow analyzed (0 errors, 0 checks, 0 warnings and 0 pragma Assume statements) and proved (0 checks)
"""


class ProofSummary(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / "sia_assurance.gpr").write_text(
            'project P is for Source_Dirs use ("src", "tests"); end P;')
        (self.root / "src").mkdir()
        (self.root / "tests").mkdir()
        self.raw_reports = self.root / "obj" / "gnatprove"
        self.raw_reports.mkdir(parents=True)
        for name in ("a", "b"):
            (self.root / "src" / (name + ".adb")).write_text("-- fixture\n")
            self.write_raw(name, self.clean_raw())
        self.report = self.root / "report.txt"

    @staticmethod
    def clean_raw():
        return {"warn_error": [], "flow": [], "proof": [], "pragma_assume": [],
                "skip_proof": [], "skip_flow_proof": []}

    def write_raw(self, name, value):
        (self.raw_reports / (name + ".spark")).write_text(json.dumps(value))

    def check_text(self, text):
        self.report.write_text(text)
        return CHECKER.check(self.root, self.report)

    def test_matching_report(self):
        self.assertEqual(self.check_text(REPORT)["units"], ["a", "b"])

    def test_missing_unexpected_and_duplicate_units(self):
        row = "in unit b, 1 subprograms and packages out of 1 analyzed\n"
        for text in (REPORT.replace(row, ""), REPORT + row,
                     REPORT.replace("in unit b,", "in unit c,")):
            with self.subTest(text=text), self.assertRaises(ValueError):
                self.check_text(text)

    def test_incomplete_and_empty_subprogram_coverage(self):
        for row in ("0 subprograms and packages out of 1",
                    "0 subprograms and packages out of 0",
                    "1 subprograms and packages out of 2"):
            with self.subTest(row=row), self.assertRaises(ValueError):
                self.check_text(REPORT.replace(
                    "1 subprograms and packages out of 1", row))

    def test_unresolved_justified_or_ambiguous_totals(self):
        for total in ("Total 2 1 . 1 .", "Total 2 1 . . 1",
                      "Total 0 . . . .", "Total bad . . . .",
                      "Total 2 2 . . .\nTotal 2 2 . . .",
                      "Total 2 . .", "Total 2 2 . extra . .",
                      "Total 2 1 . . .", "Total 2 2 (999%) . . ."):
            with self.subTest(total=total), self.assertRaises(ValueError):
                self.check_text(REPORT.replace("Total 2 2 . . .", total))

    def test_specification_only_unit_is_required(self):
        (self.root / "src" / "c.ads").write_text("-- expression-function fixture\n")
        with self.assertRaises(ValueError):
            self.check_text(REPORT)

    def test_spec_body_pair_is_one_unit(self):
        (self.root / "src" / "a.ads").write_text("-- specification fixture\n")
        self.assertEqual(self.check_text(REPORT)["units"], ["a", "b"])

    def test_extra_source_directory_refuses(self):
        (self.root / "sia_assurance.gpr").write_text(
            'project P is for Source_Dirs use ("src", "tests", "extra"); end P;')
        with self.assertRaises(ValueError):
            self.check_text(REPORT)

    def test_oversize_report(self):
        with self.assertRaises(ValueError):
            self.check_text("x" * (CHECKER.LIMIT + 1))

    def test_nonzero_detail_diagnostics_refuse(self):
        for field in ("errors", "checks,", "warnings", "pragma Assume statements"):
            for value in ("1", "999999", "-1", "unknown"):
                with self.subTest(field=field, value=value):
                    with self.assertRaises(ValueError):
                        self.check_text(REPORT.replace("0 " + field, value + " " + field))

    def test_missing_duplicate_misbound_and_malformed_details_refuse(self):
        detail = REPORT.splitlines()[3] + "\n"
        variants = (
            REPORT.replace(detail, ""),
            REPORT.replace(detail, detail + detail),
            detail + REPORT,
            REPORT.replace("A at a.adb", "A at b.adb"),
            REPORT.replace("flow analyzed", "flow not analyzed"),
            REPORT.replace("and proved (0 checks)", "and not proved"),
            REPORT.replace("0 pragma Assume statements", ""),
        )
        for text in variants:
            with self.subTest(text=text), self.assertRaises(ValueError):
                self.check_text(text)

    def test_duplicate_name_cannot_replace_missing_subprogram(self):
        detail = REPORT.splitlines()[3] + "\n"
        text = REPORT.replace(
            "in unit a, 1 subprograms and packages out of 1 analyzed",
            "in unit a, 2 subprograms and packages out of 2 analyzed")
        with self.assertRaises(ValueError):
            self.check_text(text.replace(detail, detail + detail.replace("a.adb:1", "a.ads:2")))

    def test_raw_warning_cannot_hide_behind_clean_summary(self):
        for field in ("warn_error", "flow", "proof"):
            for severity in ("warning", "error", "fatal", "unknown", None):
                value = self.clean_raw()
                value[field] = [{"severity": severity, "suppressed": ""}]
                self.write_raw("b", value)
                with self.subTest(field=field, severity=severity):
                    with self.assertRaises(ValueError):
                        self.check_text(REPORT)

    def test_raw_informational_message_is_not_a_warning(self):
        value = self.clean_raw()
        for field in ("warn_error", "flow", "proof"):
            value[field] = [{"severity": "info", "rule": "error"}]
        value["assumptions"] = [{"claim": {"predicate": "CLAIM_AORTE"}}]
        self.write_raw("a", value)
        self.assertEqual(self.check_text(REPORT)["units"], ["a", "b"])

    def test_duplicate_key_cannot_erase_a_warning(self):
        path = self.raw_reports / "a.spark"
        for rows in (
            '"warn_error":[{"severity":"warning"}],"warn_error":[]',
            '"warn_error":[{"severity":"warning","severity":"info"}]',
        ):
            path.write_text("{" + rows + ',"flow":[],"proof":[],"pragma_assume":[],'
                            '"skip_proof":[],"skip_flow_proof":[]}')
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                self.check_text(REPORT)

    def test_missing_or_nonempty_raw_exclusions_refuse(self):
        for key in ("pragma_assume", "skip_proof", "skip_flow_proof"):
            for replacement in (None, [1], False, {}):
                value = self.clean_raw()
                value[key] = replacement
                self.write_raw("a", value)
                with self.subTest(key=key, value=replacement), self.assertRaises(ValueError):
                    self.check_text(REPORT)
            value = self.clean_raw()
            del value[key]
            self.write_raw("a", value)
            with self.assertRaises(ValueError):
                self.check_text(REPORT)

    def test_malformed_missing_and_oversize_raw_reports_refuse(self):
        path = self.raw_reports / "a.spark"
        for raw in ("{", "[]", "null", "{}",
                    "x" * (CHECKER.RAW_LIMIT + 1)):
            path.write_text(raw)
            with self.subTest(raw=raw[:64]), self.assertRaises(ValueError):
                self.check_text(REPORT)
        path.unlink()
        with self.assertRaises(FileNotFoundError):
            self.check_text(REPORT)

    def test_unknown_and_oversize_raw_diagnostics_refuse(self):
        for field in ("warn_error", "flow", "proof"):
            for rows in (None, {}, [None], [{}],
                         [{"severity": "info"}] * (CHECKER.MAX_DIAGNOSTICS + 1)):
                value = self.clean_raw()
                value[field] = rows
                self.write_raw("a", value)
                with self.subTest(field=field, rows=str(rows)[:64]):
                    with self.assertRaises(ValueError):
                        self.check_text(REPORT)
            value = self.clean_raw()
            del value[field]
            self.write_raw("a", value)
            with self.assertRaises(ValueError):
                self.check_text(REPORT)

    def test_non_json_numeric_constants_refuse(self):
        path = self.raw_reports / "a.spark"
        for token in ("NaN", "Infinity", "-Infinity"):
            raw = json.dumps(self.clean_raw())[:-1] + ',"ignored":' + token + '}'
            path.write_text(raw)
            with self.subTest(token=token), self.assertRaises(ValueError):
                self.check_text(REPORT)


if __name__ == "__main__":
    unittest.main()
