#!/usr/bin/env python3
"""Real-gbrain contract lane: the argv shapes SIA sends to the pinned gbrain binary.

Both shipped defects lived at the SIA<->gbrain subprocess seam — issue #2 (an absolute
``database_path`` bound to a deleted bootstrap home) and issue #3 (``embed <slug>`` without
``--source``, so every nightly rehearsal failed with "Page not found" for the project's whole
life). Every other test stubs that seam, which is exactly how both defects could ship: the
internal invariants were guarded and the boundary with the real binary was mocked. This lane
runs the true binary through SIA's own plumbing (``sialib.gbrain`` / ``sialib.gbrain_call``),
so an argv, flag, output-shape, or source-scoping drift fails here instead of in the ledger.

Honesty rules of this lane:
- A skip states that nothing was proven; a skip is not a pass.
- A binary that is found but broken is a failure, never a skip.
- ``SIA_GBRAIN_BIN`` set but invalid is a failure: explicit operator intent is never ignored.

The default tier is hermetic and offline: the fixture brain is initialized with
``--no-embedding``, so no ollama and no network are needed and the whole lane runs in
seconds. Embedding-dependent behavior (the full issue-#3 pair) is bounded here to the
contract that ``embed <slug> --source sia`` resolves the page (its failure on this brain is
the embedding runtime, never page resolution).
"""

import importlib.machinery
import importlib.util
import json
import os
import re
import subprocess
import unittest

try:
    import sia_test_home  # test-only import-time path isolation
except ModuleNotFoundError:
    from tests import sia_test_home  # type: ignore


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN = os.path.join(REPO, "bin")
PAGE_SLUG = "events/test/alpha"
PAGE_TOKEN = "zebrafish-contract-token"


def _load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, path)
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _locate_gbrain():
    override = os.environ.get("SIA_GBRAIN_BIN")
    if override:
        if os.path.isfile(override) and os.access(override, os.X_OK):
            return override, "override"
        raise AssertionError(
            f"SIA_GBRAIN_BIN is set but is not an executable file: {override}")
    default = os.path.join(
        sia_test_home._REAL_EXPANDUSER("~"),
        ".local/share/sia/toolchain/gbrain/bin/gbrain")
    if os.path.isfile(default) and os.access(default, os.X_OK):
        return default, "toolchain"
    return None, None


def _pin_version():
    pin = os.path.join(REPO, "GBRAIN_PIN")
    with open(pin, "r", encoding="utf-8") as stream:
        for line in stream:
            if line.startswith("version="):
                return line.split("=", 1)[1].strip()
    raise AssertionError("GBRAIN_PIN has no version= line")


def _output(result):
    return (getattr(result, "stdout", "") or "") + (getattr(result, "stderr", "") or "")


