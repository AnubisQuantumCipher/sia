"""Process-wide home isolation for tests that load the SIA runtime.

SIA modules resolve several independent mutable paths at import time.  A test
that replaces only ``STATE`` or ``CORPUS`` can therefore leave a sibling such
as the graph projection, thought-recovery journal, or lifecycle lock pointed
at the operator's real home.  Keep ``expanduser`` rooted in one temporary home
for the lifetime of the test process, before any runtime module is imported.

The same "before any runtime module is imported" position is the only place a
second hazard can be closed: every ``bin`` module a test loads is answered by
``bin/__pycache__`` whenever the source's mtime second and byte length are
unchanged.  A pure-move extraction can preserve both, so a same-second
same-size edit would be certified from stale bytecode — including through the
plain ``import siagraph`` inside ``sialib.py``.  Route this process's cache to
a private directory instead, so every load compiles the file under review and
the repository tree is left alone.
"""

import atexit
import os
import sys
import tempfile
from unittest import mock


_REAL_EXPANDUSER = os.path.expanduser
_TEST_HOME_FIXTURE = tempfile.TemporaryDirectory(prefix="sia-test-home-")
ISOLATED_HOME = _TEST_HOME_FIXTURE.name

_PYCACHE_FIXTURE = tempfile.TemporaryDirectory(prefix="sia-test-pycache-")
sys.pycache_prefix = _PYCACHE_FIXTURE.name


def _isolated_expanduser(path):
    if path == "~":
        return ISOLATED_HOME
    if isinstance(path, str) and path.startswith("~/"):
        return os.path.join(ISOLATED_HOME, path[2:])
    return _REAL_EXPANDUSER(path)


_EXPANDUSER_PATCH = mock.patch(
    "os.path.expanduser", side_effect=_isolated_expanduser)
_EXPANDUSER_PATCH.start()


def _cleanup():
    _EXPANDUSER_PATCH.stop()
    _TEST_HOME_FIXTURE.cleanup()
    _PYCACHE_FIXTURE.cleanup()


atexit.register(_cleanup)
