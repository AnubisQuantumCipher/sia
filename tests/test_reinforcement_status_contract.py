#!/usr/bin/env python3
"""The exit-status contract for a refused reinforcement.

`ask` and `recall` both queue a recall touch for the brainstem, and both
print the same refusal when that queue is unavailable — but they used to
disagree about what it meant: `recall` returned 1 and `ask` returned 0.
An MCP `ask` therefore reported isError:false for a session in which no
reinforcement happened, while an MCP `recall` would have reported a
failure over a page it had delivered in full.

The contract pinned here: a refused reinforcement is not a failed answer.
Both verbs return 0 when the memory reached the caller, the refusal is
carried in-band (stderr plus the answer's own truth-boundary line), and
`rehearse` — whose entire product IS the queued touch — still refuses.
"""

import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
import types
import unittest
from unittest import mock

try:
    import sia_test_home  # test-only import-time path isolation
except ModuleNotFoundError:
    from tests import sia_test_home  # type: ignore


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SIA_PATH = os.path.join(REPO, "bin", "sia")


def _load_script(name, path):
    loader = importlib.machinery.SourceFileLoader(name, path)
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


sia = _load_script("sia_reinforcement_contract_cli", SIA_PATH)

import siamind  # noqa: E402  (bin/ joins sys.path when the CLI loads)


HYBRID_QUERY_HIT = json.dumps([{
    "slug": "organs/memory", "score": 1.0, "type": "organ",
    "title": "memory", "chunk_text": "the page body",
}])


@contextlib.contextmanager
def _ask_environment(queued):
    """Run cmd_ask over one hybrid-query hit with the touch queue forced."""
    engine = types.SimpleNamespace(
        returncode=0, stdout=HYBRID_QUERY_HIT, stderr="")
    with mock.patch.object(sia, "_gbrain_query", return_value=engine), \
            mock.patch.object(sia.sialib, "corpus_origin",
                              return_value="evidence"), \
            mock.patch.object(sia.sialib, "read_json", return_value={}), \
            mock.patch.object(sia.sialib, "associative_rerank_enabled",
                              return_value=False), \
            mock.patch.object(siamind, "queue_touches",
                              return_value=queued):
        yield


@contextlib.contextmanager
def _recall_environment(queued):
    """Run cmd_recall over one existing page with the touch queue forced."""
    page = types.SimpleNamespace(returncode=0, stdout="# page\n", stderr="")
    with mock.patch.object(sia.sialib, "page_exists", return_value=True), \
            mock.patch.object(sia.sialib, "unverified_jackal_recall_page",
                              return_value=False), \
            mock.patch.object(sia.sialib, "corpus_origin",
                              return_value="evidence"), \
            mock.patch.object(sia, "_gbrain_read", return_value=page), \
            mock.patch.object(siamind, "queue_touches",
                              return_value=queued):
        yield


class ReinforcementStatusContract(unittest.TestCase):
    def _run_ask(self, queued):
        out, err = io.StringIO(), io.StringIO()
        with _ask_environment(queued), \
                contextlib.redirect_stdout(out), \
                contextlib.redirect_stderr(err):
            status = sia.cmd_ask("memory")
        return status, out.getvalue(), err.getvalue()

    def _run_recall(self, queued):
        out, err = io.StringIO(), io.StringIO()
        with _recall_environment(queued), \
                contextlib.redirect_stdout(out), \
                contextlib.redirect_stderr(err):
            status = sia.cmd_recall("organs/memory")
        return status, out.getvalue(), err.getvalue()

    def test_ask_and_recall_agree_when_the_touch_queue_refuses(self):
        # The defect itself: one broken touch queue, two verbs, two
        # different answers to "did this work?".  Whatever the chosen
        # contract, the two must never disagree again.
        ask_status, _, ask_err = self._run_ask(False)
        recall_status, _, recall_err = self._run_recall(False)
        self.assertEqual(ask_status, recall_status)
        self.assertIn("reinforcement refused", ask_err)
        self.assertIn("reinforcement refused", recall_err)

    def test_refused_reinforcement_is_not_a_failed_answer(self):
        # The direction chosen: exit status answers "did the caller get
        # the memory?".  Both answers were delivered in full, so both
        # succeed; the touch queue is a write-behind side effect.
        self.assertEqual(self._run_ask(False)[0], 0)
        self.assertEqual(self._run_recall(False)[0], 0)

    def test_recall_still_prints_the_page_it_reports_success_for(self):
        # Returning 0 is only honest because the page really is on
        # stdout.  If the read itself ever stops producing the memory,
        # this status stops being defensible.
        status, out, _ = self._run_recall(False)
        self.assertEqual(status, 0)
        self.assertIn("[origin:evidence] organs/memory", out)
        self.assertIn("# page", out)

    def test_unreinforced_answer_carries_the_fact_in_its_boundary(self):
        # stderr can be discarded by any caller.  The compensating
        # control for returning 0 is that the truth-boundary line
        # travelling with the answer says the memory was not reinforced.
        status, out, _ = self._run_ask(False)
        self.assertEqual(status, 0)
        self.assertIn("boundary:", out)
        self.assertIn("not reinforced", out)

    def test_reinforced_answer_claims_no_degradation(self):
        # The inverse pin: a healthy touch queue must not leave the
        # boundary line crying wolf.
        status, out, err = self._run_ask(True)
        self.assertEqual(status, 0)
        self.assertIn("boundary:", out)
        self.assertNotIn("not reinforced", out)
        self.assertNotIn("reinforcement refused", err)

    def test_rehearse_still_refuses_when_no_touch_was_queued(self):
        # `recall` returning 0 must not leak into `rehearse`.  Rehearsal
        # exists to produce the touch the next scheduled run grades as q=5; with
        # no touch queued it accomplished nothing and must fail closed.
        out, err = io.StringIO(), io.StringIO()
        with _recall_environment(False), \
                contextlib.redirect_stdout(out), \
                contextlib.redirect_stderr(err):
            status = sia.cmd_rehearse(["organs/memory"])
        self.assertNotEqual(status, 0)
        self.assertNotIn("rehearsal touch queued", out.getvalue())
        self.assertIn("reinforcement refused", err.getvalue())

    def test_rehearse_reports_success_when_the_touch_is_queued(self):
        out = io.StringIO()
        with _recall_environment(True), contextlib.redirect_stdout(out):
            status = sia.cmd_rehearse(["organs/memory"])
        self.assertEqual(status, 0)
        self.assertIn("rehearsal touch queued", out.getvalue())


if __name__ == "__main__":
    unittest.main()
