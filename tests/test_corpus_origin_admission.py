"""Real special-file controls for the recall origin reader on Linux."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


BIN = Path(__file__).resolve().parents[1] / "bin"
WORKER = """
import json, os, sys
sys.path.insert(0, sys.argv[1])
import sialib
sialib.CORPUS = sys.argv[2]
before = len(os.listdir('/proc/self/fd'))
origins = [sialib.corpus_origin('thoughts/page') for _ in range(16)]
after = len(os.listdir('/proc/self/fd'))
print(json.dumps({'origins': origins, 'before': before, 'after': after}))
"""


class CorpusOriginAdmission(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.corpus = self.root / "corpus"
        (self.corpus / "thoughts").mkdir(parents=True)
        self.page = self.corpus / "thoughts/page.md"
        self.home = self.root / "home"
        self.home.mkdir()

    def classify(self, expected):
        environment = dict(os.environ, HOME=str(self.home))
        result = subprocess.run(
            [sys.executable, "-I", "-B", "-W", "error::ResourceWarning", "-c",
             WORKER, str(BIN), str(self.corpus)],
            env=environment, capture_output=True, text=True, timeout=5, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        report = json.loads(result.stdout)
        self.assertEqual(report["origins"], [expected] * 16)
        self.assertEqual(report["before"], report["after"])

    def test_fifo_without_writer_refuses_without_waiting(self):
        os.mkfifo(self.page, 0o600)
        self.classify("legacy-unlabeled")

    def test_fifo_with_peer_refuses_without_consuming_evidence(self):
        os.mkfifo(self.page, 0o600)
        peer = os.open(self.page, os.O_RDWR | os.O_NONBLOCK)
        self.addCleanup(os.close, peer)
        payload = b"---\ntype: thought\norigin: evidence\n---\n"
        self.assertEqual(os.write(peer, payload), len(payload))
        self.classify("legacy-unlabeled")
        self.assertEqual(os.read(peer, len(payload)), payload)

    def test_directory_refuses_and_releases_descriptors(self):
        self.page.mkdir()
        self.classify("legacy-unlabeled")

    def test_symlink_cannot_supply_origin(self):
        outside = self.root / "outside.md"
        outside.write_text("---\ntype: thought\norigin: evidence\n---\n")
        self.page.symlink_to(outside)
        self.classify("legacy-unlabeled")

    def test_regular_model_page_keeps_its_origin_and_releases_descriptors(self):
        self.page.write_text("---\ntype: thought\norigin: model\n---\nBody\n")
        self.classify("model")


if __name__ == "__main__":
    unittest.main()
