"""Source-bound output from an actually acknowledged v3 generation.

The existing controlled fixture performs real source-v3 capture, content/live
publication and ACK. The writer must acquire corpus-only authority, hold that
actual full parent and its original adoption, rank caller-premise rows against
that parent, and use the real held journal through actual sink writes/flush.
No successful source, rank, delivery or generation result is mocked.

Rows below are explicit caller premises selected from actual retained current
versions. They are not cmd_ask results or an engine/query adapter. The supplied
body is also a rendering premise; row admission does not establish semantic
faithfulness of arbitrary output prose. Row content and origin stay unchanged;
the original pure delivery record itself remains derived.

Positive completion is carried through the next actual source capture and pure
live preparation. That later plan is NOT source ACK, deployed output, human
receipt, complete machine history, biological cognition or a retrieval win.
Git/index observations in predecessor setup remain controlled fixture seams.
Only the original journal completion is returned, with its unchanged boundary
and nonclaims. Incomplete journals, including intent-only records, refuse;
there is no filtered complete copy or implicit incomplete-request recovery.
Root alone executes this module sequentially under the mission memory cap.
"""

import contextlib
import copy
import importlib
import inspect
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock

from tests import test_controller_delivery_epoch as epoch_tests
from tests import test_controller_source_ack as ack_tests
from tests import test_controller_source_capture_v3 as capture_tests
from tests import test_controller_source_v3_rollover as rollover_tests
from tests import test_delivery_journal as journal_tests
from tests import test_live_loop as live_tests


PARAMETERS = (
    "owner", "memo", "admitted_status", "retained_batch", "committed",
    "journal_limits", "expected_journal_limits_sha256", "expected_adoption_sha256",
    "rows", "expected_rows_sha256", "observed_at", "emitted_row_refs", "output_utf8",
    "request_id", "consumer", "binary_sink", "clock",
)
# Observed from root's actual JACKAL MCP call, not an observed machine time:
# status=exact parsed=2000000010+1 exact=2000000011 formal=false
# assurance=exact rational arithmetic (not yet checker-covered)
COMPLETED_AT = 2000000011
EXACT_NON_CLAIMS = (
    "NOT formal-bounded: this lane carries no Lean-checked certificate",
    "The epistemic class above is the STRONGEST claim this result supports",
    "exact rational arithmetic (not yet checker-covered)",
)


class _AfterIntent(KeyboardInterrupt):
    pass


