"""One-entry semantic folding uses the same kernel as whole-history replay."""

import copy
import unittest

import siaeventintake as intake_api
from tests import test_event_live_intake as fixture_tests
from tests import test_live_loop as live_tests


class EventEntryFold(unittest.TestCase):
    def setUp(self):
        self.case = fixture_tests.EventLiveIntakeProjection(methodName="runTest")
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)

    def history(self, *, append):
        first = self.case.entry({"sense_custom:alpha": [self.case.event()]})
        self.case.publish_entry_fixture(first)
        events = [self.case.event("2026-01-07")]
        if append:
            events.append(self.case.event("2026-01-07", occurrence="new-fold-event"))
        later = self.case.entry({"sense_custom:alpha": events},
                                stamp=live_tests.DELIVERED_AT, batch_id="fold-later")
        return self.case.request([first, later])

    def test_split_folding_matches_full_replay_for_repeats_and_new_versions(self):
        for append in (False, True):
            with self.subTest(append=append):
                request = self.history(append=append)
                original = copy.deepcopy(request)
                expected = self.case.project(request)
                intake, associations, versions, current, first = intake_api._intake(request), [], {}, {}, {}
                for entry in request["history"]["entries"]:
                    intake_api._fold_entry(vars(self.case.lib), request, entry,
                                           intake, associations, versions, current, first)
                intake["pages"] = list(versions.values())
                intake["current_versions"] = list(current.values())
                self.assertEqual(intake, expected["intake"])
                self.assertEqual(associations, expected["associations"])
                self.assertEqual(request, original)

    def test_prior_page_bytes_are_required_for_continuation(self):
        request = self.history(append=True)
        self.case.project(request)  # Both fixture entries pass the real front door.
        intake, associations, versions, current, first = intake_api._intake(request), [], {}, {}, {}
        before, after = request["history"]["entries"]
        intake_api._fold_entry(vars(self.case.lib), request, before,
                               intake, associations, versions, current, first)
        for version in versions.values():
            version["content"] = "corrupt prior bytes"
        with self.assertRaises(ValueError):
            intake_api._fold_entry(vars(self.case.lib), request, after,
                                   intake, associations, versions, current, first)
