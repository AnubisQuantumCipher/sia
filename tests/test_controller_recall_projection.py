"""Real held source/installed-artifact joins with supplied process output.

The source fixture genuinely captures, publishes and acknowledges a v3
generation. Actual ordinary hold_epoch and installed-engine admission retain
the same isolated core owner and real leases. Only the bounded process
provider is controlled: version, GET and projection stdout are authored
premises, NOT actual gbrain execution or an observed current indexed page.
No handles, source ACK, adoption or full generation success are fabricated.
Root alone admits/runs this private draft sequentially.
"""

try:
    import sia_test_home
except ModuleNotFoundError:
    from tests import sia_test_home

import contextlib
import copy
import errno
import hashlib
import importlib
import inspect
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bin"))


PARAMETERS = (
    "owner", "held_epoch", "held_engine", "expected_epoch_view_sha256",
    "expected_engine_binding_sha256", "expected_engine_expectations_sha256",
    "subject", "timeout",
)
RESULT_KEYS = {
    "schema", "status", "source_id", "subject", "expected_epoch_view_sha256",
    "expected_engine_binding_sha256", "expected_engine_expectations_sha256",
    "parent_committed", "parent_generation_sha256", "parent_state_sha256",
    "policy_sha256", "adoption_sha256", "source_version",
    "source_version_native_sha256", "get_stdout", "get_stdout_sha256",
    "rows", "rows_sha256", "engine_binding", "version_transport", "get_transport",
    "projection_request", "projection_request_sha256", "projection_transport",
    "consistency", "non_claims", "observation_sha256",
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def native(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def component(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def own(value, field):
    return sha(native({key: item for key, item in value.items() if key != field}))


def identity(info):
    return info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid


class CallerStop(BaseException):
    pass


class _ModuleShim:
    def __init__(self, module, **overrides):
        self.module, self.overrides = module, overrides

    def __getattr__(self, name):
        return self.overrides[name] if name in self.overrides else getattr(self.module, name)


class ControllerRecallProjection(unittest.TestCase):
    def setUp(self):
        try:
            self.module = importlib.import_module("siacontrollerrecallprojection")
        except ModuleNotFoundError as error:
            if error.name != "siacontrollerrecallprojection":
                raise
            self.fail("missing borrowed held recall projection adapter")
        self.hold = getattr(self.module, "hold_recall_projection", None)
        self.assertTrue(callable(self.hold), "missing held recall projection API")
        # Missing API fails before the actual ACK/artifact fixtures. Keep
        # fixture imports module-qualified: never rediscover their TestCases.
        self.rollover_tests = importlib.import_module("tests.test_controller_source_v3_rollover")
        self.capture_tests = importlib.import_module("tests.test_controller_source_capture_v3")
        self.epoch_tests = importlib.import_module("tests.test_controller_delivery_epoch")
        self.boundary_tests = importlib.import_module("tests.test_installed_engine_boundary")
        self.premise_tests = importlib.import_module("tests.test_get_render_admission")
        self.epoch_api = importlib.import_module("siacontrollerdeliveryepoch")
        self.engine_api = importlib.import_module("siainstalledengine")
        self.consistency = importlib.import_module("siagetrenderadmit")
        self.source = importlib.import_module("siasourcebatch")
        self.live = importlib.import_module("sialiveloop")
        self.rollover = self.artifact_fixture = None

    def fixtures(self):
        if self.rollover is None:
            self.rollover = self.rollover_tests.ControllerSourceV3Rollover(methodName="runTest")
            self.addCleanup(self.rollover.doCleanups)
            self.rollover.setUp()
            self.artifact_fixture = self.boundary_tests.InstalledEngineBoundary(methodName="runTest")
            self.addCleanup(self.artifact_fixture.doCleanups)
            self.artifact_fixture.setUp()
        return self.rollover

    @contextlib.contextmanager
    def completed(self, *, legacy=False):
        rollover = self.fixtures()
        if not legacy:
            with rollover.completed() as f:
                yield f
            return
        with rollover.epoch.completed() as values:
            case, retained, committed, status, generation, root = values
            adopted = rollover.epoch.prepare(case, retained, committed, status)
            yield SimpleNamespace(case=case, retained=retained, committed=committed,
                                  status=status, generation=generation, root=root,
                                  adopted=adopted)

    @contextlib.contextmanager
    def source_owner(self, f):
        # Existing correct isolated-source/publication authority path join.
        with self.rollover.epoch.idle.source_owner(f.case), contextlib.ExitStack() as stack:
            core = f.case.source.lib
            for name in self.capture_tests.AUTHORITY_PATHS:
                stack.enter_context(mock.patch.object(
                    core, name, getattr(f.case.lib, name),
                    create=name == self.epoch_tests.ROOT_KEY))
            core._load_live_publication()
            self.assertIsNone(core._CORPUS_OWNER_FD.get())
            self.assertIsNone(core._BRAINSTEM_OWNER_FD.get())
            yield core
            self.assertIsNone(core._CORPUS_OWNER_FD.get())
            self.assertIsNone(core._GBRAIN_OWNER_FD.get())
            self.assertIsNone(core._BRAINSTEM_OWNER_FD.get())

    @contextlib.contextmanager
    def installed_paths(self, core):
        # Copy already-declared fixture artifact bytes into THIS source
        # owner's canonical layout. Do not redirect source SHARE/STATE/CORPUS
        # or use the artifact fixture's independent global sialib owner.
        original = self.artifact_fixture.fixture
        share, state = Path(core.SHARE), Path(core.STATE)
        toolchain = share / "toolchain"
        target = SimpleNamespace(
            pin=share / "GBRAIN_PIN", pin_receipt=state / "managed-install/gbrain-pin",
            release_receipt=toolchain / "gbrain/.sia-release",
            engine_bin=toolchain / "gbrain/bin/gbrain")
        for path in (target.pin, target.pin_receipt, target.release_receipt, target.engine_bin):
            path.parent.mkdir(parents=True, exist_ok=True)
            self.assertFalse(path.exists(), "fixture install must not overwrite existing source artifacts")
        for name in ("pin", "release_receipt", "engine_bin"):
            shutil.copyfile(getattr(original, name), getattr(target, name))
            self.assertEqual(getattr(target, name).read_bytes(), getattr(original, name).read_bytes())
        target.engine_bin.chmod(0o755)
        target.pin_receipt.write_text(
            "managed-by=khephri.sia\nkind=gbrain-pin\npath=" + str(target.pin)
            + "\nsha256=" + sha(target.pin.read_bytes()) + "\n", encoding="utf-8")
        # Only the copied pin's path-bearing managed receipt changes; that
        # metadata is fixture-local, not evidence of a real engine build.
        with contextlib.ExitStack() as stack:
            for name, value in {
                "TOOLCHAIN": str(toolchain), "BUN_DIR": str(toolchain / "bun/bin"),
                "GBRAIN": str(target.engine_bin), "GBRAIN_PIN": str(target.pin),
                "GBRAIN_PIN_RECEIPT": str(target.pin_receipt),
                "GBRAIN_RUNTIME_RECEIPT": str(target.release_receipt),
                "GBRAIN_OWNER_LOCK": str(state / "gbrain-owner.lock"), "GBRAIN_SOURCE": "sia",
            }.items():
                stack.enter_context(mock.patch.object(core, name, value))
            self.assertEqual(core.CORPUS_OWNER_LOCK, str(state / "corpus-owner.lock"))
            with mock.patch.object(self.artifact_fixture, "fixture", target), \
                    mock.patch.object(self.artifact_fixture, "core", core):
                expectations = self.artifact_fixture.make_expectations()
            yield target, expectations

    @contextlib.contextmanager
    def no_source_output_effects(self, f, core):
        blocked = mock.Mock(side_effect=AssertionError("recall projection crossed source/output effects"))
        with contextlib.ExitStack() as stack:
            for owner in (core, f.case.lib):
                for name in ("brainstem_owner", "_write_memo", "atomic_write", "save_cursors",
                             "_commit_sense_cursors", "_mark_notify_baseline_attempt",
                             "_clear_notify_baseline_attempt", "_stage_live_generation",
                             "_publish_staged_live_generation", "_acknowledge_controller_source_batch",
                             "export_status", "export_graph", "utcnow", "gbrain", "gbrain_call",
                             "brain_sync"):
                    stack.enter_context(mock.patch.object(owner, name, blocked))
            for owner, names in (
                (self.epoch_api, ("prepare_epoch", "hold_capturable_epoch")),
                (self.source, ("capture", "capture_successor", "capture_successor_v3", "_collect")),
                (self.live, ("rank_recall", "prepare_pulse")),
                (self.rollover.capture.journal, ("hold_delivery_writer", "reserve_delivery", "deliver_reserved")),
            ):
                for name in names:
                    stack.enter_context(mock.patch.object(owner, name, blocked))
            yield
        blocked.assert_not_called()

    @contextlib.contextmanager
    def joined(self, f):
        with self.source_owner(f) as core, self.installed_paths(core) as (artifacts, expectations):
            state = f.generation["transition"]["state"]
            current = state["intake"]["current_versions"]
            candidates = [page for page in state["intake"]["pages"]
                          if page["version_sha256"] in current and page["content"]]
            self.assertTrue(candidates, "genuine acknowledged fixture needs a current source page")
            page = copy.deepcopy(candidates[0])
            self.assertEqual([item for item in candidates if item["subject"] == page["subject"]], [page])
            j = SimpleNamespace(core=core, owner=core.__dict__, f=f, page=page,
                artifacts=artifacts, expectations=expectations, calls=[], requests=[],
                hook=None, hook_calls=[], response_change=None, provider_stop=None,
                get_stdout="SUPPLIED GET RENDITION, NOT ENGINE EVIDENCE\n" + page["content"])
            j.projection_receipt = self.premise_tests.projection_premise(page, get_stdout=j.get_stdout)
            j.projection_stdout = self.premise_tests.projection_text(j.projection_receipt)
            j.expected_expectations = sha(native(expectations))
            epoch_request = {
                "memo": f.case.live.memo, "admitted_status": f.status,
                "retained_batch": f.retained, "committed": f.committed,
                "journal_limits": self.rollover.epoch.limits,
                "expected_journal_limits_sha256": sha(component(self.rollover.epoch.limits)),
                "expected_adoption_sha256": f.adopted["expected_adoption_sha256"],
            }
            with core.corpus_owner() as corpus_fd:
                j.corpus_fd = corpus_fd
                before = self.rollover.capture.images(f)
                with self.epoch_api.hold_epoch(j.owner, **epoch_request) as held_epoch:
                    j.epoch = held_epoch
                    j.epoch_view = held_epoch.read()
                    self.assertIs(type(held_epoch), self.epoch_api._HeldEpoch)
                    self.assertIs(type(held_epoch._tx), self.epoch_api._Transaction)
                    self.assertIs(held_epoch._tx.owner, j.owner)
                    self.assertIs(held_epoch._tx.readonly, True)
                    self.assertEqual(j.epoch_view["parent_generation"], f.generation)
                    self.assertEqual(j.epoch_view["parent_committed"], f.committed)
                    self.assertEqual(j.epoch_view["epoch_adoption"], f.adopted)
                    def authority_current():
                        held_epoch.current()
                        if j.hook is not None:
                            hook, j.hook = j.hook, None
                            j.hook_calls.append("actual-engine-authority-callback")
                            hook()
                        held_epoch.current()
                        return None
                    with mock.patch.object(
                            core, "_run_bounded_text_process",
                            side_effect=lambda *args, **kwargs: self.provider(j, *args, **kwargs)):
                        with self.engine_api.hold_overlay_engine(
                                j.owner, expectations=expectations,
                                expected_expectations_sha256=j.expected_expectations,
                                authority_current=authority_current) as held_engine:
                            j.engine = held_engine
                            j.binding = held_engine.read()
                            self.assertIs(type(held_engine), self.engine_api._Engine)
                            self.assertIs(held_engine.admission.owner, j.owner)
                            self.assertEqual(held_engine._environment()["GBRAIN_BRAIN_ID"], "host")
                            j.request = {
                                "held_epoch": held_epoch, "held_engine": held_engine,
                                "expected_epoch_view_sha256": sha(native(j.epoch_view)),
                                "expected_engine_binding_sha256": own(j.binding, "binding_sha256"),
                                "expected_engine_expectations_sha256": j.expected_expectations,
                                "subject": page["subject"], "timeout": self.boundary_tests.TIMEOUT,
                            }
                            self.assertEqual(j.request["expected_engine_binding_sha256"], j.binding["binding_sha256"])
                            with self.no_source_output_effects(f, core):
                                yield j
                    os.fstat(corpus_fd)
                    held_epoch.current()
                self.assertEqual(self.rollover.capture.images(f), before)
                self.assertEqual(list(Path(core.STATE).glob("sia-installed-projection-*")), [])
                os.fstat(corpus_fd)

    def provider(self, j, command, **kwargs):
        # Sole substituted provider. It observes actual inherited descriptors
        # and records opaque stdout premises, never executes the copied ELF.
        self.assertRegex(command[0], r"\A/proc/self/fd/[0-9]+\Z")
        self.assertRegex(kwargs["cwd"], r"\A/proc/self/fd/[0-9]+\Z")
        executable = j.engine.boundary.executable.fd
        corpus = j.engine.boundary.corpus.fd
        base = (executable, corpus, j.corpus_fd, j.core._GBRAIN_OWNER_FD.get())
        self.assertEqual(tuple(kwargs["pass_fds"][:len(base)]), base)
        self.assertEqual(command[0], "/proc/self/fd/" + str(executable))
        self.assertEqual(kwargs["cwd"], "/proc/self/fd/" + str(corpus))
        self.assertEqual(os.pread(executable, len(b"\x7fELF"), 0), b"\x7fELF")
        self.assertEqual(identity(os.fstat(executable)), identity(j.artifacts.engine_bin.stat()))
        self.assertEqual(identity(os.fstat(corpus)), identity(Path(j.core.CORPUS).stat()))
        for descriptor in kwargs["pass_fds"]:
            os.fstat(descriptor)
        self.assertEqual(j.core._CORPUS_OWNER_FD.get(), j.corpus_fd)
        self.assertGreater(j.core._CORPUS_OWNER_DEPTH.get(), 0)
        self.assertIsNone(j.core._BRAINSTEM_OWNER_FD.get())
        f = j.f
        f.case.source.pages.assert_owned()
        j.epoch.current()
        self.assertEqual(kwargs["timeout"], self.boundary_tests.TIMEOUT)
        self.assertEqual(kwargs["output_limit"], j.expectations["limits"]["max_output_bytes"])
        self.assertEqual(kwargs["env"]["GBRAIN_BRAIN_ID"], "host")
        self.assertEqual(kwargs["env"]["GBRAIN_HOME"], j.core.SHARE)
        self.assertNotIn("DATABASE_URL", kwargs["env"])
        self.assertNotIn("GBRAIN_DATABASE_URL", kwargs["env"])
        args = tuple(command[1:])
        if args == ("--version",):
            stdout = "gbrain " + j.expectations["version"] + "\n"
        elif args == ("get", j.page["subject"], "--source", "sia"):
            self.assertEqual(tuple(kwargs["pass_fds"]), base)
            stdout = j.get_stdout
        else:
            self.assertEqual(args[:5], ("call", "--no-migrate", "--source", "sia", "--params-file"))
            self.assertEqual(args[-1], "get_page_render_projection")
            self.assertEqual(len(args), len(("call", "--no-migrate", "--source", "sia", "--params-file", "leaf", "operation")))
            match = re.fullmatch(r"/proc/self/fd/([0-9]+)/request[.]json", args[5])
            self.assertIsNotNone(match)
            request_directory = int(match.group(1))
            self.assertIn(request_directory, kwargs["pass_fds"])
            self.assertTrue(stat.S_ISDIR(os.fstat(request_directory).st_mode))
            self.assertEqual(stat.S_IMODE(os.fstat(request_directory).st_mode), 0o700)
            descriptor = os.open("request.json", os.O_RDONLY | os.O_NOFOLLOW, dir_fd=request_directory)
            try:
                info = os.fstat(descriptor)
                self.assertTrue(stat.S_ISREG(info.st_mode))
                self.assertEqual(stat.S_IMODE(info.st_mode), 0o600)
                payload = os.pread(descriptor, info.st_size, 0)
                matching = [fd for fd in kwargs["pass_fds"] if identity(os.fstat(fd)) == identity(info)]
                self.assertTrue(matching, "actual regular request descriptor must be inherited")
            finally:
                os.close(descriptor)
            expected = {"source_id": "sia", "source_version": j.page,
                        "get_stdout": j.get_stdout, "expected_get_stdout_sha256": sha(j.get_stdout.encode("utf-8"))}
            self.assertEqual(payload, native(expected))
            self.assertEqual(j.core._strict_json_loads(payload), expected)
            j.requests.append({"payload": payload, "directory_fd": request_directory, "file_fd": matching[0]})
            receipt = copy.deepcopy(j.projection_receipt)
            if j.response_change is not None:
                j.response_change(receipt)
            stdout = self.premise_tests.projection_text(receipt)
        j.calls.append({"args": args, "descriptors": base, "epoch": j.epoch,
                        "engine": j.engine, "stdout": stdout})
        if j.provider_stop is not None and args[0] == "get":
            raise j.provider_stop
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    def recall(self, j, **changes):
        return self.hold(j.owner, **{**j.request, **changes})

    def borrowed_fds(self, j):
        descriptors = {j.corpus_fd, j.core._GBRAIN_OWNER_FD.get(),
                       j.engine.boundary.executable.fd, j.engine.boundary.corpus.fd}
        for held in j.epoch._tx.files.values():
            if held.fd is not None:
                descriptors.add(held.fd)
            for _name, descriptor, _generation in held.directories.chain:
                descriptors.add(descriptor)
        for held in j.epoch._tx.directories.values():
            for _name, descriptor, _generation in held.chain:
                descriptors.add(descriptor)
        return {descriptor: identity(os.fstat(descriptor)) for descriptor in descriptors}

    def assert_borrowed_alive(self, j, before):
        self.assertEqual({fd: identity(os.fstat(fd)) for fd in before}, before)
        self.assertIsNone(j.epoch.current())
        self.assertIsNone(j.engine.current())
        self.assertIs(j.epoch._closed, False)
        self.assertIs(j.engine.alive, True)

    def assert_refusal(self, error):
        self.assertIsInstance(error, self.module.ControllerRecallProjectionRefusal)
        self.assertRegex(error.reason, r"\A[a-z][a-z0-9-]*\Z")
        self.assertEqual(error.non_claims, list(self.module.NON_CLAIMS))
        self.assertFalse(hasattr(error, "output_state"), "no output phase exists in this adapter")

    def assert_result(self, j, result):
        self.assertEqual(set(result), RESULT_KEYS)
        self.assertEqual(result["schema"], "sia-controller-recall-projection-v1")
        self.assertEqual(result["status"], "observed-current-render-not-delivered")
        self.assertEqual(result["source_id"], "sia")
        self.assertEqual(result["subject"], j.page["subject"])
        for key in ("expected_epoch_view_sha256", "expected_engine_binding_sha256", "expected_engine_expectations_sha256"):
            self.assertEqual(result[key], j.request[key])
        self.assertEqual(result["parent_committed"], j.f.committed)
        self.assertEqual(result["parent_generation_sha256"], j.f.generation["generation_sha256"])
        self.assertEqual(result["parent_state_sha256"], j.f.generation["state_sha256"])
        self.assertEqual(result["policy_sha256"], j.f.generation["transition"]["state"]["policy_sha256"])
        self.assertEqual(result["adoption_sha256"], j.f.adopted["expected_adoption_sha256"])
        self.assertEqual(result["source_version"], j.page)
        self.assertEqual(result["source_version_native_sha256"], sha(native(j.page)))
        self.assertEqual(result["source_version"]["source_sha256"], sha(j.page["content"].encode("utf-8")))
        self.assertEqual(result["get_stdout"], j.get_stdout)
        self.assertNotEqual(result["get_stdout"], j.page["content"])
        self.assertEqual(result["get_stdout_sha256"], sha(j.get_stdout.encode("utf-8")))
        rows = [{"row_ref": j.page["version_sha256"], "version_sha256": j.page["version_sha256"],
                 "row": {"slug": j.page["subject"], "origin": j.page["origin"], "chunk_text": j.page["content"]}}]
        self.assertEqual(result["rows"], rows)
        self.assertEqual(result["rows_sha256"], sha(component(rows)))
        self.assertEqual(result["engine_binding"], j.binding)
        self.assertEqual(result["projection_request"], j.core._strict_json_loads(j.requests[-1]["payload"]))
        self.assertEqual(result["projection_request_sha256"], sha(j.requests[-1]["payload"]))
        for key, operation, claims in (
            ("version_transport", "--version", self.engine_api.NON_CLAIMS),
            ("get_transport", "get", self.engine_api.GET_NON_CLAIMS),
            ("projection_transport", "get_page_render_projection", self.engine_api.NON_CLAIMS),
        ):
            transport = result[key]
            self.assertEqual(transport["operation"], operation)
            self.assertEqual(transport["source_id"], "sia")
            self.assertEqual(transport["binding_sha256"], j.request["expected_engine_binding_sha256"])
            self.assertEqual(transport["expected_expectations_sha256"], j.expected_expectations)
            self.assertEqual(transport["stdout_sha256"], sha(transport["stdout"].encode("utf-8")))
            self.assertEqual(transport["transport_sha256"], own(transport, "transport_sha256"))
            self.assertEqual(transport["non_claims"], list(claims))
        self.assertEqual(result["consistency"]["status"], "supplied-match-consistent-not-observed")
        self.assertEqual(result["consistency"]["source_version"], j.page)
        self.assertEqual(result["consistency"]["source_version_native_sha256"], sha(native(j.page)))
        self.assertEqual(result["consistency"]["get_stdout"], j.get_stdout)
        self.assertEqual(result["consistency"]["get_stdout_sha256"], result["get_stdout_sha256"])
        self.assertEqual(result["consistency"]["projection_stdout"], result["projection_transport"]["stdout"])
        self.assertEqual(result["consistency"]["projection_stdout_sha256"], result["projection_transport"]["stdout_sha256"])
        self.assertEqual(result["consistency"]["projection_receipt"], j.projection_receipt)
        self.assertEqual(result["consistency"]["projection_receipt"]["non_claims"], self.premise_tests.PROJECTION_NON_CLAIMS)
        self.assertEqual(result["non_claims"], list(self.module.NON_CLAIMS))
        self.assertEqual(result["observation_sha256"], own(result, "observation_sha256"))

    def test_explicit_closed_api_and_no_output_or_enclosing_exit_claim(self):
        parameters = inspect.signature(self.hold).parameters
        self.assertEqual(tuple(parameters), PARAMETERS)
        for name, parameter in parameters.items():
            self.assertIs(parameter.default, inspect.Parameter.empty)
            self.assertEqual(parameter.kind, inspect.Parameter.POSITIONAL_OR_KEYWORD
                             if name == "owner" else inspect.Parameter.KEYWORD_ONLY)
        prose = " ".join(self.module.NON_CLAIMS).lower()
        for term in ("borrowed", "source-v3", "current-version", "origin", "get",
                     "host", "bookkeeping", "no output", "no-touch", "enclosing",
                     "jackal", "biological", "held-out"):
            self.assertIn(term, prose)

    def test_real_ack_epoch_and_installed_holds_join_preserve_source_and_do_not_close_borrowed_fds(self):
        with self.completed() as f, self.joined(f) as j:
            self.assertEqual(f.retained["schema"], "sia-controller-source-batch-v3")
            before = self.borrowed_fds(j)
            with self.recall(j) as held:
                for method in (held.read, held.current):
                    self.assertEqual(dict(inspect.signature(method).parameters), {})
                first, second = held.read(), held.read()
                self.assert_result(j, first)
                self.assertEqual(second, first)
                self.assertIsNot(second, first)
                self.assertIsNot(second["rows"], first["rows"])
                self.assertIsNone(held.current())
            self.assert_borrowed_alive(j, before)
            for operation in (held.read, held.current):
                with self.assertRaises(self.module.ControllerRecallProjectionRefusal) as caught:
                    operation()
                self.assert_refusal(caught.exception)
            self.assertEqual([call["args"][0] for call in j.calls], ["--version", "get", "call"])
            self.assertTrue(all(call["engine"] is j.engine and call["epoch"] is j.epoch for call in j.calls))
            self.assertTrue(all(call["descriptors"] == j.calls[0]["descriptors"] for call in j.calls))
            for request in j.requests:
                for key in ("directory_fd", "file_fd"):
                    with self.assertRaises(OSError) as caught:
                        os.fstat(request[key])
                    self.assertEqual(caught.exception.errno, errno.EBADF)

    def test_wrong_external_pins_subject_timeout_and_represented_handles_refuse_before_process(self):
        with self.completed() as f, self.joined(f) as j:
            before = self.borrowed_fds(j)
            changes = []
            for key in ("expected_epoch_view_sha256", "expected_engine_binding_sha256", "expected_engine_expectations_sha256"):
                changes.extend(({key: None}, {key: sha(b"foreign external pin")}))
                missing = dict(j.request)
                del missing[key]
                with self.subTest(missing=key), self.assertRaises(TypeError):
                    with self.hold(j.owner, **missing):
                        self.fail("missing mandatory external pin admitted")
            changes.extend(({"subject": value} for value in ("../escape", "Notes/upper", "--source", "notes/not-current")))
            changes.extend(({"timeout": value} for value in (True, 0, "120")))
            changes.extend((
                {"held_epoch": SimpleNamespace(read=lambda: j.epoch_view, current=lambda: None)},
                {"held_engine": SimpleNamespace(read=lambda: j.binding, current=lambda: None)},
            ))
            self.assertNotIn("notes/not-current", {page["subject"] for page in f.generation["transition"]["state"]["intake"]["pages"]})
            for changed in changes:
                with self.subTest(changed=tuple(changed)), self.assertRaises(self.module.ControllerRecallProjectionRefusal) as caught:
                    with self.recall(j, **changed):
                        self.fail("foreign external join or represented handle admitted")
                self.assert_refusal(caught.exception)
                self.assert_borrowed_alive(j, before)
            with self.assertRaises(self.module.ControllerRecallProjectionRefusal):
                with self.hold(dict(j.owner), **j.request):
                    self.fail("different owner dict borrowed real handles")
            self.assertEqual(j.calls, [])
            self.assertEqual(j.requests, [])

    def test_genuine_acknowledged_legacy_adoption_is_not_source_v3_recall_authority(self):
        with self.completed(legacy=True) as f, self.joined(f) as j:
            self.assertEqual(f.retained["schema"], "sia-controller-source-batch-v1")
            self.assertIs(j.epoch._tx.legacy, True)
            before = self.borrowed_fds(j)
            with self.assertRaises(self.module.ControllerRecallProjectionRefusal) as caught:
                with self.recall(j):
                    self.fail("real legacy adoption authorized recall projection")
            self.assert_refusal(caught.exception)
            self.assert_borrowed_alive(j, before)
            self.assertEqual(j.calls, [])

    def test_source_and_get_projection_join_failures_are_not_laundered_by_real_transport_pins(self):
        with self.completed() as f, self.joined(f) as j:
            before = self.borrowed_fds(j)
            different_origin = "model" if j.page["origin"] != "model" else "evidence"
            changes = {
                "foreign-source": lambda value: value.update(source_id="foreign"),
                "foreign-origin": lambda value: value["source_reference"].update(origin=different_origin),
                "wrong-render-digest": lambda value: value.update(current_get_stdout_sha256=sha(b"other displayed output")),
                "nonmatch": lambda value: value.update(status="mismatch", display_fields_match=False,
                    mismatch_reasons=["complete-display-fields-mismatch"]),
            }
            for label, mutation in changes.items():
                j.response_change = mutation
                with self.subTest(response=label), self.assertRaises(self.module.ControllerRecallProjectionRefusal) as caught:
                    with self.recall(j):
                        self.fail("supplied foreign/mismatched producer bytes admitted")
                self.assert_refusal(caught.exception)
                if label == "nonmatch":
                    self.assertEqual(caught.exception.upstream_reason, "upstream-non-match")
                    self.assertEqual(caught.exception.upstream_status, "mismatch")
                    self.assertEqual(caught.exception.upstream_mismatch_reasons, ["complete-display-fields-mismatch"])
                    self.assertEqual(caught.exception.upstream_non_claims["non_claims"], list(self.consistency.NON_CLAIMS))
                    self.assertEqual(caught.exception.upstream_non_claims["upstream_non_claims"], self.premise_tests.PROJECTION_NON_CLAIMS)
                self.assert_borrowed_alive(j, before)
            self.assertTrue(j.requests, "negative must reach actual descriptor request and controlled producer")
            j.response_change = None

    def test_returned_copy_mutation_and_aliasing_refuse_without_closing_borrowed_handles(self):
        with self.completed() as f, self.joined(f) as j:
            before = self.borrowed_fds(j)
            original_copy = copy.deepcopy
            for mode in ("none", "alias", "changed-origin"):
                reached = []
                def changed_copy(value, *args, **kwargs):
                    if type(value) is dict and value.get("schema") == "sia-controller-recall-projection-v1":
                        reached.append(mode)
                        if mode == "none":
                            return None
                        if mode == "alias":
                            return dict(value)
                        detached = original_copy(value, *args, **kwargs)
                        detached["source_version"]["origin"] = "foreign-copy"
                        return detached
                    return original_copy(value, *args, **kwargs)
                with self.subTest(copy=mode), self.assertRaises(self.module.ControllerRecallProjectionRefusal) as caught:
                    with self.recall(j) as held, mock.patch.object(
                            self.module, "copy", _ModuleShim(copy, deepcopy=changed_copy)):
                        held.read()
                self.assert_refusal(caught.exception)
                self.assertEqual(reached, [mode])
                self.assert_borrowed_alive(j, before)

    def test_normal_exit_checks_late_result_mutation_and_value_equal_alias_after_real_authority_callback(self):
        with self.completed() as f, self.joined(f) as j:
            before = self.borrowed_fds(j)
            for mode in ("content", "value-equal-alias"):
                with self.subTest(mode=mode), self.assertRaises(self.module.ControllerRecallProjectionRefusal) as caught:
                    with self.recall(j) as held:
                        result = held.read()
                        def late_mutation():
                            if mode == "content":
                                result["source_version"]["origin"] = "changed-at-normal-exit"
                            else:
                                self.assertEqual(result["rows"], held.documents["rows"])
                                result["rows"] = held.documents["rows"]
                        j.hook = late_mutation
                self.assert_refusal(caught.exception)
                self.assertIsNone(j.hook, "actual authority callback must consume mutation hook")
                self.assert_borrowed_alive(j, before)
            self.assertTrue(j.hook_calls)
            for authority, attribute in ((j.epoch._tx, "external"), (j.engine.admission, "expected")):
                original = getattr(authority, attribute)
                try:
                    with self.subTest(authority_pin=attribute), self.assertRaises(self.module.ControllerRecallProjectionRefusal) as caught:
                        with self.recall(j) as held:
                            held.read()
                            setattr(authority, attribute, sha(b"mutated retained authority scalar"))
                    self.assert_refusal(caught.exception)
                finally:
                    # Restore only test-induced in-memory corruption after
                    # the adapter has refused. No held storage is refreshed.
                    setattr(authority, attribute, original)
                self.assert_borrowed_alive(j, before)
            stop = CallerStop("caller body remains original")
            with self.assertRaises(CallerStop) as caught:
                with self.recall(j) as held:
                    held.read()
                    raise stop
            self.assertIs(caught.exception, stop)
            self.assert_borrowed_alive(j, before)

    def test_adapter_aggregate_budget_refuses_before_borrowed_epoch_copy_or_process(self):
        with self.completed() as f, self.joined(f) as j:
            before = self.borrowed_fds(j)
            original_read = self.epoch_api._HeldEpoch.read
            reads = []
            def observed_read(actual):
                reads.append(actual)
                return original_read(actual)
            # Narrow only this adapter's engineering ceiling, not the real
            # epoch/source owner, source receipt, or underlying live module.
            # A view by itself fits; its prospective duplicated compound does
            # not. The original reader would be called if the preflight moved.
            ceiling = len(native(j.epoch_view))
            with mock.patch.object(self.module, "live", _ModuleShim(self.live, MAX_INPUT_BYTES=ceiling)), \
                    mock.patch.object(self.epoch_api._HeldEpoch, "read", observed_read), \
                    self.assertRaises(self.module.ControllerRecallProjectionRefusal) as caught:
                with self.recall(j):
                    self.fail("over-capacity borrowed view copied")
            self.assert_refusal(caught.exception)
            self.assertEqual(reads, [])
            self.assertEqual(j.calls, [])
            self.assert_borrowed_alive(j, before)
