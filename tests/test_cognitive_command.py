"""Pinned private cognitive command handoff; no models or databases run here.

Replacement rationale, approved before production/old-test edits: the old
unavailable envelope, refusal-only help and single-AST-Raise assertion encoded
the absence of an admitted runner. The committed run_baseline now exists.
Those assertions must become accurate missing-request refusal and strict
private handoff contracts; preserving the old false absence claim is not an
honesty boundary. Early refusal without resident effects, dormant scaffold
exclusions, and every unrelated content/origin/ancestry test remain required.

Only exact `bench cognitive` is a new private capability. Other benchmark and
memory commands retain readiness gating; lifecycle locking remains mandatory.
Stdout carries only a small request/baseline-hash receipt. Full source, query,
and answer data remain in the independently published private baseline file.

Every baseline call below is replaced by a local fixture publisher. Root
alone runs these tests sequentially. No production runtime/model is executed.
"""

import contextlib
import copy
import hashlib
import importlib
import importlib.machinery
import importlib.util
import inspect
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest

try:
    import cognitive_host
except ModuleNotFoundError:
    from tests import cognitive_host  # type: ignore
from unittest import mock

try:
    import sia_test_home
except ModuleNotFoundError:
    from tests import sia_test_home

BIN = Path(__file__).resolve().parents[1] / "bin"
sys.path.insert(0, str(BIN))

REQUEST_SCHEMA = "sia-cognitive-command-request-v1"
RECEIPT_SCHEMA = "sia-cognitive-command-observation-v1"
REFUSAL_SCHEMA = "sia-cognitive-baseline-refusal-v1"
COMMAND_NON_CLAIMS = [
    "The request SHA-256 binds caller-supplied bytes, not their authorship or the truth of supplied history.",
    "The private command does not consult resident memory readiness, corpus, index, or an ambient model.",
    "Baseline and upstream nonclaims remain controlling; this receipt adds no metric, significance, or cognitive-win authority.",
    "Lifecycle locking and descriptor checks do not establish protection against a hostile same-user process.",
]
# Existing file/depth ceilings were read from sialib/siacognitivebaseline.
# Derived edge fixtures routed first: JACKAL status=exact, not formal-bounded.
JACKAL_FIXTURES = [
    {"parsed": "16777216+1", "exact": "16777217", "status": "exact"},
    {"parsed": "64+1", "exact": "65", "status": "exact"},
    {"parsed": "1000+1", "exact": "1001", "status": "exact"},
    {"parsed": "9007199254740991+1", "exact": "9007199254740992", "status": "exact"},
]
EXACT_NON_CLAIMS = [
    "NOT formal-bounded: this lane carries no Lean-checked certificate",
    "The epistemic class above is the STRONGEST claim this result supports",
    "exact rational arithmetic (not yet checker-covered)",
]


