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

if __name__ == "__main__":
    unittest.main(verbosity=2)
