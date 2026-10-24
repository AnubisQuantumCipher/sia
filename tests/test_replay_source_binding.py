"""Projector consistency cannot substitute for binding captured page bytes."""

import base64
import hashlib
import importlib
import unittest
from unittest import mock

from tests import test_event_live_intake as fixtures


class ReplaySourceBinding(unittest.TestCase):
    def setUp(self):
        self.case = fixtures.EventLiveIntakeProjection(methodName="runTest")
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.replay = importlib.import_module("siaeventintake")
        first = self.case.entry({"sense_custom:alpha": [self.case.event()]})
        self.case.publish_entry_fixture(first)
        second = self.case.entry({"sense_custom:alpha": [
            self.case.event(occurrence="native:intake:second")]})
        self.request = self.case.request([second])
        self.case.assert_projection(self.case.project(self.request), self.request)
        page = second["event_batches"][0]["batch"]["members"][0]["pages"][0]
        self.assertIsNotNone(page["before"])
        self.before_raw = base64.b64decode(page["before"]["raw_utf8_base64"], validate=True)

    def refuses(self, replace, *, late=True):
        projector = self.case.lib._corpus_page_version_from_bytes
        member = self.replay._member
        ready, changed = [not late], []

        def projected(**arguments):
            version = projector(**arguments)
            if ready[0] and arguments["raw"] == self.before_raw:
                changed.append(True)
                return replace(version)
            return version

        def admitted(*arguments):
            result = member(*arguments)
            ready[0] = True
            return result

        before = self.case.fixture.snapshot()
        with mock.patch.object(self.case.lib, "_corpus_page_version_from_bytes", projected), \
                mock.patch.object(self.replay, "_member", admitted):
            with self.assertRaises(ValueError) as caught:
                self.case.project(self.request)
        self.assertTrue(changed, "targeted before-image callback did not run")
        self.assertEqual(self.case.fixture.snapshot(), before)
        self.assertEqual(caught.exception.reason, "upstream-admission")
        self.assertEqual(str(caught.exception.__cause__),
                         "event page plan refused: projected-version-source-binding")

    @staticmethod
    def consistent(version, field, value):
        version[field] = value
        digest = hashlib.sha256(version["content"].encode("utf-8")).hexdigest()
        version["source_sha256"] = digest
        version["content_sha256"] = digest
        identity = {key: version[key] for key in (
            "subject", "content_sha256", "source_sha256", "origin")}
        version["version_sha256"] = fixtures.digest(identity)
        return version

    def test_consistent_historical_content_substitution(self):
        self.refuses(lambda v: self.consistent(v, "content", "invented history\n"))

    def test_consistent_historical_subject_substitution(self):
        self.refuses(lambda v: self.consistent(v, "subject", "events/other/2026-01-06"))

    def test_consistent_historical_origin_substitution(self):
        self.refuses(lambda v: self.consistent(v, "origin", "model"))

    def test_plan_admission_checks_before_image_content(self):
        self.refuses(lambda v: self.consistent(v, "content", "invented history\n"), late=False)

    def test_callback_extra_field_is_refused(self):
        self.refuses(lambda v: {**v, "extra": "unrecognized"})

    def test_callback_missing_field_is_refused(self):
        self.refuses(lambda v: {key: value for key, value in v.items() if key != "content"})

    def test_callback_non_mapping_is_refused(self):
        self.refuses(lambda _v: None)

    def test_callback_non_string_content_is_refused(self):
        self.refuses(lambda v: {**v, "content": []})

    def test_callback_string_subclass_is_refused(self):
        class Text(str):
            pass

        self.refuses(lambda v: {**v, "content": Text(v["content"])})

    def refuses_later_mutation(self, operation):
        projector, member = self.case.lib._corpus_page_version_from_bytes, self.replay._member
        ready, retained, changed = [], [], []

        def projected(**arguments):
            version = projector(**arguments)
            if ready:
                if arguments["raw"] == self.before_raw:
                    retained.append(version)
                elif retained:
                    self.consistent(retained[-1], "content", "invented earlier history\n")
                    changed.append(True)
            return version

        def admitted(*arguments):
            result = member(*arguments)
            ready.append(True)
            return result

        before = self.case.fixture.snapshot()
        with mock.patch.object(self.case.lib, "_corpus_page_version_from_bytes", projected), \
                mock.patch.object(self.replay, "_member", admitted):
            with self.assertRaises(ValueError) as caught:
                operation()
        self.assertTrue(changed, "later projector did not change earlier output")
        self.assertEqual(self.case.fixture.snapshot(), before)
        self.assertEqual(caught.exception.reason, "page-version-identity-changed")

    def test_later_projector_cannot_replace_an_earlier_checked_version(self):
        self.refuses_later_mutation(lambda: self.case.project(self.request))

    def test_compact_delta_rejects_later_projector_mutation(self):
        api = importlib.import_module("siaeventcheckpoint")
        owner = self.case.lib.__dict__
        request = self.case.request([self.case.entry({}, batch_id="empty-bootstrap")])
        checkpoint = api.bootstrap_incremental(
            owner, request=request, expected_request_sha256=fixtures.digest(request))
        delta = {"schema": "sia-event-replay-delta-v1",
                 "parent_checkpoint_sha256": fixtures.digest(checkpoint),
                 "entry": self.request["history"]["entries"][0],
                 "observed_at": self.request["observed_at"],
                 "non_claims": list(api.DELTA_NON_CLAIMS)}
        self.refuses_later_mutation(lambda: api.project_delta(
            owner, checkpoint=checkpoint, expected_checkpoint_sha256=fixtures.digest(checkpoint),
            delta=delta, expected_delta_sha256=fixtures.digest(delta)))

    def test_public_result_does_not_retain_projector_mapping(self):
        projector = self.case.lib._corpus_page_version_from_bytes
        returned = []

        def projected(**arguments):
            version = projector(**arguments)
            returned.append(version)
            return version

        with mock.patch.object(self.case.lib, "_corpus_page_version_from_bytes", projected):
            result = self.case.project(self.request)
        self.assertTrue(returned)
        before = fixtures.canonical(result)
        for version in returned:
            version["content"] = "subsequent callback mutation"
        self.assertEqual(fixtures.canonical(result), before)


if __name__ == "__main__":
    unittest.main()
