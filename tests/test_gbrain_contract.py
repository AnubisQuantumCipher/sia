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

import ast
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
# install.sh publishes the pack under this name; siacapsule re-validates it by
# name through gbrain's front door after a restore.
SCHEMA_PACK = "sia-pack"


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
        # anything is executed, or the lane would touch the operator's resident memory.
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

        # `schema validate <pack>` reads the pack from disk at exactly the path
        # install.sh writes it to, and the restore lane refuses when that
        # command returns non-zero (siacapsule._run_gbrain raises). Publish the
        # shipped pack here so that argv shape has the real file to validate.
        pack_dir = os.path.join(
            cls.sialib.SHARE, ".gbrain", "schema-packs", SCHEMA_PACK)
        os.makedirs(pack_dir, exist_ok=True)
        with open(os.path.join(REPO, "schema-pack", "pack.yaml"),
                  "r", encoding="utf-8") as stream:
            pack = stream.read()
        with open(os.path.join(pack_dir, "pack.yaml"), "w",
                  encoding="utf-8") as stream:
            stream.write(pack)

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

    def test_11_query_returns_a_json_list_on_stdout(self):
        # The hybrid-query result shape, unprobed until the argv gate below caught
        # it. Both readers (siabench._engine, siatakes._recall) parse it as
        # `stdout.index("[")` then a list of dicts carrying "slug" — and on a
        # brain without embeddings gbrain writes "vector search unavailable"
        # and degrades to keyword. That notice belongs on stderr: if it ever
        # moves onto stdout ahead of the list, both readers break, and this is
        # where that shows up.
        result = self.sialib.gbrain(
            ["query", PAGE_TOKEN, "--source", "sia", "--json"], timeout=120)
        self.assertEqual(result.returncode, 0, _output(result)[-300:])
        rows = json.loads(result.stdout[result.stdout.index("["):])
        self.assertIsInstance(rows, list, result.stdout[:300])
        self.assertIn(PAGE_SLUG, [row.get("slug") for row in rows
                                  if isinstance(row, dict)])

    def test_12_schema_validate_accepts_the_shipped_pack(self):
        # The restore lane's last act before declaring the projection live is
        # to re-validate the retained pack by name; a non-zero status there
        # aborts a restore on an operator's machine. If gbrain stops accepting
        # `schema-pack/pack.yaml` as written, it must fail in CI, not there.
        result = self.sialib.gbrain(
            ["schema", "validate", SCHEMA_PACK], timeout=60)
        self.assertEqual(result.returncode, 0, _output(result)[-300:])
        self.assertIn(SCHEMA_PACK, _output(result))


# ------------------------------------------------------- ROADMAP gate 3
#
# "Any new gbrain invocation shape lands with a probe in
# tests/test_gbrain_contract.py in the same commit" was a standing gate held by
# discipline alone: nothing failed when a shape shipped unprobed, which is the
# exact category the v1.7.5 audit converted to tests everywhere else. It had
# already been broken twice — `query`, the hybrid-retrieval lane both siabench
# and grading depend on, and `schema validate`, which the restore lane refuses
# on. The scan below reads argv out of the runtime's own AST instead of a
# hand-written list, so a shape cannot be added to bin/ without either a probe
# here or a red build.

_RUNTIME_EXECUTABLES = ("sia", "sia-brainstem", "sia-ledger", "sia-mcp")


def _module_name(path):
    name = os.path.basename(path)
    return name[:-3] if name.endswith(".py") else name


def _runtime_sources():
    """Exactly the Python CI compiles: bin/*.py plus the four executables."""
    names = {name for name in os.listdir(BIN) if name.endswith(".py")}
    names.update(_RUNTIME_EXECUTABLES)
    return [os.path.join(BIN, name) for name in sorted(names)]


def _leading_shape(elements):
    """The subcommand path of an argv list: its leading literal words.

    Stops at the first flag or non-literal, because that is where a shape stops
    being a shape: ``["embed", slug, "--source", ...]`` is the ``embed`` shape
    however the slug is computed. A leading flag is its own shape, which is how
    ``["--version"]`` stays visible.
    """
    shape = []
    for node in elements:
        if not (isinstance(node, ast.Constant)
                and isinstance(node.value, str)):
            break
        if node.value.startswith("-"):
            if not shape:
                shape.append(node.value)
            break
        shape.append(node.value)
    return tuple(shape)


def _is_binary_vector(node):
    """A list whose first element is the gbrain binary path."""
    if not (isinstance(node, ast.List) and node.elts):
        return False
    first = node.elts[0]
    return ((isinstance(first, ast.Name) and first.id == "GBRAIN")
            or (isinstance(first, ast.Attribute) and first.attr == "GBRAIN"))


def _argv_tail(node):
    """The argv of a ``[GBRAIN, ...]`` process vector, or None."""
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        # sialib.gbrain: [GBRAIN] + args
        if _is_binary_vector(node.left) and len(node.left.elts) == 1:
            return node.right
        return None
    if _is_binary_vector(node):
        rest = node.elts[1:]
        # siacapsule._run_gbrain: [sialib.GBRAIN, *args]
        if len(rest) == 1 and isinstance(rest[0], ast.Starred):
            return rest[0].value
        return ast.List(elts=rest, ctx=ast.Load())
    return None


_NESTED_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)


def _own_body(node):
    """Every node in this scope, not descending into a nested scope.

    Pruning has to happen on the way in as well as on the way down: a module
    body is mostly ``def``s, and walking into them from the module scope would
    read every function's argv with none of its parameters in hand.
    """
    stack = [child for child in getattr(node, "body", [])
             if not isinstance(child, _NESTED_SCOPES)]
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        stack.extend(node.args.defaults)
    seen = []
    while stack:
        current = stack.pop()
        seen.append(current)
        for child in ast.iter_child_nodes(current):
            if isinstance(child, _NESTED_SCOPES):
                continue
            stack.append(child)
    return seen


def _callee(node):
    """(module hint, function name) for a call target, or (None, None)."""
    if isinstance(node, ast.Name):
        return None, node.id
    if isinstance(node, ast.Attribute):
        value = node.value
        if isinstance(value, ast.Name):
            return value.id, node.attr
        if isinstance(value, ast.Attribute):
            return value.attr, node.attr
        return None, node.attr
    return None, None


