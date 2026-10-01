"""Metrics retain raw windows and publish no partial collection."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

PATH = Path(__file__).resolve().parents[1] / "scripts/collect_github_metrics.py"
spec = importlib.util.spec_from_file_location("github_metrics_test", PATH)
metrics = importlib.util.module_from_spec(spec)
spec.loader.exec_module(metrics)


class GithubMetrics(unittest.TestCase):
    def test_preserves_raw_windows_without_claiming_installs(self):
        clones = dict(count=439, uniques=212, clones=[])
        views = dict(count=494, uniques=205, views=[])
        releases = [{"tag_name": "v1.8.1", "assets": [
            {"id": 7, "name": "sia.tar.gz", "download_count": 9}]}]
        with mock.patch.object(metrics, "fetch", side_effect=[clones, views, releases]):
            report = metrics.collect("owner/repo")
        self.assertEqual(report["traffic"], {"clones": clones, "views": views})
        self.assertNotIn("installations", report)
        self.assertTrue(any("must not be summed" in text for text in report["limitations"]))
        with tempfile.TemporaryDirectory() as directory:
            first = metrics.save(report, directory)
            second = metrics.save(report, directory)
            self.assertNotEqual(first, second)
            self.assertEqual(json.loads(first.read_text()), report)
            self.assertEqual(first.stat().st_mode & 0o777, 0o600)
            self.assertEqual(list(Path(directory).glob("*.tmp")), [])

    def test_failed_fetch_does_not_write_a_partial_snapshot(self):
        with mock.patch.object(metrics, "fetch", side_effect=RuntimeError("unavailable")), \
                mock.patch.object(metrics, "save") as save, \
                mock.patch("sys.argv", ["collect_github_metrics.py"]):
            with self.assertRaises(SystemExit) as stopped:
                metrics.main()
        self.assertEqual(stopped.exception.code, 1)
        save.assert_not_called()

    def test_malformed_traffic_is_not_recorded_as_zero(self):
        with mock.patch.object(metrics, "fetch", return_value={"message": "denied"}):
            with self.assertRaises(ValueError):
                metrics.collect("owner/repo")
