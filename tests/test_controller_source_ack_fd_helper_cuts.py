"""Supplemental helper lifetime cuts, not full-ACK admission evidence.

The primary descriptor tests exercise actual ACK success and refusal. These
cuts deliberately pass detached invalid helper premises that the unmodified
retained-batch gate rejects. They do not forge pins, replace storage, or claim
that a malformed batch reached or completed ACK.
"""

import copy
import os
import unittest

try:
    import sia_test_home
except ModuleNotFoundError:
    from tests import sia_test_home

from tests import test_controller_source_ack as ack_tests
from tests import test_controller_source_ack_fd_lifetime as lifetime_tests


class ControllerSourceAckDescriptorHelperCuts(unittest.TestCase):
    def setUp(self):
        # Composition avoids discovering the primary fixture's test methods
        # again. The admitted primary module owns safe native-FD cleanup.
        self.lifetime = lifetime_tests.ControllerSourceAckDescriptorLifetime(
            methodName="runTest")

    def refuse_without_effect(self, case, callback, reason):
        reasons = []

        def invoke():
            try:
                return callback()
            except ack_tests.REFUSALS as exc:
                reasons.append(getattr(exc, "reason", None))
                raise

        case.assert_refused_without_effect(invoke)
        self.assertEqual(reasons, [reason])

    def assert_real_file_acquired(self, acquired, path):
        rows = [row for row in acquired if row["path"] == str(path)]
        self.assertTrue(rows, "helper never reached the requested real file")
        self.assertTrue(any(kind == "file" for row in rows
                            for kind, _descriptor, _identity in row["slots"]),
                        "helper observed absence, not the real regular file")

    def test_main_directory_mismatch_closes_actual_file_and_ancestor_chain(self):
        with self.lifetime.fixture() as case:
            import siasourceack as ack
            import siasourcebatch as source

            owner = case.lib.__dict__
            original = copy.deepcopy(case.batch)
            source.validate_batch(owner, original, original["batch_sha256"])
            mutation = copy.deepcopy(original)
            # Both identities come from actual fixture directories. Do not
            # invent an inode or weaken the actual named-directory opener.
            foreign_identity = source._directory_generation(
                os.stat(case.source.root, follow_symlinks=False))
            self.assertNotEqual(foreign_identity,
                                original["cursor_proposal"]["state_identity"])
            mutation["cursor_proposal"]["state_identity"] = foreign_identity
            with self.lifetime.caller_leases(case) as leases, \
                    self.lifetime.observe_acquisitions(
                        caller_leases=leases) as acquired:
                # No synthetic full-ACK admission: the retained pin remains
                # unchanged, and production validation rejects this mutation.
                self.refuse_without_effect(case, lambda: source.validate_batch(
                    owner, mutation, original["batch_sha256"]),
                    "source-batch-pin")
                self.assertEqual(acquired, [])
                self.refuse_without_effect(case, lambda: ack._main_cursor(
                    owner, source, mutation["cursor_proposal"]),
                    "ack-cursor-directory-generation")
                self.assertEqual(case.batch, original)
                self.assert_real_file_acquired(acquired,
                                               case.source.cursors_path)
                self.lifetime.assert_closed(
                    acquired, required_paths=[case.source.cursors_path])

    def test_later_target_decode_refusal_closes_earlier_actual_sys_cursor(self):
        with self.lifetime.fixture(journal=True) as case:
            import siasourceack as ack
            import siasourcebatch as source

            owner = case.lib.__dict__
            original = copy.deepcopy(case.batch)
            source.validate_batch(owner, original, original["batch_sha256"])
            mutation = copy.deepcopy(original)
            proposals = mutation["journal_proposals"]
            self.assertEqual(len(proposals), 1)
            proposal, = proposals
            self.assertEqual([row["scope"] for row in proposal["cursors"]],
                             ["sys", "user"])
            system_row, user_row = proposal["cursors"]
            self.assertIsNotNone(system_row["target"])
            self.assertIsNotNone(user_row["target"])
            user_row["target"]["raw_base64"] = "not!base64"
            system_cursor = case.source_state / "journal-sys.cursor"
            user_cursor = case.source_state / "journal-user.cursor"
            with self.lifetime.caller_leases(case) as leases, \
                    self.lifetime.observe_acquisitions(
                        caller_leases=leases) as acquired:
                self.refuse_without_effect(case, lambda: source.validate_batch(
                    owner, mutation, original["batch_sha256"]),
                    "source-batch-pin")
                # The ordinary proposal validator independently rejects the
                # image itself; it is not replaced or disabled for the helper.
                self.refuse_without_effect(case,
                    lambda: source._validate_journal_proposal(owner, proposal),
                    "journal-cursor-image")
                self.assertEqual(acquired, [])
                self.refuse_without_effect(case, lambda: ack._journal_cursors(
                    owner, source, mutation), "ack-journal-cursor-target")
                self.assertEqual(case.batch, original)
                self.assert_real_file_acquired(acquired, system_cursor)
                self.assertNotIn(str(user_cursor),
                                 {row["path"] for row in acquired},
                                 "invalid target must refuse before user open")
                self.lifetime.assert_closed(
                    acquired, required_paths=[system_cursor])


if __name__ == "__main__":
    unittest.main()
