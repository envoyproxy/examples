#!/bin/bash -e

# Compose files publish host ports as "${PORT_<ROLE>:-<default>}:<container>".
# Unless already set, every PORT_<ROLE> is set to 0 before `up` so Docker binds a free
# ephemeral host port, and `resolve_ports` reads the real port back and
# re-exports PORT_<ROLE> so that tests can use http://localhost:${PORT_<ROLE>}.
# Roles that are interpolated outside `ports:` (and so are needed before `up`)
# are instead pre-reserved by binding and releasing a free port.
# Set PRERESERVE_ROLES="PORT_PROXY PORT_DEV_PROXY" for roles needed in generated
# files before `up`; call prepare_ports before generating those files.
# Multiple publications of one target are also pre-reserved: Compose merges
# identical host-port-0 mappings during interpolation.
# Set PORT_PROXY=10000 ./verify.sh to pin a port locally.
#
# This file is sourced on developer machines as well as in CI, so it must stay
# bash 3.2 compatible (macOS): no mapfile, associative arrays, or [[ -v ]].

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

PORT_ROLE_RE='\$\{PORT_[A-Z0-9_]+'
RESOLVED_PORTS=()
EXEMPT_PORTS=()

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
    _compose_config_json | jq -r "$filter" | grep -oE "$PORT_ROLE_RE" | sed 's/^${//' | sort -u || true
}

