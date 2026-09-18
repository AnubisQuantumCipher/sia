"""Resume actual source-v3 effects after live publication retires its handoff.

The durable prefixes here come from real source capture, WAL adoption, status
handoff and live publication. The test never reinserts a retired handoff into
the memo. Existing controlled Git/index observers bound the external effects;
the actual resident entry point, source effects finalizer and ACK still run.
No live activation, output journal record, source truth, complete history,
biological cognition, JACKAL assurance or held-out retrieval win is claimed.
Root alone runs tests sequentially; this module composes fixtures by module
name without subclassing or rediscovering their TestCase methods.
"""

import contextlib
import copy
from pathlib import Path
import unittest
from unittest import mock

from tests import test_controller_delivery_epoch as epoch_tests
from tests import test_controller_source_ack as ack_tests
from tests import test_controller_source_resident_v3 as resident_tests


class _LivePublishedDeath(KeyboardInterrupt):
    pass


class ControllerSourceResidentV3EffectsPrefix(unittest.TestCase):
    def setUp(self):
        self.resident = resident_tests.ControllerSourceResidentV3(methodName="runTest")
        self.addCleanup(self.resident.doCleanups)
        self.resident.setUp()
        self.runner = self.resident.runner
        self.effects = self.resident.effects
        self.source = self.resident.source

    @contextlib.contextmanager
    def published_prefix(self, *, interrupt):
        with self.effects.pending(nonidle=True) as f:
            self.effects.bind_status(f)
            self.assertIn("pulse_status_effects_pending", f.case.live.memo)
            death = _LivePublishedDeath("real live publication finished before effects finalization")
            with self.effects.no_recapture(f), self.effects.content_effects(f) as observed:
                boundary = f.case.lib._controller_source_effects_boundary

                def cut(stage):
                    boundary(stage)
                    if interrupt and stage == "live-published":
                        raise death

                with mock.patch.object(f.case.lib, "_controller_source_effects_boundary", side_effect=cut):
                    if interrupt:
                        with self.assertRaises(_LivePublishedDeath) as caught:
                            f.case.effects.publisher()(memo=f.case.live.memo, admitted_status=f.status)
                        self.assertIs(caught.exception, death)
                    else:
                        self.assertIsNone(f.case.effects.publisher()(
                            memo=f.case.live.memo, admitted_status=f.status))
            durable = f.case.lib.load_memo()
            self.assertEqual(durable, f.case.live.memo)
            self.assertNotIn("pulse_status_effects_pending", durable)
            self.assertNotIn("live_loop_pending", durable)
            self.assertNotIn("ready", durable)
            self.assertNotIn("controller_source_committed", durable)
            self.assertIn("controller_source_pending", durable)
            self.assertIn("controller_source_live_pending", durable)
            selected = "controller_source_effects_pending" if interrupt else "controller_source_effects_committed"
            opposite = "controller_source_effects_committed" if interrupt else "controller_source_effects_pending"
            self.assertIn(selected, durable)
            self.assertNotIn(opposite, durable)
            live = durable["live_loop_committed"]
            self.assertEqual(live["publication_id"], f.binding["publication_id"])
            self.assertEqual(live["state_sha256"], durable[selected]["state_sha256"])
            self.assertEqual(live["transition_sha256"], durable[selected]["transition_sha256"])
            self.assertEqual(live["generation_sha256"], f.case.live._read("LIVE_STATE_PATH")["generation_sha256"])
            self.assertEqual(Path(f.case.producer.source_path).read_bytes(),
                             self.source.native_bytes(f.case.lib.__dict__, f.batch))
            self.assertFalse(f.case.archive_path(f.batch).exists())
            observed["live_published"].assert_called_once()
            yield f, copy.deepcopy(durable), observed

    def artifact_images(self, f):
        return {name: ack_tests._path_image(Path(getattr(f.case.lib, name)))
                for name in ("STATUS_PATH", "GRAPH_PATH", "LIVE_CANDIDATE_PATH", "LIVE_STATE_PATH")}

    @contextlib.contextmanager
    def pending_resume(self, f, trace):
        """Finalize retained effects, without reconstructing the retired handoff."""
        owner = trace.owner
        effects = self.effects.effects_module

        def finish(*, memo, admitted_status):
            self.assertEqual(trace.active_scopes, ["brainstem", "corpus"])
            self.assertEqual(memo, owner.load_memo())
            self.assertNotIn("pulse_status_effects_pending", memo)
            self.assertIn("controller_source_effects_pending", memo)
            trace.stages.append("effects")
            # The first real publication already populated the controlled
            # external observer. Do not call resident.observe_handoff here:
            # the actual live final memo intentionally retired that field.
            with mock.patch.object(f.case.effects, "lib", owner), \
                    mock.patch.object(f.case.live, "memo", memo), \
                    self.effects.no_recapture(f), \
                    self.effects.content_effects(f, recovery=True) as observed:
                result = effects.publish(owner.__dict__, memo=memo, admitted_status=admitted_status)
            trace.effects.append(observed)
            self.assertEqual(observed["trace"], ["receipt"])
            observed["published"].assert_not_called()
            observed["content_committed"].assert_not_called()
            observed["synced"].assert_not_called()
            observed["graphed"].assert_not_called()
            observed["clocked"].assert_not_called()
            observed["staged"].assert_not_called()
            observed["live_published"].assert_not_called()
            self.assertEqual(observed["gist_receipts"], [])
            return result

        with mock.patch.object(owner, "_publish_controller_source_effects", side_effect=finish):
            yield

    def test_actual_live_published_pending_without_handoff_resumes_to_ack_without_new_acquisition(self):
        with self.published_prefix(interrupt=True) as (f, durable, first):
            self.assertEqual(first["trace"], [
                "closure", "corpus", "sync", "graph", "pending", "live-stage", "live-publish"])
            before = self.resident.capture.images(f)
            self.assertEqual(self.runner._source_state(durable), "effects-pending")
            self.assertEqual(self.resident.capture.images(f), before)
            artifacts = self.artifact_images(f)
            pages = self.effects.content_images(f)
            adoption = epoch_tests._tree(f.root)
            retained_raw = Path(f.case.producer.source_path).read_bytes()
            with self.resident.instrument(f, recovery=True) as retry, self.pending_resume(f, retry):
                status = retry.invoke(f.adopted["expected_adoption_sha256"])
            completed = self.resident.assert_completed(f, status, retry)
            self.assertEqual(completed["pulse_seq"], durable["pulse_seq"])
            self.assertEqual(f.case.archive_path(f.batch).read_bytes(), retained_raw)
            self.assertEqual(self.artifact_images(f), artifacts)
            self.assertEqual(self.effects.content_images(f), pages)
            self.assertEqual(epoch_tests._tree(f.root), adoption)
            self.assertEqual(retry.prepares, [])
            self.assertEqual(retry.captures, [])
            self.assertEqual(retry.retained, [])
            self.assertNotIn("clock", retry.stages)
            self.assertNotIn("reserve", retry.stages)


if __name__ == "__main__":
    unittest.main()
