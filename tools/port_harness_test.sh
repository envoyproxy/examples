#!/bin/bash -e

if [[ -n "${TEST_SRCDIR:-}" ]]; then
    root="$TEST_SRCDIR/$TEST_WORKSPACE"
else
    root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fi
work="$(mktemp -d)"
export NAME=fixture MANUAL=1 PORT_MANIFEST_DIR="$work"
# shellcheck source=verify-common.sh
. "$root/verify-common.sh"
trap 'rm -rf "$work"' EXIT

fail () {
    echo "ERROR: $*" >&2
    exit 1
}

read -r low high < /proc/sys/net/ipv4/ip_local_port_range
first="$low"
second=$((low + 1))
third=$((low + 2))

compose () {
    case "$1" in
        config)
            cat <<'JSON'
{"services":{"envoy":{"environment":{"SUPPORT_LEVEL":"high","URL":"${PORT_LINK:-10000}"},"ports":[{"published":"${PORT_PROXY0:-80}","target":80},{"published":"${PORT_PROXY1:-81}","target":80},{"published":"${PORT_PIN:-8081}","target":8081}]}}}
JSON
            ;;
        port)
            printf '0.0.0.0:%s\n[::]:%s\n0.0.0.0:%s\n' "$first" "$first" "$second"
            ;;
        ps)
            printf '{"Service":"envoy","Publishers":[{"PublishedPort":%s,"TargetPort":80,"Protocol":"tcp"},{"PublishedPort":%s,"TargetPort":80,"Protocol":"tcp"},{"PublishedPort":10000,"TargetPort":8081,"Protocol":"tcp"},{"PublishedPort":0,"TargetPort":90,"Protocol":"tcp"}]}\n' "$first" "$second"
            ;;
    esac
}
DOCKER_COMPOSE=(compose)
export PORT_PIN=10000
[[ "$(_port_roles other)" == PORT_LINK ]] || fail "phantom role detected"
prepare_ports
[[ "$PORT_PROXY0" != 0 && "$PORT_PROXY1" != 0 && "$PORT_PROXY0" != "$PORT_PROXY1" && "$PORT_PIN" == 10000 ]] || fail "duplicate publications or override lost"
# shellcheck disable=SC2153
[[ "$PORT_LINK" -ge "$low" && "$PORT_LINK" -le "$high" ]] || fail "reservation outside range"
# Roles needed by generated files cannot be inferred from Compose.
(
    unset PORT_MANIFEST_PATH PORT_LINK PORT_PROXY0 PORT_PROXY1
    export PRERESERVE_ROLES="PORT_EARLY PORT_PIN PORT_LINK"
    export PORT_EARLY=0
    prepare_ports
    [[ "$PORT_EARLY" -ge "$low" && "$PORT_EARLY" -le "$high" && "$PORT_PIN" == 10000 ]] || fail "explicit reservation or pin lost"
    for role in PORT_EARLY PORT_PIN PORT_LINK; do
        [[ "$ROLES_PRERESERVED" == *" ${role} "* && " ${RESOLVED_PORTS[*]} " == *" ${!role} "* && " ${EXEMPT_PORTS[*]} " == *" ${!role} "* ]] || fail "reservation not tracked"
    done
    state="$PORT_EARLY $PORT_LINK $PORT_PROXY0 $PORT_PROXY1 $PORT_MANIFEST_PATH $ROLES_PRERESERVED $ROLES_PINNED ${RESOLVED_PORTS[*]} ${EXEMPT_PORTS[*]}"
    printf '[{"prepared":true}]\n' > "$PORT_MANIFEST_PATH"
    prepare_ports
    [[ "$state" == "$PORT_EARLY $PORT_LINK $PORT_PROXY0 $PORT_PROXY1 $PORT_MANIFEST_PATH $ROLES_PRERESERVED $ROLES_PINNED ${RESOLVED_PORTS[*]} ${EXEMPT_PORTS[*]}" ]] || fail "preparation is not idempotent"
    jq -e '.[0].prepared' "$PORT_MANIFEST_PATH" > /dev/null
)
printf '[]\n' > "$PORT_MANIFEST_PATH"
# Exercise multi-line resolution on Compose versions that retain both publications.
ROLES_PRERESERVED=" PORT_LINK "
RESOLVED_PORTS=(10000 "$PORT_LINK")
resolve_ports
[[ "$PORT_PROXY0" == "$first" && "$PORT_PROXY1" == "$second" ]] || fail "duplicate target roles collided"
check_published_ports
jq -e 'length == 3 and all(.[]; .allocated)' "$PORT_MANIFEST_PATH" > /dev/null

# Compose versions emit either an array or one JSON object per line.
published="$(compose ps)"
compose_array () {
    if [[ "$1" == ps ]]; then
        printf '[%s]\n' "$published"
    else
        compose "$@"
    fi
}
DOCKER_COMPOSE=(compose_array)
check_published_ports
jq -e 'length == 3' "$PORT_MANIFEST_PATH" > /dev/null
RESOLVED_PORTS=("$first")
if check_published_ports; then fail "unallocated publication accepted"; fi
jq -e 'any(.[]; .allocated == false)' "$PORT_MANIFEST_PATH" > /dev/null
RESOLVED_PORTS=("$first" "$second" 10000)
EXEMPT_PORTS=()
if check_published_ports; then fail "non-ephemeral publication accepted"; fi

rm "$PORT_MANIFEST_PATH"
jq -n --argjson port "$first" '[{example:"a",service:"envoy",port:$port,target:80,proto:"tcp",allocated:true}]' > "$work/a.ports.json"
jq --argjson port "$third" 'map(.example="b" | .port=$port)' "$work/a.ports.json" > "$work/b.ports.json"
bash "$root/tools/check_port_manifests.sh" "$work/a.ports.json" "$work/b.ports.json"
jq 'map(.example="b" | .port=10000 | .allocated=false)' "$work/b.ports.json" > "$work/new"
mv "$work/new" "$work/b.ports.json"
if bash "$root/tools/check_port_manifests.sh" "$work/a.ports.json" "$work/b.ports.json"; then fail "invalid allocation accepted"; fi

# shellcheck disable=SC2016
valid='{"fixture.yaml":{"services":{"envoy":{"ports":["${PORT_A:-80}:80","127.0.0.1:${PORT_B:-81}:80/udp","[::1]:${PORT_C:-82}:80",{"published":"${PORT_D:-83}","target":80}]}}}}'
jq -f "$root/tools/lint_ports.jq" <<< "$valid"
if [[ -n "${1:-}" ]]; then
    jq -e 'keys | any(.[]; endswith("gzip/docker-compose.yaml"))
        and any(.[]; endswith("load-reporting-service/docker-compose.yaml"))' "$1" > /dev/null
fi
# shellcheck disable=SC2016
for bad in '"80:80"' '"127.0.0.1:80:80/tcp"' '"80"' '{"published":80,"target":80}' '"${SUPPORT_LEVEL:-80}:80"'; do
    if jq -f "$root/tools/lint_ports.jq" <<< "{\"bad.yaml\":{\"services\":{\"envoy\":{\"ports\":[$bad]}}}}"; then
        fail "lint accepted $bad"
    fi
done