class _Scope:
    """One function (or module) body, with the names bound inside it."""

    def __init__(self, module, name, node):
        self.module = module
        self.name = name
        self.params = {}
        self.name_lists = {}
        self.calls = []
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            positional = list(node.args.posonlyargs) + list(node.args.args)
            for index, argument in enumerate(positional):
                self.params[argument.arg] = index
            for argument in node.args.kwonlyargs:
                self.params.setdefault(argument.arg, None)
        for child in _own_body(node):
            self._absorb(child)

    def _absorb(self, node):
        if isinstance(node, ast.Call):
            hint, name = _callee(node.func)
            tail = _argv_tail(node.args[0]) if node.args else None
            self.calls.append((node, hint, name, tail))
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self._bind(target.id, [node.value])
        elif isinstance(node, (ast.For, ast.AsyncFor)):
            # `for argv in (["init", ...], ["sync", ...])` is how this lane's
            # own bootstrap states three shapes; a scan that could not read it
            # would report the bootstrap as unprobed.
            if isinstance(node.target, ast.Name):
                values = (list(node.iter.elts)
                          if isinstance(node.iter, (ast.Tuple, ast.List))
                          else [node.iter])
                self._bind(node.target.id, values)

    def _bind(self, name, values):
        literals = [value for value in values if isinstance(value, ast.List)]
        if literals:
            self.name_lists.setdefault(name, []).extend(literals)


class _GbrainArgvScan:
    """Static enumeration of the gbrain argv shapes a source tree uses.

    Two kinds of function reach the binary and both are *discovered*, never
    listed: an **emitter** contains a call whose argv resolves to a fixed
    subcommand path, and a **forwarder** passes one of its own parameters
    through as argv (``sialib.gbrain``, ``siacapsule._run_gbrain``,
    ``siabench._engine``, ``sia._gbrain_read``). Discovery runs to a fixpoint
    so a wrapper around a wrapper is still read.
    """

    _MAX_PASSES = 16

    def __init__(self):
        self.scopes = []
        self.emitters = {}
        self.forwarders = {}

    def load(self, paths):
        for path in paths:
            with open(path, "r", encoding="utf-8") as stream:
                tree = ast.parse(stream.read(), filename=path)
            module = _module_name(path)
            self.scopes.append(_Scope(module, None, tree))
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    self.scopes.append(_Scope(module, node.name, node))
        for _ in range(self._MAX_PASSES):
            before = self._fingerprint()
            self._sweep(None)
            if self._fingerprint() == before:
                return self
        raise AssertionError(
            "the gbrain argv registry did not stabilize, so this gate cannot "
            "state which shapes the runtime uses")

    def _fingerprint(self):
        return (sorted(self.forwarders),
                sorted((key, tuple(sorted(value)))
                       for key, value in self.emitters.items()))

    def shapes(self, modules):
        """(shapes used by these modules, unreadable call sites in them)."""
        return self._sweep(set(modules))

    def _entry(self, hint, name, module):
        for key in ((hint, name), (module, name)):
            if key in self.forwarders or key in self.emitters:
                return key
        if hint is not None:
            return None
        matches = [key for key in set(self.forwarders) | set(self.emitters)
                   if key[1] == name]
        return matches[0] if len(matches) == 1 else None

    def _sweep(self, modules):
        shapes, unreadable = set(), []
        for scope in self.scopes:
            mine = modules is None or scope.module in modules
            for node, hint, name, tail in scope.calls:
                direct = tail is not None
                if direct:
                    argv = tail
                else:
                    key = self._entry(hint, name, scope.module)
                    if key is None:
                        continue
                    if key in self.emitters:
                        self._record(scope, node, self.emitters[key], False)
                        if mine:
                            shapes |= self.emitters[key]
                        continue
                    argv = _argument_for(node, self.forwarders[key])
                    if argv is None:
                        if mine:
                            unreadable.append(_site(scope, node))
                        continue
                found, forwarded = self._resolve(argv, scope)
                if forwarded is not None:
                    if scope.name is not None:
                        self.forwarders.setdefault(
                            (scope.module, scope.name), forwarded)
                    continue
                if not found:
                    if mine:
                        unreadable.append(_site(scope, node))
                    continue
                self._record(scope, node, found, True)
                if mine:
                    shapes |= found
        return shapes, sorted(unreadable)

    def _resolve(self, node, scope):
        """(shapes, forwarded parameter) for an argv expression."""
        if isinstance(node, ast.Starred):
            node = node.value
        if isinstance(node, ast.List):
            shape = _leading_shape(node.elts)
            return ({shape} if shape else None), None
        if isinstance(node, ast.Name):
            if node.id in scope.params:
                return None, (node.id, scope.params[node.id])
            found = set()
            for literal in scope.name_lists.get(node.id, ()):
                shape = _leading_shape(literal.elts)
                if shape:
                    found.add(shape)
            return (found or None), None
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            return self._resolve(node.left, scope)
        return None, None

    def _record(self, scope, node, shapes, direct):
        """Register the enclosing function as an emitter of these shapes.

        A call to an emitter only makes its caller an emitter when the caller
        hands over its own parameters — that is what a façade like
        ``sialib.gbrain_call`` is, and it stops the registry from swallowing
        every function that happens to sit above one.
        """
        key = (scope.module, scope.name)
        if scope.name is None or key in self.forwarders:
            return
        if not direct and not _forwards_params(node, scope):
            return
        self.emitters.setdefault(key, set()).update(shapes)


def _argument_for(node, parameter):
    name, index = parameter
    for keyword in node.keywords:
        if keyword.arg == name:
            return keyword.value
    if index is not None and index < len(node.args):
        return node.args[index]
    return None


def _forwards_params(node, scope):
    values = list(node.args) + [keyword.value for keyword in node.keywords]
    return any(isinstance(value, ast.Name) and value.id in scope.params
               for value in values)


def _site(scope, node):
    return f"{scope.module}:{node.lineno} in {scope.name or '<module>'}"


def _covers(probed, used):
    """A probe covers a shape when it is at least as specific.

    ``["schema", "validate", SCHEMA_PACK]`` here and
    ``["schema", "validate", _GBRAIN_SCHEMA_PACK_NAME]`` in siacapsule read as
    the same subcommand path through different constants, so coverage is a
    prefix relation and never the reverse: probing ``sources`` would not cover
    ``sources add``.
    """
    return any(shape[:len(used)] == used for shape in probed)


