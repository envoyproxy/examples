#!/bin/bash -e

export NAME=local_ratelimit

# shellcheck source=verify-common.sh
. "$(dirname "${BASH_SOURCE[0]}")/../verify-common.sh"


responds_with_rate_limit () {
    local count="$1" url="$2" i

    for ((i=1;i<=count;i++)); do
        responds_with \
            "local_rate_limited" \
            "$url"
    done
}

responds_without_rate_limit () {
    local count="$1" url="$2" i

    for ((i=1;i<=count;i++)); do
        responds_without \
            "local_rate_limited" \
            "$url"
    done
}
export -f responds_without_rate_limit


# envoy-stat has no healthcheck; wait until the traffic listener's workers are
# serving before the rate-limit checks. Probe the stats interface for
# listener_manager.workers_started (as shared/envoy's healthcheck does) rather
# than the data port, so no rate-limit tokens are consumed and we do not race a
# stats endpoint that is up before the workers are.
wait_for 10 bash -c "curl -s 'http://localhost:${PORT_STATS0}/stats?filter=listener_manager.workers_started' | grep -q ': 1'"

run_log "Test upstream: localhost:${PORT_PROXY} without rate limit header two times"
for i in {1..2}; do
    output=$(curl -s -X GET --head "http://localhost:${PORT_PROXY}")
    echo "${output}" | grep "429 Too Many Requests" && exit 1
    echo "${output}" | grep "x-local-rate-limit: true" && exit 1
done

run_log "Test upstream: localhost:${PORT_PROXY} with rate limit header three times"
for i in {1..3}; do
    output=$(curl -s -X GET --head "http://localhost:${PORT_PROXY}")
    echo "${output}" | grep "429 Too Many Requests" || exit 1
    echo "${output}" | grep "x-local-rate-limit: true" || exit 1
done

run_log "Test upstream: localhost:${PORT_PROXY} without rate limit response after refill"
wait_for 10 responds_without "local_rate_limited" "http://localhost:${PORT_PROXY}"

run_log "Test upstream: localhost:${PORT_PROXY} with rate limit response three times"
responds_with_rate_limit 3 "http://localhost:${PORT_PROXY}"

run_log "Test admin interface: localhost:${PORT_STATS0}/stats/prometheus without rate limit header five times"
for i in {1..5}; do
    output=$(curl -s -X GET --head "http://localhost:${PORT_STATS0}/stats/prometheus")
    echo "${output}" | grep "429 Too Many Requests" && exit 1
    echo "${output}" | grep "x-local-rate-limit: true" && exit 1
done

run_log "Test admin interface: localhost:${PORT_STATS0}/stats/prometheus without rate limit response five times"
responds_without_rate_limit 5 "http://localhost:${PORT_STATS0}/stats/prometheus"

run_log "Test admin interface: localhost:${PORT_STATS1}/stats/prometheus without rate limit header two times"
for i in {1..2}; do
    output=$(curl -s -X GET --head "http://localhost:${PORT_STATS1}/stats/prometheus")
    echo "${output}" | grep "429 Too Many Requests" && exit 1
    echo "${output}" | grep "x-local-rate-limit: true" && exit 1
done

run_log "Test admin interface: localhost:${PORT_STATS1}/stats/prometheus with rate limit header three times"
for i in {1..3}; do
    output=$(curl -s -X GET --head "http://localhost:${PORT_STATS1}/stats/prometheus")
    echo "${output}" | grep "429 Too Many Requests" || exit 1
    echo "${output}" | grep "x-local-rate-limit: true" || exit 1
done

run_log "Test admin interface: localhost:${PORT_STATS1}/stats/prometheus without rate limit response after refill"
wait_for 10 responds_without "local_rate_limited" "http://localhost:${PORT_STATS1}/stats/prometheus"

run_log "Test admin interface: localhost:${PORT_STATS1}/stats/prometheus with rate limit response three times"
responds_with_rate_limit 3 "http://localhost:${PORT_STATS1}/stats/prometheus"
