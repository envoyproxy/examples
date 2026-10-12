#!/bin/bash -e

# Compose files publish host ports as "${PORT_<ROLE>:-<default>}:<container>".
# In CI every PORT_<ROLE> is set to 0 before `up` so Docker binds a free
# ephemeral host port, and `resolve_ports` reads the real port back and
# re-exports PORT_<ROLE> so that tests can use http://localhost:${PORT_<ROLE>}.
# Roles that are interpolated outside `ports:` (and so are needed before `up`)
# are instead pre-reserved by binding and releasing a free port.

DELAY="${DELAY:-0}"
DOCKER_NO_PULL="${DOCKER_NO_PULL:-}"
MANUAL="${MANUAL:-}"
NAME="${NAME:-}"
PATHS="${PATHS:-.}"
UPARGS="${UPARGS:-}"
ENVOY_EXAMPLES_DEBUG="${ENVOY_EXAMPLES_DEBUG:-}"


if [[ -n "$DOCKER_COMPOSE" ]]; then
    read -ra DOCKER_COMPOSE <<< "$DOCKER_COMPOSE"
else
    DOCKER_COMPOSE=(docker compose)
fi

run_log () {
    echo -e "\n> [${NAME}] ${*}"
}

PORT_ROLE_RE='PORT_[A-Z0-9_]+'
RESOLVED_PORTS=()

_compose_config_json () {
    "${DOCKER_COMPOSE[@]}" config --no-interpolate --format json
}

# Print the PORT_* roles referenced anywhere in the compose config
# (arg 1: "ports" for host port publications only, "other" for the rest)
_port_roles () {
    local filter
    case "$1" in
        ports)
            filter='[.services[]?.ports[]? | if type == "object" then .published else . end | strings] | tostring'
            ;;
        *)
            filter='del(.services[]?.ports) | tostring'
            ;;
    esac
    _compose_config_json | jq -r "$filter" | grep -oE "$PORT_ROLE_RE" | sort -u || true
}

reserve_port () {
    python3 -c '
import socket
s = socket.socket()
s.bind(("", 0))
print(s.getsockname()[1])
s.close()
'
}

prepare_ports () {
    local paths path role roles reserved=() other
    read -ra paths <<< "$(echo "$PATHS" | tr ',' ' ')"
    RESOLVED_PORTS=()
    ROLES_PRERESERVED=" "
    roles=()
    for path in "${paths[@]}"; do
        pushd "$path" > /dev/null || return 1
        mapfile -t other < <(_port_roles other)
        reserved+=("${other[@]}")
        mapfile -t other < <(_port_roles ports)
        roles+=("${other[@]}")
        popd > /dev/null || return 1
    done
    for role in $(printf '%s\n' "${roles[@]}" | sort -u); do
        export "${role}=0"
    done
    for role in $(printf '%s\n' "${reserved[@]}" | sort -u); do
        [[ -n "$role" ]] || continue
        export "${role}=$(reserve_port)"
        ROLES_PRERESERVED+="${role} "
        RESOLVED_PORTS+=("${!role}")
        run_log "Pre-reserved ${role}=${!role}"
    done
}