class GbrainArgvGate(unittest.TestCase):
    """ROADMAP standing gate 3, enforced rather than trusted.

    Static only: no binary, no brain, so this runs in the ordinary unit lane
    where the contract probes above honestly skip.
    """

    @classmethod
    def setUpClass(cls):
        contract = os.path.abspath(__file__)
        cls.scan = _GbrainArgvScan().load(_runtime_sources() + [contract])
        cls.used, cls.used_unreadable = cls.scan.shapes(
            {_module_name(path) for path in _runtime_sources()})
        cls.probed, cls.probed_unreadable = cls.scan.shapes(
            {_module_name(contract)})

    def test_20_every_call_site_is_readable(self):
        # A shape the scan cannot see is a shape this gate does not guard, so
        # an unreadable argv is a failure and never a quiet pass. The fix is to
        # give the call site a literal argv, not to widen the scan.
        self.assertEqual(
            self.used_unreadable, [],
            "gbrain argv that this gate cannot read (make it a literal list "
            "or a local list assignment): "
            + ", ".join(self.used_unreadable))
        self.assertEqual(
            self.probed_unreadable, [],
            "unreadable argv in this lane's own probes: "
            + ", ".join(self.probed_unreadable))

    def test_21_the_scan_reads_the_shapes_already_known_to_ship(self):
        # Guards the gate itself: a scan that silently found nothing would
        # make the coverage assertion below vacuously true. These shapes are
        # all present in bin/ today and were read by hand from it.
        for shape in (("--version",), ("init",), ("sources", "add", "sia"),
                      ("sources", "list"), ("sync",), ("extract", "links"),
                      ("engine", "status"), ("get",), ("query",), ("search",),
                      ("embed",), ("dream",), ("call",), ("context-pack",),
                      ("schema", "validate")):
            self.assertIn(shape, self.used,
                          f"the scan stopped reading {shape}")
        self.assertGreaterEqual(len(self.used), 15)

    def test_22_every_shipped_shape_has_a_probe_in_this_file(self):
        missing = sorted(shape for shape in self.used
                         if not _covers(self.probed, shape))
        self.assertEqual(
            missing, [],
            "gbrain invocation shapes used by bin/ with no probe in this "
            "file (ROADMAP standing gate 3): "
            + ", ".join(" ".join(shape) for shape in missing))

    def test_23_installed_descriptor_transport_is_actually_discovered(self):
        # A prefix already exercised by a different call must not hide this
        # descriptor emitter from the scanner. The real compiled contract
        # above separately checks exact no-migrate argv and projection receipt.
        self.assertIn(("siainstalledengine", "_run_installed_gbrain"), self.scan.forwarders)
        self.assertEqual(
            self.scan.emitters.get(("siainstalledengine", "version")),
            {("--version",)})
        self.assertEqual(
            self.scan.emitters.get(("siainstalledengine", "project")),
            {("call",)})
        self.assertEqual(
            self.scan.emitters.get(("siainstalledengine", "get")),
            {("get",)})
        used, unreadable = self.scan.shapes({"siainstalledengine"})
        self.assertEqual(unreadable, [])
        self.assertEqual(used, {("--version",), ("get",), ("call",)})
        # Existing pathname GET probes cannot satisfy this call-site check.
        # The actual compiled fixture must call the discovered held emitter.
        probe = "test_compiled_candidate_exact_get_receipt_through_held_sia_transport"
        scopes = [scope for scope in self.scan.scopes
                  if scope.module == _module_name(__file__) and scope.name == probe]
        self.assertEqual([scope.name for scope in scopes], [probe])
        self.assertEqual(
            [(hint, name) for scope in scopes for _node, hint, name, _tail in scope.calls
             if hint == "siainstalledengine" and name == "get"],
            [("siainstalledengine", "get")])

"""PRIVATE actual compiled transport probe, not yet executed.

Admission destination: append this fragment before __main__ in the existing
tests/test_gbrain_contract.py. Do not add a second discoverable imported class:
that would run this expensive real-PGLite fixture twice in full discovery.

Absent opt-in skips an UNEXERCISED lane. Once selected, missing/invalid files,
unavailable API, CLI errors and unsupported operations FAIL; no skip fallback.
The external expectation document and its caller-supplied hash authorize the
candidate. Candidate receipts never choose their own acceptable digests.
"""

import contextlib
import datetime
import errno
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

try:
    import sia_test_home
except ModuleNotFoundError:
    from tests import sia_test_home


_CR_REPO = (Path(__file__).resolve().parents[1]
            if Path(__file__).parent.name == "tests"
            else Path("/home/sicarii/Projects/sia"))
_CR_SOURCE = "sia"
_CR_SUBJECT = "notes/projection"
# An intentionally unregistered routing name, not another database fixture.
_CR_HOSTILE_MOUNT_BYTES = b"sia-fixture-unregistered\n"
_CR_OPERATION = "get_page_render_projection"
_CR_SCHEMA = "sia-compiled-render-contract-expectations-v1"
_CR_PIN_KEYS = {"commit", "version", "bun_lock_sha256", "overlay_sha256",
                "overlay_tree_oid", "verified"}
_CR_DIGEST_KEYS = {"base_pin_sha256", "gbrain_pin_sha256",
                   "gbrain_runtime_receipt_sha256", "gbrain_executable_sha256",
                   "bun_lock_sha256", "overlay_sha256"}
_CR_LIMIT_KEYS = {"max_executable_bytes", "max_metadata_bytes",
                  "max_request_bytes", "max_output_bytes"}
_CR_INPUT_ENV = {
    "base_pin": "SIA_GBRAIN_PIN",
    "candidate_pin": "SIA_GBRAIN_CANDIDATE_PIN",
    "runtime_receipt": "SIA_GBRAIN_CANDIDATE_RUNTIME_RECEIPT",
    "binary": "SIA_GBRAIN_CANDIDATE_BIN",
    "overlay": "SIA_GBRAIN_CANDIDATE_OVERLAY",
}
# Identical synthetic raw/golden premises to the separately frozen interpreted
# CLI lane. No source parser, serializer, handler or engine result is mocked.
_CR_RAW = ("---\n# source comment must not leak into canonical GET\n"
           "title: 'Projection café'\ntype: note\norigin: model\n"
           "captured_at: 'retained-before'\ntags: [zeta, alpha]\n---\n\n"
           "A retained body with café and cafe\u0301.\n\n"
           "<!-- timeline -->\n\n- Fixture timeline, not machine history.\n")
_CR_GET = ("---\ntype: note\ntitle: Projection café\norigin: model\n"
           "captured_at: retained-before\ntags:\n  - alpha\n  - zeta\n---\n\n"
           "A retained body with café and cafe\u0301.\n\n"
           "<!-- timeline -->\n\n- Fixture timeline, not machine history.\n")
