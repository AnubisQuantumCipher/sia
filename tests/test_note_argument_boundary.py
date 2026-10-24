"""MCP to CLI note fidelity, through the actual private filesystem queue."""

import contextlib
import importlib.machinery
import importlib.util
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

try:
    import sia_test_home
except ModuleNotFoundError:
    from tests import sia_test_home


ROOT = Path(__file__).resolve().parents[1]


def load_script(name, filename):
    loader = importlib.machinery.SourceFileLoader(name, str(ROOT / "bin" / filename))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


CLI = load_script("sia_note_boundary_cli", "sia")
MCP = load_script("sia_note_boundary_mcp", "sia-mcp")


class NoteArgumentBoundary(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.path.expanduser("~"), sia_test_home.ISOLATED_HOME)

    def dispatch_cli(self, argv):
        self.assertEqual(argv[0], "note")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status = CLI.cmd_note(argv[1:])
        return output.getvalue(), status != 0

    def queued_payload(self, text, author, name="note"):
        args = {"text": text, "author": author}
        self.assertIsNone(MCP._validate_tool_args(name, args))
        with tempfile.TemporaryDirectory() as state, \
                mock.patch.object(CLI.sialib, "STATE", state), \
                mock.patch.object(MCP, "run_sia", side_effect=self.dispatch_cli):
            output, failed = MCP.call_tool(name, args)
            self.assertFalse(failed, output)
            requests, errors = MCP.siaqueue.pending(state)
            self.assertEqual(errors, [])
            self.assertEqual(len(requests), 1)
            return requests[0][1]["payload"]

    def test_option_shaped_text_keeps_exact_body_and_author(self):
        for name in ("note", "sia_note"):
            for text in ("--from", "--help", "-h", "--", "-x",
                         "ordinary note", "text containing --from someone"):
                with self.subTest(name=name, text=text):
                    self.assertEqual(self.queued_payload(text, "audit-agent", name),
                                     {"author": "audit-agent", "text": text})

    def test_option_shaped_author_is_still_data(self):
        for author in ("--from", "--help", "--"):
            with self.subTest(author=author):
                self.assertEqual(self.queued_payload("remember this", author),
                                 {"author": author, "text": "remember this"})

    def test_cli_separator_preserves_following_option_tokens(self):
        with tempfile.TemporaryDirectory() as state, \
                mock.patch.object(CLI.sialib, "STATE", state):
            output, failed = self.dispatch_cli(
                ["note", "--from", "operator", "--", "--from", "someone"])
            self.assertFalse(failed, output)
            requests, errors = MCP.siaqueue.pending(state)
            self.assertEqual(errors, [])
            self.assertEqual(requests[0][1]["payload"],
                             {"author": "operator", "text": "--from someone"})

    def test_unmarked_cli_options_still_refuse_without_queueing(self):
        with mock.patch.object(MCP.siaqueue, "enqueue_note") as enqueue:
            for argv in (["note", "--help"], ["note", "--from"],
                         ["note", "--from", "operator", "-h"],
                         ["note", "--from", "operator", "--"]):
                with self.subTest(argv=argv):
                    _, failed = self.dispatch_cli(argv)
                    self.assertTrue(failed)
            enqueue.assert_not_called()

    def test_redaction_still_applies_to_marked_text(self):
        payload = self.queued_payload("token=abcdefghijklmnop", "audit-agent")
        self.assertNotIn("abcdefghijklmnop", payload["text"])
        self.assertEqual(payload["author"], "audit-agent")


if __name__ == "__main__":
    unittest.main()
