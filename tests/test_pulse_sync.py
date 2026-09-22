#!/usr/bin/env python3
"""Pulse publication keeps PGLite retry state across crash boundaries."""

import copy
import importlib.machinery
import importlib.util
import json
import os
import tempfile
import unittest
from contextlib import ExitStack
from unittest import mock

try:
    import sia_test_home  # test-only import-time path isolation
except ModuleNotFoundError:
    from tests import sia_test_home  # type: ignore


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN = os.path.join(REPO, "bin")
READY = {
    "v": 1, "completed_at": "2026-08-30T12:00:00Z",
    "kind": "recovery", "identity": "0" * 32,
}

# Exact status roster written by the frozen predecessor after export_status()
# and before its final memo write. Its effectless marker predates the graph
# publication binding and its history row used a fresh iso() timestamp.
FROZEN_EFFECTLESS_STATUS = {
    "v": 1, "version": "1.7.8",
    "ts": "2026-08-30T12:00:02Z", "state": "thinking",
    "pulse_seq": 9, "day": "2026-08-30",
    "publication_id": "c" * 32,
    "events_pulse": 2, "events_today": 2,
    "organs": {"notify": {
        "today": 2, "last_ts": "2026-08-30T12:00:01Z"}},
    "errors": {}, "pages": 3, "graph_nodes": 2, "graph_edges": 1,
    "integrity": {
        "chains": {"sia": "pass"}, "verdict": "pass",
        "checked_at": "2026-08-30T12:00:02Z",
    },
    "ledger": {"seq": 0, "head": ""},
    "ledger_transition": {
        "state": "signed", "recovered": 0, "pending_errors": 0,
    },
    "thought": {
        "ts": "", "kind": "", "text": "",
        "origin": "legacy-unlabeled",
    },
    "dream": {},
    "history": [
        ["2026-08-29T12:00:00Z", 1],
        ["2026-08-30T12:00:01Z", 2],
    ],
    "workspace": [],
    "mind": {
        "nodes": 0, "edges": 0, "decay_active": 0,
        "decay_demoted": 0, "rehearsal_eligible": 0,
        "rehearsal_due": 0, "pinned": 0,
    },
    "takes": {}, "intents": [], "bench_trend": [],
    "bench_trend_boundary": {"legacy_truncated": False},
    "projection_debt": {"graph": "", "consolidation": ""},
    "agent_queue": {
        "materialized": 0, "refused": 0, "acknowledged": 0,
    },
    "redactions": {"notify": 2}, "sync_note": "",
}