_CR_RECEIPT_KEYS = {
    "schema", "status", "source_id", "source_reference", "get_stdout_sha256",
    "page_state", "parse_error_codes", "type_basis", "expected_projection_sha256",
    "current_projection_sha256", "current_content_hash", "current_content_hash_match",
    "projection_match", "display_fields_match", "current_get_stdout_sha256",
    "get_stdout_match", "mismatch_reasons", "retrieval_bookkeeping_updated",
    "operation_writes_performed", "non_claims",
}
_CR_GET_TRANSPORT_KEYS = {
    "schema", "status", "operation", "source_id", "subject", "binding_sha256",
    "expected_expectations_sha256", "request_sha256", "returncode", "timeout",
    "stdout", "stderr", "stdout_sha256", "stderr_sha256", "non_claims",
    "transport_sha256",
}


def _cr_canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def _cr_sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _cr_identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _cr_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise AssertionError("duplicate external JSON key")
        result[key] = value
    return result


def _cr_json(raw):
    return json.loads(raw.decode("utf-8", "strict"), object_pairs_hook=_cr_object,
                      parse_constant=lambda _value: (_ for _ in ()).throw(
                          AssertionError("nonfinite external JSON")))


class _CRArtifact:
    """Retain supplied files across comparison/copy; never execute originals."""

    def __init__(self, path, ceiling, expected=None, *, executable=False):
        self.fd = None
        if type(path) is not str or not os.path.isabs(path) \
                or os.path.realpath(path) != path:
            raise AssertionError("candidate artifact requires explicit canonical absolute path")
        self.path = path
        try:
            self.fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK)
            before = os.fstat(self.fd)
            if not stat.S_ISREG(before.st_mode) or before.st_uid != os.geteuid() \
                    or before.st_mode & 0o022 or before.st_nlink != 1 \
                    or not 0 < before.st_size <= ceiling:
                raise AssertionError("candidate artifact is not owned, regular and bounded")
            if executable and (not before.st_mode & 0o111
                               or os.pread(self.fd, 4, 0) != b"\x7fELF"):
                raise AssertionError("selected candidate is not an executable ELF")
            self.identity = _cr_identity(before)
            digest = hashlib.sha256()
            offset = 0
            while offset < before.st_size:
                block = os.pread(self.fd, min(1_048_576, before.st_size - offset), offset)
                if not block:
                    raise AssertionError("short candidate artifact read")
                digest.update(block)
                offset += len(block)
            self.sha256 = digest.hexdigest()
            if expected is not None and self.sha256 != expected:
                raise AssertionError("selected candidate differs from external expectation")
            self.current()
        except BaseException:
            self.close()
            raise

    def current(self):
        if self.fd is None or _cr_identity(os.fstat(self.fd)) != self.identity \
                or _cr_identity(os.stat(self.path, follow_symlinks=False)) != self.identity:
            raise AssertionError("supplied artifact changed during compiled fixture")

    def read_metadata(self):
        self.current()
        raw = os.pread(self.fd, self.identity[6], 0)
        self.current()
        if _cr_sha(raw) != self.sha256:
            raise AssertionError("supplied metadata changed")
        return raw

    def copy_to(self, destination, *, executable=False):
        self.current()
        digest = hashlib.sha256()
        offset = 0
        with open(destination, "xb") as stream:
            while offset < self.identity[6]:
                block = os.pread(self.fd, min(1_048_576, self.identity[6] - offset), offset)
                if not block:
                    raise AssertionError("candidate disappeared during real copy")
                stream.write(block)
                digest.update(block)
                offset += len(block)
        os.chmod(destination, 0o755 if executable else 0o600)
        self.current()
        if digest.hexdigest() != self.sha256:
            raise AssertionError("copied candidate differs from admitted bytes")

    def close(self):
        descriptor, self.fd = self.fd, None
        if descriptor is not None:
            os.close(descriptor)


def _cr_pin(raw):
    result = {}
    for line in raw.decode("utf-8", "strict").splitlines():
        if not line or line.startswith("#"):
            continue
        if line.count("=") != 1:
            raise AssertionError("candidate pin assignment malformed")
        key, value = line.split("=", 1)
        if key not in _CR_PIN_KEYS or key in result:
            raise AssertionError("candidate pin closed shape failed")
        result[key] = value
    if set(result) != _CR_PIN_KEYS:
        raise AssertionError("candidate pin is incomplete")
    return result


def _cr_selected_inputs(stack, lib, structural):
    # Hash comes from the operator/build invocation, NOT the JSON under review.
    path = os.environ.get("SIA_GBRAIN_COMPILED_EXPECTATIONS")
    expected = os.environ.get("SIA_GBRAIN_COMPILED_EXPECTATIONS_SHA256")
    if type(expected) is not str or re.fullmatch(r"[0-9a-f]{64}", expected) is None:
        raise AssertionError("explicit compiled expectation hash is mandatory")

    def retain(path, ceiling, expected=None, **kwargs):
        artifact = _CRArtifact(path, ceiling, expected, **kwargs)
        stack.callback(artifact.close)
        return artifact

    document = retain(path, lib.MAX_CONFIG_BYTES, expected)
    raw = document.read_metadata()
    value = _cr_json(raw)
    keys = {"schema", "limits", *_CR_PIN_KEYS, *_CR_DIGEST_KEYS}
    if type(value) is not dict or set(value) != keys or _cr_canonical(value) != raw \
            or value["schema"] != _CR_SCHEMA:
        raise AssertionError("external compiled expectation closed/canonical shape failed")
    for key in _CR_DIGEST_KEYS:
        if type(value[key]) is not str or re.fullmatch(r"[0-9a-f]{64}", value[key]) is None:
            raise AssertionError("external compiled digest malformed")
    for key in ("commit", "overlay_tree_oid"):
        if type(value[key]) is not str or re.fullmatch(r"[0-9a-f]{40}", value[key]) is None:
            raise AssertionError("external compiled OID malformed")
    if type(value["version"]) is not str \
            or re.fullmatch(r"(?:0|[1-9][0-9]*)(?:\.(?:0|[1-9][0-9]*))+", value["version"]) is None \
            or type(value["verified"]) is not str:
        raise AssertionError("external compiled version/date malformed")
    try:
        date = datetime.date.fromisoformat(value["verified"])
    except ValueError as exc:
        raise AssertionError("external compiled verified date malformed") from exc
    if date.isoformat() != value["verified"]:
        raise AssertionError("external compiled verified date is not canonical")
    limits = value["limits"]
    ceilings = {"max_executable_bytes": structural.MAX_EXECUTABLE_BYTES,
                "max_metadata_bytes": lib.MAX_CONFIG_BYTES,
                "max_request_bytes": structural.MAX_PROJECTION_REQUEST_BYTES,
                "max_output_bytes": lib.MAX_EXTERNAL_OUTPUT_BYTES}
    if type(limits) is not dict or set(limits) != _CR_LIMIT_KEYS \
            or any(type(limits[key]) is not int or not 0 < limits[key] <= ceiling
                   for key, ceiling in ceilings.items()):
        raise AssertionError("external compiled byte ceiling malformed")
    artifacts = {"expectations": document}
    for name, variable in _CR_INPUT_ENV.items():
        key = {"base_pin": "base_pin_sha256", "candidate_pin": "gbrain_pin_sha256",
               "runtime_receipt": "gbrain_runtime_receipt_sha256",
               "binary": "gbrain_executable_sha256", "overlay": "overlay_sha256"}[name]
        ceiling = (limits["max_executable_bytes"] if name == "binary"
                   else structural.MAX_PROJECTION_REQUEST_BYTES if name == "overlay"
                   else limits["max_metadata_bytes"])
        artifacts[name] = retain(os.environ.get(variable), ceiling, value[key],
                                 executable=name == "binary")
    base = _cr_pin(artifacts["base_pin"].read_metadata())
    if any(base[key] != value[key] for key in ("commit", "version", "bun_lock_sha256")):
        raise AssertionError("candidate does not retain explicitly admitted base")
    if _cr_pin(artifacts["candidate_pin"].read_metadata()) != {
            key: value[key] for key in _CR_PIN_KEYS}:
        raise AssertionError("candidate pin is not the externally expected overlay/build")
    runtime = ("managed-by=khephri.sia\n" + "".join(
        key + "=" + value[key] + "\n" for key in (
            "commit", "version", "bun_lock_sha256", "overlay_sha256", "overlay_tree_oid"))
        + "binary_sha256=" + value["gbrain_executable_sha256"] + "\n").encode("utf-8")
    if artifacts["runtime_receipt"].read_metadata() != runtime:
        raise AssertionError("candidate runtime receipt is not the externally expected exact build record")
    return value, artifacts


