"""Actual pinned-overlay projection seam; no installed/render authority claim.

This owns a separate disposable offline brain and uses the bounded process
runner. It does not modify the original real-gbrain fixtures or their tests.
Reported read-only flags are checked as output fields, not physical-I/O proof.
"""

import json
import os
from pathlib import Path
import tempfile
import unittest

from tests import sia_test_home
from tests import test_gbrain_contract as contracts


SLUG = "events/test/overlay-projection"
RAW = "---\ntitle: overlay projection\n---\n# overlay projection\nPinned overlay seam token.\n"


class GbrainOverlayProjectionContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.binary, _origin = contracts._locate_gbrain()
        if cls.binary is None:
            raise unittest.SkipTest(
                "real overlay projection NOT EXERCISED: no gbrain binary provided")
        cls.lib = contracts._load(
            "sialib_overlay_projection_contract", os.path.join(contracts.BIN, "sialib.py"))
        if cls.lib.SHARE != os.path.join(sia_test_home.ISOLATED_HOME, ".local/share/sia"):
            raise AssertionError("overlay fixture runtime escaped isolated home")
        cls.temporary = tempfile.TemporaryDirectory(prefix="sia-overlay-contract-")
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root = Path(cls.temporary.name)
        private_tmp = cls.root / "tmp"
        private_tmp.mkdir(mode=0o700)
        cls.corpus = cls.root / "corpus"
        cls.corpus.mkdir()
        share = cls.root / "share"
        share.mkdir()
        cls.environment = {
            "HOME": str(cls.root), "GBRAIN_HOME": str(share),
            "TMPDIR": str(private_tmp),
            "PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
            "TZ": "UTC", "NO_COLOR": "1", "GBRAIN_SKIP_STARTUP_HOOKS": "1",
            "GBRAIN_SYNC_NO_DELEGATE": "1", "GBRAIN_NO_BANNER": "1",
            "GBRAIN_SELF_UPGRADE_MODE": "off", "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_TERMINAL_PROMPT": "0",
        }
        cls.page = cls.corpus / (SLUG + ".md")
        cls.page.parent.mkdir(parents=True)
        cls.page.write_text(RAW, encoding="utf-8")
        for args in (("init", "-q"), ("add", "--", SLUG + ".md"),
                     ("-c", "user.email=overlay@test", "-c", "user.name=overlay",
                      "commit", "-qm", "overlay fixture")):
            cls._command(["/usr/bin/git", *args])
        for args in (
                ["init", "--pglite", "--non-interactive", "--json", "--skip-embed-check",
                 "--path", str(share / "brain.pglite"), "--no-embedding"],
                ["sources", "add", "sia", "--path", str(cls.corpus)],
                ["sync", "--source", "sia"]):
            cls._command([cls.binary, *args])

    @classmethod
    def _command(cls, command, *, expected_exit=0):
        result = cls.lib._run_bounded_text_process(
            command, env=cls.environment, timeout=180, cwd=str(cls.corpus),
            label="overlay projection contract", output_limit=1048576)
        if expected_exit is not None and result.returncode != expected_exit:
            raise AssertionError(
                f"overlay fixture command refused: rc={result.returncode}; "
                f"stdout={result.stdout[-1000:]!r}; stderr={result.stderr[-1000:]!r}")
        return result

    def _projection(self, raw):
        request = self.root / "projection.json"
        request.write_text(json.dumps({
            "source_id": "sia", "targets": [{"slug": SLUG, "raw_markdown": raw}]
        }), encoding="utf-8")
        result = self._command([
            self.binary, "call", "--no-migrate", "--source", "sia",
            "--params-file", str(request), "get_page_projection"])
        return self.lib._strict_json_loads(result.stdout)

    def _assert_roster(self, result):
        self.assertEqual(result["schema_version"], 1)
        self.assertEqual(result["source_id"], "sia")
        self.assertEqual(result["target_count"], 1)
        self.assertEqual([row["slug"] for row in result["targets"]], [SLUG])
        self.assertIs(result["retrieval_bookkeeping_updated"], False)
        self.assertIs(result["operation_writes_performed"], False)
        self.assertEqual(self.page.read_text(encoding="utf-8"), RAW)
        return result["targets"][0]

    def test_exact_canonical_page_matches_actual_index_projection(self):
        result = self._projection(RAW)
        row = self._assert_roster(result)
        self.assertIs(result["all_match"], True)
        self.assertEqual(row["page_state"], "live")
        self.assertEqual(row["parse_error_codes"], [])
        self.assertIs(row["projection_match"], True)
        self.assertIs(row["current_content_hash_match"], True)
        self.assertRegex(row["expected_projection_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(row["expected_projection_sha256"], row["current_projection_sha256"])
        self.assertEqual(row["current_content_hash"], row["current_projection_sha256"])

    def test_changed_expected_body_is_a_retained_mismatch(self):
        result = self._projection(RAW + "Different expected canonical body.\n")
        row = self._assert_roster(result)
        self.assertIs(result["all_match"], False)
        self.assertEqual(row["page_state"], "live")
        self.assertEqual(row["parse_error_codes"], [])
        self.assertIs(row["projection_match"], False)
        self.assertIs(row["current_content_hash_match"], True)
        self.assertNotEqual(row["expected_projection_sha256"], row["current_projection_sha256"])

    def test_projection_requires_explicit_no_migrate(self):
        request = self.root / "projection-refusal.json"
        request.write_text(json.dumps({
            "source_id": "sia", "targets": [{"slug": SLUG, "raw_markdown": RAW}]
        }), encoding="utf-8")
        result = self._command([
            self.binary, "call", "--source", "sia", "--params-file",
            str(request), "get_page_projection"], expected_exit=None)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("requires --no-migrate", result.stdout + result.stderr)
        self.assertEqual(self.page.read_text(encoding="utf-8"), RAW)


if __name__ == "__main__":
    unittest.main()
