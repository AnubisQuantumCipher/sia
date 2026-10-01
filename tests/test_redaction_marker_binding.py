"""A counted agent-note redaction must not strand an in-flight publication marker.

Found on the reference box on 2026-09-22: an agent note whose text tripped the
secret-redaction patterns was queued; the next pulse wrote its publication
marker (redaction target {}), then materialized the note, and
_account_agent_note_redactions raised the durable total to {"agent-note": 1}
without advancing the marker.  Crash recovery requires every pending target
to cover the durable totals, so the marker failed validation on every
subsequent start and the resident daemon could never start again (962
refusals over 13 hours before an operator looked).
"""
import copy
import importlib.machinery
import importlib.util
import os
import tempfile
import unittest

try:
    import sia_test_home  # noqa: F401  test-only import-time path isolation
except ModuleNotFoundError:
    from tests import sia_test_home  # type: ignore  # noqa: F401


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN = os.path.join(REPO, "bin")


def _load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, path)
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


siaqueue = _load("siaqueue_marker_test", os.path.join(BIN, "siaqueue.py"))
sialib = _load("sialib_marker_test", os.path.join(BIN, "sialib.py"))


class _Isolated(unittest.TestCase):
    def setUp(self):
        self._root = tempfile.TemporaryDirectory()
        self.addCleanup(self._root.cleanup)
        self.state = os.path.join(self._root.name, "state")
        corpus = os.path.join(self._root.name, "corpus")
        os.makedirs(self.state)
        os.makedirs(corpus)
        saved = (sialib.STATE, sialib.CORPUS, sialib.MEMO_PATH)
        sialib.STATE, sialib.CORPUS = self.state, corpus
        sialib.MEMO_PATH = os.path.join(self.state, "memo.json")
        sialib.REDACTIONS.clear()

        def restore():
            sialib.STATE, sialib.CORPUS, sialib.MEMO_PATH = saved
            sialib.REDACTIONS.clear()
        self.addCleanup(restore)

    def in_flight_pulse(self, seq=17248, durable=None):
        """A memo with a pulse publication marker already written, as the
        pulse does before it materializes agent notes."""
        memo = {"pulse_seq": seq, "redactions": copy.deepcopy(durable or {})}
        sialib._mark_pulse_publication(
            memo, seq, None, sialib._projected_pulse_redactions(memo))
        self.assertEqual(memo["pulse_publication"]["redactions"],
                         durable or {})
        return memo


class RedactedNoteDuringAPulse(_Isolated):
    def test_the_marker_advances_with_the_durable_total(self):
        memo = self.in_flight_pulse()
        siaqueue.enqueue_note(self.state, "claude-opus",
                              "text ⟦redacted⟧", redactions={"agent-note": 1})
        store = {"v": 1, "thoughts": []}
        _paths, _pages, _thoughts, errors = \
            sialib.materialize_agent_notes(store, memo)
        self.assertEqual(errors, [])
        self.assertEqual(memo["redactions"], {"agent-note": 1})
        self.assertEqual(memo["pulse_publication"]["redactions"],
                         {"agent-note": 1})
        # The exact check the daemon runs on every start.  This raised
        # "pulse publication redactions binding is invalid" before the fix.
        marker = sialib._pending_pulse_marker(memo)
        self.assertEqual(marker["redactions"], {"agent-note": 1})

    def test_the_rebind_is_durable_not_only_in_memory(self):
        memo = self.in_flight_pulse()
        siaqueue.enqueue_note(self.state, "claude-opus",
                              "text ⟦redacted⟧", redactions={"agent-note": 1})
        sialib.materialize_agent_notes({"v": 1, "thoughts": []}, memo)
        on_disk = sialib.load_memo()
        self.assertEqual(on_disk["pulse_publication"]["redactions"],
                         on_disk["redactions"])
        sialib._pending_pulse_marker(on_disk)  # a fresh start validates

    def test_process_local_increments_stay_in_the_target(self):
        # The pulse marker binds durable + not-yet-folded increments; the
        # rebind must keep both, or the later fold at status time refuses.
        memo = self.in_flight_pulse()
        sialib.REDACTIONS["notify"] = 2
        sialib._mark_pulse_publication(
            memo, memo["pulse_seq"], None,
            sialib._projected_pulse_redactions(memo))
        siaqueue.enqueue_note(self.state, "claude-opus",
                              "text ⟦redacted⟧", redactions={"agent-note": 1})
        sialib.materialize_agent_notes({"v": 1, "thoughts": []}, memo)
        self.assertEqual(memo["pulse_publication"]["redactions"],
                         {"agent-note": 1, "notify": 2})
        self.assertEqual(memo["redactions"], {"agent-note": 1})

    def test_a_pending_dream_marker_is_advanced_too(self):
        memo = {"pulse_seq": 3, "redactions": {}}
        sialib._mark_dream_publication(memo, {})
        siaqueue.enqueue_note(self.state, "claude-opus",
                              "text ⟦redacted⟧", redactions={"agent-note": 1})
        sialib.materialize_agent_notes({"v": 1, "thoughts": []}, memo)
        self.assertEqual(memo["dream_publication"]["redactions"],
                         {"agent-note": 1})
        sialib._pending_dream_marker(memo)

    def test_a_note_without_redactions_changes_nothing(self):
        memo = self.in_flight_pulse()
        siaqueue.enqueue_note(self.state, "claude-opus", "plain text")
        sialib.materialize_agent_notes({"v": 1, "thoughts": []}, memo)
        self.assertEqual(memo["pulse_publication"]["redactions"], {})
        sialib._pending_pulse_marker(memo)


class RefusalsNameTheirReason(_Isolated):
    def test_the_stranded_state_names_the_organ(self):
        # The exact memo found on the box.
        memo = self.in_flight_pulse()
        memo["redactions"] = {"agent-note": 1}
        with self.assertRaisesRegex(
                RuntimeError,
                r"redactions binding is invalid: "
                r"agent-note: marker absent < durable 1"):
            sialib._pending_pulse_marker(memo)

    def test_a_target_is_never_retracted(self):
        memo = self.in_flight_pulse(durable={"agent-note": 1})
        memo["pulse_publication"]["redactions"] = {"agent-note": 5}
        with self.assertRaisesRegex(RuntimeError, "would retract"):
            sialib._rebind_pending_redaction_targets(memo)


if __name__ == "__main__":
    unittest.main()
