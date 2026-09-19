"""Retained renderer premises cannot change across real output/exit cuts.

Compose the actual acknowledged-source renderer fixture, without inheriting
its TestCase or replacing source, rank, journal, sink or completion authority.
Only detached renderer objects are changed. Normal-exit checks reuse one real
durable completion; they cannot excuse rewriting storage or re-emitting output.

Interrupted writes have a real intent/attempt, not a manufactured completion.
That incomplete history remains incomplete and the first source-writer API
must refuse its retry before rank, renderer, output or clock. These tests do
not implement an incomplete-output recovery API or claim human receipt,
deployment, semantic prose fidelity, cognition or a held-out retrieval win.
"""

import base64
import contextlib
import copy
from types import SimpleNamespace
import unittest
from unittest import mock

from tests import test_controller_delivery_render_writer as render_tests
from tests import test_controller_delivery_writer as writer_tests
from tests import test_delivery_journal as journal_tests


class _AfterSink(journal_tests.ByteSink):
    """Delegate the actual sink operation before the selected mutation."""

    def __init__(self, phase, mutate):
        super().__init__()
        self.phase, self.mutate = phase, mutate

    def write(self, value):
        result = super().write(value)
        if self.phase == "write":
            self.mutate()
        return result

    def flush(self):
        result = super().flush()
        if self.phase == "flush":
            self.mutate()
        return result


