#!/usr/bin/env bash
# Reproduce committed policy checks in a fresh, retained build directory.
set -euo pipefail
umask 077
if [[ $# != 1 ]]; then
    printf 'usage: verify-policy.sh NEW_OUTPUT_DIR\n' >&2
    exit 2
fi
root=$(git -C "$(dirname -- "${BASH_SOURCE[0]}")" rev-parse --show-toplevel)
cd -- "$root"
if [[ -n $(git status --porcelain --untracked-files=normal) ]]; then
    printf 'Refusing an uncommitted source tree. Commit the intended source first.\n' >&2
    exit 2
fi
for tool in gprbuild gnatprove gnatls gcc timeout sha256sum tar; do
    command -v "$tool" >/dev/null
done
mkdir -- "$1"
output=$(cd -- "$1" && pwd)
commit=$(git rev-parse HEAD)
printf '%s\n' "$commit" > "$output/source-commit.txt"
git archive --format=tar -o "$output/source.tar" "$commit" spark
sha256sum -- "$output/source.tar" > "$output/source-archive.sha256"
mkdir -- "$output/source"
tar -xf "$output/source.tar" -C "$output/source"

run_check() {
    local name=$1 duration=$2 status=0
    shift 2
    printf '%q ' "$@" > "$output/$name.command"
    printf '\n' >> "$output/$name.command"
    timeout --kill-after=5s "$duration" "$@" > "$output/$name.log" 2>&1 || status=$?
    printf '%s\n' "$status" > "$output/$name.exit"
    if [[ $status != 0 ]]; then
        printf 'Check failed: %s; inspect %s\n' "$name" "$output/$name.log" >&2
        return "$status"
    fi
}

for tool in gprbuild gnatprove gnatls gcc; do
    resolved=$(command -v "$tool")
    printf '%s\n' "$resolved" > "$output/$tool.path"
    sha256sum -- "$resolved" > "$output/$tool.sha256"
    run_check "$tool-version" 10s "$resolved" --version
done
cd -- "$output/source"
run_check build 120s gprbuild -p -P spark/sia_assurance.gpr
run_check policy-tests 30s spark/bin/policy_tests
run_check transaction-tests 30s spark/bin/transaction_tests
run_check proof 180s gnatprove -P spark/sia_assurance.gpr -U --mode=all \
    --assumptions --no-inlining --memlimit=512 --timeout=10
test -s spark/obj/gnatprove/gnatprove.out
cp -- spark/obj/gnatprove/gnatprove.out "$output/gnatprove-summary.txt"
printf 'All commands passed for %s. Review proof coverage and assumptions in %s.\n' \
    "$commit" "$output"
