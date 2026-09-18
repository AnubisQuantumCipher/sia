"""Keep installed GET, projection consistency and executed evidence distinct."""

try:
    import sia_test_home  # test-only import-time path isolation
except ModuleNotFoundError:
    from tests import sia_test_home  # type: ignore

from pathlib import Path
import unittest


class InstalledEngineDocumentation(unittest.TestCase):
    def prose(self):
        return " ".join((Path(__file__).resolve().parents[1] / "docs" /
                         "ARCHITECTURE.md").read_text(encoding="utf-8").split())

    def test_architecture_names_unreleased_transport_and_separate_display_authority(self):
        prose = self.prose()
        for phrase in (
                "siainstalledengine.hold_overlay_engine",
                "sia-installed-overlay-engine-expectations-v1",
                "expected_expectations_sha256",
                "authority_current",
                "a receipt cannot select its own expected runtime",
                "identity-bound regular leaf",
                "not a kernel-sealed file",
                "captured-unadmitted-projection",
                "get_page_render_projection",
                "complete displayed-field equality",
                "Canonical GET Markdown is not raw source-file bytes",
                "no JACKAL status or cognitive benchmark result"):
            with self.subTest(phrase=phrase):
                self.assertTrue(phrase in prose, "missing installed-engine boundary: " + phrase)

    def test_architecture_separates_actual_ordinary_get_transport_and_effects(self):
        prose = self.prose()
        for phrase in (
                "get(subject=..., timeout=...)",
                "_run_installed_gbrain",
                "get <subject> --source sia",
                "does not pass `--no-migrate`",
                "sia-installed-overlay-engine-get-transport-v1",
                "captured-unadmitted-get",
                "GET_NON_CLAIMS",
                "InstalledEngineGetRefusal",
                "Connection migrations and retrieval bookkeeping may occur",
                "GET transport makes no no-write assertion",
                "Captured output is not source-version admission"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, prose, "missing ordinary-GET boundary: " + phrase)

    def test_architecture_requires_fixed_host_without_claiming_compiled_evidence(self):
        prose = self.prose()
        for phrase in (
                "literal `GBRAIN_BRAIN_ID=host`",
                "`GBRAIN_HOME` alone is not brain selection",
                "fixed-host correction is a prerequisite",
                "trusted host backend configuration",
                "remote URL/thin-client routing",
                "not an executed test result",
                "Compiling a candidate and reading its version does not prove",
                "tests/test_gbrain_contract.py",
                "a skip proves nothing",
                "No retained observation is fresh authority",
                "does not validate later exits of an enclosing caller-owned scope"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, prose, "missing fixed-host/evidence limit: " + phrase)


if __name__ == "__main__":
    unittest.main()
