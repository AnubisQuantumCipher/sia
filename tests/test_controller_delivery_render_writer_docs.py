"""Keep the held renderer's observable output boundary separate from claims."""

from pathlib import Path
import unittest


class ControllerDeliveryRenderWriterDocumentation(unittest.TestCase):
    def test_architecture_names_held_render_contract_and_remaining_cli_join(self):
        prose = (Path(__file__).resolve().parents[1] / "docs" / "ARCHITECTURE.md").read_text()
        for phrase in (
                "siacontrollerdeliverywriter.render_and_deliver",
                "sia-controller-delivery-render-config-v1",
                "rank-prefix-v1",
                "expected_render_config_sha256",
                "one actual held rank",
                "no semantic fidelity claim for arbitrary callback prose",
                "exact front-door CLI version joins remain separate"):
            with self.subTest(phrase=phrase):
                self.assertTrue(phrase in prose, "missing held-render boundary: " + phrase)


if __name__ == "__main__":
    unittest.main()