class _OsShim:
    """Keep syscall faults local to the module executing the command."""

    def __init__(self, **overrides):
        self._overrides = overrides

    def __getattr__(self, name):
        if name in self._overrides:
            return self._overrides[name]
        return getattr(os, name)


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _load_script(name, path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def _kwargs(root):
    # Transport fixtures deliberately leave deep semantic admission to the
    # mocked committed runner. They are not usable model/runtime requests.
    return {
        "capture": {"private_source": "DO-NOT-PRINT-SOURCE"},
        "expected_capture_sha256": _sha(b"caller capture pin"),
        "selection_policy": {"private_policy": "fixture"},
        "expected_policy_sha256": _sha(b"caller policy pin"),
        "selection": {"pages_sha256": _sha(b"selected pages"), "private_selection": "fixture"},
        "expected_selection_sha256": _sha(b"caller selection pin"),
        "split": "calibration", "preparer": {"private_build": "preparer fixture"},
        "adapter": {"private_build": "adapter fixture"},
        "embedding": {"model": "ollama:nomic-embed-text:v1.5", "dimensions": 768,
                      "endpoint": "http://127.0.0.1:11434/v1"},
        "model_expectations": {"private_model": "fixture"},
        "shared_runtime": [{"private_runtime": "fixture"}],
        "code_expectations": {"schema": "sia-bin-source-inventory-v1", "files": {"sia": _sha(b"source")}},
        "limit": 5, "timeout": 30, "scratch_parent": str(root),
        "parameter_freeze": None, "expected_parameter_freeze_sha256": None,
    }


class CognitiveImportOrder(unittest.TestCase):
    def test_fresh_process_import_orders_are_isolated_and_do_not_reenter_partial_command(self):
        # Root observed the baseline-first cycle through selection -> bench
        # before the command import became lazy. In-process tests can mask it
        # once another fixture has populated sys.modules, so each order needs
        # a new interpreter. Import-only children never run the baseline.
        orders = [
            ["siacognitivebaseline", "siacognitiveselect", "siabench", "siacognitivecommand"],
            ["siacognitiveselect", "siabench", "siacognitivecommand", "siacognitivebaseline"],
            ["siacognitivecommand", "siacognitivebaseline", "siacognitiveselect", "siabench"],
        ]
        child = """
import importlib
import os
import sys
from unittest import mock

assert sys.dont_write_bytecode, "bytecode writes were not disabled"
test_directory, bin_directory, *order = sys.argv[1:]
sys.path.insert(0, test_directory)
import sia_test_home
sys.path.insert(0, bin_directory)
with mock.patch("subprocess.Popen", side_effect=AssertionError("import spawned a child")), \\
        mock.patch("sqlite3.connect", side_effect=AssertionError("import opened a database")):
    for name in order:
        importlib.import_module(name)
import sialib
assert os.path.commonpath([sialib.STATE, sia_test_home.ISOLATED_HOME]) == sia_test_home.ISOLATED_HOME
assert os.path.commonpath([sialib.CORPUS, sia_test_home.ISOLATED_HOME]) == sia_test_home.ISOLATED_HOME
print("import-order-observed")
"""
        for order in orders:
            with self.subTest(order=order):
                result = subprocess.run(
                    [sys.executable, "-I", "-B", "-c", child,
                     str(BIN.parent / "tests"), str(BIN), *order],
                    cwd=sia_test_home.ISOLATED_HOME, stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                    timeout=30, check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, "import-order-observed\n")
                self.assertEqual(result.stderr, "")


class CognitiveCommandRequest(unittest.TestCase):
    def setUp(self):
        self.bench = importlib.import_module("siabench")
        self.baseline = importlib.import_module("siacognitivebaseline")
        self.command = importlib.import_module("siacognitivecommand")
        parameters = inspect.signature(self.bench.run_cognitive).parameters
        self.assertIn("request_file", parameters, "public cognitive entrypoint lacks pinned-request admission")
        self.assertIn("request_sha256", parameters, "external request hash must be a separate argument")
        private = tempfile.TemporaryDirectory(prefix="sia-command-contract-")
        self.addCleanup(private.cleanup)
        self.root = Path(private.name)
        self.root.chmod(0o700)
        self.output = self.root / "baseline-output"
        self.request_path = self.root / "request.json"
        self.kw = _kwargs(self.root)
        self.request = {"schema": REQUEST_SCHEMA, "baseline": copy.deepcopy(self.kw)}
        self.raw = _canonical(self.request)
        self._write_request(self.raw)
        self.request_sha256 = _sha(self.raw)
        self.baseline_result = self._baseline_result()

    def _write_request(self, raw):
        self.request_path.write_bytes(raw)
        self.request_path.chmod(0o600)

    def _baseline_result(self):
        queries = [{"id": "query", "text": "DO-NOT-PRINT-QUERY"}]
        contract = {"fixture": "independently validated by the baseline in production"}
        body = {
            "schema": "sia-cognitive-baseline-v1", "status": "observed", "lane": "raw_vector",
            "split": self.kw["split"], "capture_sha256": self.kw["expected_capture_sha256"],
            "policy_sha256": self.kw["expected_policy_sha256"],
            "selection_sha256": self.kw["expected_selection_sha256"],
            "pages_sha256": self.kw["selection"]["pages_sha256"],
            "query_roster_sha256": _sha(_canonical(queries)),
            "baseline_contract_sha256": _sha(_canonical(contract)),
            "parameter_freeze_sha256": self.kw["expected_parameter_freeze_sha256"],
            "parameter_freeze": self.kw["parameter_freeze"], "contract": contract, "queries": queries,
            "pages": [{"text": "DO-NOT-PRINT-SOURCE", "origin": "model"}],
            "answer_key": [{"answer": "DO-NOT-PRINT-ANSWER"}],
            "preparation": {"fixture": True}, "observation": {"fixture": True},
            "retrieval_rows": [], "archive": {"fixture": True},
            "source_non_claims": {"selection": ["selection premise"], "history": ["history premise"]},
            "non_claims": list(self.baseline.NON_CLAIMS),
        }
        return {**body, "artifact_sha256": _sha(_canonical(body))}

    def _publish(self, **kwargs):
        self.assertEqual(kwargs, {**self.kw, "output_directory": str(self.output)})
        self.output.mkdir(mode=0o700)
        artifact = self.output / "baseline.json"
        artifact.write_bytes(_canonical(self.baseline_result))
        artifact.chmod(0o600)
        return copy.deepcopy(self.baseline_result)

    def _run(self, **changes):
        arguments = {"request_file": str(self.request_path), "request_sha256": self.request_sha256}
        arguments.update(changes)
        return self.bench.run_cognitive(str(self.output), **arguments)

    def _refused(self, function, reason=None):
        with self.assertRaises(self.bench.BenchmarkRefusal) as raised:
            function()
        result = json.loads(str(raised.exception))
        self.assertEqual(result["schema"], REFUSAL_SCHEMA)
        self.assertEqual(result["status"], "refused")
        self.assertEqual(result["consequence_ceiling"], "informational")
        self.assertEqual(result["non_claims"], COMMAND_NON_CLAIMS)
        if reason is not None:
            self.assertEqual(result["reason"], reason)
        self.assertNotIn("DO-NOT-PRINT", str(raised.exception))
        return result

    def test_every_baseline_parameter_is_explicit_and_output_has_only_cli_authority(self):
        expected = set(inspect.signature(self.baseline.run_baseline).parameters) - {"output_directory"}
        self.assertEqual(set(self.kw), expected)
        signature = inspect.signature(self.bench.run_cognitive)
        self.assertEqual(list(signature.parameters), ["out_dir", "repo", "request_file", "request_sha256"])
        for name in ("repo", "request_file", "request_sha256"):
            self.assertIsNone(signature.parameters[name].default)
            self.assertEqual(signature.parameters[name].kind, inspect.Parameter.KEYWORD_ONLY)
        with mock.patch.object(self.baseline, "run_baseline", side_effect=self._publish) as runner:
            result = self._run()
        runner.assert_called_once_with(**self.kw, output_directory=str(self.output))
        self.assertEqual(result, {
            "schema": RECEIPT_SCHEMA, "status": "observed", "request_sha256": self.request_sha256,
            "baseline_artifact_sha256": self.baseline_result["artifact_sha256"],
            "output_directory": str(self.output), "artifact": "baseline.json",
            "baseline_non_claims": self.baseline_result["non_claims"], "non_claims": COMMAND_NON_CLAIMS,
        })
        self.assertEqual(self.request_path.read_bytes(), self.raw)
        self.assertEqual((self.output / "baseline.json").read_bytes(), _canonical(self.baseline_result))

    def test_missing_external_pin_or_alternate_repo_refuses_before_any_private_or_resident_effect(self):
        with mock.patch.object(self.baseline, "run_baseline") as runner, \
                mock.patch.object(self.bench, "build_ledger_dataset") as dataset, \
                mock.patch.object(self.bench, "_engine") as hybrid, \
                mock.patch.object(self.bench, "_atomic_text") as publish, \
                mock.patch.object(self.bench.sialib, "corpus_owner") as owner:
            self._refused(lambda: self.bench.run_cognitive(None), "pinned-request-required")
            self._refused(lambda: self._run(request_file=None), "pinned-request-required")
            self._refused(lambda: self._run(request_sha256=None), "pinned-request-required")
            self._refused(lambda: self._run(repo=str(self.root)), "unsupported-alternate-source-root")
            self._refused(lambda: self.bench.run_cognitive(None, request_file=str(self.request_path),
                          request_sha256=self.request_sha256), "output-directory-required")
        for operation in (runner, dataset, hybrid, publish, owner):
            operation.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_external_sha_binds_exact_wire_bytes_not_self_hash_or_reserialized_equivalence(self):
        other_wire = json.dumps(self.request, indent=2, ensure_ascii=False).encode("utf-8")
        self._write_request(other_wire)
        with mock.patch.object(self.baseline, "run_baseline") as runner:
            self._refused(self._run)
            self_hash = {**self.request, "request_sha256": _sha(other_wire)}
            self._write_request(_canonical(self_hash))
            self._refused(lambda: self._run(request_sha256=None), "pinned-request-required")
        runner.assert_not_called()

    def test_request_schema_and_complete_kwarg_roster_reject_extra_or_missing_authority(self):
        variants = [{**self.request, "schema": "unversioned"}, {**self.request, "repo": str(self.root)},
                    {**self.request, "request_sha256": self.request_sha256},
                    {**self.request, "baseline": {**self.kw, "output_directory": str(self.output)}},
                    {**self.request, "baseline": {**self.kw, "repo": str(self.root)}}]
        for key in self.kw:
            partial = copy.deepcopy(self.kw)
            del partial[key]
            variants.append({**self.request, "baseline": partial})
        with mock.patch.object(self.baseline, "run_baseline") as runner:
            for request in variants:
                raw = _canonical(request)
                self._write_request(raw)
                with self.subTest(request=repr(request)):
                    self._refused(lambda: self._run(request_sha256=_sha(raw)))
        runner.assert_not_called()

    def test_duplicate_nonfinite_out_of_range_and_deep_json_refuse_before_runner(self):
        # Keep the complete kwarg roster, so these cannot pass merely because
        # a different missing-field check happens to reject the same fixture.
        malformed = [self.raw.replace(b'"schema":"sia-cognitive-command-request-v1"',
                                      b'"schema":"sia-cognitive-command-request-v1","schema":"sia-cognitive-command-request-v1"'),
                     self.raw.replace(b'"private_source":"DO-NOT-PRINT-SOURCE"', b'"x":1,"x":2'),
                     self.raw.replace(b'"private_source":"DO-NOT-PRINT-SOURCE"', b'"x":NaN'),
                     self.raw.replace(b'"private_source":"DO-NOT-PRINT-SOURCE"', b'"x":1e999'),
                     self.raw.replace(b'"private_source":"DO-NOT-PRINT-SOURCE"', b'"x":9007199254740992'),
                     b'\xff', b'[]', b'null']
        deep = copy.deepcopy(self.request)
        nested = []
        for _ in range(65):
            nested = [nested]
        deep["baseline"]["capture"] = nested
        malformed.append(_canonical(deep))
        with mock.patch.object(self.baseline, "run_baseline") as runner:
            for raw in malformed:
                self._write_request(raw)
                with self.subTest(raw=raw[:64]):
                    self._refused(lambda: self._run(request_sha256=_sha(raw)))
        runner.assert_not_called()

    def test_request_wire_ceiling_is_checked_before_parse_or_full_read(self):
        # Sparse over-ceiling file: no large fixture buffer or database.
        with self.request_path.open("r+b") as stream:
            stream.truncate(16777217)
        request_os = _OsShim(
            read=mock.Mock(side_effect=AssertionError("oversized bytes read")),
            pread=mock.Mock(side_effect=AssertionError("oversized bytes read")),
            fdopen=mock.Mock(side_effect=AssertionError("oversized descriptor streamed")),
        )
        with mock.patch.object(self.baseline, "run_baseline") as runner, \
                mock.patch.object(self.bench.json, "loads", side_effect=AssertionError("oversized input parsed")), \
                mock.patch.object(self.command, "os", request_os):
            with self.assertRaises(self.bench.BenchmarkRefusal):
                self._run()
        runner.assert_not_called()

    def test_request_leaf_and_every_parent_are_nofollow_and_hardlinks_are_refused(self):
        leaf = self.root / "leaf-link.json"
        leaf.symlink_to(self.request_path)
        physical = self.root / "physical"
        physical.mkdir(mode=0o700)
        nested_request = physical / "request.json"
        nested_request.write_bytes(self.raw)
        nested_request.chmod(0o600)
        parent_link = self.root / "linked-parent"
        parent_link.symlink_to(physical, target_is_directory=True)
        with mock.patch.object(self.baseline, "run_baseline") as runner:
            for path in (leaf, parent_link / "request.json", physical):
                with self.subTest(path=path):
                    self._refused(lambda: self._run(request_file=str(path)))
            hard = self.root / "hard-link.json"
            os.link(self.request_path, hard)
            self._refused(self._run)
        runner.assert_not_called()

    @cognitive_host.requires_admitted_interpreter
    def test_exact_owner_private_mode_and_absolute_request_path_are_required(self):
        with mock.patch.object(self.baseline, "run_baseline") as runner:
            for mode in (0o400, 0o640, 0o644, 0o700):
                self.request_path.chmod(mode)
                with self.subTest(mode=mode):
                    self._refused(self._run)
            self.request_path.chmod(0o600)
            self._refused(lambda: self._run(request_file="request.json"))
            # Observed operator UID was 1000; JACKAL derived the foreign fixture 1001.
            with mock.patch.object(self.command, "os", _OsShim(geteuid=mock.Mock(return_value=1001))):
                self._refused(self._run)
        runner.assert_not_called()

    def test_generation_replacement_after_parse_refuses_before_baseline_invocation(self):
        real_loads = json.loads
        changed = []

        def decode_then_replace(*args, **kwargs):
            result = real_loads(*args, **kwargs)
            if not changed:
                replacement = self.root / "replacement.json"
                replacement.write_bytes(self.raw)
                replacement.chmod(0o600)
                os.replace(replacement, self.request_path)
                changed.append(True)
            return result

        with mock.patch.object(self.baseline, "run_baseline") as runner, \
                mock.patch.object(self.bench.json, "loads", side_effect=decode_then_replace):
            with self.assertRaises(self.bench.BenchmarkRefusal):
                self._run()
        self.assertTrue(changed)
        runner.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_post_call_request_replacement_refuses_but_preserves_independent_baseline_artifact(self):
        def publish_then_replace(**kwargs):
            result = self._publish(**kwargs)
            replacement = self.root / "replacement.json"
            replacement.write_bytes(self.raw)
            replacement.chmod(0o600)
            os.replace(replacement, self.request_path)
            return result

        with mock.patch.object(self.baseline, "run_baseline", side_effect=publish_then_replace) as runner:
            self._refused(self._run, "request-generation-changed")
        runner.assert_called_once()
        artifact = self.output / "baseline.json"
        self.assertEqual(artifact.read_bytes(), _canonical(self.baseline_result))
        self.assertEqual(stat.S_IMODE(artifact.stat().st_mode), 0o600)

    def test_post_call_request_permission_change_also_withdraws_only_command_success(self):
        def publish_then_change_mode(**kwargs):
            result = self._publish(**kwargs)
            self.request_path.chmod(0o644)
            return result

        with mock.patch.object(self.baseline, "run_baseline", side_effect=publish_then_change_mode):
            self._refused(self._run, "request-generation-changed")
        self.assertTrue((self.output / "baseline.json").is_file())

    def test_returned_baseline_identity_schema_lane_status_and_self_hash_are_admitted(self):
        variants = []
        for field, value in (("schema", "unknown"), ("status", "refused"), ("lane", "hybrid"),
                             ("split", "heldout"), ("capture_sha256", _sha(b"foreign capture")),
                             ("policy_sha256", _sha(b"foreign policy")),
                             ("selection_sha256", _sha(b"foreign selection"))):
            changed = {**copy.deepcopy(self.baseline_result), field: value}
            changed["artifact_sha256"] = _sha(_canonical({key: item for key, item in changed.items() if key != "artifact_sha256"}))
            variants.append(changed)
        variants.append({**self.baseline_result, "artifact_sha256": _sha(b"wrong body")})
        variants.append({key: value for key, value in self.baseline_result.items() if key != "artifact_sha256"})
        extra = {**self.baseline_result, "win": True}
        extra["artifact_sha256"] = _sha(_canonical({key: value for key, value in extra.items() if key != "artifact_sha256"}))
        variants.append(extra)
        for result in variants:
            with self.subTest(result=repr(result)), mock.patch.object(self.baseline, "run_baseline", return_value=result):
                self._refused(self._run, "baseline-result-not-admitted")

    def test_baseline_refusal_is_sanitized_and_retains_upstream_boundaries(self):
        error = self.baseline.BaselineRefusal("DO-NOT-PRINT-SOURCE private failure details")
        error.non_claims = list(self.baseline.NON_CLAIMS)
        error.upstream_non_claims = ["Upstream admission remains a caller premise."]
        with mock.patch.object(self.baseline, "run_baseline", side_effect=error) as runner:
            refusal = self._refused(self._run, "baseline-refused")
        runner.assert_called_once()
        self.assertEqual(refusal["baseline_non_claims"], self.baseline.NON_CLAIMS)
        self.assertEqual(refusal["upstream_non_claims"], error.upstream_non_claims)

    def test_cli_prints_only_small_receipt_not_private_source_queries_answers_or_metrics(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with mock.patch.object(self.baseline, "run_baseline", side_effect=self._publish), \
                contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            try:
                code = self.bench.main(["cognitive", "--request", str(self.request_path),
                                        "--request-sha256", self.request_sha256, "--out", str(self.output)])
            except SystemExit as exc:
                self.fail(f"pinned command parser intercepted the handoff: {exc.code}")
        self.assertEqual(code, 0)
        self.assertEqual(stderr.getvalue(), "")
        receipt = json.loads(stdout.getvalue())
        self.assertEqual(receipt["schema"], RECEIPT_SCHEMA)
        self.assertEqual(receipt["request_sha256"], self.request_sha256)
        self.assertEqual(receipt["baseline_artifact_sha256"], self.baseline_result["artifact_sha256"])
        self.assertNotIn("DO-NOT-PRINT", stdout.getvalue())
        self.assertNotIn("answer_key", receipt)
        self.assertNotIn("queries", receipt)
        self.assertNotIn("metrics", receipt)
        self.assertNotIn("win", receipt)

    def test_cli_without_request_remains_structured_even_without_output_option(self):
        for arguments in (["cognitive"], ["cognitive", "--out", str(self.output)]):
            stdout, stderr = io.StringIO(), io.StringIO()
            with mock.patch.object(self.baseline, "run_baseline") as runner, \
                    contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                try:
                    code = self.bench.main(arguments)
                except SystemExit as exc:
                    self.fail(f"missing-request structured refusal intercepted by argparse: {exc.code}")
            self.assertEqual(code, 1)
            self.assertEqual(stdout.getvalue(), "")
            self.assertTrue(stderr.getvalue().startswith("REFUSED: "))
            refusal = json.loads(stderr.getvalue()[len("REFUSED: "):])
            self.assertEqual(refusal["reason"], "pinned-request-required")
            self.assertNotIn("has no descriptor-bound", stderr.getvalue())
            runner.assert_not_called()

    def test_withdrawn_scoring_scaffold_is_not_reintroduced_by_private_transport(self):
        from tests.test_cognitive_claim_gate import PROVISIONAL_HELPERS, PROVISIONAL_CONSTANTS
        for name in PROVISIONAL_HELPERS + PROVISIONAL_CONSTANTS:
            with self.subTest(name=name):
                self.assertFalse(hasattr(self.bench, name))


class CognitivePrivateDispatch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sia = _load_script("sia_cognitive_private_dispatch", BIN / "sia")
        cls.bench = importlib.import_module("siabench")

    def test_exact_private_cognitive_dispatch_retains_lifecycle_without_resident_readiness_or_owner(self):
        events = []

        @contextlib.contextmanager
        def lifecycle():
            events.append("lifecycle-enter")
            try:
                yield
            finally:
                events.append("lifecycle-exit")

        arguments = ["cognitive", "--request", "/private/request.json", "--request-sha256", _sha(b"request"), "--out", "/private/output"]

        def dispatch(received):
            self.assertEqual(events, ["lifecycle-enter"])
            self.assertEqual(received, arguments)
            events.append("private-dispatch")
            return 0

        with mock.patch.object(self.sia.sialib, "_lifecycle_reader", side_effect=lifecycle), \
                mock.patch.object(self.sia.sialib, "corpus_owner", side_effect=AssertionError("resident owner acquired")) as owner, \
                mock.patch.object(self.sia.sialib, "memory_readiness", side_effect=AssertionError("resident readiness consulted")) as readiness, \
                mock.patch.object(self.bench, "main", side_effect=dispatch) as runner:
            self.assertEqual(self.sia.main(["sia", "bench", *arguments]), 0)
        self.assertEqual(events, ["lifecycle-enter", "private-dispatch", "lifecycle-exit"])
        runner.assert_called_once()
        owner.assert_not_called()
        readiness.assert_not_called()

    def test_other_bench_shapes_and_every_existing_memory_gate_remain_readiness_bound(self):
        self.assertIn("bench", self.sia.READINESS_GATED_COMMANDS)
        commands = [["sia", command] for command in sorted(self.sia.READINESS_GATED_COMMANDS)]
        commands += [["sia", "bench", name] for name in ("run", "generate", "score", "legacy")]
        commands += [["sia", "bench", "--out", "/private/output", "cognitive"],
                     ["sia", "bench", "run", "--skip-readiness"],
                     ["sia", "bench", "cognitive-extra"]]
        for arguments in commands:
            with self.subTest(arguments=arguments), \
                    mock.patch.object(self.sia.sialib, "_lifecycle_reader", return_value=contextlib.nullcontext()), \
                    mock.patch.object(self.sia.sialib, "corpus_owner", return_value=contextlib.nullcontext()) as owner, \
                    mock.patch.object(self.sia.sialib, "memory_readiness", return_value=(False, "unreconciled fixture")) as readiness, \
                    mock.patch.object(self.sia, "_dispatch") as dispatch, \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(self.sia.main(arguments), 1)
                owner.assert_called_once()
                readiness.assert_called_once()
                dispatch.assert_not_called()

    def test_private_dispatch_still_refuses_when_lifecycle_generation_is_unavailable(self):
        with mock.patch.object(self.sia.sialib, "_lifecycle_reader", side_effect=RuntimeError("generation unavailable")), \
                mock.patch.object(self.bench, "main") as runner, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(self.sia.main(["sia", "bench", "cognitive"]), 1)
        runner.assert_not_called()


if __name__ == "__main__":
    unittest.main()
