"""The cognitive timing lane's interpreter admission, judged on this host."""
import os
import stat
import sys
import unittest
from unittest import mock

_BIN = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin")
if _BIN not in sys.path:
    sys.path.insert(0, _BIN)

try:
    import sia_test_home  # noqa: F401  test-only import-time path isolation
except ModuleNotFoundError:
    from tests import sia_test_home  # type: ignore  # noqa: F401

try:
    import cognitive_host
except ModuleNotFoundError:
    from tests import cognitive_host  # type: ignore


class CognitiveHostAdmission(unittest.TestCase):
    def test_refusal_names_every_failing_rule_or_is_none(self):
        """On an admitted host the helper is a no-op; elsewhere it names why.

        GitHub's hosted tool cache Python errored every pinning test with
        "interpreter is not an admitted ordinary executable"; the skip must
        carry the concrete rule the host breaks, never a bare skip.
        """
        reason = cognitive_host.interpreter_refusal()
        self.assertTrue(reason is None or reason.startswith("running interpreter "))

    def test_hard_linked_or_writable_interpreter_is_named_not_pinned(self):
        path = os.path.realpath(sys.executable)
        fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC)
        info = os.fstat(fd)
        os.close(fd)

        class Info:
            def __init__(self, **over):
                for name in ("st_mode", "st_uid", "st_nlink", "st_size"):
                    setattr(self, name, over.get(name, getattr(info, name)))

        cases = {
            "2 hard links": Info(st_nlink=2),
            "group/other writable": Info(st_mode=info.st_mode | 0o022),
            "owned by uid": Info(st_uid=os.geteuid() + 12345),
        }
        for expected, fake in cases.items():
            with self.subTest(expected=expected), \
                    mock.patch.object(cognitive_host, "_fstat", return_value=fake):
                reason = cognitive_host.interpreter_refusal()
            self.assertIsNotNone(reason)
            self.assertIn(expected, reason)
            self.assertIn(path, reason)

        outcome = []

        class Probe(unittest.TestCase):
            @cognitive_host.requires_admitted_interpreter
            def test_pin(self):
                outcome.append("ran")

        with mock.patch.object(cognitive_host, "interpreter_refusal",
                               return_value="running interpreter x is not admitted (2 hard links)"):
            result = unittest.TestResult()
            Probe("test_pin").run(result)
        self.assertEqual(outcome, [])
        self.assertEqual(len(result.skipped), 1)
        self.assertIn("2 hard links", result.skipped[0][1])


if __name__ == "__main__":
    unittest.main()
