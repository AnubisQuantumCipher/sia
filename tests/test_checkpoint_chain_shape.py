"""Isolated schema admission for the compact chain continuation pointer.

Shape only. Behavioral authority over a chain stays with acknowledgment and
the pinned manifest; nothing here establishes that a pointer names a real
chain, only that a malformed representation is refused by name rather than
crashing or being silently accepted.
"""

import unittest

import siacheckpointdispatch as api


OWNER = {"MAX_JSON_SAFE_INTEGER": 2 ** 53 - 1}
COMMITTED = {
    "source_batch_sha256": "c" * 64,
    "live_generation_sha256": "d" * 64,
    "source_effects_receipt_sha256": "e" * 64,
}


class ChainPointerShape(unittest.TestCase):
    def pointer(self, **changes):
        marker = dict(api._build_chain(OWNER, directory="/tmp/sia-chain-shape",
            root_sha256="a" * 64, head_sha256="b" * 64, next_generation=2,
            committed=COMMITTED, status=api._CHAIN_CONTINUED), **changes)
        # Re-digest so the self-hash never masks the field under test.
        marker["marker_sha256"] = api._chain_digest(marker)
        return marker

    def test_both_defined_states_are_admitted(self):
        for status in (api._CHAIN_STATUS, api._CHAIN_CONTINUED):
            admitted = api._validate_chain(OWNER, self.pointer(status=status))
            self.assertEqual(admitted["status"], status)

    def test_non_string_status_refuses_by_name_instead_of_raising_typeerror(self):
        # [] and {} are unhashable: an unguarded `in frozenset` would raise
        # TypeError here rather than a named refusal.
        for bad in ([], {}, 1, 1.5, None, True):
            with self.subTest(status=bad):
                with self.assertRaises(ValueError) as refused:
                    api._validate_chain(OWNER, self.pointer(status=bad))
                self.assertEqual(refused.exception.reason,
                    "checkpoint-chain-marker-shape")

    def test_unknown_string_status_is_refused(self):
        for bad in ("", "retired", "selected", "CONTINUED"):
            with self.subTest(status=bad):
                with self.assertRaises(ValueError) as refused:
                    api._validate_chain(OWNER, self.pointer(status=bad))
                self.assertEqual(refused.exception.reason,
                    "checkpoint-chain-marker-shape")

    def test_a_present_null_pointer_is_malformed_not_absent(self):
        with self.assertRaises(ValueError) as refused:
            api.select_chain(OWNER, memo={api._CHAIN: None})
        self.assertEqual(refused.exception.reason, "checkpoint-chain-marker-shape")
        # Absence stays absence, and is not evidence that no chain exists.
        self.assertIsNone(api.select_chain(OWNER, memo={}))


if __name__ == "__main__":
    unittest.main()
