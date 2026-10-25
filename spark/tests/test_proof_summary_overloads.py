"""Synthetic checker controls, not evidence of a GNATprove execution."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPARK = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location(
    "sia_proof_overloads", SPARK / "check-proof-summary.py")
CHECKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKER)
UNIT = "sia_continuity_record_wire"
FILE = UNIT + ".ads"
# Independently enumerated declarations from the reviewed specification.
DECLARATIONS = [("", 5), ("Word_Value", 21), ("Kind_Value", 32),
                ("Origin_Value", 41), ("Role_Value", 47), ("Phase_Value", 53),
                ("Valid", 59), ("Valid", 66), ("Valid", 71),
                ("Decoded_As", 76), ("Decoded_As", 88), ("Decoded_As", 99),
                ("Decode", 108), ("Decode", 115), ("Decode", 123)]


def report(declarations):
    count = len(declarations)
    rows = ["SPARK Analysis results Total Flow Provers Justified Unproved",
            "Total 2 2 . . .",
            f"in unit {UNIT}, {count} subprograms and packages out of {count} analyzed"]
    for name, line in declarations:
        qualified = UNIT + ("." + name if name else "")
        rows.append(f"  {qualified} at {FILE}:{line} flow analyzed "
                    "(0 errors, 0 checks, 0 warnings and 0 pragma Assume statements)"
                    " and proved (0 checks)")
    return "\n".join(rows) + "\n"


class OverloadPolicy(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        for directory in ("src", "tests", "obj/gnatprove"):
            (self.root / directory).mkdir(parents=True)
        (self.root / "sia_assurance.gpr").write_text(
            'project P is for Source_Dirs use ("src", "tests"); end P;')
        self.source = self.root / "src" / FILE
        self.source.write_bytes((SPARK / "src" / FILE).read_bytes())
        raw = {name: [] for name in ("warn_error", "flow", "proof",
                                    "pragma_assume", "skip_proof", "skip_flow_proof")}
        (self.root / "obj/gnatprove" / (UNIT + ".spark")).write_text(json.dumps(raw))
        self.policy = json.loads((SPARK / "proof-overloads.json").read_text())
        self.policy_path = self.root / "policy.json"
        self.report_path = self.root / "report.txt"

    def check(self, text):
        self.report_path.write_text(text)
        return CHECKER.check(self.root, self.report_path)

    def load(self, value):
        self.policy_path.write_text(json.dumps(value))
        return CHECKER.source_overloads(self.root, self.policy_path)

    def test_complete_overloads_pass_and_unregistered_mode_refuses(self):
        text = report(DECLARATIONS)
        self.assertEqual(self.check(text)["units"], [UNIT])
        with self.assertRaises(ValueError):
            CHECKER.check_details(text.splitlines())

    def test_every_registered_location_is_required(self):
        for index in range(6, len(DECLARATIONS)):
            with self.subTest(index=index), self.assertRaises(ValueError):
                self.check(report(DECLARATIONS[:index] + DECLARATIONS[index + 1:]))

    def test_entire_group_cannot_be_omitted(self):
        for group in ("Valid", "Decoded_As", "Decode"):
            remaining = [row for row in DECLARATIONS if row[0] != group]
            with self.subTest(group=group), self.assertRaises(ValueError):
                self.check(report(remaining))

    def test_each_same_count_duplicate_or_substitution_refuses(self):
        for index in range(6, len(DECLARATIONS)):
            name, line = DECLARATIONS[index]
            for replacement in ((name, line + 1), (name, 1),
                                DECLARATIONS[6 if index != 6 else 7],
                                ("Unregistered", line)):
                changed = DECLARATIONS.copy()
                changed[index] = replacement
                with self.subTest(index=index, replacement=replacement):
                    with self.assertRaises(ValueError):
                        self.check(report(changed))

    def test_body_wrong_unit_filename_and_case_duplicates_refuse(self):
        text = report(DECLARATIONS)
        for original, replacement in (
                (FILE + ":59", UNIT + ".adb:59"),
                (FILE + ":59", "other.ads:59"),
                ("in unit " + UNIT, "in unit other"),
                (".Valid at " + FILE + ":66", ".VALID at " + FILE + ":59")):
            with self.subTest(replacement=replacement), self.assertRaises(ValueError):
                self.check(text.replace(original, replacement))

    def test_changed_missing_ambiguous_and_symlink_source_refuse(self):
        original = self.source.read_bytes()
        self.source.write_bytes(original + b"\n")
        with self.assertRaises(ValueError):
            self.check(report(DECLARATIONS))
        self.source.unlink()
        with self.assertRaises(ValueError):
            self.check(report(DECLARATIONS))
        self.source.write_bytes(original)
        alternate = self.root / "tests" / FILE
        alternate.write_bytes(original)
        with self.assertRaises(ValueError):
            self.check(report(DECLARATIONS))
        alternate.unlink()
        self.source.unlink()
        self.source.symlink_to(SPARK / "src" / FILE)
        with self.assertRaises(ValueError):
            self.check(report(DECLARATIONS))

    def test_missing_bundled_policy_does_not_disable_validation(self):
        with patch.object(CHECKER, "OVERLOAD_POLICY", self.root / "absent"):
            with self.assertRaises(FileNotFoundError):
                self.check(report(DECLARATIONS))

    def test_both_reviewed_sources_bind(self):
        actual = CHECKER.source_overloads(SPARK)
        self.assertEqual(set(actual), {
            unit + "." + name
            for unit in (UNIT, "sia_continuity_observation_wire")
            for name in ("valid", "decoded_as", "decode")})
        for filename, entry in self.policy["sources"].items():
            self.assertEqual(hashlib.sha256((SPARK / "src" / filename).read_bytes()).hexdigest(),
                             entry["sha256"])
            for name, locations in entry["overloads"].items():
                self.assertEqual(actual[name], {(filename, line) for line in locations})

    def test_unrelated_source_root_gets_no_exceptions(self):
        self.source.unlink()
        self.assertEqual(self.load(self.policy), {})

    def test_policy_schema_and_inventory_bounds(self):
        for value in (None, [], {}, {**self.policy, "extra": 1},
                      {**self.policy, "schema": True}, {**self.policy, "schema": 2},
                      {"schema": 1, "sources": {}}, {"schema": 1, "sources": []}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.load(value)
        entry = self.policy["sources"][FILE]
        value = {"schema": 1, "sources": {f"a{i}.ads": entry for i in range(17)}}
        with self.assertRaises(ValueError):
            self.load(value)

    def test_policy_entry_and_group_controls(self):
        entry = self.policy["sources"][FILE]
        for changed in (None, {}, {**entry, "extra": 1},
                        {**entry, "sha256": "x" * 64}, {**entry, "sha256": None},
                        {**entry, "overloads": {}}, {**entry, "overloads": []},
                        {**entry, "overloads": {"other.valid": [59, 66]}},
                        {**entry, "overloads": {UNIT + f".v{i}": [59, 66]
                                               for i in range(33)}}):
            value = copy.deepcopy(self.policy)
            value["sources"][FILE] = changed
            with self.subTest(entry=changed), self.assertRaises(ValueError):
                self.load(value)

    def test_policy_location_controls(self):
        for lines in (None, {}, [], [59], [59] * 17, [True, 66], [0, 66],
                      [59, 1000000], [59, "66"], [66, 59], [59, 59],
                      [59, 76], [59, 60], [59, 999999]):
            value = copy.deepcopy(self.policy)
            value["sources"][FILE]["overloads"][UNIT + ".valid"] = lines
            with self.subTest(lines=lines), self.assertRaises(ValueError):
                self.load(value)

    def test_policy_filename_controls(self):
        for filename in ("../" + FILE, "/" + FILE, "a.adb", "A.ads", "a" * 129 + ".ads"):
            value = {"schema": 1, "sources": {filename: self.policy["sources"][FILE]}}
            with self.subTest(filename=filename), self.assertRaises(ValueError):
                self.load(value)

    def test_duplicate_json_keys_constants_and_oversize_refuse(self):
        raw = json.dumps(self.policy)
        for text in ('{"schema":1,"schema":1,"sources":{}}',
                     raw.replace('"sha256":', '"sha256":"ignored","sha256":', 1),
                     raw.replace('"schema": 1', '"schema": NaN'),
                     raw.replace('"schema": 1', '"schema": Infinity'),
                     "{" * 10, "x" * (CHECKER.POLICY_LIMIT + 1)):
            self.policy_path.write_text(text)
            with self.subTest(text=text[:64]), self.assertRaises(ValueError):
                CHECKER.source_overloads(self.root, self.policy_path)


if __name__ == "__main__":
    unittest.main()
