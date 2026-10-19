#!/usr/bin/env bash
# Reproduce bounded checks; retain all output in a new caller-selected directory.
set -euo pipefail
umask 077
: "${JAVA_BIN:?Set JAVA_BIN to the verified Java executable}"
: "${TLA_JAR:?Set TLA_JAR to the verified TLC jar}"
if [[ $# != 1 || ! -x "$JAVA_BIN" || ! -f "$TLA_JAR" ]]; then
    printf 'usage: JAVA_BIN=... TLA_JAR=... check-model.sh NEW_OUTPUT_DIR\n' >&2
    exit 2
fi
model_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/model" && pwd)
expected=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["TLC"]["sha256"])' "$model_dir/toolchain.json")
actual=$(sha256sum -- "$TLA_JAR")
if [[ ${actual%% *} != "$expected" ]]; then
    printf 'TLC artifact digest mismatch\n' >&2
    exit 2
fi
mkdir -- "$1"
output=$(cd -- "$1" && pwd)
"$JAVA_BIN" -version > "$output/java-version.txt" 2>&1
cd -- "$model_dir"
for lane in positive negative reachability; do
    case "$lane" in
        positive) config=Publication.cfg; expected_status=0; marker='No error has been found.' ;;
        negative) config=Publication-negative.cfg; expected_status=12; marker='Invariant ReadySafe is violated.' ;;
        reachability) config=Publication-reachability.cfg; expected_status=12; marker='Invariant NotReadyYet is violated.' ;;
    esac
    mkdir -- "$output/$lane-tmp"
    status=0
    timeout --kill-after=5s 120s "$JAVA_BIN" -Xmx256m -XX:+UseParallelGC \
        "-Djava.io.tmpdir=$output/$lane-tmp" \
        -jar "$TLA_JAR" -workers 1 -metadir "$output/$lane-state" \
        -config "$config" Publication.tla > "$output/$lane.log" 2>&1 || status=$?
    printf '%s\n' "$status" > "$output/$lane.exit"
    if [[ $status != "$expected_status" ]] || ! grep -Fq -- "$marker" "$output/$lane.log"; then
        printf 'model lane failed: %s; inspect %s\n' "$lane" "$output/$lane.log" >&2
        exit 1
    fi
done
printf 'Bounded model, premature-ready rejection and final-ready reachability checks passed.\n'