class ControllerDeliveryRenderTail(unittest.TestCase):
    def setUp(self):
        self.render = render_tests.ControllerDeliveryRenderWriter(methodName="runTest")
        self.addCleanup(self.render.doCleanups)
        self.render.setUp()
        self.fixture = self.render.fixture
        self.module = self.render.module

    def renderer(self, f, owner, trace, ranks, retained):
        def render(*, ranked, expected_ranked_sha256, config, expected_config_sha256):
            self.render.assert_renderer_inputs(
                f, owner, trace, ranks, ranked=ranked,
                expected_ranked_sha256=expected_ranked_sha256, config=config,
                expected_config_sha256=expected_config_sha256)
            self.assertIsNone(retained.result)
            result = self.render.rendered(ranked, config)
            retained.ranked, retained.config, retained.result = ranked, config, result
            retained.original = copy.deepcopy(result)
            return result
        return render

    @staticmethod
    def retained():
        return SimpleNamespace(ranked=None, config=None, result=None, original=None)

    def assert_pending_retry_is_effectless(self, f):
        fixture = self.fixture
        records, authority = fixture.record_images(f), f.case.images()
        sink = mock.Mock()
        clock = fixture.forbidden("incomplete render retry sampled clock")
        renderer = fixture.forbidden("incomplete render retry reached renderer")
        with fixture.writer_owner(f) as owner, \
                fixture.boundary(f, owner, forbid_records=True, forbid_rank=True), \
                self.assertRaises(self.module.ControllerDeliveryWriterRefusal) as caught:
            self.render.call(f, owner, renderer=renderer, sink=sink, clock=clock)
        self.assertEqual(caught.exception.reason, "complete-delivery-journal-required")
        self.assertEqual(caught.exception.output_state, "not-started")
        renderer.assert_not_called()
        sink.write.assert_not_called()
        sink.flush.assert_not_called()
        clock.assert_not_called()
        self.assertEqual(fixture.record_images(f), records)
        self.assertEqual(f.case.images(), authority)

    def output_mutation(self, phase):
        fixture = self.fixture
        with self.render.completed() as f:
            authority = f.case.images()
            before = fixture.inspect(f)
            self.assertIs(before["complete"], True)
            self.assertEqual(before["records"], [])
            retained, mutated = self.retained(), []

            def mutate():
                self.assertEqual(mutated, [])
                self.assertIsNotNone(retained.original)
                if phase == "write":
                    retained.result["output_utf8"] = b"Foreign callback body after actual sink write\n"
                    self.assertNotEqual(retained.result["output_utf8"], retained.original["output_utf8"])
                else:
                    retained.result["emitted_row_refs"][:] = [f.rows[0]["row_ref"]]
                    self.assertNotEqual(retained.result["emitted_row_refs"], retained.original["emitted_row_refs"])
                mutated.append(phase)

            sink = _AfterSink(phase, mutate)
            clock = fixture.forbidden("changed render result sampled completion clock")
            with fixture.writer_owner(f) as owner, fixture.boundary(f, owner) as trace, \
                    self.render.one_actual_rank() as ranks, \
                    self.assertRaises(self.module.ControllerDeliveryWriterRefusal) as caught:
                self.render.call(f, owner,
                    renderer=self.renderer(f, owner, trace, ranks, retained),
                    sink=sink, clock=clock)
            self.assertEqual(mutated, [phase])
            self.assertEqual(bytes(sink.body), retained.original["output_utf8"])
            self.assertEqual(sink.events, ["write"] if phase == "write" else ["write", "flush"])
            self.assertEqual(caught.exception.output_state,
                             "unknown" if phase == "write" else "completed-unrecorded")
            self.assertEqual(caught.exception.non_claims, list(self.module.NON_CLAIMS))
            clock.assert_not_called()
            inspected = fixture.inspect(f)
            self.assertIs(inspected["complete"], False)
            self.assertEqual(inspected["records"], before["records"])
            self.assertEqual(inspected["pending"], [journal_tests.REQUEST_A])
            self.assertEqual(set(fixture.record_images(f)), {
                journal_tests.REQUEST_A + ".intent.json",
                journal_tests.REQUEST_A + ".attempt.json",
            })
            self.assertEqual(f.case.images(), authority)
            self.assert_pending_retry_is_effectless(f)

    def test_returned_body_mutation_after_actual_write_preserves_unknown_and_no_retry_output(self):
        self.output_mutation("write")

    def test_returned_refs_mutation_after_actual_flush_preserves_unrecorded_and_no_retry_output(self):
        self.output_mutation("flush")

    @contextlib.contextmanager
    def normal_exit_mutation(self, owner, cut, mutate):
        if cut == "journal":
            module, name = self.module.journal_api, "hold_delivery_writer"
        elif cut == "epoch":
            module, name = self.module.epoch_api, "hold_epoch"
        else:
            self.assertEqual(cut, "corpus")
            module, name = owner, "corpus_owner"
        original = getattr(module, name)

        @contextlib.contextmanager
        def delegated(*args, **kwargs):
            # This code runs after the REAL selected context's normal exit,
            # never instead of its currentness or descriptor close operation.
            with original(*args, **kwargs) as held:
                yield held
            if cut != "corpus" or owner._CORPUS_OWNER_FD.get() is None:
                mutate()

        with mock.patch.object(module, name, delegated):
            yield

    def test_normal_exit_mutations_refuse_without_changing_real_completion_or_reemitting(self):
        fixture = self.fixture
        with self.render.completed() as f:
            authority = f.case.images()
            initial = self.retained()
            sink = journal_tests.ByteSink()

            def clock():
                self.assertEqual(sink.events, ["write", "flush"])
                self.assertEqual(bytes(sink.body), initial.original["output_utf8"])
                return writer_tests.COMPLETED_AT

            # The baseline is an actual output, not a fabricated complete row.
            with fixture.writer_owner(f) as owner, fixture.boundary(f, owner) as trace, \
                    self.render.one_actual_rank() as ranks:
                completed = self.render.call(f, owner,
                    renderer=self.renderer(f, owner, trace, ranks, initial),
                    sink=sink, clock=clock)
            completion_pin = fixture.live._sha(completed)
            records = fixture.record_images(f)
            self.assertEqual(fixture.inspect(f)["records"], [completed["record"]])
            self.assertEqual(base64.b64decode(completed["record"]["output_utf8_base64"], validate=True),
                             initial.original["output_utf8"])
            self.assertEqual(f.case.images(), authority)

            for cut, target in (("journal", "rank"), ("epoch", "config"),
                                ("corpus", "body"), ("corpus", "refs")):
                with self.subTest(normal_exit=cut, retained_callback_value=target):
                    retained, mutations = self.retained(), []
                    retry_sink = mock.Mock()
                    retry_clock = fixture.forbidden("completed render retry sampled clock")

                    def mutate():
                        self.assertEqual(mutations, [])
                        self.assertIsNotNone(retained.result)
                        if cut == "corpus":
                            self.assertIsNone(owner._CORPUS_OWNER_FD.get())
                        else:
                            f.case.source.pages.assert_owned()
                        if target == "rank":
                            old_pin = retained.ranked["rank_sha256"]
                            retained.ranked["order"].reverse()
                            retained.ranked["rank_sha256"] = fixture.live._own(retained.ranked, "rank_sha256")
                            self.assertNotEqual(retained.ranked["rank_sha256"], old_pin)
                        elif target == "config":
                            retained.config["selection"] = "changed-after-epoch-exit"
                        elif target == "body":
                            retained.result["output_utf8"] = b"Foreign result after corpus exit\n"
                            self.assertNotEqual(retained.result["output_utf8"], initial.original["output_utf8"])
                        else:
                            retained.result["emitted_row_refs"][:] = [f.rows[0]["row_ref"]]
                            self.assertNotEqual(retained.result["emitted_row_refs"], initial.original["emitted_row_refs"])
                        mutations.append((cut, target))

                    with fixture.writer_owner(f) as owner, \
                            fixture.boundary(f, owner) as trace, \
                            self.render.one_actual_rank() as ranks, \
                            self.normal_exit_mutation(owner, cut, mutate), \
                            self.assertRaises(self.module.ControllerDeliveryWriterRefusal) as caught:
                        self.render.call(f, owner,
                            renderer=self.renderer(f, owner, trace, ranks, retained),
                            sink=retry_sink, clock=retry_clock)
                    self.assertEqual(mutations, [(cut, target)])
                    self.assertEqual(caught.exception.reason,
                        "renderer-input-changed" if target in ("rank", "config") else "renderer-result-changed")
                    self.assertEqual(caught.exception.output_state, "completed-unrecorded")
                    self.assertEqual(caught.exception.non_claims, list(self.module.NON_CLAIMS))
                    retry_sink.write.assert_not_called()
                    retry_sink.flush.assert_not_called()
                    retry_clock.assert_not_called()
                    self.assertEqual(trace.writes, [journal_tests.REQUEST_A + ".intent.json"])
                    self.assertEqual(fixture.record_images(f), records)
                    self.assertEqual(fixture.inspect(f)["records"], [completed["record"]])
                    self.assertEqual(fixture.live._sha(completed), completion_pin)
                    self.assertEqual(f.case.images(), authority)

            # Removing only the mutation restores the exact original receipt;
            # no callback body drift permits a new sink write or durable rewrite.
            retained = self.retained()
            retry_sink = mock.Mock()
            retry_clock = fixture.forbidden("final exact render retry sampled clock")
            with fixture.writer_owner(f) as owner, \
                    fixture.boundary(f, owner) as trace, \
                    self.render.one_actual_rank() as ranks:
                retry = self.render.call(f, owner,
                    renderer=self.renderer(f, owner, trace, ranks, retained),
                    sink=retry_sink, clock=retry_clock)
            self.assertEqual(retry, completed)
            retry_sink.write.assert_not_called()
            retry_sink.flush.assert_not_called()
            retry_clock.assert_not_called()
            self.assertEqual(trace.writes, [journal_tests.REQUEST_A + ".intent.json"])
            self.assertEqual(fixture.record_images(f), records)
            self.assertEqual(f.case.images(), authority)


if __name__ == "__main__":
    unittest.main()
