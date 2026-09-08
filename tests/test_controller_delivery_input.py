"""RED contract for pure append-only delivery input, not live acquisition.

Root alone runs this suite. Existing synthetic source/clock fixtures and the
real reserve/write/flush/inspect journal path supply the ordinary inputs.
Adversarial copies are explicitly rehashed caller representations; a hash
does not make them witnessed source state or historical output.

The binder consumes no queue, opens no path and invents no clock. An outer
corpus-owner capture must provide the complete inspected epoch and the fully
source-authorized committed parent. The inspection's truth boundary remains
verbatim; pure delivery records remain derived, with their original boundary.
No content, source origin, engine row or retained version may change here.
Existing source-batch v1/v2 contracts are not extended by this test file.

Equal-time journal sorting is not committed history order: an ID delivered
later can sort before a previously consumed ID. Preserve the old byte-exact
prefix, require every old record unchanged by identity, then append new
records in journal order. A pending intent or uncertain output refuses the
whole input, never a partial history. New records must reference the exact
parent state and versions that parent held, not successor-only perception.
All timestamps and numeric limits below are observed existing fixture values;
there is no new numerical score, duration, metric or arithmetic oracle.
"""

import copy
import importlib
import inspect
import unittest
from unittest import mock

from tests import test_delivery_journal as journal_tests
from tests import test_live_loop as live_tests


BINDING_KEYS = {
    "schema", "status", "epoch_id", "observed_at", "journal_sha256",
    "previous_state_sha256", "intake_sha256", "policy_sha256",
    "deliveries", "deliveries_sha256", "journal_non_claims", "non_claims",
    "binding_sha256",
}


