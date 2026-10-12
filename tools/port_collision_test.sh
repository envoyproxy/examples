#!/bin/bash -e

if [[ -n "${TEST_SRCDIR:-}" ]]; then
    root="$TEST_SRCDIR/$TEST_WORKSPACE"
else
    root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fi
work="$(mktemp -d)"
pids=()

cleanup () {
    local project
    for pid in "${pids[@]}"; do
        kill "$pid" 2> /dev/null || true
    done
    for pid in "${pids[@]}"; do
        wait "$pid" 2> /dev/null || true
    done
    for project in gzip_a gzip_b; do
        (cd "$work/$project/gzip" && COMPOSE_PROJECT_NAME="$project" docker compose down --volumes --remove-orphans) || true
    done
    rm -rf "$work"
}
trap cleanup EXIT

for project in gzip_a gzip_b; do
    mkdir -p "$work/$project" "$work/manifests/$project"
    if [[ -n "${1:-}" ]]; then
        tar xf "$1" -C "$work/$project"
    else
        cp -a "$root/gzip" "$root/shared" "$root/verify-common.sh" "$work/$project/"
    fi
    (
        cd "$work/$project/gzip"
        export NAME="$project" COMPOSE_PROJECT_NAME="$project"
        export PORT_MANIFEST_DIR="$work/manifests/$project"
        unset PORT_PROXY PORT_STATS0 PORT_STATS1
        # Keep both stacks alive until both manifests have been collected.
        export MANUAL=1
        # shellcheck source=verify-common.sh
        . ../verify-common.sh
        trap - EXIT
        bring_up_example
    ) > "$work/$project.log" 2>&1 &
    pids+=("$!")
done

status=0
for pid in "${pids[@]}"; do
    wait "$pid" || status=1
done
cat "$work"/gzip_*.log
[[ "$status" == 0 ]] || exit 1

jq -se '
    .[0] as $a | .[1] as $b
    | ($a | length > 0) and ($b | length > 0)
      and all($a[]; .allocated) and all($b[]; .allocated)
      and ([ $a[].port ] - [ $b[].port ] | unique | length)
          == ([ $a[].port ] | unique | length)
' "$work/manifests/gzip_a/gzip_a.ports.json" "$work/manifests/gzip_b/gzip_b.ports.json"

if [[ -n "${TEST_UNDECLARED_OUTPUTS_DIR:-}" ]]; then
    cp "$work/manifests/gzip_a/gzip_a.ports.json" "$work/manifests/gzip_b/gzip_b.ports.json" "$TEST_UNDECLARED_OUTPUTS_DIR/"
fi
