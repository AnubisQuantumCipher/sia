#!/usr/bin/env python3
"""Fail closed on missing unit coverage or unresolved summary obligations.

This checks a GNATprove report's declared scope, not its authenticity or the
physical system. The caller must bind source, command success and toolchain.
"""
import json
from pathlib import Path
import re
import sys

LIMIT = 1024 * 1024
UNIT = re.compile(r"in unit ([a-z][a-z0-9_]*), ([0-9]{1,6}) subprograms and packages out of ([0-9]{1,6}) analyzed")


def required_units(root):
    project = (root / "sia_assurance.gpr").read_text()
    declarations = re.findall(r"for\s+Source_Dirs\s+use\s*([^;]+);", project,
                              flags=re.IGNORECASE)
    if len(declarations) != 1 or re.sub(r"\s+", "", declarations[0]) != '("src","tests")':
        raise ValueError("unsupported source-directory layout")
    paths = sorted([path for directory in ("src", "tests")
                    for pattern in ("*.ads", "*.adb")
                    for path in root.joinpath(directory).glob(pattern)])
    if not paths or len(paths) > 128:
        raise ValueError("source-unit inventory outside declared bounds")
    names = [path.name for path in paths]
    if len(set(names)) != len(names):
        raise ValueError("duplicate source filenames")
    return {path.stem for path in paths}


def check_totals(lines):
    header = "SPARK Analysis results Total Flow Provers Justified Unproved"
    if sum(" ".join(line.split()) == header for line in lines) != 1:
        raise ValueError("unsupported proof-summary header")
    totals = [line for line in lines if line.startswith("Total ")]
    cell = r"(?:\.|[0-9]{1,6}(?: \((?:100|[0-9]{1,2})%\))?)"
    pattern = r"Total\s+([1-9][0-9]{0,5})\s+(" + cell + r")\s+(" + cell + r")\s+\.\s+\."
    match = re.fullmatch(pattern, totals[0].strip()) if len(totals) == 1 else None
    if match is None:
        raise ValueError("missing, malformed or unresolved proof totals")
    total, flow, provers = match.groups()
    counts = [0 if cell == "." else int(cell.split()[0]) for cell in (flow, provers)]
    if sum(counts) != int(total):
        raise ValueError("inconsistent discharged-check totals")


def check(root, report):
    with report.open("rb") as stream:
        raw = stream.read(LIMIT + 1)
    if len(raw) > LIMIT:
        raise ValueError("proof report exceeds byte limit")
    lines = raw.decode("utf-8", errors="strict").splitlines()
    check_totals(lines)
    seen = set()
    for line in lines:
        if not line.startswith("in unit "):
            continue
        matched = UNIT.fullmatch(line)
        if matched is None:
            raise ValueError("unsupported unit coverage row")
        name, analyzed, available = matched.groups()
        if name in seen or int(analyzed) == 0 or analyzed != available:
            raise ValueError("duplicate or incomplete subprogram coverage")
        seen.add(name)
    expected = required_units(root)
    if seen != expected:
        raise ValueError("unit coverage mismatch: missing=" +
                         repr(sorted(expected - seen)) + "; unexpected=" +
                         repr(sorted(seen - expected)))
    return {"status": "checks-discharged", "units": sorted(seen),
            "scope": "reported proof obligations only; authenticity and system assurance external"}


def main():
    if len(sys.argv) != 3:
        raise ValueError("usage: check-proof-summary.py SPARK_SOURCE_DIR REPORT")
    print(json.dumps(check(Path(sys.argv[1]), Path(sys.argv[2])), sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except (OSError, UnicodeError, ValueError) as error:
        print("proof summary refused: " + str(error), file=sys.stderr)
        sys.exit(1)
