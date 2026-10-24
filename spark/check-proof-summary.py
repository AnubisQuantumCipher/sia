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
RAW_LIMIT = 4 * 1024 * 1024
MAX_DIAGNOSTICS = 4096
UNIT = re.compile(r"in unit ([a-z][a-z0-9_]*), ([0-9]{1,6}) subprograms and packages out of ([0-9]{1,6}) analyzed")
DETAIL = re.compile(
    r"  ([A-Za-z][A-Za-z0-9_.]*) at ([a-z][a-z0-9_]*\.(?:ads|adb)):"
    r"[1-9][0-9]{0,5} flow analyzed "
    r"\(0 errors, 0 checks, 0 warnings and 0 pragma Assume statements\)"
    r" and proved \([0-9]{1,6} checks\)")


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
    check_details(lines)
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
    check_raw_diagnostics(root, expected)
    return {"status": "checks-discharged", "units": sorted(seen),
            "raw_diagnostics": "no warnings, errors or declared exclusions",
            "scope": "reported proof obligations only; authenticity and system assurance external"}


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate raw-report key")
        result[key] = value
    return result


def reject_constant(_value):
    raise ValueError("non-JSON numeric constant")


def check_raw_diagnostics(root, units):
    """Summary flow rows do not include miscellaneous proof warnings."""
    for name in sorted(units):
        path = root / "obj" / "gnatprove" / (name + ".spark")
        with path.open("rb") as stream:
            raw = stream.read(RAW_LIMIT + 1)
        if len(raw) > RAW_LIMIT:
            raise ValueError("raw proof report exceeds byte limit")
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object,
                           parse_constant=reject_constant)
        if type(value) is not dict:
            raise ValueError("raw proof report is not an object")
        for field in ("pragma_assume", "skip_proof", "skip_flow_proof"):
            if value.get(field) != []:
                raise ValueError("missing or nonempty raw exclusion field")
        for field in ("warn_error", "flow", "proof"):
            rows = value.get(field)
            if type(rows) is not list or len(rows) > MAX_DIAGNOSTICS:
                raise ValueError("missing or oversized raw diagnostics")
            for row in rows:
                if type(row) is not dict or row.get("severity") != "info":
                    raise ValueError("raw diagnostic is not informational")


def check_details(lines):
    """Require complete, clean detail rows for this pinned report format."""
    current = None
    required = 0
    seen = set()
    for line in lines:
        if line.startswith("in unit "):
            if current is not None and len(seen) != required:
                raise ValueError("missing analysis detail rows")
            match = UNIT.fullmatch(line)
            if match is None:
                raise ValueError("unsupported unit coverage row")
            current, count, _ = match.groups()
            required, seen = int(count), set()
        elif " at " in line or "flow analyzed" in line or "pragma Assume" in line:
            match = DETAIL.fullmatch(line)
            if match is None or current is None:
                raise ValueError("unsupported or non-clean analysis detail row")
            name, filename = match.groups()
            if Path(filename).stem != current or name.lower() in seen:
                raise ValueError("misbound or duplicate analysis detail row")
            seen.add(name.lower())
    if current is None or len(seen) != required:
        raise ValueError("missing analysis detail rows")


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
