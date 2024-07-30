#!/bin/bash -e

EXAMPLE_NAME="${1}"
EXAMPLE_DIR="${2}"
TMPOUT=$(mktemp)
RUNDIR=$(mktemp -d)

export TERM=xterm-256color

complete () {
    EXITCODE=$(tail -n 1 $TMPOUT | grep -oP '(?<=COMMAND_EXIT_CODE=")[0-9]+')
    echo "${EXAMPLE_NAME}: ${EXITCODE}:${TIME}"
    tail -n 1 $TMPOUT
    echo
    echo
    if [[ $EXITCODE != 0 ]]; then
        cat $TMPOUT
    fi
    echo
    echo
    rm -rf $RUNDIR
    rm -rf $TMPOUT
}

verify () {
    tar xf $EXAMPLE_DIR -C $RUNDIR
    cd "$RUNDIR/${EXAMPLE_NAME}"
    script -q -c "unbuffer ./verify.sh" "$TMPOUT" >/dev/null
}

trap complete EXIT

TIME=$({ time verify; } 2>&1 | grep real | cut -dl -f2)
