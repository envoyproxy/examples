#!/bin/bash -e

EXAMPLE_NAME="${1}"
EXAMPLE_DIR="${2}"
CHECK_PORT_MANIFESTS="${TEST_SRCDIR}/${TEST_WORKSPACE}/${3}"
# $HOME may be unset (or read-only) under `bazel test`
WORKDIR="${TEST_TMPDIR:-${HOME:-/tmp}}"
TMPOUT=$(mktemp -p "${WORKDIR}")
RUNDIR=$(mktemp -d -p "${WORKDIR}")
if [[ -n "${TEST_UNDECLARED_OUTPUTS_DIR:-}" ]]; then
    PORT_MANIFEST_DIR="${TEST_UNDECLARED_OUTPUTS_DIR}"
    mkdir -p "$PORT_MANIFEST_DIR"
else
    PORT_MANIFEST_DIR="$(mktemp -d -p "${WORKDIR}")"
    CLEANUP_MANIFESTS=1
fi
export PORT_MANIFEST_DIR

export COMPOSE_INTERACTIVE_NO_CLI=1
export COMPOSE_PROGRESS=quiet

merge_manifests () {
    local out manifests=()
    out="${TEST_UNDECLARED_OUTPUTS_DIR:-${PORT_MANIFEST_DIR}}/${EXAMPLE_NAME}.ports.json"
    shopt -s nullglob
    manifests=("$PORT_MANIFEST_DIR"/*.ports.json)
    shopt -u nullglob
    if [[ ${#manifests[@]} -gt 0 ]]; then
        jq -s --arg example "$EXAMPLE_NAME" 'add | map(.example = $example)' \
            "${manifests[@]}" > "${out}.merged"
        mv "${out}.merged" "$out"
    else
        echo '[]' > "$out"
    fi
}

complete () {
    local trapcode=$? exitcode
    set +e
    exitcode="$(tail -n 1 "${TMPOUT}" | grep -oP '(?<=COMMAND_EXIT_CODE=")[0-9]+')"
    [[ "$trapcode" == 0 || "$exitcode" != 0 ]] || exitcode="$trapcode"
    echo "${EXAMPLE_NAME}: ${exitcode}:${TIME}"
    tail -n 1 "$TMPOUT"
    echo
    echo
    if [[ "$exitcode" != 0 ]]; then
        cat "$TMPOUT"
    fi
    echo
    echo
    rm -rf "$RUNDIR"
    rm -rf "$TMPOUT"
    [[ -n "${CLEANUP_MANIFESTS:-}" ]] && rm -rf "$PORT_MANIFEST_DIR"
    if [[ -z "$exitcode" ]]; then
        # Could not parse the example's exit code: always fail
        exit "$(( trapcode != 0 ? trapcode : 1 ))"
    fi
    exit "$exitcode"
}

verify () {
    tar xf "$EXAMPLE_DIR" -C "$RUNDIR"
    export DOCKER_NO_PULL=1
    export DOCKER_RMI_CLEANUP=1
    # This is set to simulate an environment where users have shared home drives protected
    # by a strong umask (ie only group readable by default).
    umask 027
    chmod -R u+w,o-rwx "$RUNDIR"
    cd "$RUNDIR"
    dirlist=$(ls .)
    if [[ "$dirlist" == "external" ]]; then
        cd "external/envoy_examples/${EXAMPLE_NAME}"
    else
        cd "${EXAMPLE_NAME}"
    fi
    script -q -c "./verify.sh" "$TMPOUT" >/dev/null </dev/null
}

trap complete EXIT

TIME=$({ time verify; } 2>&1 | grep real | cut -dl -f2)
merge_manifests
MERGED_MANIFEST="${TEST_UNDECLARED_OUTPUTS_DIR:-${PORT_MANIFEST_DIR}}/${EXAMPLE_NAME}.ports.json"
if jq -e 'length > 0' "$MERGED_MANIFEST" > /dev/null; then
    "$CHECK_PORT_MANIFESTS" "$MERGED_MANIFEST"
fi