class ControllerDeliveryInput(unittest.TestCase):
    def setUp(self):
        try:
            self.module = importlib.import_module("siacontrollerdeliveryinput")
        except ModuleNotFoundError as exc:
            self.fail("source-bound delivery input must exist: " + str(exc))
        self.assertTrue(callable(getattr(self.module, "bind", None)))
        self.assertTrue(hasattr(self.module, "ControllerDeliveryInputRefusal"))
        self.assertTrue(hasattr(self.module, "NON_CLAIMS"))
        self.journal = journal_tests.DeliveryJournal(methodName="runTest")
        self.addCleanup(self.journal.doCleanups)
        self.journal.setUp()
        self.fx = self.journal.fx
        self.live = self.journal.live
        self.parent = self.fx._prepare(self.live)
        self.assertEqual(self.journal.ranked["state_sha256"],
                         self.parent["state_sha256"])
        self.kw = {
            "journal": self.journal._inspect(),
            "expected_journal_sha256": None,
            "previous_state": self.parent["state"],
            "expected_previous_state_sha256": self.parent["state_sha256"],
            "intake": self.fx.kw["intake"],
            "expected_intake_sha256": self.fx.kw["expected_intake_sha256"],
            "policy": self.fx.policy,
            "expected_policy_sha256": self.fx.kw["expected_policy_sha256"],
            "observed_at": live_tests.EXPIRED_AT,
        }
        self.kw["expected_journal_sha256"] = live_tests.digest(self.kw["journal"])

    def _bind(self, **changes):
        return self.module.bind(**{**self.kw, **changes})

    def _journal_arguments(self, value=None):
        value = self.journal._inspect() if value is None else value
        return {"journal": value, "expected_journal_sha256": live_tests.digest(value)}

    def _deliver(self, request_id=journal_tests.REQUEST_A, *, ranked=None):
        changes = {"request_id": request_id}
        if ranked is not None:
            changes.update(ranked=ranked,
                           expected_ranked_sha256=ranked["rank_sha256"],
                           emitted_row_refs=list(ranked["order"]))
        reservation = self.journal._reserve(**changes)
        sink = journal_tests.ByteSink()
        result = self.journal._deliver(reservation, sink=sink)
        self.assertEqual(bytes(sink.body), self.journal.body)
        self.assertEqual(sink.events[-1], "flush")
        self.assertEqual(result["boundary"], "write-all-and-flush-returned")
        return result["record"]

    def _parent_with(self, binding):
        return self.fx._prepare(
            self.live, previous_state=self.parent["state"],
            expected_previous_state_sha256=self.parent["state_sha256"],
            deliveries=binding["deliveries"],
            expected_deliveries_sha256=binding["deliveries_sha256"],
            observed_at=live_tests.DELIVERED_AT)

    def _refusal(self, **changes):
        with self.assertRaises(self.module.ControllerDeliveryInputRefusal) as caught:
            self._bind(**changes)
        self.assertIs(type(caught.exception.reason), str)
        self.assertRegex(caught.exception.reason, r"\A[a-z][a-z0-9-]*\Z")
        self.assertEqual(caught.exception.non_claims, list(self.module.NON_CLAIMS))
        return caught.exception

    def _assert_contract(self, result, *, journal, parent=None):
        parent = self.parent if parent is None else parent
        self.assertEqual(set(result), BINDING_KEYS)
        self.assertEqual(result["schema"], "sia-controller-delivery-binding-v1")
        self.assertEqual(result["status"], "bound-not-consumed")
        self.assertEqual(result["epoch_id"], live_tests.EPOCH)
        self.assertEqual(result["observed_at"], self.kw["observed_at"])
        self.assertEqual(result["journal_sha256"], live_tests.digest(journal))
        self.assertEqual(result["previous_state_sha256"], parent["state_sha256"])
        self.assertEqual(result["intake_sha256"], self.kw["expected_intake_sha256"])
        self.assertEqual(result["policy_sha256"], self.kw["expected_policy_sha256"])
        self.assertEqual(result["journal_non_claims"], list(self.journal.module.NON_CLAIMS))
        self.assertEqual(result["non_claims"], list(self.module.NON_CLAIMS))
        self.assertEqual(result["deliveries_sha256"], live_tests.digest(result["deliveries"]))
        self.assertEqual(result["binding_sha256"],
                         live_tests.own_digest(result, "binding_sha256"))
        self.assertNotIn("published", result)
        self.assertNotIn("acknowledged", result)

    def test_api_requires_exact_keyword_only_pins_and_no_ambient_authority(self):
        signature = inspect.signature(self.module.bind)
        self.assertEqual(set(signature.parameters), set(self.kw))
        for parameter in signature.parameters.values():
            self.assertEqual(parameter.kind, inspect.Parameter.KEYWORD_ONLY)
            self.assertIs(parameter.default, inspect.Parameter.empty)
        self.assertTrue(self.module.NON_CLAIMS)
        self.assertTrue(all(type(item) is str and item for item in self.module.NON_CLAIMS))
        self._refusal(previous_state=None, expected_previous_state_sha256=None)

    def test_complete_empty_epoch_preserves_parent_without_files_clocks_or_consumption(self):
        before = copy.deepcopy(self.kw)
        disk = self.journal._snapshot()
        with mock.patch("builtins.open", side_effect=AssertionError("pure binder opened file")), \
                mock.patch("os.open", side_effect=AssertionError("pure binder acquired descriptor")), \
                mock.patch("time.time", side_effect=AssertionError("pure binder invented clock")), \
                mock.patch.object(self.journal.module, "inspect_deliveries",
                                  side_effect=AssertionError("pure binder acquired journal")):
            result = self._bind()
        self._assert_contract(result, journal=self.kw["journal"])
        self.assertEqual(result["deliveries"], self.parent["state"]["deliveries"])
        self.assertEqual(self.kw, before)
        self.assertEqual(self.journal._snapshot(), disk)

    def test_real_completion_is_unchanged_and_drives_the_real_successor_loop(self):
        record = self._deliver()
        arguments = self._journal_arguments()
        before = copy.deepcopy({**self.kw, **arguments})
        disk = self.journal._snapshot()
        result = self._bind(**arguments)
        self._assert_contract(result, journal=arguments["journal"])
        self.assertEqual(result["deliveries"], {
            "schema": "sia-live-deliveries-v1", "epoch_id": live_tests.EPOCH,
            "complete": True, "records": [record],
        })
        self.assertEqual(result["deliveries"]["records"][0]["origin"], "derived")
        self.assertEqual(result["deliveries"]["records"][0]["boundary"],
                         "supplied-bytes-admitted-not-observed-output-v1")
        successor = self._parent_with(result)
        uses = [use for use in successor["state"]["uses"]
                if use["kind"] == "service-output-completed"]
        pages = {page["version_sha256"]: page for page in self.kw["intake"]["pages"]}
        self.assertEqual({use["version_sha256"] for use in uses},
                         {row["version_sha256"] for row in record["rows"]})
        for use in uses:
            page = pages[use["version_sha256"]]
            self.assertEqual(use["origin"], "derived")
            self.assertEqual(use["subject_origin"], page["origin"])
            self.assertEqual(use["content_sha256"], page["content_sha256"])
            self.assertEqual(use["source_sha256"], page["source_sha256"])
            self.assertEqual(use["record_id"], record["id"])
        self.assertEqual(successor["state"]["intake"], self.kw["intake"])
        self.assertTrue(successor["state"]["coretrieval_trace"]["deliveries"])
        self.assertTrue(successor["state"]["coretrieval"]["graph"]["edges"])
        self.assertEqual({**self.kw, **arguments}, before)
        self.assertEqual(self.journal._snapshot(), disk)
        result["deliveries"]["records"][0]["rows"][0]["row"]["chunk_text"] = "caller edit"
        result["journal_non_claims"].clear()
        self.assertEqual({**self.kw, **arguments}, before)
        self.assertEqual(self.journal._snapshot(), disk)

    def test_same_second_later_lower_id_appends_after_the_exact_committed_prefix(self):
        prior_record = self._deliver(journal_tests.REQUEST_B)
        first = self._bind(**self._journal_arguments())
        parent = self._parent_with(first)
        ranked = self.fx._rank(self.live, parent, observed_at=live_tests.DELIVERED_AT)
        later_record = self._deliver(journal_tests.REQUEST_A, ranked=ranked)
        arguments = self._journal_arguments()
        self.assertEqual(arguments["journal"]["records"], [later_record, prior_record])
        parent_arguments = {
            "previous_state": parent["state"],
            "expected_previous_state_sha256": parent["state_sha256"],
        }
        result = self._bind(**arguments, **parent_arguments)
        self._assert_contract(result, journal=arguments["journal"], parent=parent)
        self.assertEqual(live_tests.canonical(result["deliveries"]["records"][:1]),
                         live_tests.canonical(parent["state"]["deliveries"]["records"]))
        self.assertEqual(result["deliveries"]["records"], [prior_record, later_record])
        self.assertEqual(self._bind(**arguments, **parent_arguments), result)
        resumed = self.fx._prepare(
            self.live, **parent_arguments, deliveries=result["deliveries"],
            expected_deliveries_sha256=result["deliveries_sha256"],
            observed_at=live_tests.EXPIRED_AT)
        self.assertEqual(resumed["state"]["deliveries"]["records"],
                         [prior_record, later_record])

    def test_unchanged_consumed_history_is_idempotent_not_another_use(self):
        record = self._deliver()
        arguments = self._journal_arguments()
        first = self._bind(**arguments)
        parent = self._parent_with(first)
        second = self._bind(
            **arguments, previous_state=parent["state"],
            expected_previous_state_sha256=parent["state_sha256"])
        self.assertEqual(second["deliveries"], parent["state"]["deliveries"])
        self.assertEqual(second["deliveries"]["records"], [record])

    def test_missing_or_rewritten_committed_record_refuses_even_with_fresh_hashes(self):
        record = self._deliver()
        first = self._bind(**self._journal_arguments())
        parent = self._parent_with(first)
        parent_arguments = {
            "previous_state": parent["state"],
            "expected_previous_state_sha256": parent["state_sha256"],
        }
        missing = self.journal._inspect()
        missing["records"] = []
        self._refusal(**self._journal_arguments(missing), **parent_arguments)
        changed = self.journal._inspect()
        changed["records"] = [self.live.complete_delivery(
            ranked=self.journal.ranked,
            expected_ranked_sha256=self.journal.ranked["rank_sha256"],
            emitted_row_refs=self.journal.refs, output_utf8=b"different supplied bytes\n",
            request_id=record["id"], completed_at=record["completed_at"])]
        self._refusal(**self._journal_arguments(changed), **parent_arguments)
        changed = self.journal._inspect()
        typed_record = changed["records"][0]
        self.assertIs(type(typed_record["rows"][0]["row"]["score"]), float)
        typed_record["rows"][0]["row"]["score"] = 1
        typed_record["record_sha256"] = live_tests.own_digest(typed_record, "record_sha256")
        self._refusal(**self._journal_arguments(changed), **parent_arguments)

    def test_pending_intent_and_attempt_with_unknown_output_refuse_without_repair(self):
        reservation = self.journal._reserve()
        self._refusal(**self._journal_arguments())

        def unknown():
            raise OSError("synthetic flush refusal")

        with self.assertRaises(self.journal.module.DeliveryJournalRefusal) as caught:
            self.journal._deliver(
                reservation, sink=journal_tests.ByteSink(before_flush=unknown))
        self.assertEqual(caught.exception.output_state, "unknown")
        inspected = self.journal._inspect()
        self.assertIs(inspected["complete"], False)
        self.assertEqual(inspected["pending"], [journal_tests.REQUEST_A])
        self.assertEqual(inspected["records"], [])
        disk = self.journal._snapshot()
        self._refusal(**self._journal_arguments(inspected))
        self.assertEqual(self.journal._snapshot(), disk)

    def test_closed_journal_epoch_pending_and_nonclaims_contract_refuses_rehashes(self):
        for change in (
            {"schema": "legacy-touch-tail"}, {"epoch_id": "foreign-epoch"},
            {"complete": False}, {"complete": 1},
            {"pending": [journal_tests.REQUEST_A]}, {"non_claims": []},
            {"complete": True, "extra": "ignored authority is forbidden"},
        ):
            with self.subTest(change=change):
                value = {**copy.deepcopy(self.kw["journal"]), **change}
                self._refusal(**self._journal_arguments(value))

    def test_duplicate_or_noncanonical_full_journal_order_refuses(self):
        self._deliver(journal_tests.REQUEST_A)
        self._deliver(journal_tests.REQUEST_B)
        inspected = self.journal._inspect()
        changed = copy.deepcopy(inspected)
        changed["records"].reverse()
        self._refusal(**self._journal_arguments(changed))
        changed = copy.deepcopy(inspected)
        changed["records"].append(copy.deepcopy(changed["records"][0]))
        self._refusal(**self._journal_arguments(changed))

    def test_external_pins_clock_and_parent_contract_are_not_inferred(self):
        self._deliver()
        arguments = self._journal_arguments()
        for field in ("expected_journal_sha256", "expected_previous_state_sha256",
                      "expected_intake_sha256", "expected_policy_sha256"):
            with self.subTest(field=field):
                self._refusal(**{**arguments, field: "0" * 64})
        for clock in (None, True, live_tests.START, live_tests.NOW):
            with self.subTest(clock=clock):
                self._refusal(**arguments, observed_at=clock)
        changed = copy.deepcopy(self.parent["state"])
        changed["uses"] = []
        self._refusal(**arguments, previous_state=changed,
                      expected_previous_state_sha256=live_tests.digest(changed))

    def test_new_record_cannot_claim_another_state_or_preparent_rank_clock(self):
        self._deliver(journal_tests.REQUEST_A)
        first = self._bind(**self._journal_arguments())
        parent = self._parent_with(first)
        # This real journal completion used the older rank plan. It is not a
        # newly witnessed recall against the successor's committed state.
        self._deliver(journal_tests.REQUEST_B)
        arguments = self._journal_arguments()
        self._refusal(**arguments, previous_state=parent["state"],
                      expected_previous_state_sha256=parent["state_sha256"])
        changed = copy.deepcopy(arguments["journal"])
        record = changed["records"][-1]
        record["state_sha256"] = parent["state_sha256"]
        record["record_sha256"] = live_tests.own_digest(record, "record_sha256")
        self._refusal(**self._journal_arguments(changed), previous_state=parent["state"],
                      expected_previous_state_sha256=parent["state_sha256"])

    def test_new_record_cannot_rewrite_content_origin_rows_or_version_joins(self):
        self._deliver()
        inspected = self.journal._inspect()
        for field, value in (
            ("chunk_text", "invented source content"),
            ("origin", "legacy-unlabeled"),
            ("slug", "events/foreign-source"),
        ):
            with self.subTest(field=field):
                changed = copy.deepcopy(inspected)
                record = changed["records"][0]
                record["rows"][0]["row"][field] = value
                record["record_sha256"] = live_tests.own_digest(record, "record_sha256")
                self._refusal(**self._journal_arguments(changed))
        changed = copy.deepcopy(inspected)
        record = changed["records"][0]
        record["rows"][0]["version_sha256"] = "0" * 64
        record["record_sha256"] = live_tests.own_digest(record, "record_sha256")
        self._refusal(**self._journal_arguments(changed))

    def test_successor_only_version_does_not_backfill_a_parent_recall(self):
        self._deliver()
        changed = self.journal._inspect()
        intake = copy.deepcopy(self.kw["intake"])
        page = copy.deepcopy(intake["pages"][0])
        old_version = page["version_sha256"]
        page["content"] += "\nadditional synthetic successor episode\n"
        page["content_sha256"] = live_tests.bytes_digest(page["content"].encode("utf-8"))
        page["version_sha256"] = live_tests.version_digest(page)
        intake["pages"].append(page)
        intake["current_versions"] = [
            page["version_sha256"] if version == old_version else version
            for version in intake["current_versions"]]
        record = changed["records"][0]
        target = next(row for row in record["rows"] if row["version_sha256"] == old_version)
        target["version_sha256"] = page["version_sha256"]
        target["row"]["chunk_text"] = page["content"]
        record["record_sha256"] = live_tests.own_digest(record, "record_sha256")
        self._refusal(**self._journal_arguments(changed), intake=intake,
                      expected_intake_sha256=live_tests.digest(intake))


if __name__ == "__main__":
    unittest.main()
