"""Ordered fold controls; synthetic private state, not cache qualification."""

import copy
import unittest
from unittest import mock

import siaeventintake as replay
from tests import test_event_live_intake as fixtures


class ReplayRefusalOrder(unittest.TestCase):
    def setUp(self):
        self.case = fixtures.EventLiveIntakeProjection(methodName="runTest")
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        events = [self.case.event(), self.case.event("2026-01-07", "native:order:second")]
        self.entry = self.case.entry({"sense_custom:alpha": events})
        self.request = self.case.request([self.entry])
        self.owner = dict(vars(self.case.lib))
        members = self.entry["event_batches"][0]["batch"]["members"]
        self.images = list(replay.pages._union_images(self.owner, members).values())
        self.assertEqual(len(self.images), 2)
        self.assertTrue(all(image["before"] is None for image in self.images))
        self.intake = replay._intake(self.request)
        self.associations, self.versions, self.current, self.first = [], {}, {}, {}
        self.trace = []

    def fold_with_trace(self):
        version = self.owner["_corpus_page_version_from_bytes"]
        union, digest = replay.pages._union_images, replay._sha

        def observed_version(*, slug, raw):
            self.trace.append(("version", slug, raw))
            return version(slug=slug, raw=raw)

        def observed_union(owner, members):
            result = union(owner, members)
            self.trace.append(("images-admitted",))
            return result

        def observed_digest(owner, value):
            if type(value) is dict and value.get("schema") == "sia-controller-event-association-v1":
                self.trace.append(("association", value["source_id"], value["event_id"]))
            return digest(owner, value)

        self.owner["_corpus_page_version_from_bytes"] = observed_version
        with self.case.pure_boundary(), \
                mock.patch.object(replay.pages, "_union_images", observed_union), \
                mock.patch.object(replay, "_sha", observed_digest):
            replay._fold_entry(self.owner, self.request, self.entry, self.intake,
                               self.associations, self.versions, self.current, self.first)

    def image_trace(self, *, admission=False):
        result = []
        for image in self.images:
            fields = ("raw", "before") if admission else ("before", "raw")
            for field in fields:
                if image[field] is not None:
                    result.append(("version", image["page"]["slug"], image[field]))
        return result

    def existing_images(self):
        self.case.publish_entry_fixture(self.entry)
        events = [self.case.event(occurrence="native:order:next-first"),
                  self.case.event("2026-01-07", "native:order:next-second")]
        self.entry = self.case.entry({"sense_custom:alpha": events}, batch_id="next-return")
        self.request = self.case.request([self.entry])
        members = self.entry["event_batches"][0]["batch"]["members"]
        self.images = list(replay.pages._union_images(self.owner, members).values())
        self.assertEqual(len(self.images), 2)
        self.assertTrue(all(image["before"] is not None for image in self.images))
        for image in self.images:
            version = self.owner["_corpus_page_version_from_bytes"](
                slug=image["page"]["slug"], raw=image["before"])
            self.versions[version["version_sha256"]] = version
            self.current[image["page"]["slug"]] = version["version_sha256"]

    def assert_refusal(self, reason):
        before = copy.deepcopy((self.request, self.versions, self.current))
        with self.assertRaises(ValueError) as raised:
            self.fold_with_trace()
        self.assertEqual(raised.exception.reason, reason)
        self.assertEqual((self.request, self.versions, self.current), before)
        self.assertEqual(self.associations, [])
        self.assertEqual(self.intake["observations"], [])
        self.assertEqual(self.first, {})

    def test_bad_before_join_stops_fold_callbacks_after_image_admission(self):
        slug = self.images[0]["page"]["slug"]
        self.current[slug] = "prior-pin"
        self.versions["prior-pin"] = {"content": "prior content"}
        self.assert_refusal("unexplained-page-version-change")
        self.assertEqual(self.trace, self.image_trace(admission=True) + [("images-admitted",)])

    def test_collision_stops_later_version_and_association_callbacks(self):
        image = self.images[0]
        version = self.owner["_corpus_page_version_from_bytes"](
            slug=image["page"]["slug"], raw=image["raw"])
        version["content"] = "different content under the same pin"
        self.versions[version["version_sha256"]] = version
        self.assert_refusal("page-version-collision")
        self.assertEqual(self.trace, self.image_trace(admission=True) + [("images-admitted",)]
                         + self.image_trace()[:1])

    def assert_valid_order(self):
        before = copy.deepcopy(self.request)
        self.fold_with_trace()
        records = self.entry["source_returns"]["runs"][0]["events"]
        association_trace = [("association", "sense_custom:alpha", row["event_id"])
                             for row in records]
        self.assertEqual(self.trace, self.image_trace(admission=True) + [("images-admitted",)]
                         + self.image_trace() + association_trace)
        self.assertEqual(len(self.associations), 2)
        self.assertEqual([row["status"] for row in self.associations],
                         ["first-observation", "first-observation"])
        self.assertEqual(self.request, before)

    def test_valid_control_reaches_both_versions_and_associations_in_order(self):
        self.assert_valid_order()

    def test_existing_pages_preserve_admission_and_fold_byte_order(self):
        self.existing_images()
        self.assert_valid_order()

    def test_existing_before_mismatch_stops_fold_after_image_admission(self):
        self.existing_images()
        pin = self.current[self.images[0]["page"]["slug"]]
        self.versions[pin]["content"] = "mismatched existing page"
        self.assert_refusal("unexplained-page-version-change")
        self.assertEqual(self.trace, self.image_trace(admission=True) + [("images-admitted",)])

    def test_later_collision_keeps_private_progress_but_no_associations(self):
        image = self.images[1]
        version = self.owner["_corpus_page_version_from_bytes"](
            slug=image["page"]["slug"], raw=image["raw"])
        version["content"] = "different content under the later pin"
        self.versions[version["version_sha256"]] = version
        before = copy.deepcopy(self.request)
        with self.assertRaises(ValueError) as raised:
            self.fold_with_trace()
        self.assertEqual(raised.exception.reason, "page-version-collision")
        self.assertEqual(self.trace, self.image_trace(admission=True) + [("images-admitted",)]
                         + self.image_trace())
        first = self.images[0]
        self.assertEqual(self.current, {first["page"]["slug"]: first["page"]["version_sha256"]})
        self.assertEqual(self.versions[first["page"]["version_sha256"]]["content"].encode(),
                         first["raw"])
        self.assertEqual(self.versions[version["version_sha256"]], version)
        self.assertEqual(self.associations, [])
        self.assertEqual(self.intake["observations"], [])
        self.assertEqual(self.first, {})
        self.assertEqual(self.request, before)


if __name__ == "__main__":
    unittest.main()
