"""The observation controller joins build, physical-copy and row admission."""

import contextlib
import hashlib
import importlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

try:
    import sia_test_home
except ModuleNotFoundError:
    from tests import sia_test_home

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bin"))


def sha(data):
    return hashlib.sha256(data).hexdigest()


class RawVectorRunner(unittest.TestCase):
    def setUp(self):
        try:
            self.runner = importlib.import_module("siavectorrun")
        except ModuleNotFoundError as exc:
            self.fail(f"raw-vector observation controller must exist: {exc}")
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.receipt = self.root / "receipt.json"
        self.expected = {"executable_sha256": sha(b"compiled"),
                         "builder_sha256": sha(b"builder"),
                         "adapter_sha256": sha(b"adapter"),
                         "bun_sha256": sha(b"bun"),
                         "gbrain_commit": "7" * 40,
                         "gbrain_lock_sha256": sha(b"lock")}
        self.build = {
            "schema": "sia-raw-vector-build-v1",
            "builder": {"sha256": self.expected["builder_sha256"]},
            "adapter": {"sha256": self.expected["adapter_sha256"],
                        "staged_path": "src/sia-raw-vector.ts"},
            "bun": {"binary_sha256": self.expected["bun_sha256"]},
            "gbrain": {"commit": self.expected["gbrain_commit"],
                       "bun_lock_sha256": self.expected["gbrain_lock_sha256"]},
            "output": {"path": "sia-raw-vector",
                       "sha256": self.expected["executable_sha256"]},
            "non_claims": ["Build observation is not a reproducible-build proof."],
        }
        self.receipt.write_text(json.dumps(self.build), encoding="utf-8")
        self.receipt_sha = sha(self.receipt.read_bytes())
        self.embedding = {"model": "ollama:nomic-embed-text:v1.5", "dimensions": 768,
                          "endpoint": "http://127.0.0.1:11434/v1"}
        self.queries = [{"id": "smoke", "text": "What was recalled?"}]
        self.index_sha = sha(b"physical index archive")

    def _run(self):
        return self.runner.observe(
            executable=str(self.root / "executable"), expected=self.expected,
            build_receipt=str(self.receipt), build_receipt_sha256=self.receipt_sha,
            index_archive=str(self.root / "index.tar"), index_sha256=self.index_sha,
            embedding=self.embedding, queries=self.queries, limit=5, timeout=30,
            scratch_parent=str(self.root))

    @contextlib.contextmanager
    def _private(self, *args, **kwargs):
        yield {"directory": str(self.root / "copy"),
               "descriptor_parent": str(self.root / "copy-parent"),
               "archive_sha256": self.index_sha,
               "manifest": [], "manifest_sha256": sha(b"tree")}

    def test_capture_then_query_are_separate_copies_of_one_physical_generation(self):
        calls = []
        identities = {"logical_sha256": sha(b"logical"),
                      "catalog_sha256": sha(b"catalog")}

        def invoke(executable, executable_sha, request, directory, **kwargs):
            self.assertEqual(directory, str(self.root / "copy-parent"))
            calls.append(json.loads(json.dumps(request)))
            if request["operation"] == "capture":
                self.assertEqual(request["queries"], [])
                self.assertIsNone(request["snapshot"]["logical_sha256"])
            else:
                self.assertEqual(request["queries"], self.queries)
                for key, value in identities.items():
                    self.assertEqual(request["snapshot"][key], value)
            return {"payload": {"bindings": identities, "results": [],
                                "non_claims": ["adapter boundary"]},
                    "executable_sha256": executable_sha,
                    "request_sha256": sha(request["operation"].encode()),
                    "returncode": 0, "wall_elapsed_ns": 123,
                    "stdout_sha256": sha(b"stdout"), "launch_sha256": sha(b"launch"),
                    "launch_contract": {}}

        def admit(payload, request, **kwargs):
            self.assertEqual(kwargs["executable_sha256"], self.expected["executable_sha256"])
            self.assertEqual(kwargs["config_sha256"],
                             self.runner.configuration_sha256(self.embedding, 5))
            return payload

        with mock.patch.object(self.runner.siavector, "private_index_snapshot",
                               side_effect=self._private) as snapshots, \
                mock.patch.object(self.runner.siavector, "invoke_adapter",
                                  side_effect=invoke), \
                mock.patch.object(self.runner.siavectoradmit, "admit_response",
                                  side_effect=admit) as admission:
            result = self._run()
        self.assertEqual([item["operation"] for item in calls], ["capture", "query"])
        self.assertEqual(snapshots.call_count, 2)
        self.assertEqual(admission.call_count, 2)
        self.assertEqual(result["schema"], "sia-raw-vector-observation-v1")
        self.assertEqual(result["status"], "observed")
        self.assertEqual(result["index_archive_sha256"], self.index_sha)
        self.assertEqual(result["build_receipt_sha256"], self.receipt_sha)
        self.assertEqual(result["build_non_claims"], self.build["non_claims"])
        self.assertIn("This observation does not attest served model weights or earn a cognitive claim.",
                      result["non_claims"])

    def test_build_mismatches_refuse_before_snapshot_or_execution(self):
        for name in self.expected:
            prior = self.expected[name]
            self.expected[name] = "0" * len(prior)
            with self.subTest(name=name), \
                    mock.patch.object(self.runner.siavector, "private_index_snapshot") as snapshot, \
                    self.assertRaises(self.runner.siavector.VectorRefusal):
                self._run()
            snapshot.assert_not_called()
            self.expected[name] = prior

    def test_wrong_receipt_digest_refuses_before_snapshot(self):
        self.receipt_sha = "0" * 64
        with mock.patch.object(self.runner.siavector, "private_index_snapshot") as snapshot, \
                self.assertRaises(self.runner.siavector.VectorRefusal):
            self._run()
        snapshot.assert_not_called()

    def test_bad_query_refuses_before_artifact_reads_or_capture(self):
        self.queries = [{"id": "smoke", "text": "x" * 8001}]
        with mock.patch.object(
                self.runner.siavector, "sealed_file",
                side_effect=self.runner.siavector.VectorRefusal("build opened")) as files, \
                mock.patch.object(self.runner.siavector, "private_index_snapshot") as snapshot, \
                self.assertRaises(self.runner.siavector.VectorRefusal):
            self._run()
        files.assert_not_called()
        snapshot.assert_not_called()

    def test_capture_refusal_never_runs_a_query(self):
        with mock.patch.object(self.runner.siavector, "private_index_snapshot",
                               side_effect=self._private) as snapshots, \
                mock.patch.object(self.runner.siavector, "invoke_adapter",
                                  side_effect=self.runner.siavector.VectorRefusal("capture refused")), \
                self.assertRaisesRegex(self.runner.siavector.VectorRefusal, "capture refused"):
            self._run()
        self.assertEqual(snapshots.call_count, 1)


if __name__ == "__main__":
    unittest.main()
