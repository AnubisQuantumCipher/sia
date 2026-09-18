"""Adversarial additive gist publication checks using isolated native fixtures.

These tests establish local byte, roster and filesystem behavior only. They
do not establish native truth, biological consolidation or retrieval benefit.
"""

import copy
import importlib
from pathlib import Path
import unittest
from unittest import mock

try:
    import sia_test_home
except ModuleNotFoundError:
    from tests import sia_test_home

from tests import test_live_gist_binding as binding_tests
from tests import test_live_loop as live_tests


class SourceGistIntegrity(unittest.TestCase):
    def setUp(self):
        self.fixture = binding_tests.LiveGistBinding(methodName="runTest")
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.lib = self.fixture.lib
        self.component = importlib.import_module("siasourcegist")
        request = self.fixture.request(("1",))
        self.transition = self.fixture.pulse(request, wrapper=self.fixture.wrapper(request))
        self.assertTrue(self.transition["gist_pages"])
        self.plan = self.component.prepare(
            self.lib.__dict__, transition=self.transition,
            expected_transition_sha256=self.transition["transition_sha256"])

    @staticmethod
    def reseal(value, field):
        value[field] = live_tests.digest({key: item for key, item in value.items() if key != field})

    def publish(self, plan=None):
        plan = self.plan if plan is None else plan
        return self.component.publish(
            self.lib.__dict__, plan=plan, expected_plan_sha256=plan["plan_sha256"])

    def test_resealed_omitted_proposal_cannot_redefine_transition(self):
        changed = copy.deepcopy(self.transition)
        changed["gist_pages"] = []
        self.reseal(changed, "transition_sha256")
        with self.assertRaises(ValueError), mock.patch.object(
                self.lib.siaqueue, "fixed_atomic_publish") as publish:
            self.component.prepare(
                self.lib.__dict__, transition=changed,
                expected_transition_sha256=changed["transition_sha256"])
        publish.assert_not_called()

    def test_resealed_page_metadata_and_roster_mutations_refuse_before_effect(self):
        mutations = (
            lambda plan: plan["pages"][0].update(raw_bytes=True),
            lambda plan: plan["pages"][0].update(raw_utf8_base64=""),
            lambda plan: plan["pages"][0]["target_version"].update(origin="evidence"),
            lambda plan: plan["target_versions"].clear(),
            lambda plan: plan["pages"].append(copy.deepcopy(plan["pages"][0])),
            lambda plan: plan["non_claims"].clear(),
        )
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                changed = copy.deepcopy(self.plan)
                mutate(changed)
                self.reseal(changed, "plan_sha256")
                with mock.patch.object(self.lib, "corpus_owner") as owner, \
                        mock.patch.object(self.lib.siaqueue, "fixed_atomic_publish") as publish, \
                        self.assertRaises(ValueError):
                    self.publish(changed)
                owner.assert_not_called()
                publish.assert_not_called()

    def test_late_conflicting_target_refuses_before_any_page_is_added(self):
        proposals = copy.deepcopy(self.transition["gist_pages"])
        added = copy.deepcopy(proposals[0])
        added["subject"] = "gists/live/" + live_tests.digest("additional-pinned-gist")
        added["version_sha256"] = live_tests.digest({key: added[key] for key in (
            "subject", "content_sha256", "source_sha256", "origin")})
        proposals.append(added)
        plan = self.component.prepare_pages(
            self.lib.__dict__, gist_pages=proposals,
            expected_gist_pages_sha256=live_tests.digest(proposals),
            transition_sha256=self.transition["transition_sha256"])
        target = Path(self.lib.corpus_path(added["subject"]))
        target.parent.mkdir(parents=True, exist_ok=True)
        original = b"episode bytes already occupying this name\n"
        target.write_bytes(original)
        target.chmod(0o600)
        with mock.patch.object(self.lib, "_before_corpus_mutation") as mutation, \
                mock.patch.object(self.lib.siaqueue, "fixed_atomic_publish") as publish, \
                self.assertRaises(ValueError):
            self.publish(plan)
        mutation.assert_not_called()
        publish.assert_not_called()
        self.assertEqual(target.read_bytes(), original)
        self.assertFalse(Path(self.lib.corpus_path(proposals[0]["subject"])).exists())

    def test_mutation_barrier_cannot_change_admitted_input_before_page_effect(self):
        target = Path(self.lib.corpus_path(self.plan["target_versions"][0]["slug"]))

        def mutate():
            self.plan["non_claims"].append("changed after admission")

        with mock.patch.object(self.lib, "_before_corpus_mutation", side_effect=mutate), \
                self.assertRaises(ValueError):
            self.publish()
        self.assertFalse(target.exists(), "changed caller plan reached a page write")

    def test_empty_replay_has_no_filesystem_effect_and_expected_receipt_is_pure(self):
        plan = self.component.prepare_pages(
            self.lib.__dict__, gist_pages=[], expected_gist_pages_sha256=live_tests.digest([]),
            transition_sha256=self.transition["transition_sha256"])
        with mock.patch.object(self.lib, "corpus_owner") as owner, \
                mock.patch.object(self.lib.siaqueue, "fixed_atomic_publish") as publish:
            expected = self.component.publication_receipt(
                self.lib.__dict__, plan=plan, expected_plan_sha256=plan["plan_sha256"])
            observed = self.publish(plan)
        self.assertEqual(observed, expected)
        self.assertEqual(observed["target_versions"], [])
        owner.assert_not_called()
        publish.assert_not_called()

    def test_intermediate_parent_swap_cannot_redirect_gist_publication(self):
        target = Path(self.lib.corpus_path(self.plan["target_versions"][0]["slug"]))
        ancestor = target.parent.parent
        retained = Path(self.fixture.fixture.root) / "retained-gist-parent"
        redirected = Path(self.fixture.fixture.root) / "redirected-gist-parent"
        (redirected / "live").mkdir(parents=True)
        real_publish = self.lib.siaqueue.fixed_atomic_publish
        swapped = []

        def replace_parent_then_publish(path, data, **kwargs):
            if Path(path) == target and not swapped:
                ancestor.rename(retained)
                ancestor.symlink_to(redirected, target_is_directory=True)
                swapped.append(True)
            return real_publish(path, data, **kwargs)

        try:
            with mock.patch.object(self.lib.siaqueue, "fixed_atomic_publish",
                                   side_effect=replace_parent_then_publish), \
                    self.assertRaises((ValueError, RuntimeError, OSError)):
                self.publish()
        finally:
            if swapped:
                ancestor.unlink()
                retained.rename(ancestor)
        self.assertEqual(swapped, [True])
        self.assertFalse((redirected / "live" / target.name).exists(),
                         "publication followed a substituted intermediate directory")