def _load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, path)
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PulseSyncRetry(unittest.TestCase):
    def setUp(self):
        self.sialib = _load(
            "sialib_pulse_sync_test", os.path.join(BIN, "sialib.py"))

    def _complete_status(self, verdict="pass"):
        chain = "fail" if verdict == "fail" else (
            "absent" if verdict == "degraded" else "pass")
        state = "failed" if verdict == "fail" else (
            "degraded" if verdict == "degraded" else "ok")
        return {
            "v": 1, "version": self.sialib.VERSION,
            "ts": "2026-08-30T12:00:00Z", "state": state,
            "pulse_seq": 8, "day": "2026-08-30",
            "publication_id": "a" * 32,
            "graph_publication_id": "b" * 32,
            "events_pulse": 0, "events_today": 0,
            "organs": {}, "errors": {}, "pages": 0,
            "graph_nodes": 0, "graph_edges": 0,
            "integrity": {
                "chains": {"sia": chain}, "verdict": verdict,
                "checked_at": "2026-08-30T12:00:00Z",
            },
            "ledger": {"seq": 1, "head": "a" * 12},
            "ledger_transition": {
                "state": "not-required", "recovered": 0,
                "pending_errors": 0,
            },
            "thought": {
                "ts": "", "kind": "", "text": "",
                "origin": "legacy-unlabeled",
            },
            "dream": {}, "history": [], "workspace": [],
            "mind": {
                "nodes": 0, "edges": 0, "decay_active": 0,
                "decay_demoted": 0, "rehearsal_eligible": 0,
                "rehearsal_due": 0, "pinned": 0,
            },
            "takes": {}, "intents": [], "bench_trend": [],
            "bench_trend_boundary": {"legacy_truncated": False},
            "projection_debt": {"graph": "", "consolidation": ""},
            "agent_queue": {
                "materialized": 0, "refused": 0, "acknowledged": 0,
            },
            "redactions": {}, "sync_note": "",
        }

    def test_recovery_marker_versions_require_exact_json_integers(self):
        stamp = "2026-08-30T12:00:00Z"
        history = [stamp, 1]
        cases = (
            ("ready", self.sialib._ready_receipt, {
                "ready": {
                    "v": 1, "completed_at": stamp, "kind": "pulse",
                    "identity": "a" * 32}}, ("ready",)),
            ("pulse", self.sialib._pending_pulse_marker, {
                "pulse_seq": 1, "sync_needed": True,
                "pulse_publication": {
                    "v": 1, "seq": 1, "id": "a" * 32,
                    "started_at": stamp}}, ("pulse_publication",)),
            ("status-effects", self.sialib._pending_pulse_status_effects, {
                "pulse_history": [history],
                "pulse_status_effects_pending": {
                    "v": 1, "publication_id": "a" * 32,
                    "effects": {
                        "day": "2026-08-30", "events_pulse": 1,
                        "organs": {}},
                    "history": history}},
             ("pulse_status_effects_pending",)),
            ("notification", self.sialib._pending_notify_baseline_attempt, {
                self.sialib.NOTIFY_BASELINE_ATTEMPT_KEY: {
                    "v": 1, "id": "a" * 32, "started_at": stamp}},
             (self.sialib.NOTIFY_BASELINE_ATTEMPT_KEY,)),
            ("dream", self.sialib._pending_dream_marker, {
                "sync_needed": True, "dream_publication": {
                    "v": 1, "id": "a" * 32, "started_at": stamp}},
             ("dream_publication",)),
            ("consolidation", self.sialib._pending_consolidation_marker, {
                "consolidation_pending": {
                    "v": 1, "id": "a" * 32, "started_at": stamp}},
             ("consolidation_pending",)),
        )
        for label, validator, valid, path in cases:
            self.assertIsNotNone(validator(copy.deepcopy(valid)), label)
            for replacement in (True, 1.0):
                with self.subTest(label=label, replacement=replacement):
                    malformed = copy.deepcopy(valid)
                    target = malformed
                    for key in path:
                        target = target[key]
                    target["v"] = replacement
                    with self.assertRaisesRegex(RuntimeError, "invalid"):
                        validator(malformed)

    @staticmethod
    def _complete_graph():
        return {
            "v": 2, "ts": "2026-08-30T12:00:00Z",
            "publication_id": "b" * 32,
            "nodes": [{
                "id": "notes/fixture", "t": "note", "title": "Fixture",
                "ts": "2026-08-30T12:00:00Z", "origin": "derived",
                "deg": 4, "din": 2, "dout": 2,
            }],
            "edges": [{
                "s": "notes/fixture", "d": "notes/fixture",
                "t": "links", "why": "fixture",
            }, {
                "s": "notes/fixture", "d": "notes/fixture",
                "t": "mentions", "why": "fixture",
            }],
            "pages_total": 3, "pages_total_complete": True,
            "snapshot": {
                "complete": True, "truncated": 0,
                "omitted_nodes": 0, "omitted_edges": 0,
                "omissions_imply_absence": False,
                "aged_out": 2, "counts_by_kind": {"note": 1},
                "failed_ops": [], "window_days": 14,
            },
        }

    @staticmethod
    def _empty_graph(publication_id="b" * 32):
        return {
            "v": 2, "ts": "2026-08-30T12:00:00Z",
            "publication_id": publication_id,
            "nodes": [], "edges": [], "pages_total": 0,
            "pages_total_complete": True,
            "snapshot": {
                "complete": True, "truncated": 0,
                "omitted_nodes": 0, "omitted_edges": 0,
                "omissions_imply_absence": False,
                "aged_out": 0, "counts_by_kind": {},
                "failed_ops": [], "window_days": 14,
            },
        }

    def test_pulse_effects_refuse_impossible_calendar_day(self):
        with self.assertRaisesRegex(
                RuntimeError, "pulse publication effects are invalid"):
            self.sialib._canonical_pulse_effects(
                "2026-02-30", 0, {})

        status = self._complete_status("pass")
        status["day"] = "2026-02-30"
        self.assertIsNone(
            self.sialib._recoverable_status_integrity(status))
        status = self._complete_status("pass")
        status["pulse_seq"] = 9007199254740992
        self.assertIsNone(
            self.sialib._recoverable_status_integrity(status))
        status = self._complete_status("pass")
        status["v"] = True
        self.assertIsNone(
            self.sialib._recoverable_status_integrity(status))

    def test_current_status_nested_contract_is_exact_and_bounded(self):
        valid = self._complete_status("pass")
        valid["thought"] = {
            "ts": "2026-08-30T11:59:59Z", "kind": "integrity",
            "text": "the retained sweep passed", "origin": "derived",
        }
        valid["dream"] = {
            "last": "2026-08-29T03:33:00Z", "status": "ok",
            "summary": "cycle complete",
        }
        valid["takes"] = {
            "open": 2, "due": 1, "resolved": 1, "brier": 0.25,
            "calibration_status": "single-case",
            "monitoring_display_eligible": False,
            "unresolvable": 0, "invalid_resolved": 0,
            "invalid_records": 0,
        }
        valid["ledger"] = {"seq": 1, "head": "a" * 12}
        self.assertEqual(
            self.sialib._recoverable_status_integrity(valid), "pass")

        mutations = []
        extra = copy.deepcopy(valid); extra["claim"] = "not produced"
        mutations.append(extra)
        for field in ("thought", "dream", "takes"):
            row = copy.deepcopy(valid)
            row[field]["claim"] = "not produced"
            mutations.append(row)
        bad = copy.deepcopy(valid); bad["thought"]["ts"] = "tomorrow"
        mutations.append(bad)
        for kind, text in (
                ("Not Canonical", "ordinary thought"),
                ("integrity", "active [link]"),
                ("integrity", "hidden\U000e0001format"),
                ("integrity", "token=abcdefghijklmnop")):
            bad = copy.deepcopy(valid)
            bad["thought"].update({"kind": kind, "text": text})
            mutations.append(bad)
        bad = copy.deepcopy(valid); bad["dream"]["last"] = "yesterday"
        mutations.append(bad)
        bad = copy.deepcopy(valid); bad["takes"]["brier"] = float("inf")
        mutations.append(bad)
        bad = copy.deepcopy(valid); bad["takes"]["due"] = 3
        mutations.append(bad)
        bad = copy.deepcopy(valid)
        bad["takes"]["monitoring_display_eligible"] = True
        mutations.append(bad)
        bad = copy.deepcopy(valid); bad["ledger"] = {"seq": 0, "head": "a"}
        mutations.append(bad)
        bad = copy.deepcopy(valid); bad["publication_id"] = "generation"
        mutations.append(bad)
        bad = copy.deepcopy(valid); bad["graph_publication_id"] = "A" * 32
        mutations.append(bad)
        bad = copy.deepcopy(valid)
        bad["errors"] = {"token=abcdefghijklmnop": "refused"}
        mutations.append(bad)
        bad = copy.deepcopy(valid)
        bad["errors"] = {"source": {"error": "not a producer row"}}
        mutations.append(bad)
        bad = copy.deepcopy(valid)
        bad["errors"] = {"source": "x" * 161}
        mutations.append(bad)
        bad = copy.deepcopy(valid)
        bad["errors"] = {
            "source": [{"file": "fixture", "error": "x" * 161}]}
        mutations.append(bad)
        bad = copy.deepcopy(valid)
        bad["organs"] = {
            "x" * 201: {"today": 0, "last_ts": ""}}
        mutations.append(bad)
        bad = copy.deepcopy(valid)
        bad["organs"] = {
            f"x{index}": {"today": 0, "last_ts": ""}
            for index in range(
                self.sialib.MAX_LEDGER_PENDING_RECORDS
                + len(self.sialib.BASE_ORGANS)
                + len(self.sialib.OPTIONAL_ORGANS) + 1)}
        mutations.append(bad)
        bad = copy.deepcopy(valid)
        bad["integrity"]["chains"] = {"x" * 201: "pass"}
        mutations.append(bad)
        bad = copy.deepcopy(valid)
        bad["redactions"] = {"x" * 201: 1}
        mutations.append(bad)
        bad = copy.deepcopy(valid)
        bad["sync_note"] = "line one\nline two"
        mutations.append(bad)
        for workspace in (
                ["not a slug"], ["../escape"], ["sia/cortex\u200b"],
                ["sia/cortex", "sia/cortex"]):
            bad = copy.deepcopy(valid)
            bad["workspace"] = workspace
            mutations.append(bad)
        for control in (
                "\u0890", "\u0891", "\U000110bd", "\U000110cd",
                "\U00013430", "\U0001343f", "\U0001bca0",
                "\U0001bca3", "\U0001d173", "\U0001d17a",
                "\U000e0001", "\U000e0020", "\U000e007f"):
            bad = copy.deepcopy(valid)
            bad["errors"] = {"source": "hidden" + control + "format"}
            mutations.append(bad)
        bad = copy.deepcopy(valid)
        bad["intents"] = [{
            "id": "not-an-id", "text": "finish the audit",
            "due": "2026-08-30", "days_left": 0,
        }]
        mutations.append(bad)
        bad = copy.deepcopy(valid)
        bad["intents"] = [{
            "id": "0123456789", "text": "x" * 300 + "y",
            "due": "2026-08-30", "days_left": 0,
        }]
        mutations.append(bad)
        bad = copy.deepcopy(valid)
        bad["intents"] = [{
            "id": "0123456789", "text": "token=abcdefghijklmnop",
            "due": "2026-08-30", "days_left": 0,
        }]
        mutations.append(bad)
        bad = copy.deepcopy(valid)
        bad["integrity"]["chains"] = {"other": "pass"}
        bad["ledger"] = {"seq": 0, "head": ""}
        mutations.append(bad)
        bad = copy.deepcopy(valid); bad["pages"] = 0
        bad["graph_nodes"] = 1
        mutations.append(bad)
        bad = copy.deepcopy(valid)
        bad["graph_nodes"] = self.sialib.MAX_GRAPH_NODES + 1
        mutations.append(bad)
        bad = copy.deepcopy(valid)
        bad["graph_edges"] = self.sialib.MAX_GRAPH_EDGES + 1
        mutations.append(bad)
        for impossible_mind in ({
                "nodes": 1, "edges": 1,
                "decay_active": 1, "decay_demoted": 1,
                "rehearsal_eligible": 0, "rehearsal_due": 0,
                "pinned": 0,
        }, {
                "nodes": 1, "edges": 0,
                "decay_active": 0, "decay_demoted": 0,
                "rehearsal_eligible": 2, "rehearsal_due": 0,
                "pinned": 0,
        }, {
                "nodes": 1, "edges": 0,
                "decay_active": 0, "decay_demoted": 0,
                "rehearsal_eligible": 1, "rehearsal_due": 2,
                "pinned": 0,
        }, {
                "nodes": 1, "edges": 0,
                "decay_active": 0, "decay_demoted": 0,
                "rehearsal_eligible": 1, "rehearsal_due": 1,
                "pinned": 2,
        }):
            bad = copy.deepcopy(valid); bad["mind"] = impossible_mind
            mutations.append(bad)
        bad = copy.deepcopy(valid)
        bad["agent_queue"] = {
            "materialized": 0, "refused": 0, "acknowledged": 1}
        mutations.append(bad)
        bad = copy.deepcopy(valid)
        bad["agent_queue"] = {
            "materialized": self.sialib.siaqueue.MAX_PENDING_REQUESTS + 1,
            "refused": 0, "acknowledged": 0}
        mutations.append(bad)
        bad = copy.deepcopy(valid)
        bad["takes"].update({
            "resolved": 2, "calibration_status": "monitoring-population",
            "monitoring_display_eligible": True})
        mutations.append(bad)
        bad = copy.deepcopy(valid)
        bad["takes"].update({
            "resolved": self.sialib.siatakes.CALIBRATION_MIN_RESOLVED,
            "calibration_status": "descriptive-series"})
        mutations.append(bad)
        bad = copy.deepcopy(valid)
        bad["ledger_transition"]["recovered"] = \
            self.sialib.MAX_LEDGER_PENDING_RECORDS + 1
        mutations.append(bad)
        bad = copy.deepcopy(valid)
        bad["ledger_transition"]["pending_errors"] = 1
        mutations.append(bad)
        bad = copy.deepcopy(valid)
        bad["ledger_transition"]["state"] = "pending"
        mutations.append(bad)
        for status in mutations:
            with self.subTest(status=status):
                self.assertIsNone(
                    self.sialib._recoverable_status_integrity(status))

        descriptive = copy.deepcopy(valid)
        descriptive["takes"].update({
            "resolved": 2, "calibration_status": "descriptive-series"})
        self.assertEqual(
            self.sialib._recoverable_status_integrity(descriptive), "pass")
        imbalanced = copy.deepcopy(valid)
        imbalanced["takes"].update({
            "resolved": self.sialib.siatakes.CALIBRATION_MIN_RESOLVED,
            "calibration_status": "outcome-imbalanced"})
        self.assertEqual(
            self.sialib._recoverable_status_integrity(imbalanced), "pass")

        prior = copy.deepcopy(self.sialib.REDACTIONS)
        self.sialib.REDACTIONS.clear()
        try:
            sanitized = self.sialib._redacted_status_errors({
                "token=abcdefghijklmnop": "secret=qrstuvwxyzabcdef",
                "not a row": 7,
            })
            self.assertEqual(sanitized, {
                "status_projection":
                    "malformed status error detail refused",
            })
            self.assertTrue(self.sialib._status_errors_shape(sanitized))
            self.assertEqual(
                self.sialib.REDACTIONS.get("status-error"), 2)
        finally:
            self.sialib.REDACTIONS.clear()
            self.sialib.REDACTIONS.update(prior)

        empty = self._complete_status("pass")
        self.assertEqual(
            self.sialib._recoverable_status_integrity(empty), "pass")
        empty["graph_publication_id"] = ""
        self.assertEqual(
            self.sialib._recoverable_status_integrity(empty), "pass")
        for field in ("pages", "graph_nodes", "graph_edges"):
            unbound = copy.deepcopy(empty)
            unbound[field] = 1
            with self.subTest(unbound_graph_count=field):
                self.assertIsNone(
                    self.sialib._recoverable_status_integrity(unbound))

    def test_legacy_minimal_thought_projects_to_empty_status_boundary(self):
        self.assertEqual(
            self.sialib._status_thought_projection({
                "kind": "dream", "text": "legacy model prose",
                "origin": "model",
            }),
            {"ts": "", "kind": "", "text": "",
             "origin": "legacy-unlabeled"})

    def test_status_effects_handoff_binds_its_history_count(self):
        history = ["2026-08-30T12:00:00Z", 1]
        memo = {
            "pulse_history": [history],
            "pulse_status_effects_pending": {
                "v": 1, "publication_id": "a" * 32,
                "effects": {
                    "day": "2026-08-30", "events_pulse": 2,
                    "organs": {},
                },
                "history": history,
            },
        }
        with self.assertRaisesRegex(
                RuntimeError, "status-effects handoff is invalid"):
            self.sialib._pending_pulse_status_effects(memo)

    def test_pulse_marker_history_binds_its_start_timestamp(self):
        history = ["2026-08-29T12:00:00Z", 1]
        memo = {
            "pulse_seq": 9, "sync_needed": True,
            "pulse_history": [history],
            "pulse_publication": {
                "v": 1, "seq": 9, "id": "a" * 32,
                "started_at": "2026-08-30T12:00:00Z",
                "effects": {
                    "day": "2026-08-30", "events_pulse": 1,
                    "organs": {},
                },
                "history": history,
            },
        }
        with self.assertRaisesRegex(
                RuntimeError, "history binding is invalid"):
            self.sialib._pending_pulse_marker(memo)

    def test_pulse_marker_cannot_come_from_a_future_sequence(self):
        marker = {
            "v": 1, "seq": 10, "id": "a" * 32,
            "started_at": "2026-08-30T12:00:00Z",
            "effects": {
                "day": "2026-08-30", "events_pulse": 0,
                "organs": {},
            },
        }
        for memo in (
                {"sync_needed": True,
                 "pulse_publication": copy.deepcopy(marker)},
                {"pulse_seq": 9, "sync_needed": True,
                 "pulse_publication": copy.deepcopy(marker)}):
            with self.subTest(memo=memo), self.assertRaisesRegex(
                    RuntimeError, "recovery marker is invalid"):
                self.sialib._pending_pulse_marker(memo)

    def test_frozen_effectless_status_recovers_exact_history_handoff(self):
        for version in ("1.7.7", "1.7.8"):
            with self.subTest(version=version):
                status = copy.deepcopy(FROZEN_EFFECTLESS_STATUS)
                status["version"] = version
                old_history = copy.deepcopy(status["history"][:-1])
                memo = {
                    "pulse_seq": 9, "sync_needed": True,
                    "pulse_history": old_history,
                    "redactions": {"notify": 1},
                    "pulse_publication": {
                        "v": 1, "seq": 9, "id": "c" * 32,
                        "started_at": "2026-08-30T12:00:00Z",
                    },
                }
                graph = {
                    "publication_id": "b" * 32,
                    "nodes": [], "edges": [], "pages_total": 0,
                }
                writes = []

                def read(path, default):
                    if path == self.sialib.STATUS_PATH:
                        return copy.deepcopy(status)
                    if path == self.sialib.GRAPH_PATH:
                        return copy.deepcopy(graph)
                    return copy.deepcopy(default)

                with mock.patch.object(
                        self.sialib, "read_json", side_effect=read), \
                        mock.patch.object(
                            self.sialib.siamind, "load_mind",
                            return_value={}), \
                        mock.patch.object(
                            self.sialib, "_bind_pending_pulse_ledger"), \
                        mock.patch.object(
                            self.sialib, "_settle_pending_pulse_ledger"), \
                        mock.patch.object(
                            self.sialib, "_write_memo",
                            side_effect=lambda value: writes.append(
                                copy.deepcopy(value))), \
                        mock.patch.object(
                            self.sialib, "export_status") as publish:
                    self.assertTrue(
                        self.sialib._recover_pending_pulse_publication(memo))

                self.assertEqual(
                    set(status),
                    self.sialib._LEGACY_EFFECTLESS_STATUS_KEYS)
                self.assertEqual(memo["pulse_history"], status["history"])
                self.assertEqual(memo["redactions"], status["redactions"])
                handoff = self.sialib._pending_pulse_status_effects(memo)
                self.assertEqual(handoff["publication_id"], "c" * 32)
                self.assertEqual(handoff["effects"], {
                    "day": "2026-08-30", "events_pulse": 2,
                    "organs": status["organs"],
                })
                self.assertEqual(handoff["history"], status["history"][-1])
                self.assertNotIn("pulse_publication", memo)
                self.assertNotIn("sync_needed", memo)
                self.assertNotIn("ready", memo)
                self.assertEqual(writes[-1], memo)
                publish.assert_not_called()

    def test_frozen_effectless_ledger_zero_requires_exact_json_integer(self):
        validate = \
            self.sialib._recoverable_legacy_effectless_status_integrity
        for confused in (False, 0.0):
            status = copy.deepcopy(FROZEN_EFFECTLESS_STATUS)
            status["ledger"]["seq"] = confused
            with self.subTest(seq=repr(confused)):
                self.assertIsNone(validate(status))

    def test_frozen_effectless_recovery_remains_exact_and_prefix_bound(self):
        old_history = copy.deepcopy(FROZEN_EFFECTLESS_STATUS["history"][:-1])

        def recover(status):
            memo = {
                "pulse_seq": 9, "sync_needed": True,
                "pulse_history": copy.deepcopy(old_history),
                "redactions": {"notify": 1},
                "pulse_publication": {
                    "v": 1, "seq": 9, "id": "c" * 32,
                    "started_at": "2026-08-30T12:00:00Z",
                },
            }

            def read(path, default):
                if path == self.sialib.STATUS_PATH:
                    return copy.deepcopy(status)
                return copy.deepcopy(default)

            with mock.patch.object(
                    self.sialib, "read_json", side_effect=read), \
                    mock.patch.object(
                        self.sialib.siamind, "load_mind",
                        return_value={}), \
                    mock.patch.object(
                        self.sialib, "_bind_pending_pulse_ledger"), \
                    mock.patch.object(
                        self.sialib, "_settle_pending_pulse_ledger"):
                self.sialib._recover_pending_pulse_publication(memo)

        extra_field = copy.deepcopy(FROZEN_EFFECTLESS_STATUS)
        extra_field["unfrozen"] = True
        wrong_version = copy.deepcopy(FROZEN_EFFECTLESS_STATUS)
        wrong_version["version"] = "1.7.6"
        wrong_prefix = copy.deepcopy(FROZEN_EFFECTLESS_STATUS)
        wrong_prefix["history"][0] = ["2026-08-28T12:00:00Z", 1]
        lower_redactions = copy.deepcopy(FROZEN_EFFECTLESS_STATUS)
        lower_redactions["redactions"] = {"notify": 0}
        for status in (
                extra_field, wrong_version, wrong_prefix,
                lower_redactions):
            with self.subTest(status=status), self.assertRaisesRegex(
                    RuntimeError,
                    "effectless pulse publication recovery is ambiguous"):
                recover(status)

    def test_current_status_redactions_adopt_only_from_exact_publication(self):
        effects = {
            "day": "2026-08-30", "events_pulse": 1,
            "organs": {"notify": {
                "today": 1, "last_ts": "2026-08-30T12:00:00Z"}},
        }
        old_row = ["2026-08-29T12:00:00Z", 1]

        def recover(status_redactions, marker_redactions=None):
            status = self._complete_status("pass")
            status.update({
                "pulse_seq": 9, "publication_id": "c" * 32,
                "graph_publication_id": "b" * 32,
                "day": effects["day"], "events_pulse": 1,
                "events_today": 1,
                "organs": copy.deepcopy(effects["organs"]),
                "history": [
                    copy.deepcopy(old_row),
                    ["2026-08-30T12:00:00Z", 1],
                ],
                "redactions": copy.deepcopy(status_redactions),
            })
            marker = {
                "v": 1, "seq": 9, "id": "c" * 32,
                "started_at": "2026-08-30T12:00:00Z",
                "effects": copy.deepcopy(effects),
            }
            if marker_redactions is not None:
                marker["redactions"] = copy.deepcopy(marker_redactions)
            memo = {
                "pulse_seq": 9, "sync_needed": True,
                "pulse_history": [copy.deepcopy(old_row)],
                "redactions": {"notify": 1},
                "pulse_publication": marker,
            }
            graph = self._empty_graph()

            def read(path, default):
                if path == self.sialib.STATUS_PATH:
                    return copy.deepcopy(status)
                if path == self.sialib.GRAPH_PATH:
                    return copy.deepcopy(graph)
                return copy.deepcopy(default)

            with mock.patch.object(
                    self.sialib, "read_json", side_effect=read), \
                    mock.patch.object(
                        self.sialib.siamind, "load_mind",
                        return_value={}), \
                    mock.patch.object(
                        self.sialib, "_bind_pending_pulse_ledger"), \
                    mock.patch.object(
                        self.sialib, "_settle_pending_pulse_ledger"), \
                    mock.patch.object(self.sialib, "_write_memo"):
                self.assertTrue(
                    self.sialib._recover_pending_pulse_publication(memo))
            return memo

        adopted = recover({"notify": 2})
        self.assertEqual(adopted["redactions"], {"notify": 2})
        self.assertIn("ready", adopted)
        self.assertNotIn("pulse_status_effects_pending", adopted)

        downgrade = recover({"notify": 0})
        self.assertEqual(downgrade["redactions"], {"notify": 1})
        self.assertNotIn("ready", downgrade)
        self.assertIsNotNone(
            self.sialib._pending_pulse_status_effects(downgrade))

        marker_bound = recover(
            {"notify": 2}, marker_redactions={"notify": 3})
        self.assertEqual(marker_bound["redactions"], {"notify": 3})
        self.assertNotIn("ready", marker_bound)
        self.assertIsNotNone(
            self.sialib._pending_pulse_status_effects(marker_bound))

    def test_pulse_recovery_never_release_stamps_a_partial_status(self):
        effects = {"day": "2026-08-30", "events_pulse": 0,
                   "organs": {}}

        def recover(current, graph=None):
            memo = {"pulse_seq": 9, "sync_needed": True,
                    "pulse_publication": {
                "v": 1, "seq": 9, "id": "c" * 32,
                "started_at": "2026-08-30T12:00:00Z",
                "effects": effects,
            }}
            exported = []
            writes = []

            def read(path, default):
                if path == self.sialib.STATUS_PATH:
                    return copy.deepcopy(current)
                if path == self.sialib.GRAPH_PATH:
                    return copy.deepcopy(graph or self._empty_graph())
                return copy.deepcopy(default)

            with mock.patch.object(
                    self.sialib, "read_json", side_effect=read), \
                    mock.patch.object(
                        self.sialib.siamind, "load_mind",
                        return_value={}), \
                    mock.patch.object(
                        self.sialib, "_bind_pending_pulse_ledger"), \
                    mock.patch.object(
                        self.sialib, "_settle_pending_pulse_ledger"), \
                    mock.patch.object(
                        self.sialib, "_write_memo",
                        side_effect=lambda value: writes.append(
                            copy.deepcopy(value))), \
                    mock.patch.object(
                        self.sialib, "export_status",
                        side_effect=lambda status: exported.append(status)):
                self.assertTrue(
                    self.sialib._recover_pending_pulse_publication(memo))
            return exported, memo, writes

        inconsistent = self._complete_status("pass")
        inconsistent["events_today"] = 99
        malformed_state = self._complete_status("pass")
        malformed_state["state"] = []
        for partial in ({}, {
                "v": 1, "ts": "2026-08-30T12:00:00Z",
                "state": "degraded", "events_today": 0, "errors": {}},
                inconsistent, malformed_state):
            with self.subTest(partial=partial):
                exported, memo, writes = recover(partial)
                self.assertEqual(exported, [])
                handoff = self.sialib._pending_pulse_status_effects(memo)
                self.assertEqual(handoff["effects"], effects)
                self.assertEqual(handoff["history"][1],
                                 effects["events_pulse"])
                self.assertEqual(writes[-1], memo)

        for verdict in ("pass", "degraded", "fail"):
            exported, recovered_memo, _writes = recover(
                self._complete_status(verdict))
            self.assertEqual(exported, [])
            self.assertIsNotNone(
                self.sialib._pending_pulse_status_effects(recovered_memo))

        wrong_effects = self._complete_status("pass")
        wrong_effects.update({
            "publication_id": "c" * 32, "pulse_seq": 9,
            "events_pulse": 1, "events_today": 1,
            "organs": {"notify": {"today": 1, "last_ts": ""}},
            "history": [["2026-08-30T12:00:00Z", 1]],
        })
        _exported, mismatched_memo, _writes = recover(wrong_effects)
        self.assertIsNotNone(
            self.sialib._pending_pulse_status_effects(mismatched_memo))

        already_published = self._complete_status("pass")
        already_published["publication_id"] = "c" * 32
        already_published["pulse_seq"] = 9
        already_published["history"] = [[
            "2026-08-30T12:00:00Z", effects["events_pulse"]]]
        exported, published_memo, _writes = recover(already_published)
        self.assertEqual(exported, [])
        self.assertIsNone(
            self.sialib._pending_pulse_status_effects(published_memo))
        self.assertEqual(published_memo["pulse_history"],
                         already_published["history"])

        forged_histories = (
            [["2026-08-30T11:59:59Z", effects["events_pulse"]]],
            [["2026-08-01T00:00:00Z", 99],
             ["2026-08-30T12:00:00Z", effects["events_pulse"]]],
        )
        for forged_history in forged_histories:
            forged_status = copy.deepcopy(already_published)
            forged_status["history"] = forged_history
            with self.subTest(forged_history=forged_history):
                _exported, forged_memo, _writes = recover(forged_status)
                handoff = self.sialib._pending_pulse_status_effects(
                    forged_memo)
                self.assertEqual(handoff["history"], [
                    "2026-08-30T12:00:00Z", effects["events_pulse"]])
                self.assertEqual(
                    forged_memo["pulse_history"], [[
                        "2026-08-30T12:00:00Z",
                        effects["events_pulse"]]])
                self.assertNotIn("ready", forged_memo)

        wrong_graph = self._empty_graph("d" * 32)
        _exported, graph_mismatch_memo, _writes = recover(
            already_published, wrong_graph)
        self.assertIsNotNone(
            self.sialib._pending_pulse_status_effects(graph_mismatch_memo))

        malformed_graph = self._empty_graph()
        malformed_graph["snapshot"]["counts_by_kind"] = {"ghost": 0}
        _exported, malformed_graph_memo, _writes = recover(
            already_published, malformed_graph)
        self.assertIsNotNone(
            self.sialib._pending_pulse_status_effects(malformed_graph_memo))

    def test_second_crash_preserves_prior_recovered_history(self):
        first_effects = {
            "day": "2026-08-30", "events_pulse": 1,
            "organs": {"notify": {
                "today": 1, "last_ts": "2026-08-30T12:00:00Z"}},
        }
        second_effects = {
            "day": "2026-08-30", "events_pulse": 2,
            "organs": {"notify": {
                "today": 3, "last_ts": "2026-08-30T12:01:00Z"}},
        }
        first_history = ["2026-08-30T12:00:00Z", 1]
        memo = {
            "pulse_seq": 10, "sync_needed": True,
            "pulse_history": [first_history],
            "pulse_status_effects_pending": {
                "v": 1, "publication_id": "a" * 32,
                "effects": first_effects, "history": first_history,
            },
            "pulse_publication": {
                "v": 1, "seq": 10, "id": "c" * 32,
                "started_at": "2026-08-30T12:01:00Z",
                "effects": second_effects,
            },
        }

        with mock.patch.object(
                self.sialib, "read_json", return_value={}), \
                mock.patch.object(
                    self.sialib.siamind, "load_mind", return_value={}), \
                mock.patch.object(
                    self.sialib, "_bind_pending_pulse_ledger"), \
                mock.patch.object(
                    self.sialib, "_settle_pending_pulse_ledger"), \
                mock.patch.object(self.sialib, "_write_memo"):
            self.assertTrue(
                self.sialib._recover_pending_pulse_publication(memo))

        self.assertEqual([row[1] for row in memo["pulse_history"]], [1, 2])
        handoff = self.sialib._pending_pulse_status_effects(memo)
        self.assertEqual(handoff["publication_id"], "c" * 32)
        self.assertEqual(handoff["effects"], second_effects)
        self.assertEqual(handoff["history"], memo["pulse_history"][-1])

    def test_recovery_does_not_duplicate_marker_bound_history(self):
        effects = {
            "day": "2026-08-30", "events_pulse": 2,
            "organs": {"notify": {
                "today": 2, "last_ts": "2026-08-30T12:01:00Z"}},
        }
        history = [["2026-08-30T12:01:00Z", 2]]
        memo = {
            "pulse_seq": 10, "sync_needed": True,
            "pulse_history": history,
            "pulse_publication": {
                "v": 1, "seq": 10, "id": "c" * 32,
                "started_at": "2026-08-30T12:01:00Z",
                "effects": effects, "history": history[-1],
            },
        }

        with mock.patch.object(
                self.sialib, "read_json", return_value={}), \
                mock.patch.object(
                    self.sialib.siamind, "load_mind", return_value={}), \
                mock.patch.object(
                    self.sialib, "_bind_pending_pulse_ledger"), \
                mock.patch.object(
                    self.sialib, "_settle_pending_pulse_ledger"), \
                mock.patch.object(self.sialib, "_write_memo"):
            self.assertTrue(
                self.sialib._recover_pending_pulse_publication(memo))

        self.assertEqual(memo["pulse_history"], history)
        handoff = self.sialib._pending_pulse_status_effects(memo)
        self.assertEqual(handoff["history"], history[-1])

    def test_next_pulse_consumes_durable_recovered_status_effects(self):
        effects = {
            "day": self.sialib.today(), "events_pulse": 1,
            "organs": {"notify": {
                "today": 5, "last_ts": "2026-08-30T12:00:00Z"}},
        }
        initial = {
            "pulse_seq": 8, "chains": {"sia": "pass"},
            "sync_needed": True,
            "pulse_publication": {
                "v": 1, "seq": 8, "id": "c" * 32,
                "started_at": "2026-08-30T12:00:00Z",
                "effects": effects,
            },
        }
        status = self._run_barrier_pulse(
            page_activity=False, initial_memo=initial)
        self.assertEqual(status["organs"], effects["organs"])
        self.assertEqual(status["events_today"], 5)
        self.assertEqual(
            (status["graph_nodes"], status["graph_edges"], status["pages"]),
            (1, 2, 3))
        self.assertEqual(status["history"][-2][1],
                         effects["events_pulse"])
        self.assertNotIn(
            "pulse_status_effects_pending", self.barrier_persisted)

    def test_restart_consumes_preexisting_status_effects_handoff(self):
        effects = {
            "day": self.sialib.today(), "events_pulse": 1,
            "organs": {"notify": {
                "today": 5, "last_ts": "2026-08-30T12:00:00Z"}},
        }
        initial = {
            "chains": {"sia": "pass"},
            "pulse_history": [["2026-08-30T12:00:00Z", 1]],
            "pulse_status_effects_pending": {
                "v": 1, "publication_id": "c" * 32,
                "effects": effects,
                "history": ["2026-08-30T12:00:00Z", 1],
            },
        }

        status = self._run_barrier_pulse(
            page_activity=False, initial_memo=initial)

        self.assertEqual(status["day"], effects["day"])
        self.assertEqual(status["organs"], effects["organs"])
        self.assertEqual(status["events_today"], 5)
        self.assertEqual(status["history"][0][1], 1)
        self.assertNotIn(
            "pulse_status_effects_pending", self.barrier_persisted)

    def _run_barrier_pulse(self, *, raise_after_page=False,
                           graph_error=None, page_activity=True,
                           inbox_claim=None, initial_memo=None,
                           status_error=None, senses=None,
                           initial_cursors=None, takes_summary=None,
                           think_impl=None, initial_graph=None,
                           intent_side_effect=None,
                           status_admission_side_effect=None,
                           initial_mind=None, use_real_memory_summary=False):
        """Run an otherwise-idle pulse with one simulated page mutation."""
        persisted = (copy.deepcopy(initial_memo)
                     if initial_memo is not None else
                     {"chains": {"sia": "pass"},
                      "ready": copy.deepcopy(READY)})
        if "chains" in persisted and "chains_checked_at" not in persisted:
            persisted["chains_checked_at"] = "2026-08-30T12:00:00Z"
        pending = persisted.get("pulse_publication")
        prior_sequence = persisted.get("pulse_seq", 0)
        if isinstance(pending, dict) \
                and isinstance(pending.get("seq"), int):
            prior_sequence = max(prior_sequence, pending["seq"])
        sequence = prior_sequence + 1
        persisted["pulse_seq"] = sequence
        trace = []
        self.barrier_persisted = persisted
        self.barrier_trace = trace
        self.barrier_status = None
        persisted_cursors = copy.deepcopy(initial_cursors or {})
        published_graph = copy.deepcopy(
            self._empty_graph() if initial_graph is None else initial_graph)
        self.barrier_cursors = persisted_cursors
        graph_sync = mock.Mock()
        self.barrier_graph_sync = graph_sync
        strict_state_reader = self.sialib.read_state_json
        status_admissions = (
            iter(status_admission_side_effect)
            if status_admission_side_effect is not None else None)

        def load_memo():
            return copy.deepcopy(persisted)

        def capture_write(path, payload, mode=None):
            if path != self.sialib.MEMO_PATH:
                return
            value = json.loads(payload)
            persisted.clear()
            persisted.update(value)
            trace.append(("memo", value.get("sync_needed", False)))
            trace.append((
                "notify-fence",
                self.sialib.NOTIFY_BASELINE_ATTEMPT_KEY in value))

        def capture_cursors(value):
            persisted_cursors.clear()
            persisted_cursors.update(copy.deepcopy(value))
            trace.append(("cursors", True))

        def mutate_page():
            self.sialib._before_corpus_mutation()
            trace.append(("page", persisted.get("sync_needed", False)))
            if raise_after_page:
                raise OSError("page fsync refused")
            return True

        def commit(_message):
            trace.append(("commit", persisted.get("sync_needed", False)))
            return "committed"

        def sync():
            trace.append(("sync", persisted.get("sync_needed", False)))
            return True, ""

        def graph():
            trace.append(("graph", persisted.get("sync_needed", False)))
            current_graph_error = (
                graph_error() if callable(graph_error) else graph_error)
            if current_graph_error is not None:
                raise current_graph_error
            published_graph.clear()
            published_graph.update(self._complete_graph())
            return 1, 2, 3

        def read(path, default):
            if path == self.sialib.GRAPH_PATH:
                return copy.deepcopy(published_graph)
            return copy.deepcopy(default)

        def publish_status(status):
            self.barrier_status = copy.deepcopy(status)
            if status_error is not None:
                raise status_error

        def read_admitted_state(path, default, label, **kwargs):
            if path != self.sialib.STATUS_PATH:
                return strict_state_reader(
                    path, default, label, **kwargs)
            value = next(status_admissions)
            if isinstance(value, BaseException):
                raise value
            return copy.deepcopy(value)

        patches = {
            "ensure_dirs": None,
            "load_cursors": lambda: copy.deepcopy(persisted_cursors),
            "save_cursors": capture_cursors,
            "load_thoughts": {"v": 1, "thoughts": []},
            "load_memo": load_memo,
            "read_json": read,
            "recover_ledger_transitions": ([], []),
            "_settle_thought_page_signals": (0, 0),
            "think": [] if think_impl is None else think_impl,
            "materialize_agent_notes": ([], [], [], []),
            "drain_thought_inbox": ([], inbox_claim),
            "ensure_organs": mutate_page if page_activity else False,
            "corpus_dirty": False,
            "atomic_write": capture_write,
            "corpus_commit": commit,
            "brain_sync": sync,
            "export_graph": graph,
            "queue_ledger_transition": "pending-record",
            "_settle_ledger_transition": None,
            "export_thoughts": None,
            "acknowledge_thought_inbox": lambda claim:
                trace.append(("inbox-ack", claim)),
            "ledger_head": (1, "a" * 64),
            "export_status": publish_status,
        }
        with tempfile.TemporaryDirectory() as state_dir, ExitStack() as stack:
            stack.enter_context(mock.patch.object(
                self.sialib, "STATE", state_dir))
            stack.enter_context(mock.patch.object(
                self.sialib, "GRAPH_PATH",
                os.path.join(state_dir, "graph.json")))
            stack.enter_context(mock.patch.object(
                self.sialib, "SENSES", [] if senses is None else senses))
            for name, value in patches.items():
                replacement = value if callable(value) else mock.Mock(
                    return_value=value)
                stack.enter_context(mock.patch.object(
                    self.sialib, name, replacement))
            if status_admission_side_effect is not None:
                stack.enter_context(mock.patch.object(
                    self.sialib, "read_state_json",
                    side_effect=read_admitted_state))
            stack.enter_context(mock.patch.object(
                self.sialib.siatakes, "recover_grade_transactions",
                return_value=([], [])))
            stack.enter_context(mock.patch.object(
                self.sialib.siatakes, "migrate_legacy_take_pages",
                return_value=([], [])))
            stack.enter_context(mock.patch.object(
                self.sialib.siatakes, "auto_propose_heals",
                return_value=[]))
            intent_reader = mock.Mock(return_value=[])
            if intent_side_effect is not None:
                intent_reader.side_effect = intent_side_effect
            stack.enter_context(mock.patch.object(
                self.sialib.siatakes, "open_intents", intent_reader))
            self.barrier_intent_reader = intent_reader
            stack.enter_context(mock.patch.object(
                self.sialib.siatakes, "summary", return_value={}))
            if takes_summary is not None:
                stack.enter_context(mock.patch.object(
                    self.sialib.siatakes, "summary",
                    return_value=takes_summary))
            stack.enter_context(mock.patch.object(
                self.sialib.siamind, "load_mind", return_value=(
                    copy.deepcopy(initial_mind) if initial_mind is not None
                    else {"workspace": [], "seen": {},
                          "nodes": {}, "edges": {}})))
            stack.enter_context(mock.patch.object(
                self.sialib.siamind, "touch_queue_usage", return_value={}))
            stack.enter_context(mock.patch.object(
                self.sialib.siamind, "sync_graph_state", graph_sync))
            stack.enter_context(mock.patch.object(
                self.sialib.siamind, "drain_touch_queue",
                side_effect=lambda *args, **kwargs:
                (0, None, 0) if kwargs.get("report_capacity")
                else (0, None)))
            stack.enter_context(mock.patch.object(
                self.sialib.siamind, "surprisal_update", return_value=[]))
            stack.enter_context(mock.patch.object(
                self.sialib.siamind, "rebuild_workspace", return_value=[]))
            if not use_real_memory_summary:
                stack.enter_context(mock.patch.object(
                    self.sialib.siamind, "memory_summary", return_value={}))
            stack.enter_context(mock.patch.object(
                self.sialib.siamind, "save_mind"))
            return self.sialib._pulse_transaction(sequence)

    def test_pulse_publishes_actual_familiarity_from_memory_summary(self):
        for complete, expected in ((False, "incomplete"), (True, "complete")):
            mind = self.sialib.siamind._empty_mind()
            mind["familiarity_complete"] = complete
            with self.subTest(expected=expected):
                status = self._run_barrier_pulse(
                    page_activity=False, initial_mind=mind,
                    use_real_memory_summary=True)
                self.assertEqual(status["v"], 2)
                self.assertEqual(
                    status["mind"]["familiarity_status"], expected)
                self.assertEqual(
                    self.barrier_status["mind"]["familiarity_status"],
                    expected)

    def test_status_authority_cannot_disappear_after_sequence_admission(self):
        status = self._complete_status()
        status["pulse_seq"] = 1
        status["organs"] = {
            "retained": {
                "today": status["events_today"],
                "last_ts": status["ts"],
            },
        }
        with self.assertRaisesRegex(
                RuntimeError, "resident status changed after admission"):
            self._run_barrier_pulse(
                page_activity=False,
                status_admission_side_effect=(status, None))
        self.assertIsNone(self.barrier_status)

    def test_admitted_legacy_status_retains_same_day_organ_counters(self):
        status = copy.deepcopy(FROZEN_EFFECTLESS_STATUS)
        status["day"] = self.sialib.today()
        initial_memo = {
            "pulse_seq": status["pulse_seq"],
            "chains": {"sia": "pass"},
            "chains_checked_at": status["integrity"]["checked_at"],
            "ready": copy.deepcopy(READY),
        }
        published = self._run_barrier_pulse(
            page_activity=False, initial_memo=initial_memo,
            status_admission_side_effect=(status, status))
        self.assertEqual(published["organs"], status["organs"])
        self.assertEqual(published["events_today"], status["events_today"])

    def test_invalid_status_memo_fields_withdraw_readiness_before_export(self):
        cases = (
            {"dream": "oops"},
            {"pulse_history": [["not-a-time", 0]]},
            {"redactions": "oops"},
        )
        for corrupt in cases:
            initial = {
                "chains": {"sia": "pass"},
                "ready": copy.deepcopy(READY),
                **copy.deepcopy(corrupt),
            }
            with self.subTest(corrupt=corrupt), self.assertRaisesRegex(
                    RuntimeError, "status memo fields are invalid"):
                self._run_barrier_pulse(
                    page_activity=False, initial_memo=initial)
            self.assertNotIn("ready", self.barrier_persisted)
            self.assertIsNone(self.barrier_status)

    def test_final_status_self_check_withdraws_readiness(self):
        with self.assertRaisesRegex(
                RuntimeError, "pulse status projection is invalid"):
            self._run_barrier_pulse(
                page_activity=False, takes_summary=[])
        self.assertNotIn("ready", self.barrier_persisted)
        self.assertIsNone(self.barrier_status)

    def test_quiet_pulse_retains_the_actual_chain_sweep_timestamp(self):
        checked_at = "2026-08-29T12:00:00Z"
        sweep = mock.Mock(return_value={"sia": "pass"})
        with mock.patch.object(self.sialib, "verify_chains", sweep):
            status = self._run_barrier_pulse(
                page_activity=False,
                initial_memo={
                    "chains": {"sia": "pass"},
                    "chains_checked_at": checked_at,
                    "ready": copy.deepcopy(READY),
                })
        sweep.assert_not_called()
        self.assertEqual(status["integrity"]["checked_at"], checked_at)
        self.assertEqual(
            self.barrier_persisted["chains_checked_at"], checked_at)

    def test_status_intent_roster_reuses_the_admitted_pulse_read(self):
        status = self._run_barrier_pulse(
            page_activity=False,
            intent_side_effect=([], OSError("intent roster changed")))
        self.assertEqual(self.barrier_intent_reader.call_count, 1)
        self.assertEqual(status["intents"], [])
        self.assertNotIn("intents", status["errors"])

    def test_status_intent_roster_refusal_is_not_reported_as_absence(self):
        status = self._run_barrier_pulse(
            page_activity=False,
            intent_side_effect=OSError("intent roster unavailable"))
        self.assertEqual(self.barrier_intent_reader.call_count, 1)
        self.assertEqual(status["intents"], [])
        self.assertEqual(
            status["errors"]["intents"], "intent roster unavailable")
        self.assertEqual(status["state"], "degraded")

    def test_quiet_pulse_binds_only_an_exact_graph_generation(self):
        graph = self._complete_graph()
        status = self._run_barrier_pulse(
            page_activity=False, initial_graph=graph)
        self.assertEqual(status["graph_publication_id"],
                         graph["publication_id"])
        self.assertEqual(status["pages"], graph["pages_total"])
        self.assertEqual(status["graph_nodes"], len(graph["nodes"]))
        self.assertEqual(status["graph_edges"], len(graph["edges"]))

        malformed = copy.deepcopy(graph)
        malformed["nodes"] = "not a graph node roster"
        refused = self._run_barrier_pulse(
            page_activity=False, initial_graph=malformed)
        self.assertEqual(refused["graph_publication_id"], "")
        self.assertEqual(
            (refused["pages"], refused["graph_nodes"],
             refused["graph_edges"]),
            (0, 0, 0))
        self.assertEqual(refused["state"], "degraded")
        self.assertEqual(
            refused["errors"]["graph_snapshot"],
            "resident graph snapshot is invalid")

    def test_invalid_graph_envelope_never_reaches_cognitive_state(self):
        graph = self._complete_graph()
        graph["unexpected"] = "open envelope"
        status = self._run_barrier_pulse(
            page_activity=False, initial_graph=graph)
        self.barrier_graph_sync.assert_not_called()
        self.assertEqual(
            status["errors"]["siamind"],
            "resident graph snapshot is invalid")
        self.assertEqual(
            status["errors"]["graph_snapshot"],
            "resident graph snapshot is invalid")

    def test_partial_graph_envelope_never_reaches_cognitive_state(self):
        graph = self._complete_graph()
        graph["pages_total_complete"] = False
        graph["snapshot"]["complete"] = False
        graph["snapshot"]["failed_ops"] = ["list_pages"]
        status = self._run_barrier_pulse(
            page_activity=False, initial_graph=graph)
        self.barrier_graph_sync.assert_not_called()
        self.assertEqual(
            status["errors"]["siamind"],
            "resident graph snapshot is incomplete")
        self.assertEqual(status["state"], "degraded")

    def test_quiet_pulse_refreshes_an_invalid_chain_cache_pair(self):
        for checked_at in (None, "not-a-time"):
            with self.subTest(checked_at=checked_at):
                sweep = mock.Mock(return_value={"sia": "pass"})
                observed_baselines = []

                def capture(_store, memo, _events, _chains, _salience,
                            _anomalies, **_kwargs):
                    observed_baselines.append(
                        copy.deepcopy(memo.get("chains")))
                    return []

                fixed_now = self.sialib.datetime.datetime(
                    2026, 8, 30, 12,
                    tzinfo=self.sialib.datetime.timezone.utc)
                with mock.patch.object(
                        self.sialib, "verify_chains", sweep), \
                        mock.patch.object(
                            self.sialib, "utcnow", return_value=fixed_now):
                    status = self._run_barrier_pulse(
                        page_activity=False,
                        initial_memo={
                            "chains": {"sia": "pass"},
                            "chains_checked_at": checked_at,
                            "ready": copy.deepcopy(READY),
                        }, think_impl=capture)
                sweep.assert_called_once_with()
                self.assertEqual(observed_baselines, [{"sia": "pass"}])
                self.assertEqual(
                    status["integrity"]["checked_at"],
                    "2026-08-30T12:00:00Z")
                self.assertEqual(
                    self.barrier_persisted["chains_checked_at"],
                    status["integrity"]["checked_at"])

    def test_quiet_pulse_quarantines_a_malformed_chain_roster(self):
        observed_baselines = []

        def capture(_store, memo, _events, _chains, _salience, _anomalies,
                    **_kwargs):
            observed_baselines.append(copy.deepcopy(memo.get("chains")))
            return []

        sweep = mock.Mock(return_value={"sia": "pass"})
        with mock.patch.object(self.sialib, "verify_chains", sweep):
            status = self._run_barrier_pulse(
                page_activity=False, think_impl=capture,
                initial_memo={
                    "chains": ["not", "a", "roster"],
                    "chains_checked_at": "2026-08-29T12:00:00Z",
                    "ready": copy.deepcopy(READY),
                })
        sweep.assert_called_once_with()
        self.assertEqual(observed_baselines, [{}])
        self.assertEqual(status["integrity"]["chains"], {"sia": "pass"})

    def test_absent_notification_baseline_is_durable_before_fence_clear(self):
        with tempfile.TemporaryDirectory() as home, \
                mock.patch.object(self.sialib, "HOME", home):
            status = self._run_barrier_pulse(
                page_activity=False, senses=[self.sialib.sense_notify])
            self.assertEqual(status["events_pulse"], 0)
            self.assertEqual(self.barrier_cursors, {
                "notify.baseline": {
                    "schema": "sia-notification-baseline-v1",
                    "kind": "exact", "names": [],
                },
                "notify.scan_mode": "empty-replay",
            })
            self.assertNotIn(
                self.sialib.NOTIFY_BASELINE_ATTEMPT_KEY,
                self.barrier_persisted)
            fence_set = self.barrier_trace.index(("notify-fence", True))
            cursor_write = self.barrier_trace.index(("cursors", True))
            fence_clear = next(
                index for index, item in enumerate(self.barrier_trace)
                if index > cursor_write
                and item == ("notify-fence", False))
            self.assertLess(fence_set, cursor_write)
            self.assertLess(cursor_write, fence_clear)

            history = os.path.join(
                home, ".local/state/omarchy/notifications/history")
            os.makedirs(history)
            with open(os.path.join(history, "first.json"), "w") as stream:
                json.dump({"app": "fixture", "summary": "first"}, stream)
            replay = self.sialib.sense_notify(self.barrier_cursors)
            while "source.notify.page" in self.barrier_cursors:
                replay.extend(
                    self.sialib.sense_notify(self.barrier_cursors))
            self.assertEqual(
                {event.summary for event in replay
                 if event.kind == "notification"},
                {"fixture: first"})

    def test_idle_status_crash_cannot_retract_published_history(self):
        with self.assertRaisesRegex(OSError, "post-status crash"):
            self._run_barrier_pulse(
                page_activity=False,
                initial_memo={
                    "chains": {"sia": "pass"},
                    "ready": copy.deepcopy(READY),
                },
                status_error=OSError("post-status crash"))

        self.assertEqual(
            self.barrier_persisted["pulse_history"],
            self.barrier_status["history"])

    def test_failed_status_export_recovers_marker_bound_redactions(self):
        prior_redactions = copy.deepcopy(self.sialib.REDACTIONS)
        self.sialib.REDACTIONS.clear()
        self.sialib.REDACTIONS["notify"] = 2
        try:
            with self.assertRaisesRegex(OSError, "status refused"):
                self._run_barrier_pulse(
                    page_activity=True,
                    initial_memo={
                        "chains": {"sia": "pass"},
                        "redactions": {"notify": 1},
                        "ready": copy.deepcopy(READY),
                    },
                    status_error=OSError("status refused"))
        finally:
            self.sialib.REDACTIONS.clear()
            self.sialib.REDACTIONS.update(prior_redactions)

        marker = self.sialib._pending_pulse_marker(
            self.barrier_persisted)
        self.assertEqual(marker["redactions"], {"notify": 3})
        self.assertEqual(
            self.barrier_persisted["redactions"], {"notify": 1})

        def read(path, default):
            if path == self.sialib.STATUS_PATH:
                return {}
            if path == self.sialib.GRAPH_PATH:
                return {
                    "publication_id": "b" * 32,
                    "nodes": [], "edges": [], "pages_total": 0,
                }
            return copy.deepcopy(default)

        with mock.patch.object(
                self.sialib, "read_json", side_effect=read), \
                mock.patch.object(
                    self.sialib.siamind, "load_mind", return_value={}), \
                mock.patch.object(
                    self.sialib, "_bind_pending_pulse_ledger"), \
                mock.patch.object(
                    self.sialib, "_settle_pending_pulse_ledger"), \
                mock.patch.object(self.sialib, "_write_memo"):
            self.assertTrue(
                self.sialib._recover_pending_pulse_publication(
                    self.barrier_persisted))

        self.assertEqual(
            self.barrier_persisted["redactions"], {"notify": 3})
        self.assertNotIn("ready", self.barrier_persisted)
        self.assertIsNotNone(self.sialib._pending_pulse_status_effects(
            self.barrier_persisted))

    def test_late_secret_error_rebinds_redactions_before_status_export(self):
        secret = "token=abcdefghijklmnop"
        prior_redactions = copy.deepcopy(self.sialib.REDACTIONS)
        self.sialib.REDACTIONS.clear()
        try:
            with self.assertRaisesRegex(OSError, "status refused"):
                self._run_barrier_pulse(
                    page_activity=True,
                    initial_memo={
                        "chains": {"sia": "pass"},
                        "redactions": {},
                        "ready": copy.deepcopy(READY),
                    },
                    graph_error=OSError("graph refused " + secret),
                    status_error=OSError("status refused"))
        finally:
            self.sialib.REDACTIONS.clear()
            self.sialib.REDACTIONS.update(prior_redactions)
        self.assertNotIn(secret, self.barrier_status["errors"]["graph_export"])
        self.assertIn("⟦redacted⟧",
                      self.barrier_status["errors"]["graph_export"])
        marker = self.sialib._pending_pulse_marker(self.barrier_persisted)
        self.assertEqual(marker["redactions"], {"status-error": 1})
        self.assertEqual(self.barrier_persisted.get("redactions", {}), {})

        with mock.patch.object(
                self.sialib, "read_json", return_value={}), \
                mock.patch.object(
                    self.sialib.siamind, "load_mind", return_value={}), \
                mock.patch.object(self.sialib, "_bind_pending_pulse_ledger"), \
                mock.patch.object(self.sialib, "_settle_pending_pulse_ledger"), \
                mock.patch.object(self.sialib, "_write_memo"):
            self.assertTrue(self.sialib._recover_pending_pulse_publication(
                self.barrier_persisted))
        self.assertEqual(
            self.barrier_persisted["redactions"], {"status-error": 1})

    def test_idle_pulse_acknowledges_empty_inbox_claim_without_graph(self):
        status = self._run_barrier_pulse(
            page_activity=False, inbox_claim="empty.draining.json")
        self.assertNotIn("graph_export", status["errors"])
        self.assertIn(("inbox-ack", "empty.draining.json"),
                      self.barrier_trace)
        self.assertFalse(any(item[0] == "graph"
                             for item in self.barrier_trace))

    def test_write_ahead_marker_precedes_first_pulse_page_mutation(self):
        self._run_barrier_pulse()
        self.assertLess(self.barrier_trace.index(("memo", True)),
                        self.barrier_trace.index(("page", True)))
        page_index = self.barrier_trace.index(("page", True))
        self.assertTrue(any(
            kind == "memo" and pending
            for kind, pending in self.barrier_trace[:page_index]))

    def test_page_exception_leaves_write_ahead_marker_durable(self):
        with self.assertRaisesRegex(OSError, "page fsync refused"):
            self._run_barrier_pulse(raise_after_page=True)
        self.assertIs(self.barrier_persisted.get("sync_needed"), True)
        page_index = self.barrier_trace.index(("page", True))
        self.assertTrue(any(
            kind == "memo" and pending
            for kind, pending in self.barrier_trace[:page_index]))

    def test_graph_failure_keeps_pulse_publication_debt(self):
        status = self._run_barrier_pulse(
            graph_error=OSError("graph snapshot refused"),
            initial_graph=self._complete_graph())
        self.assertIn("graph_export", status["errors"])
        self.assertEqual(status["graph_publication_id"], "")
        self.assertEqual(
            (status["pages"], status["graph_nodes"],
             status["graph_edges"]),
            (0, 0, 0))
        self.assertEqual(
            status["errors"]["graph_snapshot"],
            "graph publication failed; current graph claims withdrawn")
        self.assertIs(self.barrier_persisted.get("sync_needed"), True)
        self.assertIn(("graph", True), self.barrier_trace)
        marker = self.sialib._pending_pulse_marker(self.barrier_persisted)
        self.assertEqual(marker["effects"], {
            "day": status["day"], "events_pulse": status["events_pulse"],
            "organs": status["organs"],
        })

    def test_failed_event_free_handoff_recovery_keeps_effects_until_status(self):
        effects = {
            "day": self.sialib.today(), "events_pulse": 1,
            "organs": {"notify": {
                "today": 5, "last_ts": "2026-08-30T12:00:00Z"}},
        }
        initial = {
            "chains": {"sia": "pass"},
            "pulse_history": [["2026-08-30T12:00:00Z", 1]],
            "pulse_status_effects_pending": {
                "v": 1, "publication_id": "c" * 32,
                "effects": effects,
                "history": ["2026-08-30T12:00:00Z", 1],
            },
        }
        status = self._run_barrier_pulse(
            page_activity=False, initial_memo=initial,
            graph_error=OSError("graph snapshot refused"))
        marker = copy.deepcopy(
            self.sialib._pending_pulse_marker(self.barrier_persisted))
        self.assertEqual(marker["effects"]["organs"], effects["organs"])
        self.assertNotIn(
            "pulse_status_effects_pending", self.barrier_persisted)

        fresh_graph = {
            "publication_id": "f" * 32,
            "nodes": [], "edges": [], "pages_total": 0,
        }

        def read(path, default):
            if path == self.sialib.STATUS_PATH:
                return copy.deepcopy(status)
            if path == self.sialib.GRAPH_PATH:
                return copy.deepcopy(fresh_graph)
            return copy.deepcopy(default)

        with mock.patch.object(
                self.sialib, "read_json", side_effect=read), \
                mock.patch.object(
                    self.sialib.siamind, "load_mind", return_value={}), \
                mock.patch.object(
                    self.sialib, "_bind_pending_pulse_ledger"), \
                mock.patch.object(
                    self.sialib, "_settle_pending_pulse_ledger"), \
                mock.patch.object(self.sialib, "_write_memo"):
            self.assertTrue(self.sialib._recover_pending_pulse_publication(
                self.barrier_persisted))

        handoff = self.sialib._pending_pulse_status_effects(
            self.barrier_persisted)
        self.assertEqual(handoff["effects"]["organs"], effects["organs"])
        self.assertEqual(
            [row[1] for row in self.barrier_persisted["pulse_history"]],
            [1, 0])
        self.assertNotIn("ready", self.barrier_persisted)

    def test_pulse_debt_clears_only_after_graph_success(self):
        self._run_barrier_pulse()
        self.assertIn(("graph", True), self.barrier_trace)
        self.assertNotIn("sync_needed", self.barrier_persisted)
        final_clear = max(
            index for index, item in enumerate(self.barrier_trace)
            if item == ("memo", False))
        self.assertGreater(
            final_clear, self.barrier_trace.index(("graph", True)))

    def test_failed_sync_is_retried_by_next_idle_pulse(self):
        persisted = {"pulse_seq": 1, "chains": {"sia": "pass"},
                     "ready": copy.deepcopy(READY)}
        trace = []
        statuses = []
        dirty_results = iter((True, False))
        commit_results = iter(("committed", "clean", "clean"))
        sync_results = iter((
            (False, "index refused"), (True, ""), (True, "")))

        def load_memo():
            return copy.deepcopy(persisted)

        def capture_write(path, payload, mode=None):
            if path != self.sialib.MEMO_PATH:
                return
            value = json.loads(payload)
            persisted.clear()
            persisted.update(value)
            trace.append(("memo", value.get("sync_needed", False)))

        def corpus_commit(_message):
            result = next(commit_results)
            trace.append(("commit", result))
            return result

        def brain_sync():
            result = next(sync_results)
            trace.append(("sync", result[0]))
            return result

        def new_mind():
            return {"workspace": [], "seen": {}, "nodes": {}, "edges": {}}

        patches = {
            "ensure_dirs": None,
            "load_cursors": {},
            "save_cursors": None,
            "load_thoughts": {"v": 1, "thoughts": [{
                "ts": "2026-01-01T00:00:00Z", "kind": "grade",
                "text": "judged", "origin": "model",
            }]},
            "load_memo": load_memo,
            "read_json": self._empty_graph(),
            "recover_ledger_transitions": ([], []),
            "_settle_thought_page_signals": (0, 0),
            "think": [],
            "materialize_agent_notes": ([], [], [], []),
            "drain_thought_inbox": ([], None),
            "ensure_organs": False,
            "corpus_dirty": lambda: next(dirty_results),
            "atomic_write": capture_write,
            "corpus_commit": corpus_commit,
            "brain_sync": brain_sync,
            "export_graph": (0, 0, 0),
            "queue_ledger_transition": "pending-record",
            "_settle_ledger_transition": None,
            "export_thoughts": None,
            "ledger_head": (1, "a" * 64),
            "export_status": lambda status: statuses.append(status),
        }
        with tempfile.TemporaryDirectory() as state_dir, ExitStack() as stack:
            stack.enter_context(mock.patch.object(
                self.sialib, "STATE", state_dir))
            stack.enter_context(mock.patch.object(self.sialib, "SENSES", []))
            for name, value in patches.items():
                replacement = value if callable(value) else mock.Mock(
                    return_value=value)
                stack.enter_context(mock.patch.object(
                    self.sialib, name, replacement))
            stack.enter_context(mock.patch.object(
                self.sialib.siatakes, "recover_grade_transactions",
                return_value=([], [])))
            stack.enter_context(mock.patch.object(
                self.sialib.siatakes, "migrate_legacy_take_pages",
                return_value=([], [])))
            stack.enter_context(mock.patch.object(
                self.sialib.siatakes, "auto_propose_heals",
                return_value=[]))
            stack.enter_context(mock.patch.object(
                self.sialib.siatakes, "open_intents", return_value=[]))
            stack.enter_context(mock.patch.object(
                self.sialib.siatakes, "summary", return_value={}))
            stack.enter_context(mock.patch.object(
                self.sialib.siamind, "load_mind", side_effect=new_mind))
            stack.enter_context(mock.patch.object(
                self.sialib.siamind, "touch_queue_usage", return_value={}))
            stack.enter_context(mock.patch.object(
                self.sialib.siamind, "sync_graph_state"))
            stack.enter_context(mock.patch.object(
                self.sialib.siamind, "drain_touch_queue",
                side_effect=lambda *args, **kwargs:
                (0, None, 0) if kwargs.get("report_capacity")
                else (0, None)))
            stack.enter_context(mock.patch.object(
                self.sialib.siamind, "surprisal_update", return_value=[]))
            stack.enter_context(mock.patch.object(
                self.sialib.siamind, "rebuild_workspace", return_value=[]))
            stack.enter_context(mock.patch.object(
                self.sialib.siamind, "memory_summary", return_value={}))
            stack.enter_context(mock.patch.object(
                self.sialib.siamind, "save_mind"))

            first = self.sialib._pulse_transaction(1)
            self.assertEqual(first["state"], "degraded")
            self.assertEqual(first["sync_note"], "index refused")
            self.assertIs(persisted.get("sync_needed"), True)
            self.assertLess(trace.index(("memo", True)),
                            trace.index(("commit", "committed")))

            second_start = len(trace)
            persisted["pulse_seq"] = 2
            second = self.sialib._pulse_transaction(2)
            self.assertEqual(second["state"], "ok")
            self.assertEqual(second["events_pulse"], 0)
            self.assertNotIn("sync_needed", persisted)
            self.assertEqual(trace[second_start:second_start + 2],
                             [("commit", "clean"), ("sync", True)])

        self.assertEqual([item for item in trace if item[0] == "sync"],
                         [("sync", False), ("sync", True), ("sync", True)])
        self.assertEqual(statuses, [first, second])
        self.assertTrue(all(status["thought"]["origin"] == "model"
                            for status in statuses))

    def test_malformed_sync_intent_refuses_before_sensing(self):
        with mock.patch.object(self.sialib, "ensure_dirs"), \
                mock.patch.object(self.sialib, "load_cursors",
                                  return_value={}), \
                mock.patch.object(self.sialib, "load_thoughts",
                                  return_value={"v": 1, "thoughts": []}), \
                mock.patch.object(self.sialib, "load_memo",
                                  return_value={"pulse_seq": 1,
                                                "sync_needed": "yes"}), \
                mock.patch.object(self.sialib, "recover_ledger_transitions") \
                as recover:
            with self.assertRaisesRegex(
                    RuntimeError, "memo sync-needed state is invalid"):
                self.sialib._pulse_transaction(1)
        recover.assert_not_called()

    def test_graph_publication_failure_is_visible_and_signed_as_failure(self):
        queued, settled = [], []

        def queue(*args):
            queued.append(args)
            return "pending"

        patches = {
            "ensure_dirs": None,
            "load_cursors": {},
            "save_cursors": None,
            "load_thoughts": {"v": 1, "thoughts": []},
            "load_memo": {"pulse_seq": 1, "sync_needed": False,
                          "chains": {"sia": "pass"},
                          "ready": copy.deepcopy(READY)},
            "read_json": self._empty_graph(),
            "recover_ledger_transitions": ([], []),
            "_settle_thought_page_signals": (0, 0),
            "think": [],
            "materialize_agent_notes": ([], [], [], []),
            "drain_thought_inbox": ([], None),
            "ensure_organs": False,
            "corpus_dirty": True,
            "atomic_write": None,
            "corpus_commit": "clean",
            "brain_sync": (True, ""),
            "export_graph": OSError("graph snapshot refused"),
            "queue_ledger_transition": queue,
            "_settle_ledger_transition": lambda path: settled.append(path),
            "export_thoughts": None,
            "ledger_head": (0, ""),
            "export_status": None,
        }
        with tempfile.TemporaryDirectory() as state_dir, ExitStack() as stack:
            stack.enter_context(mock.patch.object(
                self.sialib, "STATE", state_dir))
            stack.enter_context(mock.patch.object(self.sialib, "SENSES", []))
            for name, value in patches.items():
                if isinstance(value, BaseException):
                    replacement = mock.Mock(side_effect=value)
                else:
                    replacement = value if callable(value) else mock.Mock(
                        return_value=value)
                stack.enter_context(mock.patch.object(
                    self.sialib, name, replacement))
            stack.enter_context(mock.patch.object(
                self.sialib.siatakes, "recover_grade_transactions",
                return_value=([], [])))
            stack.enter_context(mock.patch.object(
                self.sialib.siatakes, "migrate_legacy_take_pages",
                return_value=([], [])))
            stack.enter_context(mock.patch.object(
                self.sialib.siatakes, "auto_propose_heals",
                return_value=[]))
            stack.enter_context(mock.patch.object(
                self.sialib.siatakes, "open_intents", return_value=[]))
            stack.enter_context(mock.patch.object(
                self.sialib.siatakes, "summary", return_value={}))
            stack.enter_context(mock.patch.object(
                self.sialib.siamind, "load_mind", return_value={
                    "workspace": [], "seen": {}, "nodes": {}, "edges": {}}))
            stack.enter_context(mock.patch.object(
                self.sialib.siamind, "touch_queue_usage", return_value={}))
            stack.enter_context(mock.patch.object(
                self.sialib.siamind, "sync_graph_state"))
            stack.enter_context(mock.patch.object(
                self.sialib.siamind, "drain_touch_queue",
                side_effect=lambda *args, **kwargs:
                (0, None, 0) if kwargs.get("report_capacity")
                else (0, None)))
            stack.enter_context(mock.patch.object(
                self.sialib.siamind, "surprisal_update", return_value=[]))
            stack.enter_context(mock.patch.object(
                self.sialib.siamind, "rebuild_workspace", return_value=[]))
            stack.enter_context(mock.patch.object(
                self.sialib.siamind, "memory_summary", return_value={}))
            stack.enter_context(mock.patch.object(
                self.sialib.siamind, "save_mind"))
            status = self.sialib._pulse_transaction(1)

        self.assertIn("graph_export", status["errors"])
        self.assertEqual(queued[0][1], "PULSE:ingest")
        self.assertEqual(queued[0][3], "graph-fail")
        self.assertEqual(settled, ["pending"])


if __name__ == "__main__":
    unittest.main()
