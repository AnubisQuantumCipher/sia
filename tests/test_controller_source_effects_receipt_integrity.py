"""Closed validation for source-effects WAL and committed receipts."""

import copy
import unittest

from tests import test_controller_source_effects as effects_tests
from tests import test_live_loop as live_tests


REFUSALS = (ValueError, RuntimeError, OSError)


class ControllerSourceEffectsReceiptIntegrity(unittest.TestCase):
    def fresh(self):
        case = effects_tests.ControllerSourceEffects(methodName="runTest")
        case.setUp()
        self.addCleanup(case.doCleanups)
        return case

    @staticmethod
    def _reseal(value, field):
        value[field] = live_tests.digest({
            key: item for key, item in value.items() if key != field
        })

    def test_recovery_refuses_resealed_wrong_handoff_or_closure_result(self):
        for selected in ("status-effects", "closure-result"):
            with self.subTest(selected=selected):
                case = self.fresh()
                case.start()
                with case.publication_effects(
                        crash_at="effects-pending"), self.assertRaisesRegex(
                            RuntimeError,
                            "injected source-effects crash: effects-pending"):
                    case.publisher()(
                        memo=case.live.memo,
                        admitted_status=case.admitted_status)
                changed = copy.deepcopy(case.live.memo)
                pending = changed["controller_source_effects_pending"]
                field = ("status_effects_sha256"
                         if selected == "status-effects"
                         else "closure_result_sha256")
                pending[field] = "9" * 64
                self._reseal(pending, "pending_sha256")
                case.live._write(case.live.paths["MEMO_PATH"], changed)
                case.live.memo.clear()
                case.live.memo.update(changed)

                with case.no_effect_boundary(), self.assertRaises(REFUSALS):
                    case.publisher()(
                        memo=case.live.memo,
                        admitted_status=case.admitted_status)

    def test_completed_retry_revalidates_every_nested_generation_and_binding(self):
        for selected in ("transition", "sync", "target"):
            with self.subTest(selected=selected):
                case = self.fresh()
                case.start()
                with case.publication_effects():
                    case.publisher()(
                        memo=case.live.memo,
                        admitted_status=case.admitted_status)
                changed = copy.deepcopy(case.live.memo)
                receipt = changed["controller_source_effects_committed"]
                if selected == "transition":
                    receipt["transition_sha256"] = "9" * 64
                elif selected == "sync":
                    sync = receipt["sync_generation"]
                    sync["chunks_unembedded"] = 1
                    self._reseal(sync, "generation_sha256")
                else:
                    receipt["target_manifest"][0]["slug"] += "-foreign"
                    manifest_sha256 = live_tests.digest(
                        receipt["target_manifest"])
                    receipt["target_manifest_sha256"] = manifest_sha256
                    sync = receipt["sync_generation"]
                    sync["index_manifest_sha256"] = manifest_sha256
                    self._reseal(sync, "generation_sha256")
                self._reseal(receipt, "receipt_sha256")
                case.live._write(case.live.paths["MEMO_PATH"], changed)
                case.live.memo.clear()
                case.live.memo.update(changed)
                current_status = case.live._read("STATUS_PATH")

                with case.no_effect_boundary(), self.assertRaises(REFUSALS):
                    case.publisher()(
                        memo=case.live.memo,
                        admitted_status=current_status)


if __name__ == "__main__":
    unittest.main()
