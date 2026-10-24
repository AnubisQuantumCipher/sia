#!/usr/bin/env bash
# Finite protocol exploration only; never authorizes migration.
set -euo pipefail
umask 077
: "${JAVA_BIN:?Set JAVA_BIN to the verified Java executable}"
: "${TLA_JAR:?Set TLA_JAR to the verified TLC jar}"
if [[ $# != 1 || ! -x "$JAVA_BIN" || ! -f "$TLA_JAR" ]]; then
    printf 'usage: JAVA_BIN=... TLA_JAR=... check-event-pack-model.sh NEW_OUTPUT_DIR\n' >&2
    exit 2
fi
JAVA_BIN=$(realpath -e -- "$JAVA_BIN")
TLA_JAR=$(realpath -e -- "$TLA_JAR")
script=$(realpath -e -- "${BASH_SOURCE[0]}")
model_dir=$(cd -- "$(dirname -- "$script")/model" && pwd)
expected=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["TLC"]["sha256"])' "$model_dir/toolchain.json")
actual=$(sha256sum -- "$TLA_JAR")
if [[ ${actual%% *} != "$expected" ]]; then
    printf 'TLC artifact digest mismatch\n' >&2
    exit 2
fi
mkdir -- "$1"
output=$(cd -- "$1" && pwd)
"$JAVA_BIN" -version > "$output/java-version.txt" 2>&1
source_paths=("$model_dir"/EventPackMigration* "$model_dir/toolchain.json"
    "$model_dir/EVENT-PACK-MIGRATION.md" "$script" "$JAVA_BIN" "$TLA_JAR")
sha256sum -- "${source_paths[@]}" > "$output/source-tool-before.sha256"
cd -- "$model_dir"
for lane in positive intent-negative data-negative parent-negative coverage-negative prior-negative complete-negative ready-negative completion readiness repeated-recovery rename-recovery; do
    expected_status=12
    case "$lane" in
        positive) expected_status=0; marker='No error has been found.' ;;
        intent-negative) marker='Invariant IntentSafe is violated.' ;;
        data-negative|parent-negative|coverage-negative|prior-negative) marker='Invariant Retained is violated.' ;;
        complete-negative) marker='Invariant CompleteSafe is violated.' ;;
        ready-negative) marker='Invariant ReadySafe is violated.' ;;
        completion) marker='Invariant NoCompletion is violated.' ;;
        readiness) marker='Invariant NoReady is violated.' ;;
        repeated-recovery) marker='Invariant NoRepeatedPartialRecovery is violated.' ;;
        rename-recovery) marker='Invariant NoRenameRecovery is violated.' ;;
    esac
    mkdir -- "$output/$lane-tmp"
    command=(timeout --kill-after=5s 120s "$JAVA_BIN" -Xmx256m -XX:+UseParallelGC
        "-Djava.io.tmpdir=$output/$lane-tmp" -jar "$TLA_JAR" -workers 1
        -metadir "$output/$lane-state" -config "EventPackMigration-$lane.cfg"
        EventPackMigration.tla)
    printf '%q ' "${command[@]}" > "$output/$lane.command"
    printf '\n' >> "$output/$lane.command"
    status=0
    "${command[@]}" > "$output/$lane.log" 2>&1 || status=$?
    printf '%s\n' "$status" > "$output/$lane.exit"
    if [[ $status != "$expected_status" ]] || ! grep -Fq -- "$marker" "$output/$lane.log"; then
        printf 'model lane failed: %s; inspect %s\n' "$lane" "$output/$lane.log" >&2
        exit 1
    fi
done
sha256sum -- "${source_paths[@]}" > "$output/source-tool-after.sha256"
cmp -- "$output/source-tool-before.sha256" "$output/source-tool-after.sha256"
printf 'Finite event-pack protocol: safety, seven fault controls and four reachability witnesses passed.\n'
