#!/usr/bin/env python3
"""Archive GitHub's aggregate repository metrics, never installer telemetry."""
import argparse
import datetime
import json
import os
from pathlib import Path
import subprocess
import tempfile


def fetch(repository, endpoint):
    result = subprocess.run(
        ["gh", "api", f"repos/{repository}/{endpoint}"],
        capture_output=True, text=True, timeout=120, check=False)
    if result.returncode:
        raise RuntimeError(f"GitHub {endpoint} request failed; check gh authentication and repository access")
    return json.loads(result.stdout)


def collect(repository):
    traffic = {}
    for endpoint in ("clones", "views"):
        value = fetch(repository, "traffic/" + endpoint)
        if (not isinstance(value, dict)
                or type(value.get("count")) is not int
                or type(value.get("uniques")) is not int
                or not isinstance(value.get(endpoint), list)):
            raise ValueError(f"Invalid {endpoint} response")
        traffic[endpoint] = value
    releases = fetch(repository, "releases?per_page=100")
    if not isinstance(releases, list):
        raise ValueError("Invalid releases response")
    assets = [{"tag": release["tag_name"], "assets": [
        {"id": asset["id"], "name": asset["name"],
         "download_count": asset["download_count"]}
        for asset in release["assets"]]} for release in releases]
    return {
        "schema": "sia-github-metrics-v1",
        "repository": repository,
        "observed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "traffic": traffic,
        "recent_releases": assets,
        "limitations": [
            "Traffic reports GitHub's rolling 14-day window, not lifetime totals.",
            "Overlapping windows and unique counts must not be summed.",
            "Clones and downloads do not establish successful installations or distinct people.",
            "Release data covers the latest API page (up to 100 releases); source archives are not uploaded assets.",
            "This collector contacts GitHub only; installed SIA clients send it no reports.",
        ],
    }


def save(snapshot, directory):
    directory = Path(directory).expanduser()
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    # A unique name preserves repeated samples without replacing older history.
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    fd, name = tempfile.mkstemp(prefix=stamp + "-", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(snapshot, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        target = Path(name).with_suffix(".json")
        os.rename(name, target)
        return target
    finally:
        if os.path.exists(name):
            os.unlink(name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", default="AnubisQuantumCipher/sia")
    parser.add_argument("--output", default="~/.local/state/sia-maintainer/github-traffic")
    args = parser.parse_args()
    try:
        snapshot = collect(args.repository)
        print(save(snapshot, args.output))
    except (OSError, ValueError, KeyError, TypeError, RuntimeError,
            subprocess.SubprocessError) as error:
        parser.exit(1, f"Metrics collection failed: {error}\n")


if __name__ == "__main__":
    main()
