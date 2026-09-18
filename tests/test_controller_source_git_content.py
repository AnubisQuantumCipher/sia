"""The source Git boundary accepts an explicit content-publication identity.

The v2 request covers both event closures and additive gist pages. Its returned
Git generation keeps the existing exact contract and descriptor protections.
"""

from unittest import mock

from tests import test_controller_source_git_generation as generation


class ControllerSourceGitContent(generation.ControllerSourceGitGeneration):
    def helper(self):
        operation = getattr(
            generation.sialib,
            "_controller_source_corpus_commit_generation_v2", None)
        self.assertTrue(callable(operation),
                        "missing content-publication Git generation API")
        return operation

    def _call(self):
        return self.helper()(
            source_batch_sha256=generation.BATCH_SHA256,
            content_publication_sha256=generation.CLOSURE_SHA256)

    def test_invalid_content_pin_refuses_before_any_git_process(self):
        operation = self.helper()
        with mock.patch.object(
                generation.sialib, "_run_bounded_text_process",
                side_effect=AssertionError("invalid pin invoked Git")):
            for pin in (None, "", "b" * 63, True):
                with self.subTest(pin=pin), self.assertRaises(
                        generation.REFUSALS):
                    operation(
                        source_batch_sha256=generation.BATCH_SHA256,
                        content_publication_sha256=pin)