# Map each published ${PORT_<ROLE>} to its actual host port, and re-export it
resolve_ports () {
    local role service target proto host_port lines
    lines=$(_compose_config_json | jq -r '
        .services | to_entries[] | .key as $svc
        | (.value.ports // [])[]
        | if type == "object"
          then [(.published // ""), (.target | tostring), (.protocol // "tcp")]
          else (capture("^(?<p>.*):(?<t>[0-9]+)(/(?<proto>[a-z]+))?$")
                | [.p, .t, (.proto // "tcp")])
          end
        | select(.[0] | test("^\\$\\{PORT_[A-Z0-9_]+(:-[^}]*)?\\}$"))
        | [(.[0] | sub("^\\$\\{"; "") | sub("[:}].*$"; "")), $svc, .[1], .[2]]
        | @tsv')
    while IFS=$'\t' read -r role service target proto; do
        [[ -n "$role" ]] || continue
        if [[ "$ROLES_PRERESERVED" == *" ${role} "* ]]; then
            continue
        fi
        host_port=$("${DOCKER_COMPOSE[@]}" port --protocol "$proto" "$service" "$target" | head -n1 | sed 's/.*://')
        if [[ ! "$host_port" =~ ^[0-9]+$ ]]; then
            echo "ERROR: could not resolve host port for ${role} (${service}:${target}/${proto})" >&2
            return 1
        fi
        export "${role}=${host_port}"
        RESOLVED_PORTS+=("$host_port")
        run_log "Resolved ${role}=${host_port} (${service}:${target}/${proto})"
    done <<< "$lines"
}

# Fail if anything is published on a host port that was not allocated above
check_published_ports () {
    local port published
    published=$("${DOCKER_COMPOSE[@]}" ps --format json | jq -r '.Publishers[]? | .PublishedPort | select(. != 0)' | sort -u)
    for port in $published; do
        if [[ " ${RESOLVED_PORTS[*]} " != *" ${port} "* ]]; then
            echo "ERROR: ${NAME} publishes host port ${port} that was not allocated via PORT_*" >&2
            return 1
        fi
    done
}

bring_up_example_stack () {
    local args path up_args
    args=("${UPARGS[@]}")
    path="$1"
    read -ra up_args <<< "up --quiet-pull --pull missing --build --wait -d ${args[*]}"

    if [[ -z "$DOCKER_NO_PULL" ]]; then
        run_log "Pull the images ($path)"
        "${DOCKER_COMPOSE[@]}" pull -q
        echo
    fi
    run_log "Bring up services ($path)"
    "${DOCKER_COMPOSE[@]}" "${up_args[@]}" || return 1

    if [[ -n "$ENVOY_EXAMPLES_DEBUG" ]]; then
        echo "----------------------------------------------"
        docker system df -v
        echo
        sudo du -ch / | grep "[0-9]G"
        echo
        df -h
        echo
        echo "----------------------------------------------"
    fi
    echo
    resolve_ports || return 1
}

bring_up_example () {
    local path paths
    read -ra paths <<< "$(echo "$PATHS" | tr ',' ' ')"

    prepare_ports || return 1
    for path in "${paths[@]}"; do
        pushd "$path" > /dev/null || return 1
        bring_up_example_stack "$path" || {
            echo "ERROR: starting ${NAME} ${path}" >&2
            return 1
        }
        check_published_ports || return 1
        popd > /dev/null || return 1
    done
    if [[ "$DELAY" -ne "0" ]]; then
        run_log "Snooze for ${DELAY} while ${NAME} gets started"
        sleep "$DELAY"
    fi
    if [[ -z "$ENVOY_EXAMPLES_DEBUG" ]]; then
        return
    fi
    for path in "${paths[@]}"; do
        pushd "$path" > /dev/null || return 1
        "${DOCKER_COMPOSE[@]}" ps
        "${DOCKER_COMPOSE[@]}" logs
        popd > /dev/null || return 1
    done
}

bring_down_example () {
    if [[ -n "$DEBUG_EXIT" ]]; then
        return
    fi
    local path paths
    read -ra paths <<< "$(echo "$PATHS" | tr ',' ' ')"
    for path in "${paths[@]}"; do
        pushd "$path" > /dev/null || return 1
        cleanup_stack "$path" || {
            echo "ERROR: cleanup ${NAME} ${path}" >&2
        }
        popd > /dev/null || {
            echo "BRING DOWN: ${path}" >&2
            return 1
        }
    done
}

cleanup_stack () {
    local path down_args
    path="$1"
    down_args=(--remove-orphans)

    if [[ -n "$DOCKER_RMI_CLEANUP" ]]; then
        down_args+=(--rmi all)
    fi

    # Remove sandbox volumes by default
    if [[ -z "$DOCKER_SAVE_VOLUMES" ]]; then
        down_args+=(--volumes)
    fi

    run_log "Cleanup ($path)"
    "${DOCKER_COMPOSE[@]}" down "${down_args[@]}"
}

debug_failure () {
    >&2 echo "FAILURE DEBUG"
    >&2 echo "DISK SPACE"
    df -h
    >&2 echo "DOCKER COMPOSE LOGS"
    "${DOCKER_COMPOSE[@]}" logs
    >&2 echo "DOCKER COMPOSE PS"
    "${DOCKER_COMPOSE[@]}" ps
}

cleanup () {
    local code="$?"

    if [[ "$code" -ne 0 ]]; then
        debug_failure
    fi

    bring_down_example

    if type -t finally &> /dev/null; then
        finally
    fi

    if [[ "$code" -ne 0 ]]; then
        run_log Failed
    else
        run_log Success
    fi
    echo
}

_curl () {
    local arg curl_command
    curl_command=(curl -s)
    if [[ ! "$*" =~ "-X" ]]; then
        curl_command+=(-X GET)
    fi
    for arg in "${@}"; do
        curl_command+=("$arg")
    done
    "${curl_command[@]}" || {
        echo "ERROR: curl (${curl_command[*]})" >&2
        return 1
    }
}

move_if_exists () {
    if [ -e "$1" ]; then
        mv -f "$1" "$2"
    else
        echo "Warning: $1 does not exist. Skipping move operation."
    fi
}

responds_with () {
    local expected response
    expected="$1"
    shift
    response=$(_curl "${@}")
    grep -Fs "$expected" <<< "$response" || {
        echo "ERROR: curl (${*})" >&2
        echo "EXPECTED:" >&2
        echo "$expected" >&2
        echo "RECEIVED:" >&2
        echo "$response" >&2
        return 1
    }
}

responds_without () {
    local expected response
    expected="$1"
    shift
    response=$(_curl "${@}")
    # shellcheck disable=2266
    grep -s "$expected" <<< "$response" | [[ "$(wc -l)" -eq 0 ]] || {
        echo "ERROR: curl (${*})" >&2
        echo "DID NOT EXPECT: $expected" >&2
        echo "RECEIVED:" >&2
        echo "$response" >&2
        return 1
    }
}

responds_with_header () {
    local expected response
    expected="$1"
    shift
    response=$(_curl --head "${@}")
    grep -s "$expected" <<< "$response"  || {
        echo "ERROR: curl (${*})" >&2
        echo "EXPECTED HEADER:" >&2
        echo "$expected" >&2
        echo "RECEIVED:" >&2
        echo "$response" >&2
        return 1
    }
}

responds_without_header () {
    local expected response
    expected="$1"
    shift
    response=$(_curl --head "${@}")
    # shellcheck disable=2266
    grep -s "$expected" <<< "$response" | [[ "$(wc -l)" -eq 0 ]] || {
        echo "ERROR: curl (${*})" >&2
        echo "DID NOT EXPECT HEADER: $expected" >&2
        echo "RECEIVED:" >&2
        echo "$response" >&2
        return 1
    }
}

wait_for () {
    local i=1 returns=1 seconds="$1"
    shift
    while ((i<=seconds)); do
        if "${@}" &> /dev/null; then
            returns=0
            break
        else
            sleep 1
            ((i++))
        fi
    done
    if [[ "$returns" != 0 ]]; then
        echo "Wait (${seconds}) failed: ${*}" >&2
    fi
    return "$returns"
}

debug_exit () {
    DEBUG_EXIT=1
    exit 0
}

trap 'cleanup' EXIT

if [[ -z "$NAME" ]]; then
    echo "ERROR: You must set the '$NAME' variable before sourcing this script" >&2
    exit 1
fi

if [[ -z "$MANUAL" ]]; then
    bring_up_example
fi


# These allow the functions to be used in subshells, e.g. in `wait_for`
export -f responds_with
export -f responds_without
export -f responds_with_header
export -f responds_without_header
export -f _curl