class _CRFixture:
    def __init__(self, case, stack, lib, selected, artifacts):
        self.case, self.lib = case, lib
        self.selected, self.artifacts = selected, artifacts
        self.root = Path(stack.enter_context(tempfile.TemporaryDirectory(
            prefix="sia-compiled-render-", dir=sia_test_home.ISOLATED_HOME)))
        self.share, self.state = self.root / "share", self.root / "state"
        self.corpus = self.share / "corpus"
        self.toolchain = self.share / "toolchain"
        self.engine = self.toolchain / "gbrain/bin/gbrain"
        self.pin = self.share / "GBRAIN_PIN"
        self.runtime = self.toolchain / "gbrain/.sia-release"
        self.pin_receipt = self.state / "managed-install/gbrain-pin"
        self.corpus.mkdir(parents=True)
        self.engine.parent.mkdir(parents=True)
        self.pin_receipt.parent.mkdir(parents=True)
        artifacts["binary"].copy_to(self.engine, executable=True)
        artifacts["candidate_pin"].copy_to(self.pin)
        artifacts["runtime_receipt"].copy_to(self.runtime)
        # This receipt has an unavoidable fixture-local path. Its pin digest
        # is independently admitted above; this is NOT new build evidence.
        local_receipt = ("managed-by=khephri.sia\nkind=gbrain-pin\n"
                         f"path={self.pin}\nsha256={selected['gbrain_pin_sha256']}\n").encode("utf-8")
        self.pin_receipt.write_bytes(local_receipt)
        self.pin_receipt.chmod(0o600)
        self.expectations = {
            "schema": "sia-installed-overlay-engine-expectations-v1", "source_id": _CR_SOURCE,
            **{key: selected[key] for key in _CR_PIN_KEYS},
            "gbrain_pin_sha256": selected["gbrain_pin_sha256"],
            "gbrain_pin_receipt_sha256": _cr_sha(local_receipt),
            "gbrain_runtime_receipt_sha256": selected["gbrain_runtime_receipt_sha256"],
            "gbrain_executable_sha256": selected["gbrain_executable_sha256"],
            "limits": dict(selected["limits"]),
        }
        self.expected_expectations_sha256 = _cr_sha(_cr_canonical(self.expectations))
        values = {
            "HOME": self.root, "SHARE": self.share, "STATE": self.state,
            "CORPUS": self.corpus, "TOOLCHAIN": self.toolchain,
            "BUN_DIR": self.toolchain / "bun/bin", "GBRAIN": self.engine,
            "GBRAIN_PIN": self.pin, "GBRAIN_PIN_RECEIPT": self.pin_receipt,
            "GBRAIN_RUNTIME_RECEIPT": self.runtime,
            "GBRAIN_OWNER_LOCK": self.state / "gbrain-owner.lock",
            "CORPUS_OWNER_LOCK": self.state / "corpus-owner.lock",
            "LIFECYCLE_LOCK": self.state / "lifecycle.lock",
            "LIFECYCLE_TOMBSTONE": self.state / "lifecycle-removed",
            "RESTORE_BARRIER_PATH": self.state / "restore.json",
            "RESTORE_MASK_PATH": self.state / "restore-mask",
            "RESTORE_SUPERVISOR_PATH": self.state / "restore-supervisor.json",
        }
        for key, value in values.items():
            stack.enter_context(mock.patch.object(lib, key, str(value), create=True))
        stack.enter_context(mock.patch.object(lib, "GBRAIN_SOURCE", _CR_SOURCE))
        self.env = {
            "HOME": str(self.root), "GBRAIN_HOME": str(self.share), "GBRAIN_BRAIN_ID": "host",
            "TMPDIR": str(self.state), "PATH": "/usr/bin:/bin", "BUN_OPTIONS": "--no-env-file",
            "GBRAIN_SELF_UPGRADE_MODE": "off", "GBRAIN_SKIP_STARTUP_HOOKS": "1",
            "GBRAIN_SYNC_NO_DELEGATE": "1", "DO_NOT_TRACK": "1", "NO_COLOR": "1",
            "GBRAIN_NO_BANNER": "1", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "TZ": "UTC",
            "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_TERMINAL_PROMPT": "0",
        }
        stack.enter_context(mock.patch.object(lib, "GBRAIN_ENV", self.env))
        self.git(["-c", "init.templateDir=", "init", "-q"])
        self.page = self.corpus / (_CR_SUBJECT + ".md")
        self.page.parent.mkdir(parents=True)
        self.page.write_bytes(_CR_RAW.encode("utf-8"))
        self.git(["add", "--", _CR_SUBJECT + ".md"])
        self.git(["-c", "user.name=compiled-render-fixture",
                  "-c", "user.email=projection@example.invalid",
                  "commit", "-qm", "synthetic exact source for compiled transport"])
        self.head = self.git(["rev-parse", "HEAD"])
        case.assertEqual(self.git(["show", "HEAD:" + _CR_SUBJECT + ".md"]), _CR_RAW)
        self.page_identity = _cr_identity(self.page.stat())
        # The SAME private corpus/index now lives under an adversarial
        # ancestor marker. Setup commands explicitly select host already;
        # the held GET transport must independently do so as well. Never
        # register this name or write another DB/config for the control.
        marker = self.share / ".gbrain-mount"
        with marker.open("xb") as stream:
            stream.write(_CR_HOSTILE_MOUNT_BYTES)
        marker.chmod(0o600)
        self.mount_marker = _CRArtifact(
            str(marker), lib.MAX_CONFIG_BYTES, _cr_sha(_CR_HOSTILE_MOUNT_BYTES))
        stack.callback(self.mount_marker.close)
        case.assertEqual(marker.parent, self.corpus.parent)
        case.assertFalse(os.path.lexists(self.corpus / ".gbrain-mount"))
        case.assertFalse(os.path.lexists(self.root / ".gbrain/mounts.json"))

    def git(self, args):
        result = subprocess.run(
            ["/usr/bin/git", "--no-replace-objects", "-c", "core.hooksPath=/dev/null",
             "-c", "commit.gpgsign=false", *args], cwd=self.corpus, env=self.env,
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="strict", timeout=180, check=False)
        self.case.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def cli(self, args):
        sialib = self.lib  # module-qualified spelling joins the existing argv scan.
        result = sialib.gbrain(args, timeout=180)
        self.case.assertEqual(result.returncode, 0, f"{args!r}: {result.stderr}")
        return result.stdout

    def authority_current(self):
        # This is fixture artifact/source authority, not a source-generation or
        # database truth claim. The actual transport separately holds artifacts.
        for artifact in self.artifacts.values():
            artifact.current()
        self.mount_marker.current()
        self.case.assertEqual(self.mount_marker.read_metadata(), _CR_HOSTILE_MOUNT_BYTES)
        self.case.assertFalse(os.path.lexists(self.corpus / ".gbrain-mount"))
        self.case.assertFalse(os.path.lexists(self.root / ".gbrain/mounts.json"))
        self.case.assertEqual(_cr_identity(self.page.stat()), self.page_identity)
        self.case.assertEqual(self.page.read_bytes(), _CR_RAW.encode("utf-8"))
        return None


class GbrainCompiledRenderContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        selected = os.environ.get("SIA_GBRAIN_COMPILED_RENDER")
        if selected is None:
            raise unittest.SkipTest(
                "compiled render transport NOT EXERCISED: select SIA_GBRAIN_COMPILED_RENDER=1 "
                "and independently pinned candidate artifacts; this skip is not proof")
        if selected != "1":
            raise AssertionError("SIA_GBRAIN_COMPILED_RENDER must be exactly 1 when supplied")

    def test_compiled_candidate_exact_get_receipt_through_held_sia_transport(self):
        sys.path.insert(0, str(_CR_REPO / "bin"))
        import siainstalledengine as installed
        import siasourceengine as structural
        spec = importlib.util.spec_from_file_location(
            "sialib_compiled_render_contract", _CR_REPO / "bin/sialib.py")
        lib = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(lib)
        self.assertTrue(str(lib.SHARE).startswith(sia_test_home.ISOLATED_HOME + os.sep))
        self.assertTrue(callable(getattr(installed, "hold_overlay_engine", None)))
        self.assertTrue(callable(getattr(installed._Engine, "get", None)),
                        "missing actual installed-engine GET transport")
        with contextlib.ExitStack() as stack:
            selected, artifacts = _cr_selected_inputs(stack, lib, structural)
            fixture = _CRFixture(self, stack, lib, selected, artifacts)
            with lib.corpus_owner() as caller_fd:
                caller_identity = _cr_identity(os.fstat(caller_fd))
                # Real CLI front doors initialize/index only this fresh private
                # corpus. No direct database/config write or ordinary store read.
                database = str(fixture.share / ".gbrain/brain.pglite")
                fixture.cli(args=["init", "--pglite", "--non-interactive", "--json",
                             "--skip-embed-check", "--path", database, "--no-embedding"])
                fixture.cli(args=["sources", "add", "sia", "--path", str(fixture.corpus)])
                fixture.cli(args=["sync", "--source", "sia", "--no-pull", "--no-embed", "--no-extract"])
                fixture.cli(args=["config", "set", "search.track_retrieval", "false"])
                actual_get = fixture.cli(args=["get", _CR_SUBJECT, "--source", "sia"])
                fixture.cli(args=["config", "set", "search.track_retrieval", "true"])
                self.assertEqual(actual_get, _CR_GET)
                self.assertNotEqual(actual_get, _CR_RAW)
                calls = []
                get_descriptor_observations = []
                real_process = lib._run_bounded_text_process

                def observed_process(command, **kwargs):
                    # Observation wraps and delegates the actual bounded process;
                    # never supplies a CompletedProcess or fabricated stdout.
                    self.assertEqual(lib._CORPUS_OWNER_FD.get(), caller_fd)
                    self.assertGreater(lib._CORPUS_OWNER_DEPTH.get(), 0)
                    engine_fd = lib._GBRAIN_OWNER_FD.get()
                    self.assertIs(type(engine_fd), int)
                    self.assertEqual(os.fstat(engine_fd).st_ino,
                                     os.stat(lib.GBRAIN_OWNER_LOCK).st_ino)
                    descriptors = kwargs["pass_fds"]
                    self.assertIn(caller_fd, descriptors)
                    self.assertIn(engine_fd, descriptors)
                    self.assertTrue(command[0].startswith("/proc/self/fd/"))
                    executable_fd = int(command[0].rsplit("/", 1)[1])
                    self.assertIn(executable_fd, descriptors)
                    self.assertEqual(_cr_identity(os.fstat(executable_fd)),
                                     _cr_identity(fixture.engine.stat()))
                    self.assertEqual(os.stat(kwargs["cwd"]).st_ino, fixture.corpus.stat().st_ino)
                    self.assertEqual(kwargs["env"]["GBRAIN_HOME"], str(fixture.share))
                    self.assertNotIn("GBRAIN_DATABASE_URL", kwargs["env"])
                    self.assertNotIn("DATABASE_URL", kwargs["env"])
                    self.assertNotIn("GBRAIN_SOURCE", kwargs["env"])
                    is_get = command[1:2] == ["get"]
                    get_descriptors = None
                    if is_get:
                        self.assertEqual(command[1:],
                                         ["get", _CR_SUBJECT, "--source", "sia"])
                        self.assertTrue(kwargs["cwd"].startswith("/proc/self/fd/"))
                        corpus_fd = int(kwargs["cwd"].rsplit("/", 1)[1])
                        self.assertEqual(tuple(descriptors),
                                         (executable_fd, corpus_fd, caller_fd, engine_fd))
                        self.assertEqual(os.fstat(corpus_fd).st_ino,
                                         fixture.corpus.stat().st_ino)
                        self.assertEqual(kwargs["timeout"], 180)
                        self.assertEqual(kwargs["output_limit"],
                                         fixture.expectations["limits"]["max_output_bytes"])
                        # Observe only inherited descriptors, without any
                        # syscall replacement or newly opened test descriptor.
                        # Directory identity excludes ordinary metadata churn.
                        get_descriptors = tuple(
                            (descriptor, (info.st_dev, info.st_ino, info.st_mode,
                                          info.st_uid, info.st_gid))
                            for descriptor in descriptors
                            for info in (os.fstat(descriptor),))
                        self.assertEqual(
                            list(fixture.state.glob("sia-installed-projection-*")), [])
                    elif command[1:] != ["--version"]:
                        self.assertEqual(command[1:6], ["call", "--no-migrate", "--source",
                                                       "sia", "--params-file"])
                        self.assertEqual(command[7:], [_CR_OPERATION])
                        request_path = command[6]
                        directory_path, leaf = request_path.rsplit("/", 1)
                        self.assertEqual(leaf, "request.json")
                        self.assertTrue(directory_path.startswith("/proc/self/fd/"))
                        request_directory_fd = int(directory_path.rsplit("/", 1)[1])
                        self.assertIn(request_directory_fd, descriptors)
                        self.assertEqual(stat.S_IMODE(os.fstat(request_directory_fd).st_mode), 0o700)
                        request_stat = os.stat(leaf, dir_fd=request_directory_fd, follow_symlinks=False)
                        self.assertTrue(stat.S_ISREG(request_stat.st_mode))
                        self.assertEqual(stat.S_IMODE(request_stat.st_mode), 0o600)
                        self.assertEqual(Path(request_path).read_bytes(), current_request)
                    result = real_process(command, **kwargs)
                    if is_get:
                        # Check after the REAL child. Before the production
                        # host fix this must expose its Unknown brain stderr,
                        # not fail an environment assertion before execution.
                        self.assertEqual(result.returncode, 0, result.stderr)
                        self.assertEqual(kwargs["env"].get("GBRAIN_BRAIN_ID"), "host")
                        self.assertNotIn("GBRAIN_MOUNTS_PATH", kwargs["env"])
                        fixture.mount_marker.current()
                        self.assertEqual(fixture.mount_marker.read_metadata(),
                                         _CR_HOSTILE_MOUNT_BYTES)
                        # This is the actual returning child, not a fabricated
                        # CompletedProcess. The same native FDs must survive it.
                        for descriptor, identity in get_descriptors:
                            info = os.fstat(descriptor)
                            self.assertEqual(
                                (info.st_dev, info.st_ino, info.st_mode,
                                 info.st_uid, info.st_gid), identity)
                        self.assertEqual(command[1:],
                                         ["get", _CR_SUBJECT, "--source", "sia"])
                        get_descriptor_observations.append(get_descriptors)
                    calls.append((tuple(command[1:]), result.returncode, result.stdout, result.stderr))
                    return result

                stack.enter_context(mock.patch.object(lib, "_run_bounded_text_process", observed_process))
                source_sha = _cr_sha(_CR_RAW.encode("utf-8"))
                version_fields = {"subject": _CR_SUBJECT, "origin": "model",
                                  "source_sha256": source_sha, "content_sha256": source_sha}
                source_version = {**version_fields, "content": _CR_RAW,
                                  "version_sha256": _cr_sha(_cr_canonical(version_fields))}
                source_reference = {key: value for key, value in source_version.items() if key != "content"}
                outputs = []
                # This module-qualified handle spelling keeps the unchanged
                # argv scanner joined to the actual get/project/version emitters.
                with installed.hold_overlay_engine(
                        vars(lib), expectations=fixture.expectations,
                        expected_expectations_sha256=fixture.expected_expectations_sha256,
                        authority_current=fixture.authority_current) as siainstalledengine:
                    binding = siainstalledengine.read()
                    self.assertEqual(binding["status"], "bound-installed-artifacts")
                    self.assertEqual(binding["artifacts"]["executable"]["sha256"],
                                     selected["gbrain_executable_sha256"])
                    self.assertEqual(binding["binding_sha256"], _cr_sha(_cr_canonical(
                        {key: value for key, value in binding.items() if key != "binding_sha256"})))
                    version = siainstalledengine.version(timeout=180)
                    self.assertEqual(version["status"], "observed-version-only")
                    self.assertEqual(version["stdout"], "gbrain " + selected["version"] + "\n")
                    held_get = siainstalledengine.get(subject=_CR_SUBJECT, timeout=180)
                    self.assertEqual(set(held_get), _CR_GET_TRANSPORT_KEYS)
                    self.assertEqual(held_get["schema"],
                                     "sia-installed-overlay-engine-get-transport-v1")
                    self.assertEqual(held_get["status"], "captured-unadmitted-get")
                    self.assertEqual(held_get["operation"], "get")
                    self.assertEqual(held_get["source_id"], "sia")
                    self.assertEqual(held_get["subject"], _CR_SUBJECT)
                    self.assertEqual(held_get["binding_sha256"], binding["binding_sha256"])
                    self.assertEqual(held_get["expected_expectations_sha256"],
                                     fixture.expected_expectations_sha256)
                    self.assertIs(type(held_get["returncode"]), int)
                    self.assertEqual(held_get["returncode"], 0)
                    self.assertEqual(held_get["timeout"], 180)
                    self.assertIs(type(held_get["stdout"]), str)
                    self.assertIs(type(held_get["stderr"]), str)
                    # The independent golden predates this transport; never
                    # derive a GET oracle from its returned bytes or parser.
                    self.assertEqual(held_get["stdout"], _CR_GET)
                    self.assertEqual(held_get["stdout"], actual_get)
                    self.assertNotEqual(held_get["stdout"], _CR_RAW)
                    self.assertEqual(held_get["stdout_sha256"],
                                     _cr_sha(_CR_GET.encode("utf-8")))
                    get_request = {"operation": "get", "source_id": "sia",
                                   "subject": _CR_SUBJECT, "timeout": 180}
                    self.assertEqual(held_get["request_sha256"],
                                     _cr_sha(_cr_canonical(get_request)))
                    self.assertEqual(held_get["transport_sha256"], _cr_sha(_cr_canonical(
                        {key: value for key, value in held_get.items() if key != "transport_sha256"})))
                    self.assertEqual(held_get["non_claims"], list(installed.GET_NON_CLAIMS))
                    get_boundary = " ".join(held_get["non_claims"])
                    self.assertIn("Ordinary GET is not the no-migrate render-projection operation",
                                  get_boundary)
                    self.assertIn("connection migrations and retrieval bookkeeping may occur", get_boundary)
                    self.assertIn("does not establish whether they occurred", get_boundary)
                    self.assertIn("not necessarily original Markdown bytes", get_boundary)
                    self.assertIn("source-version join, rendered-field admission, output delivery", get_boundary)
                    # Tracking is enabled by the original real config call.
                    # This GET makes no no-bookkeeping/no-migrate assertion;
                    # those fields below belong only to the projection receipt.
                    get_calls = [row for row in calls if row[0][:1] == ("get",)]
                    self.assertEqual([row[0] for row in get_calls],
                                     [("get", _CR_SUBJECT, "--source", "sia")])
                    self.assertEqual(held_get["stdout"], get_calls[0][2])
                    self.assertEqual(held_get["stderr"], get_calls[0][3])
                    self.assertEqual(held_get["stderr_sha256"],
                                     _cr_sha(get_calls[0][3].encode("utf-8")))
                    self.assertTrue(get_descriptor_observations)
                    outputs.append((_cr_canonical(held_get), held_get))
                    for supplied_stdout, expected_status, reasons in (
                            (held_get["stdout"], "matched", []),
                            (_CR_RAW, "mismatch", ["get-stdout-mismatch"])):
                        request = {"source_id": "sia", "source_version": source_version,
                                   "get_stdout": supplied_stdout,
                                   "expected_get_stdout_sha256": _cr_sha(supplied_stdout.encode("utf-8"))}
                        current_request = _cr_canonical(request)
                        result = siainstalledengine.project(
                            operation="get_page_render_projection", request_utf8=current_request,
                            expected_request_sha256=_cr_sha(current_request), timeout=180)
                        self.assertEqual(result["status"], "captured-unadmitted-projection")
                        self.assertEqual(result["operation"], _CR_OPERATION)
                        self.assertEqual(result["source_id"], "sia")
                        self.assertEqual(result["binding_sha256"], binding["binding_sha256"])
                        self.assertEqual(result["request_sha256"], _cr_sha(current_request))
                        self.assertEqual(result["stdout_sha256"], _cr_sha(result["stdout"].encode("utf-8")))
                        self.assertEqual(result["non_claims"], list(installed.NON_CLAIMS))
                        receipt = _cr_json(result["stdout"].encode("utf-8"))
                        self.assertEqual(set(receipt), _CR_RECEIPT_KEYS)
                        self.assertEqual(receipt["schema"], "sia-gbrain-get-render-projection-v1")
                        self.assertEqual(receipt["status"], expected_status)
                        self.assertEqual(receipt["source_id"], "sia")
                        self.assertEqual(receipt["source_reference"], source_reference)
                        self.assertEqual(receipt["page_state"], "live")
                        self.assertEqual(receipt["parse_error_codes"], [])
                        self.assertEqual(receipt["type_basis"], "source-explicit")
                        for key in ("current_content_hash_match", "projection_match", "display_fields_match"):
                            self.assertIs(receipt[key], True)
                        self.assertIs(receipt["get_stdout_match"], supplied_stdout == actual_get)
                        self.assertEqual(receipt["get_stdout_sha256"], request["expected_get_stdout_sha256"])
                        self.assertEqual(receipt["current_get_stdout_sha256"], _cr_sha(actual_get.encode("utf-8")))
                        self.assertEqual(receipt["mismatch_reasons"], reasons)
                        self.assertEqual(receipt["expected_projection_sha256"], receipt["current_projection_sha256"])
                        self.assertEqual(receipt["current_projection_sha256"], receipt["current_content_hash"])
                        self.assertNotEqual(receipt["current_content_hash"], source_sha)
                        self.assertIs(receipt["retrieval_bookkeeping_updated"], False)
                        self.assertIs(receipt["operation_writes_performed"], False)
                        self.assertIn("supplied source/version pins and origin are not independently authenticated",
                                      " ".join(receipt["non_claims"]))
                        self.assertIn("not output delivery", " ".join(receipt["non_claims"]))
                        self.assertIn("no JACKAL status", " ".join(receipt["non_claims"]))
                        outputs.append((_cr_canonical(result), result))
                    siainstalledengine.current()
                    # The GET descriptors are still held through BOTH actual
                    # projections and the final currentness sweep, not closed
                    # when GET returned or replaced with newly opened handles.
                    for observed in get_descriptor_observations:
                        for descriptor, identity in observed:
                            info = os.fstat(descriptor)
                            self.assertEqual(
                                (info.st_dev, info.st_ino, info.st_mode,
                                 info.st_uid, info.st_gid), identity)
                self.assertEqual(_cr_identity(os.fstat(caller_fd)), caller_identity)
                self.assertIsNone(lib._GBRAIN_OWNER_FD.get())
                for observed in get_descriptor_observations:
                    for descriptor, _identity in observed:
                        if descriptor == caller_fd:
                            continue
                        with self.assertRaises(OSError) as closed:
                            os.fstat(descriptor)
                        self.assertEqual(closed.exception.errno, errno.EBADF)
                for raw, result in outputs:
                    self.assertEqual(_cr_canonical(result), raw)
                self.assertEqual([row[0][0] for row in calls], ["--version", "get", "call", "call"])
                for _argv, code, _stdout, _stderr in calls:
                    self.assertEqual(code, 0)
                self.assertEqual(fixture.git(["rev-parse", "HEAD"]), fixture.head)
                fixture.authority_current()
                self.assertEqual(list(fixture.state.glob("sia-installed-projection-*")), [])

if __name__ == "__main__":
    unittest.main(verbosity=2)
