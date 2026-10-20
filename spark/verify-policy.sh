#!/usr/bin/env bash
# Reproduce committed policy checks in a fresh, retained build directory.
set -euo pipefail
umask 077
if [[ $# != 1 ]]; then
    printf 'usage: verify-policy.sh NEW_OUTPUT_DIR\n' >&2
    exit 2
fi
# Resolve before any directory change: PATH may contain relative entries.
declare -A tool_paths
for tool in gprbuild gnatprove gnatls gcc timeout sha256sum tar git python3; do
    selected=$(type -P -- "$tool")
    tool_paths[$tool]=$(realpath -e -- "$selected")
    test -x "${tool_paths[$tool]}"
done
readonly -A tool_paths
root=$("${tool_paths[git]}" -C "$(dirname -- "${BASH_SOURCE[0]}")" rev-parse --show-toplevel)
cd -- "$root"
if [[ -n $("${tool_paths[git]}" status --porcelain --untracked-files=normal) ]]; then
    printf 'Refusing an uncommitted source tree. Commit the intended source first.\n' >&2
    exit 2
fi
mkdir -- "$1"
output=$(cd -- "$1" && pwd)
commit=$("${tool_paths[git]}" rev-parse HEAD)
printf '%s\n' "$commit" > "$output/source-commit.txt"
"${tool_paths[git]}" archive --format=tar -o "$output/source.tar" "$commit" spark
"${tool_paths[sha256sum]}" -- "$output/source.tar" > "$output/source-archive.sha256"
mkdir -- "$output/source"
"${tool_paths[tar]}" -xf "$output/source.tar" -C "$output/source"

run_check() {
    local name=$1 duration=$2 status=0
    shift 2
    printf '%q ' "$@" > "$output/$name.command"
    printf '\n' >> "$output/$name.command"
    "${tool_paths[timeout]}" --kill-after=5s "$duration" "$@" > "$output/$name.log" 2>&1 || status=$?
    printf '%s\n' "$status" > "$output/$name.exit"
    if [[ $status != 0 ]]; then
        printf 'Check failed: %s; inspect %s\n' "$name" "$output/$name.log" >&2
        return "$status"
    fi
}

for tool in gprbuild gnatprove gnatls gcc; do
    resolved=${tool_paths[$tool]}
    printf '%s\n' "$resolved" > "$output/$tool.path"
    "${tool_paths[sha256sum]}" -- "$resolved" > "$output/$tool.sha256"
    run_check "$tool-version" 10s "$resolved" --version
done
cd -- "$output/source"
run_check build 120s "${tool_paths[gprbuild]}" -p -P spark/sia_assurance.gpr
run_check policy-tests 30s spark/bin/policy_tests
run_check transaction-tests 30s spark/bin/transaction_tests
run_check request-wire-tests 30s spark/bin/request_wire_tests
run_check request-admission-tests 30s spark/bin/request_admission_tests
run_check grant-lifetime-tests 30s spark/bin/grant_lifetime_tests
run_check retraction-tests 30s spark/bin/retraction_tests
run_check consolidation-tests 30s spark/bin/consolidation_tests
run_check continuity-tests 30s spark/bin/continuity_tests
run_check continuity-transition-tests 30s spark/bin/continuity_transition_tests
run_check continuity-record-wire-tests 30s spark/bin/continuity_record_wire_tests
run_check proof 600s "${tool_paths[gnatprove]}" -P spark/sia_assurance.gpr -U --mode=all \
    --assumptions --no-inlining --memlimit=512 --timeout=10
test -s spark/obj/gnatprove/gnatprove.out
cp -- spark/obj/gnatprove/gnatprove.out "$output/gnatprove-summary.txt"
run_check coverage 10s "${tool_paths[python3]}" spark/check-proof-summary.py \
    spark "$output/gnatprove-summary.txt"
printf 'All commands passed for %s. Review proof coverage and assumptions in %s.\n' \
    "$commit" "$output"
