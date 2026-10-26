#!/usr/bin/env python3
"""Fail closed on missing unit coverage or unresolved summary obligations.

This checks a GNATprove report's declared scope, not its authenticity or the
physical system. The caller must bind source, command success and toolchain.
"""
import hashlib
import json
from pathlib import Path
import re
import sys

LIMIT = 1024 * 1024
RAW_LIMIT = 4 * 1024 * 1024
MAX_DIAGNOSTICS = 4096
POLICY_LIMIT = 65536
OVERLOAD_POLICY = Path(__file__).with_name("proof-overloads.json")
UNIT = re.compile(r"in unit ([a-z][a-z0-9_]*), ([0-9]{1,6}) subprograms and packages out of ([0-9]{1,6}) analyzed")
DETAIL = re.compile(
    r"  ([A-Za-z][A-Za-z0-9_.]*) at ([a-z][a-z0-9_]*\.(?:ads|adb)):"
    r"([1-9][0-9]{0,5}) flow analyzed "
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
    check_details(lines, source_overloads(root))
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


def read_overload_policy(path):
    """Policy ships with the checker; no working-directory discovery."""
    with path.open("rb") as stream:
        raw = stream.read(POLICY_LIMIT + 1)
    if len(raw) > POLICY_LIMIT:
        raise ValueError("overload policy exceeds byte limit")
    value = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object,
                       parse_constant=reject_constant)
    if type(value) is not dict or set(value) != {"schema", "sources"}:
        raise ValueError("unsupported overload policy fields")
    if type(value["schema"]) is not int or value["schema"] != 1:
        raise ValueError("unsupported overload policy schema")
    sources = value["sources"]
    if type(sources) is not dict or not 1 <= len(sources) <= 16:
        raise ValueError("overload policy source inventory outside bounds")
    for filename, entry in sources.items():
        validate_overload_entry(filename, entry)
    return sources


def validate_overload_entry(filename, entry):
    if re.fullmatch(r"[a-z][a-z0-9_]{0,127}\.ads", filename) is None:
        raise ValueError("unsafe overload source filename")
    if type(entry) is not dict or set(entry) != {"sha256", "overloads"}:
        raise ValueError("unsupported overload source fields")
    digest, groups = entry["sha256"], entry["overloads"]
    if type(digest) is not str or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        raise ValueError("invalid overload source hash")
    if type(groups) is not dict or not 1 <= len(groups) <= 32:
        raise ValueError("overload group inventory outside bounds")
    locations = set()
    for name, lines in groups.items():
        prefix = filename[:-4] + "."
        if not name.startswith(prefix) or re.fullmatch(
                re.escape(prefix) + r"[a-z][a-z0-9_]{0,127}", name) is None:
            raise ValueError("misbound overload name")
        if type(lines) is not list or not 2 <= len(lines) <= 16:
            raise ValueError("overload location inventory outside bounds")
        if any(type(line) is not int or not 1 <= line <= 999999 for line in lines):
            raise ValueError("invalid overload declaration line")
        if lines != sorted(set(lines)) or locations.intersection(lines):
            raise ValueError("duplicate or unordered overload locations")
        locations.update(lines)


def registered_source(root, filename, entry):
    paths = [root / directory / filename for directory in ("src", "tests")
             if (root / directory / filename).exists()
             or (root / directory / filename).is_symlink()]
    if not paths:
        return None
    if len(paths) != 1:
        raise ValueError("ambiguous registered source")
    path = paths[0]
    if path.is_symlink() or path.parent.is_symlink() or not path.is_file():
        raise ValueError("unsupported registered source path")
    with path.open("rb") as stream:
        raw = stream.read(RAW_LIMIT + 1)
    if len(raw) > RAW_LIMIT or hashlib.sha256(raw).hexdigest() != entry["sha256"]:
        raise ValueError("registered source hash mismatch or byte limit exceeded")
    return raw.decode("utf-8").splitlines()


def source_overloads(root, policy=None):
    """Closed, reviewed exceptions; this is not an Ada signature parser."""
    sources = read_overload_policy(OVERLOAD_POLICY if policy is None else policy)
    result = {}
    for filename, entry in sources.items():
        source = registered_source(root, filename, entry)
        if source is None:
            continue  # Unrelated fixture roots receive no exceptions.
        for name, lines in entry["overloads"].items():
            declaration = r"\s*(?:function|procedure)\s+" + re.escape(
                name.rsplit(".", 1)[1]) + r"(?:\s|\(|$)"
            for line in lines:
                if line > len(source) or re.match(
                        declaration, source[line - 1], re.IGNORECASE) is None:
                    raise ValueError("registered declaration location mismatch")
            result[name] = {(filename, line) for line in lines}
    return result


def detail_identity(name, filename, line, overloads):
    name = name.lower()
    if name not in overloads:
        return (name, None, None)
    if (filename, line) not in overloads[name]:
        raise ValueError("unregistered overload declaration location")
    return (name, filename, line)


def check_details(lines, overloads=None):
    """Require complete, clean detail rows for this pinned report format."""
    current = None
    required = 0
    seen = set()
    overloads = {} if overloads is None else overloads
    observed = set()
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
            name, filename, location = match.groups()
            identity = detail_identity(name, filename, int(location), overloads)
            if Path(filename).stem != current or identity in seen:
                raise ValueError("misbound or duplicate analysis detail row")
            seen.add(identity)
            if name.lower() in overloads:
                observed.add(identity)
    if current is None or len(seen) != required:
        raise ValueError("missing analysis detail rows")
    expected = {(name, filename, line) for name, locations in overloads.items()
                for filename, line in locations}
    if observed != expected:
        raise ValueError("incomplete registered overload coverage")


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
