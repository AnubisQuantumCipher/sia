#!/usr/bin/env python3
"""`--` as the end-of-options marker for takes and intents.

`sia take --help` once registered a take whose claim was "--help", so the
take path now refuses any option-shaped token.  That guard cannot tell a
typo'd flag from an honest claim that opens with a minus sign, which left
a legitimate take — "-1 regressions will land by March" — with no way to
be registered at all.  `--` is the caller saying "the rest is text": the
guard keeps refusing typos, and real claims stay filable.

`sia intend` had the mirror-image hole.  Its loop treats an unrecognised
option as text, so a typo committed itself as prospective memory with the
flag embedded.  The same marker makes that boundary explicit there too.
"""

import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
import unittest
from unittest import mock

try:
    import sia_test_home  # test-only import-time path isolation
except ModuleNotFoundError:
    from tests import sia_test_home  # type: ignore


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SIA_PATH = os.path.join(REPO, "bin", "sia")


def _load_script(name, path):
    loader = importlib.machinery.SourceFileLoader(name, path)
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


sia = _load_script("sia_option_terminator_cli", SIA_PATH)

import siatakes  # noqa: E402  (bin/ joins sys.path when the CLI loads)


@contextlib.contextmanager
def _registrations(kind):
    """Capture what a take/intent path would commit, writing nothing."""
    memo, recorded = {}, []

    def capture_write(path, payload, mode=None):
        if path == sia.sialib.MEMO_PATH:
            json.loads(payload)

    def create_take(claim, **kwargs):
        kwargs.get("before_publish", lambda: None)()
        recorded.append(claim)
        return {"id": "take-id", "confidence": 0.6,
                "deadline": "2099-01-01", "domain": "ops", "claim": claim}

    def create_intent(text, due, before_publish=None):
        if before_publish is not None:
            before_publish()
        recorded.append(text)
        return {"id": "intent-id", "text": text, "due": due}

    factory = create_take if kind == "take" else create_intent
    name = "create_take" if kind == "take" else "create_intent"
    with mock.patch.object(sia.sialib, "corpus_owner",
                           return_value=contextlib.nullcontext()), \
            mock.patch.object(sia.sialib, "load_memo", return_value=memo), \
            mock.patch.object(sia.sialib, "atomic_write",
                              side_effect=capture_write), \
            mock.patch.object(siatakes, name, side_effect=factory):
        yield recorded


class TakeEndOfOptions(unittest.TestCase):
    def test_claim_beginning_with_a_minus_is_registerable(self):
        # The finding verbatim: this take was unregisterable before `--`.
        with _registrations("take") as recorded, \
                contextlib.redirect_stdout(io.StringIO()):
            status = sia.cmd_take([
                "--confidence", "0.6", "--by", "2099-01-01", "--",
                "-1", "regressions", "will", "land", "by", "March"])
        self.assertEqual(status, 0)
        self.assertEqual(recorded, ["-1 regressions will land by March"])

    def test_options_before_the_marker_are_still_parsed(self):
        # `--` ends option parsing; it does not disable it retroactively.
        seen = {}

        def create_take(claim, **kwargs):
            kwargs.get("before_publish", lambda: None)()
            seen.update(kwargs)
            return {"id": "take-id", "confidence": 0.9,
                    "deadline": kwargs["deadline"],
                    "domain": kwargs["domain"], "claim": claim}

        with mock.patch.object(sia.sialib, "corpus_owner",
                               return_value=contextlib.nullcontext()), \
                mock.patch.object(sia.sialib, "load_memo", return_value={}), \
                mock.patch.object(sia.sialib, "atomic_write"), \
                mock.patch.object(siatakes, "create_take",
                                  side_effect=create_take), \
                contextlib.redirect_stdout(io.StringIO()):
            status = sia.cmd_take([
                "--domain", "Ops", "--by", "2099-01-01", "--", "-1", "day"])
        self.assertEqual(status, 0)
        self.assertEqual(seen["domain"], "ops")
        self.assertEqual(seen["deadline"], "2099-01-01")

    def test_only_the_first_marker_terminates_options(self):
        # Everything after the first `--` is claim text, including a
        # second `--`.  Anything else would make some claims unfilable
        # for exactly the reason this marker exists.
        with _registrations("take") as recorded, \
                contextlib.redirect_stdout(io.StringIO()):
            status = sia.cmd_take(["--", "spec", "--", "revision"])
        self.assertEqual(status, 0)
        self.assertEqual(recorded, ["spec -- revision"])

    def test_typos_are_still_refused_without_the_marker(self):
        # The `sia take --help` incident must stay fixed: an
        # option-shaped token with no marker before it is a typo, not a
        # claim, and nothing may be registered.
        for argv in (["--help"], ["-h"], ["real claim", "--confidnce", "1"]):
            with self.subTest(argv=argv), \
                    _registrations("take") as recorded, \
                    contextlib.redirect_stdout(io.StringIO()) as out:
                status = sia.cmd_take(argv)
            self.assertEqual(status, 2)
            self.assertEqual(recorded, [])
            self.assertIn("nothing was registered", out.getvalue())

    def test_marker_with_no_claim_registers_nothing(self):
        with _registrations("take") as recorded, \
                contextlib.redirect_stdout(io.StringIO()) as out:
            status = sia.cmd_take(["--"])
        self.assertEqual(status, 2)
        self.assertEqual(recorded, [])
        self.assertIn("usage:", out.getvalue())


class IntendEndOfOptions(unittest.TestCase):
    def test_text_beginning_with_a_minus_is_registerable(self):
        with _registrations("intend") as recorded, \
                contextlib.redirect_stdout(io.StringIO()):
            status = sia.cmd_intend([
                "--by", "2099-01-01", "--", "-1", "day", "of", "cleanup"])
        self.assertEqual(status, 0)
        self.assertEqual(recorded, ["-1 day of cleanup"])

    def test_marker_is_not_swallowed_into_the_intent_text(self):
        # Before the marker existed, "--" was just another word: the
        # intent committed with the literal token inside its text.
        with _registrations("intend") as recorded, \
                contextlib.redirect_stdout(io.StringIO()):
            sia.cmd_intend(["--by", "2099-01-01", "--", "ship", "it"])
        self.assertEqual(recorded, ["ship it"])

    def test_deadline_after_the_marker_is_text_not_an_option(self):
        # `--by` after the marker is text, so no deadline was given and
        # nothing may be committed.  Silently accepting it would file an
        # intent whose text carried its own flag — the failure that made
        # the intend path worse than a refusal.
        with _registrations("intend") as recorded, \
                contextlib.redirect_stdout(io.StringIO()) as out:
            status = sia.cmd_intend(["--", "ship", "--by", "2099-01-01"])
        self.assertEqual(status, 2)
        self.assertEqual(recorded, [])
        self.assertIn("usage:", out.getvalue())


if __name__ == "__main__":
    unittest.main()
