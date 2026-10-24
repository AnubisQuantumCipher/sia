#!/usr/bin/env bash
# Candidate model only; retained diagnostics are mandatory in every lane.
set -euo pipefail
umask 077
: "${JAVA_BIN:?Set JAVA_BIN to the verified Java executable}"
: "${TLA_JAR:?Set TLA_JAR to the verified TLC jar}"
if [[ $# != 1 || ! -x "$JAVA_BIN" || ! -f "$TLA_JAR" ]]; then
    printf 'usage: JAVA_BIN=... TLA_JAR=... check-admission-model.sh NEW_OUTPUT_DIR\n' >&2
    exit 2
fi
JAVA_BIN=$(realpath -e -- "$JAVA_BIN")
TLA_JAR=$(realpath -e -- "$TLA_JAR")
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
sha256sum -- "$model_dir"/AdmissionRecovery* "$model_dir/toolchain.json" \
    "$model_dir/ADMISSION-RECOVERY.md" "${BASH_SOURCE[0]}" \
    "$JAVA_BIN" "$TLA_JAR" > "$output/source-tool-sha256.txt"
cd -- "$model_dir"
for lane in positive negative permission-negative reachability restart-reachability durable-reachability; do
    case "$lane" in
        positive) config=AdmissionRecovery.cfg; expected_status=0; marker='No error has been found.' ;;
        negative) config=AdmissionRecovery-negative.cfg; expected_status=12; marker='Invariant PayloadSafe is violated.' ;;
        reachability) config=AdmissionRecovery-reachability.cfg; expected_status=12; marker='Invariant NoExpiredCompletion is violated.' ;;
        permission-negative) config=AdmissionRecovery-permission-negative.cfg; expected_status=12; marker='Invariant PayloadSafe is violated.' ;;
        restart-reachability) config=AdmissionRecovery-restart-reachability.cfg; expected_status=12; marker='Invariant NoUnsyncedExpiredRecovery is violated.' ;;
        durable-reachability) config=AdmissionRecovery-durable-reachability.cfg; expected_status=12; marker='Invariant NoDurableRecovery is violated.' ;;
    esac
    mkdir -- "$output/$lane-tmp"
    printf '%q ' timeout --kill-after=5s 120s "$JAVA_BIN" -Xmx256m -XX:+UseParallelGC \
        "-Djava.io.tmpdir=$output/$lane-tmp" -jar "$TLA_JAR" -workers 1 \
        -metadir "$output/$lane-state" -config "$config" AdmissionRecovery.tla \
        > "$output/$lane.command"
    printf '\n' >> "$output/$lane.command"
    status=0
    timeout --kill-after=5s 120s "$JAVA_BIN" -Xmx256m -XX:+UseParallelGC \
        "-Djava.io.tmpdir=$output/$lane-tmp" \
        -jar "$TLA_JAR" -workers 1 -metadir "$output/$lane-state" \
        -config "$config" AdmissionRecovery.tla > "$output/$lane.log" 2>&1 || status=$?
    printf '%s\n' "$status" > "$output/$lane.exit"
    if [[ $status != "$expected_status" ]] || ! grep -Fq -- "$marker" "$output/$lane.log"; then
        printf 'model lane failed: %s; inspect %s\n' "$lane" "$output/$lane.log" >&2
        exit 1
    fi
done
printf 'Candidate admission model: safety, sync/permission negatives and expiry/restart reachability passed.\n'