class GbrainContract(unittest.TestCase):
    """One shared brain, initialized once; each test pins one invocation shape."""

    sialib = None

    @classmethod
    def setUpClass(cls):
        binary, origin = _locate_gbrain()
        if binary is None:
            raise unittest.SkipTest(
                "real-gbrain contract lane: no gbrain binary found (set SIA_GBRAIN_BIN or "
                "install the toolchain at ~/.local/share/sia/toolchain/gbrain/bin/gbrain); "
                "the gbrain contract was NOT exercised — this skip is not a pass")
        cls.binary = binary
        cls.origin = origin
        cls.sialib = _load("sialib_gbrain_contract", os.path.join(BIN, "sialib.py"))

        # Isolation guard: the runtime must already be rehomed under the test fixture before
        # anything is executed, or the lane would touch the operator's real brain.
        if not cls.sialib.SHARE.startswith(sia_test_home.ISOLATED_HOME):
            raise AssertionError(
                f"sialib.SHARE escaped the isolated home: {cls.sialib.SHARE}")
        if cls.sialib.GBRAIN_ENV.get("GBRAIN_HOME") != cls.sialib.SHARE:
            raise AssertionError("GBRAIN_ENV.GBRAIN_HOME is not the isolated SHARE")

        # The single seam patch: point the runtime at the located binary. Everything else —
        # env construction, cwd=CORPUS, the owner lease, output bounds — is the shipped
        # plumbing, which is the thing under test.
        cls.sialib.GBRAIN = binary
        # Hermeticity: mirror siacapsule._gbrain_environment's strip of remote/db routing so
        # an operator's ambient gbrain configuration cannot leak into the fixture brain.
        for key in ("GBRAIN_DATABASE_URL", "DATABASE_URL", "GBRAIN_BRAIN_ID",
                    "GBRAIN_SOURCE", "GBRAIN_SCHEMA_PACK"):
            cls.sialib.GBRAIN_ENV.pop(key, None)
        cls.sialib.GBRAIN_ENV["GBRAIN_SELF_UPGRADE_MODE"] = "off"

        page_dir = os.path.join(cls.sialib.CORPUS, "events", "test")
        os.makedirs(page_dir, exist_ok=True)
        with open(os.path.join(page_dir, "alpha.md"), "w", encoding="utf-8") as stream:
            stream.write(
                "---\ntitle: alpha\n---\n# alpha\n"
                f"The {PAGE_TOKEN} lives here with organs/test context.\n")
        # gbrain sync reads through git objects: uncommitted files are invisible to the
        # walker, so the corpus must be a committed git repository — as SIA's real corpus is.
        for argv in (("git", "init", "-q"),
                     ("git", "add", "-A"),
                     ("git", "-c", "user.email=contract@test", "-c", "user.name=contract",
                      "commit", "-qm", "contract fixture")):
            subprocess.run(argv, cwd=cls.sialib.CORPUS, check=True, capture_output=True)

        cls.db_path = os.path.join(cls.sialib.SHARE, ".gbrain", "brain.pglite")
        os.makedirs(os.path.dirname(cls.db_path), exist_ok=True)
        for argv in (
            ["init", "--pglite", "--non-interactive", "--json", "--skip-embed-check",
             "--path", cls.db_path, "--no-embedding"],
            ["sources", "add", "sia", "--path", cls.sialib.CORPUS],
            ["sync", "--source", "sia"],
        ):
            result = cls.sialib.gbrain(argv, timeout=180)
            if result.returncode != 0:
                raise AssertionError(
                    f"gbrain bootstrap failed at {argv[:2]}: rc={result.returncode} "
                    f"output tail: {_output(result)[-400:]}")

    def test_00_version_is_wellformed_and_matches_pin(self):
        result = self.sialib.gbrain(["--version"], timeout=30)
        self.assertEqual(result.returncode, 0, _output(result)[-200:])
        reported = _output(result).strip().splitlines()[-1]
        self.assertRegex(reported, r"gbrain \d+(\.\d+)+$")
        if self.origin == "toolchain":
            # The toolchain binary is receipt-bound to the pin; an explicit SIA_GBRAIN_BIN
            # may deliberately test a candidate pin, so drift is a failure only here.
            self.assertIn(_pin_version(), reported,
                          f"toolchain gbrain drifted from GBRAIN_PIN: {reported}")

    def test_01_engine_status_probe_reports_exact_database_path(self):
        # The issue-#2 contract: the engine must report the exact absolute database_path it
        # was initialized with, because SIA's health probes compare it byte-for-byte.
        result = self.sialib.gbrain(["engine", "status", "--probe", "--json"], timeout=60)
        self.assertEqual(result.returncode, 0, _output(result)[-300:])
        # Parse stdout alone, from the first opener — exactly the shipped consumers' shape
        # (sialib's dream parse; siacapsule's probe): stderr may carry log lines.
        text = result.stdout
        report = json.loads(text[text.index("{"):])
        self.assertEqual(report.get("schema_version"), 1)
        self.assertEqual(report.get("database_path"), self.db_path)
        self.assertIs(report.get("probe", {}).get("ok"), True)

    def test_02_sources_list_names_exactly_sia(self):
        result = self.sialib.gbrain(["sources", "list", "--json"], timeout=60)
        self.assertEqual(result.returncode, 0, _output(result)[-300:])
        # siacapsule's restore path (_strict_json on full stdout, then report["sources"])
        # demands strictly-pure JSON on stdout with this exact object shape; pin that.
        report = json.loads(result.stdout)
        rows = report.get("sources")
        self.assertIsInstance(rows, list, report)
        sia_rows = [row for row in rows if row.get("id") == "sia"]
        self.assertEqual(len(sia_rows), 1, rows)
        self.assertEqual(sia_rows[0].get("local_path"), self.sialib.CORPUS)

    def test_03_sync_is_idempotent(self):
        result = self.sialib.gbrain(["sync", "--source", "sia"], timeout=180)
        self.assertEqual(result.returncode, 0, _output(result)[-300:])

    def test_04_extract_links_accepts_both_shipped_shapes(self):
        for argv in (["extract", "links", "--source", "db", "--stale", "--json"],
                     ["extract", "links", "--by-mention", "--ner", "--source", "db",
                      "--source-id", "sia", "--json"]):
            result = self.sialib.gbrain(argv, timeout=180)
            self.assertEqual(result.returncode, 0,
                             f"{argv}: {_output(result)[-300:]}")

    def test_05_get_with_source_returns_the_page(self):
        result = self.sialib.gbrain(["get", PAGE_SLUG, "--source", "sia"], timeout=60)
        self.assertEqual(result.returncode, 0, _output(result)[-300:])
        self.assertIn(PAGE_TOKEN, _output(result))
        # Deliberately NOT asserted: `get <slug>` without --source. Its behavior is
        # brain-state-dependent (it resolves in a single-source brain and failed with
        # "Page not found (source=default)" on the real deployment — issue #3), which is
        # precisely why the runtime contract is "every page-addressed invocation names its
        # source" (bin/sialib.py, GBRAIN_SOURCE).

    def test_06_search_keyword_lane_finds_the_seeded_page(self):
        result = self.sialib.gbrain(
            ["search", PAGE_TOKEN, "--source", "sia", "--json"], timeout=120)
        self.assertEqual(result.returncode, 0, _output(result)[-300:])
        self.assertIn(PAGE_SLUG, _output(result))

    def test_07_call_ops_return_parseable_json(self):
        for op, params in (("get_recent_salience", {"days": 7, "limit": 5}),
                           ("find_anomalies", {"sigma": 3.0})):
            value = self.sialib.gbrain_call(op, params, timeout=120)
            self.assertIsNotNone(
                value, f"gbrain call {op} returned unparseable or failing output")

    def test_08_context_pack_is_brain_wide_by_design(self):
        # context-pack is a cross-brain "memory verb" (entity cards + threads + facts): it
        # accepts no --source flag at all, so the runtime's bare invocation in `bin/sia` is
        # correct and is NOT an instance of the issue-#3 missing-source class.
        result = self.sialib.gbrain(
            ["context-pack", "--entities", "test", "--budget-tokens", "4000"], timeout=120)
        self.assertEqual(result.returncode, 0, _output(result)[-300:])
        self.assertIn("protocol_version", _output(result))

    def test_09_embed_with_source_resolves_the_page(self):
        # The issue-#3 argv, pinned as far as an offline brain allows: on a --no-embedding
        # brain the command fails because of the embedding runtime, and that failure must
        # never be a page-resolution failure. If --source scoping regressed, the output
        # would be the "not found" class again and this assertion catches it.
        result = self.sialib.gbrain(
            ["embed", PAGE_SLUG, "--source", "sia"], timeout=120)
        self.assertNotIn("not found", _output(result).lower(),
                         "embed --source failed to resolve a synced page: the issue-#3 "
                         "source-scoping contract has regressed")

    def test_10_dream_reports_an_honest_status(self):
        result = self.sialib.gbrain(["dream", "--json"], timeout=300)
        self.assertEqual(result.returncode, 0, _output(result)[-300:])
        # Mirror sialib's own dream parse: stdout, from the first "{". If gbrain ever moves
        # log lines onto stdout after the JSON, production would read the cycle as
        # unfinished — this assertion is that early warning.
        report = json.loads(result.stdout[result.stdout.index("{"):])
        self.assertIn(report.get("status"), {"ok", "clean", "partial"},
                      f"dream status outside the accepted set: {report.get('status')}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