class ControllerDeliveryWriter(unittest.TestCase):
    def setUp(self):
        try:
            self.module = importlib.import_module("siacontrollerdeliverywriter")
        except ModuleNotFoundError as exc:
            self.fail("missing actual source-v3 writer admission: " + str(exc))
        self.assertTrue(callable(getattr(self.module, "deliver", None)))
        self.assertTrue(hasattr(self.module, "ControllerDeliveryWriterRefusal"))
        self.assertTrue(hasattr(self.module, "NON_CLAIMS"))
        # Missing module/API fails before the expensive actual ACK fixture.
        self.rollover = rollover_tests.ControllerSourceV3Rollover(methodName="runTest")
        self.addCleanup(self.rollover.doCleanups)
        self.rollover.setUp()
        self.capture, self.epoch = self.rollover.capture, self.rollover.epoch
        self.source, self.live = self.rollover.source, self.rollover.live
        self.journal = self.capture.journal
        self.adapter = importlib.import_module("siacontrollerliveinput")

    @staticmethod
    def forbidden(name):
        return mock.Mock(side_effect=AssertionError("source writer crossed " + name))

    def request(self, f):
        state = f.generation["transition"]["state"]
        current = state["intake"]["current_versions"]
        page = next(page for page in state["intake"]["pages"]
                    if page["version_sha256"] in current and page["content"])
        rows = [{
            "row_ref": "source-current-row", "version_sha256": page["version_sha256"],
            "row": {"slug": page["subject"], "chunk_text": page["content"],
                    "origin": page["origin"], "fixture_backend": "caller-premise-not-engine-result"},
        }]
        f.page, f.rows = copy.deepcopy(page), rows
        f.records = self.epoch.paths(f.retained, f.root)[-1]
        f.body = b"Controlled source-bound result body\n" + page["content"].encode("utf-8")
        return {
            "memo": f.case.live.memo, "admitted_status": f.status,
            "retained_batch": f.retained, "committed": f.committed,
            "journal_limits": copy.deepcopy(self.epoch.limits),
            "expected_journal_limits_sha256": self.live._sha(self.epoch.limits),
            "expected_adoption_sha256": f.adopted["expected_adoption_sha256"],
            "rows": rows, "expected_rows_sha256": self.live._sha(rows),
            "observed_at": state["observed_at"], "emitted_row_refs": [rows[0]["row_ref"]],
            "output_utf8": f.body, "request_id": journal_tests.REQUEST_A,
            "consumer": "cli.recall",
        }

    @contextlib.contextmanager
    def completed(self):
        with self.rollover.completed() as f:
            f.writer_request = self.request(f)
            self.assertLess(f.writer_request["observed_at"], COMPLETED_AT)
            yield f

    @contextlib.contextmanager
    def writer_owner(self, f):
        # Path binding only: the source writer must enter its own ordinary
        # corpus scope and may never request the resident brainstem lock.
        with self.epoch.idle.source_owner(f.case), contextlib.ExitStack() as stack:
            owner = f.case.source.lib
            for name in capture_tests.AUTHORITY_PATHS:
                stack.enter_context(mock.patch.object(
                    owner, name, getattr(f.case.lib, name),
                    create=name == epoch_tests.ROOT_KEY))
            owner._load_live_publication()
            self.assertIsNone(owner._CORPUS_OWNER_FD.get())
            self.assertIsNone(owner._BRAINSTEM_OWNER_FD.get())
            try:
                yield owner
            finally:
                self.assertIsNone(owner._CORPUS_OWNER_FD.get())
                self.assertIsNone(owner._BRAINSTEM_OWNER_FD.get())

    @contextlib.contextmanager
    def boundary(self, f, owner, *, forbid_records=False, forbid_rank=False):
        trace = SimpleNamespace(epochs=[], journals=[], ranked=[], writes=[])
        epoch_hold = self.capture.epoch_module.hold_epoch
        writer_hold = self.journal.hold_delivery_writer
        rank = self.live.rank_recall
        publish = self.journal.queue.fixed_atomic_publish
        active_epochs, active_journals = [], []

        @contextlib.contextmanager
        def hold_epoch(actual_owner, **kwargs):
            self.assertIs(actual_owner, owner.__dict__)
            f.case.source.pages.assert_owned()
            self.assertIsNone(owner._BRAINSTEM_OWNER_FD.get())
            with epoch_hold(actual_owner, **kwargs) as held:
                observed = held.read()
                self.assertEqual(observed["parent_generation"], f.generation)
                self.assertEqual(observed["parent_committed"], f.committed)
                self.assertEqual(observed["epoch_adoption"], f.adopted)
                trace.epochs.append(held)
                active_epochs.append(held)
                try:
                    yield held
                finally:
                    active_epochs.remove(held)

        @contextlib.contextmanager
        def hold_writer(**kwargs):
            self.assertTrue(active_epochs, "journal acquired without held source authority")
            self.assertEqual(kwargs["directory"], str(f.records))
            self.assertEqual(kwargs["epoch_id"], f.generation["epoch_id"])
            self.assertEqual(kwargs["limits"], self.epoch.limits)
            self.assertEqual(kwargs["expected_directory_identity"], f.adopted["adoption"]["records_identity"])
            self.assertTrue(callable(kwargs["authority_current"]))
            with writer_hold(**kwargs) as held:
                trace.journals.append(held)
                active_journals.append(held)
                try:
                    yield held
                finally:
                    active_journals.remove(held)

        def ranked(**kwargs):
            if forbid_rank:
                raise AssertionError("inadmissible authority reached recall ranking")
            self.assertTrue(active_epochs)
            self.assertTrue(active_journals)
            for held in active_epochs + active_journals:
                held.current()
            self.assertEqual(kwargs["state"], f.generation["transition"]["state"])
            self.assertEqual(kwargs["expected_state_sha256"], f.generation["state_sha256"])
            self.assertEqual(kwargs["policy"], f.generation["transition"]["state"]["policy"])
            self.assertEqual(kwargs["expected_policy_sha256"], f.generation["transition"]["state"]["policy_sha256"])
            self.assertEqual(kwargs["observed_at"], f.writer_request["observed_at"])
            result = rank(**kwargs)
            self.assertEqual(result["status"], "computed-unverified")
            trace.ranked.append(copy.deepcopy(result))
            return result

        def publication(path, *args, **kwargs):
            if forbid_records:
                raise AssertionError("inadmissible writer published journal storage")
            self.assertEqual(Path(path).parent, f.records)
            self.assertTrue(active_epochs)
            self.assertTrue(active_journals)
            trace.writes.append(Path(path).name)
            return publish(path, *args, **kwargs)

        blocked = self.forbidden("brainstem, legacy output, source or live mutation")
        with contextlib.ExitStack() as stack:
            for module in (owner, f.case.lib):
                for name in ("brainstem_owner", "_write_memo", "atomic_write", "save_cursors",
                             "_commit_sense_cursors", "_discard_pending_cursor_renames",
                             "_mark_notify_baseline_attempt", "_clear_notify_baseline_attempt",
                             "_stage_live_generation", "_publish_staged_live_generation",
                             "_acknowledge_controller_source_batch", "export_status", "export_graph", "utcnow"):
                    stack.enter_context(mock.patch.object(module, name, blocked))
            for module, name in (
                    (self.capture.epoch_module, "prepare_epoch"),
                    (self.capture.epoch_module, "hold_capturable_epoch"),
                    (self.source, "capture"), (self.source, "capture_successor"),
                    (self.source, "capture_successor_v3"), (self.source, "_collect"),
                    (self.journal, "reserve_delivery"), (self.journal, "deliver_reserved")):
                stack.enter_context(mock.patch.object(module, name, blocked))
            stack.enter_context(mock.patch.object(self.capture.epoch_module, "hold_epoch", hold_epoch))
            stack.enter_context(mock.patch.object(self.journal, "hold_delivery_writer", hold_writer))
            stack.enter_context(mock.patch.object(self.live, "rank_recall", ranked))
            stack.enter_context(mock.patch.object(self.journal.queue, "fixed_atomic_publish", publication))
            yield trace
        blocked.assert_not_called()

    def call(self, f, owner, *, sink, clock, **changes):
        return self.module.deliver(owner.__dict__, **{
            **f.writer_request, "binary_sink": sink, "clock": clock, **changes})

    def record_images(self, f):
        return {path.name: ack_tests._path_image(path) for path in f.records.iterdir()
                if path.name != ".publish"}

    def inspect(self, f):
        return self.journal.inspect_deliveries(
            directory=str(f.records), epoch_id=f.generation["epoch_id"], limits=self.epoch.limits)

    def refused(self, f, *, forbid_rank=True, **changes):
        before = self.capture.images(f)
        sink = mock.Mock()
        clock = self.forbidden("clock before admission")
        with self.writer_owner(f) as owner, \
                self.boundary(f, owner, forbid_records=True, forbid_rank=forbid_rank), \
                self.assertRaises(self.module.ControllerDeliveryWriterRefusal) as caught:
            self.call(f, owner, sink=sink, clock=clock, **changes)
        self.assertEqual(caught.exception.output_state, "not-started")
        self.assertEqual(caught.exception.non_claims, list(self.module.NON_CLAIMS))
        self.assertRegex(caught.exception.reason, r"\A[a-z][a-z0-9-]*\Z")
        sink.write.assert_not_called()
        sink.flush.assert_not_called()
        clock.assert_not_called()
        self.assertEqual(self.capture.images(f), before)
        return caught.exception

    def test_closed_explicit_api_and_honest_completion_boundary(self):
        parameters = inspect.signature(self.module.deliver).parameters
        self.assertEqual(tuple(parameters), PARAMETERS)
        for name, parameter in parameters.items():
            self.assertEqual(parameter.kind, inspect.Parameter.POSITIONAL_OR_KEYWORD
                             if name == "owner" else inspect.Parameter.KEYWORD_ONLY)
            self.assertIs(parameter.default, inspect.Parameter.empty)
        self.assertTrue(all(type(item) is str and item for item in self.module.NON_CLAIMS))
        prose = " ".join(self.module.NON_CLAIMS).lower()
        for subject in (r"caller", r"render|body", r"row", r"human|receipt", r"consum|acknowledg",
                        r"legacy", r"clock|fresh", r"cognit|biolog", r"held[- ]?out", r"jackal"):
            self.assertRegex(prose, subject)

    def test_real_output_then_next_capture_binding_and_pulse_keep_exact_nonempty_record(self):
        with self.completed() as f:
            before = f.case.images()
            files = self.epoch.paths(f.retained, f.root)
            adoption_files = [ack_tests._path_image(path) for path in files[-3:-1]]
            original_rows = copy.deepcopy(f.rows)
            sink = journal_tests.ByteSink(short=True)

            def clock():
                self.assertEqual(sink.events[-1], "flush")
                self.assertEqual(bytes(sink.body), f.body)
                return COMPLETED_AT

            with self.writer_owner(f) as owner, self.boundary(f, owner) as trace:
                result = self.call(f, owner, sink=sink, clock=clock)
            self.assertEqual(set(result), journal_tests.COMPLETION_KEYS)
            self.assertEqual(result["status"], "service-output-completed")
            self.assertEqual(result["boundary"], "write-all-and-flush-returned")
            self.assertEqual(result["non_claims"], list(self.journal.NON_CLAIMS))
            self.assertEqual(result["completion_sha256"], self.live._own(result, "completion_sha256"))
            self.assertEqual(bytes(sink.body), f.body)
            self.assertEqual(f.rows, original_rows)
            self.assertTrue(trace.ranked)
            self.assertEqual(trace.ranked[-1]["rows"], original_rows)
            self.assertEqual(trace.ranked[-1]["versions"], [f.page])
            record = result["record"]
            self.assertEqual(record["rank_sha256"], trace.ranked[-1]["rank_sha256"])
            self.assertEqual(record["state_sha256"], f.generation["state_sha256"])
            self.assertEqual(record["rows"], original_rows)
            self.assertEqual(record["origin"], "derived")
            self.assertEqual(record["rows"][0]["row"]["origin"], f.page["origin"])
            self.assertEqual(record["boundary"], self.live.DELIVERY_BOUNDARY)
            self.assertEqual(record["non_claims"], list(self.live.NON_CLAIMS))
            self.assertEqual(record["completed_at"], COMPLETED_AT)
            self.assertEqual(record["ranked_at"], f.writer_request["observed_at"])
            complete_path = f.records / (journal_tests.REQUEST_A + ".complete.json")
            self.assertEqual(complete_path.read_bytes(), live_tests.canonical(result) + b"\n")
            intent = json.loads((f.records / (journal_tests.REQUEST_A + ".intent.json")).read_bytes())
            self.assertEqual(intent["ranked"], trace.ranked[-1])
            self.assertEqual(intent["ranked"]["status"], "computed-unverified")
            inspected = self.inspect(f)
            self.assertEqual(inspected["records"], [record])
            self.assertIs(inspected["complete"], True)
            self.assertEqual(inspected["pending"], [])
            self.assertEqual(f.case.images(), before)
            self.assertEqual([ack_tests._path_image(path) for path in files[-3:-1]], adoption_files)

            # Completed-after-ranking chronology must not force a new rank
            # clock or a second sink emission on exact completed retry.
            records_before = self.record_images(f)
            retry_sink = mock.Mock()
            retry_clock = self.forbidden("completed retry sampled completion clock")
            with self.writer_owner(f) as owner, self.boundary(f, owner):
                retry = self.call(f, owner, sink=retry_sink, clock=retry_clock)
            self.assertEqual(retry, result)
            retry_sink.write.assert_not_called()
            retry_sink.flush.assert_not_called()
            retry_clock.assert_not_called()
            self.assertEqual(self.record_images(f), records_before)

            # Genuine next source front door with a real durable reservation,
            # original adoption, and the declared post-output clock. This
            # stops at inert live preparation; no later source ACK is claimed.
            adopted = self.epoch.prepare(f.case, f.retained, f.committed, f.status,
                expected_adoption_sha256=f.adopted["expected_adoption_sha256"])
            self.assertEqual(adopted, f.adopted)
            self.capture.reserve(f.case)
            request = self.epoch.idle.epoch.build_successor(
                f.case.source.lib.__dict__, retained_batch=f.retained,
                committed=f.committed, observed_at=COMPLETED_AT)
            request.update({
                "memo": f.case.live.memo, "admitted_status": f.status,
                "retained_batch": f.retained, "committed": f.committed,
                "journal_limits": copy.deepcopy(self.epoch.limits),
                "expected_journal_limits_sha256": self.live._sha(self.epoch.limits),
                "expected_adoption_sha256": f.adopted["expected_adoption_sha256"],
            })
            f.request = request
            batch = self.capture.capture(f)
            self.assertIsNone(self.source.validate_batch(f.case.lib.__dict__, batch, batch["batch_sha256"]))
            self.assertEqual(batch["schema"], "sia-controller-source-batch-v3")
            wrapper = batch["delivery_input"]
            self.assertEqual(wrapper["journal"], inspected)
            self.assertEqual(wrapper["binding"]["deliveries"]["records"], [record])
            self.assertEqual(wrapper["epoch_view"]["parent_generation"], f.generation)
            self.assertEqual(wrapper["expected_adoption_sha256"], f.adopted["expected_adoption_sha256"])
            prepared = self.adapter.prepare_inputs_v3(
                f.case.lib.__dict__, batch=batch, previous_generation=f.generation,
                expected_previous_generation_sha256=self.live._own(f.generation, "generation_sha256"))
            self.assertEqual(prepared["deliveries"], wrapper["binding"]["deliveries"])
            transition = self.live.prepare_pulse(**prepared)
            self.assertEqual(transition["state"]["deliveries"]["records"], [record])
            self.assertEqual(transition["history_capture"]["deliveries"]["records"], [record])
            self.assertEqual(self.record_images(f), records_before)

    def test_adopted_but_only_legacy_source_completion_does_not_admit_writer(self):
        with self.epoch.completed() as (case, retained, committed, status, generation, root):
            adopted = self.epoch.prepare(case, retained, committed, status)
            f = SimpleNamespace(case=case, retained=retained, committed=committed,
                status=status, generation=generation, root=root, adopted=adopted,
                marker=None, nonidle=False, owner=case.source.lib.__dict__)
            f.writer_request = self.request(f)
            self.refused(f)

    def test_missing_wrong_adoption_and_foreign_source_commit_refuse_before_output(self):
        with self.completed() as f:
            self.assertNotEqual(f.adopted["expected_adoption_sha256"], "0" * 64)
            for pin in (None, "0" * 64):
                with self.subTest(pin=pin):
                    self.refused(f, expected_adoption_sha256=pin)
            changed = copy.deepcopy(f.committed)
            changed["live_generation_sha256"] = "0" * 64
            self.refused(f, committed=changed)

    def test_actual_fixed_successor_wal_prevents_new_output(self):
        with self.completed() as f:
            self.rollover.next_request(f)
            with self.capture.capture_owner(f) as owner:
                with self.capture.no_effects(f, owner):
                    batch = self.capture.operation(owner.__dict__, **f.request)
                self.assertIsNone(self.rollover.publication.retain_successor(
                    owner.__dict__, memo=f.case.live.memo, retained_batch=f.retained,
                    committed=f.committed, batch=batch,
                    expected_batch_sha256=batch["batch_sha256"], seq=f.case.live.memo["pulse_seq"]))
            self.assertEqual(f.case.live.memo["controller_source_committed"], f.committed)
            self.assertTrue(Path(f.case.producer.source_path).exists())
            self.refused(f)

    def test_intent_only_actual_crash_prefix_is_not_filtered_into_complete_history(self):
        with self.completed() as f:
            sink = mock.Mock()
            clock = self.forbidden("pre-attempt crash sampled clock")
            with self.writer_owner(f) as owner, self.boundary(f, owner), \
                    mock.patch.object(self.journal._HeldDeliveryWriter, "deliver",
                                      side_effect=_AfterIntent("actual reserved intent retained")), \
                    self.assertRaises(_AfterIntent):
                self.call(f, owner, sink=sink, clock=clock)
            sink.write.assert_not_called()
            sink.flush.assert_not_called()
            clock.assert_not_called()
            self.assertEqual(set(self.record_images(f)), {journal_tests.REQUEST_A + ".intent.json"})
            inspected = self.inspect(f)
            self.assertIs(inspected["complete"], False)
            self.assertEqual(inspected["pending"], [journal_tests.REQUEST_A])
            self.assertEqual(inspected["records"], [])
            self.refused(f)
            self.refused(f, request_id=journal_tests.REQUEST_B)

    def test_changed_row_origin_or_current_version_cannot_be_recorded_as_original(self):
        with self.completed() as f:
            rows = copy.deepcopy(f.rows)
            rows[0]["row"]["origin"] = "model" if f.page["origin"] != "model" else "evidence"
            self.refused(f, forbid_rank=False, rows=rows, expected_rows_sha256=self.live._sha(rows))
            rows = copy.deepcopy(f.rows)
            rows[0]["version_sha256"] = "0" * 64
            self.refused(f, forbid_rank=False, rows=rows, expected_rows_sha256=self.live._sha(rows))

    def test_real_source_authority_loss_at_write_or_flush_preserves_output_phase(self):
        for phase, expected_state in (("write", "unknown"), ("flush", "completed-unrecorded")):
            with self.subTest(phase=phase), self.completed() as f:
                before_generation = ack_tests._path_image(f.case.live.paths["LIVE_STATE_PATH"])

                def change_actual_memo(*_args):
                    changed = f.case.live._read("MEMO_PATH")
                    changed["writer_fixture_drift"] = phase
                    # Deliberate temporary-fixture authority mutation, not a
                    # mocked current() refusal or a gateway-authorized write.
                    f.case.live._write(f.case.live.paths["MEMO_PATH"], changed)

                sink = journal_tests.ByteSink(
                    short=phase == "write", before_write=change_actual_memo if phase == "write" else None,
                    before_flush=change_actual_memo if phase == "flush" else None)
                clock = self.forbidden("lost source authority sampled completion clock")
                with self.writer_owner(f) as owner, self.boundary(f, owner), \
                        self.assertRaises(self.module.ControllerDeliveryWriterRefusal) as caught:
                    self.call(f, owner, sink=sink, clock=clock)
                self.assertEqual(caught.exception.output_state, expected_state)
                self.assertEqual(caught.exception.non_claims, list(self.module.NON_CLAIMS))
                self.assertTrue(caught.exception.upstream_non_claims)
                clock.assert_not_called()
                self.assertEqual(sink.events, ["write"] if phase == "write" else ["write", "flush"])
                self.assertEqual(bytes(sink.body), f.body[:1] if phase == "write" else f.body)
                self.assertFalse((f.records / (journal_tests.REQUEST_A + ".complete.json")).exists())
                self.assertTrue((f.records / (journal_tests.REQUEST_A + ".attempt.json")).exists())
                self.assertEqual(ack_tests._path_image(f.case.live.paths["LIVE_STATE_PATH"]), before_generation)
                inspected = self.inspect(f)
                self.assertIs(inspected["complete"], False)
                self.assertEqual(inspected["pending"], [journal_tests.REQUEST_A])
                self.assertEqual(inspected["records"], [])


if __name__ == "__main__":
    unittest.main()