_port_bindings () {
    _compose_config_json | jq -c '
        .services | to_entries[] | .key as $svc
        | (.value.ports // [])[]
        | if type == "object"
          then [(.published // ""), (.target | tostring), (.protocol // "tcp")]
          else (capture("^(?<p>.*):(?<t>[0-9]+)(/(?<proto>[a-z]+))?$")
                | [.p, .t, (.proto // "tcp")])
          end
        | select(.[0] | test("\\$\\{PORT_[A-Z0-9_]+"))
        | [(.[0] | capture("\\$\\{(?<role>PORT_[A-Z0-9_]+)").role), $svc, .[1], .[2]]'
}

reserve_port () {
    command -v python3 > /dev/null || {
        echo "ERROR: reserve_port requires python3" >&2
        return 1
    }
    python3 -c '
import socket
s = socket.socket()
s.bind(("", 0))
print(s.getsockname()[1])
s.close()
'
}

# True if the variable named by $1 is set (possibly empty). bash 3.2 has no [[ -v ]].
_is_set () {
    [[ -n "${!1+x}" ]]
}

prepare_ports () {
    [[ -n "${PORT_MANIFEST_PATH:-}" ]] && return 0
    local paths path role roles reserved=() other port
    read -ra reserved <<< "${PRERESERVE_ROLES:-}"
    read -ra paths <<< "$(echo "$PATHS" | tr ',' ' ')"
    RESOLVED_PORTS=()
    EXEMPT_PORTS=()
    ROLES_PRERESERVED=" "
    ROLES_PINNED=" "
    mkdir -p "${PORT_MANIFEST_DIR:-${TEST_UNDECLARED_OUTPUTS_DIR:-/tmp}}" || return 1
    PORT_MANIFEST_PATH="$(cd "${PORT_MANIFEST_DIR:-${TEST_UNDECLARED_OUTPUTS_DIR:-/tmp}}" && pwd)/${NAME}.ports.json"
    printf '[]\n' > "$PORT_MANIFEST_PATH"
    roles=()
    # Role names are [A-Z0-9_]+ so whitespace splitting is safe.
    for path in "${paths[@]}"; do
        pushd "$path" > /dev/null || return 1
        read -ra other <<< "$(_port_roles other | tr '\n' ' ')"
        reserved+=("${other[@]}")
        read -ra other <<< "$(_port_bindings | jq -sr 'group_by(.[1:])[] | select(length > 1) | .[][0]' | tr '\n' ' ')"
        reserved+=("${other[@]}")
        read -ra other <<< "$(_port_roles ports | tr '\n' ' ')"
        roles+=("${other[@]}")
        popd > /dev/null || return 1
    done
    # A role may be in both roles (published) and reserved (pre-reserved);
    # one already set non-zero is pinned and wins over ephemeral allocation
    # and pre-reservation.
    for role in $(printf '%s\n' "${roles[@]}" | sort -u); do
        [[ -n "$role" ]] || continue
        if _is_set "$role" && [[ "${!role}" != 0 ]]; then
            ROLES_PINNED+="${role} "
            EXEMPT_PORTS+=("${!role}")
            RESOLVED_PORTS+=("${!role}")
        elif ! _is_set "$role"; then
            export "${role}=0"
        fi
    done
    for role in $(printf '%s\n' "${reserved[@]}" | sort -u); do
        [[ -n "$role" ]] || continue
        if [[ "$ROLES_PINNED" != *" ${role} "* ]]; then
            if ! _is_set "$role" || [[ "${!role}" == 0 ]]; then
                port=$(reserve_port) || return 1
                export "${role}=${port}"
            fi
        fi
        ROLES_PRERESERVED+="${role} "
        RESOLVED_PORTS+=("${!role}")
        EXEMPT_PORTS+=("${!role}")
        run_log "Pre-reserved ${role}=${!role}"
    done
}

# Map each published ${PORT_<ROLE>} to its actual host port, and re-export it
resolve_ports () {
    local role service target proto host_port lines candidates candidate key
    # Space-delimited set of "service:target/proto:port" already claimed
    # (no associative arrays in bash 3.2).
    local used=" "
    lines=$(_port_bindings | jq -r '@tsv') || return 1
    while IFS=$'\t' read -r role service target proto; do
        [[ -n "$role" ]] || continue
        if [[ "$ROLES_PRERESERVED" == *" ${role} "* || "$ROLES_PINNED" == *" ${role} "* ]]; then
            used+="${service}:${target}/${proto}:${!role} "
        fi
    done <<< "$lines"
    while IFS=$'\t' read -r role service target proto; do
        [[ -n "$role" ]] || continue
        if [[ "$ROLES_PRERESERVED" == *" ${role} "* || "$ROLES_PINNED" == *" ${role} "* ]]; then
            continue
        fi
        candidates=$("${DOCKER_COMPOSE[@]}" port --protocol "$proto" "$service" "$target") || return 1
        host_port=""
        # Consume distinct publications in order, ignoring duplicate IPv4/IPv6 bindings.
        while read -r candidate; do
            candidate="${candidate##*:}"
            key="${service}:${target}/${proto}:${candidate}"
            [[ "$used" == *" ${key} "* ]] && continue
            host_port="$candidate"
            break
        done <<< "$candidates"
        if [[ ! "$host_port" =~ ^[0-9]+$ ]]; then
            echo "ERROR: could not resolve host port for ${role} (${service}:${target}/${proto})" >&2
            return 1
        fi
        export "${role}=${host_port}"
        used+="${service}:${target}/${proto}:${host_port} "
        RESOLVED_PORTS+=("$host_port")
        run_log "Resolved ${role}=${host_port} (${service}:${target}/${proto})"
    done <<< "$lines"
}

# Record all publications, then reject unallocated or non-ephemeral ports.
check_published_ports () {
    local published manifest low high
    published=$("${DOCKER_COMPOSE[@]}" ps --format json) || return 1
    manifest=$(jq -s --arg example "$NAME" --arg ports " ${RESOLVED_PORTS[*]} " '
        [.. | objects | select(has("Publishers")) | .Service as $service
         | .Publishers[]? | select(.PublishedPort != null and .PublishedPort != 0)
         | .PublishedPort as $port
         | {example: $example, service: $service, port: .PublishedPort,
            target: .TargetPort, proto: .Protocol,
            allocated: ($ports | contains(" \($port) "))}]
    ' <<< "$published") || return 1
    manifest=$(jq -s --arg ports " ${RESOLVED_PORTS[*]} " '
        add | unique_by([.example, .service, .port, .target, .proto])
        | map(.port as $port | .allocated = ($ports | contains(" \($port) ")))
    ' \
        "$PORT_MANIFEST_PATH" <(printf '%s\n' "$manifest")) || return 1
    printf '%s\n' "$manifest" > "$PORT_MANIFEST_PATH"
    if ! jq -e 'all(.[]; .allocated)' "$PORT_MANIFEST_PATH" > /dev/null; then
        echo "ERROR: ${NAME} publishes unallocated ports; see ${PORT_MANIFEST_PATH}" >&2
        return 1
    fi
    if [[ -r /proc/sys/net/ipv4/ip_local_port_range ]]; then
        read -r low high < /proc/sys/net/ipv4/ip_local_port_range
        if ! jq -e --argjson low "$low" --argjson high "$high" --arg exempt " ${EXEMPT_PORTS[*]} " '
            all(.[]; .port as $port | (.port >= $low and .port <= $high)
                or ($exempt | contains(" \($port) ")))
        ' "$PORT_MANIFEST_PATH" > /dev/null; then
            echo "ERROR: ${NAME} publishes ports outside ${low}-${high}; see ${PORT_MANIFEST_PATH}" >&2
            return 1
        fi
    fi
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
