#!/bin/bash -e

if [[ $# == 0 ]]; then
    echo "ERROR: no port manifests provided" >&2
    exit 1
fi
# Skip the range check where the kernel range is unreadable
low=0 high=65535
[[ -r /proc/sys/net/ipv4/ip_local_port_range ]] && read -r low high < /proc/sys/net/ipv4/ip_local_port_range

printf 'EXAMPLE\tSERVICE\tPORT\tTARGET\tPROTO\tALLOCATED\n'
jq -sr 'add | sort_by(.example, .service, .port)[] |
    [.example, .service, .port, .target, .proto, .allocated] | @tsv' "$@"

# Kernel reuses freed ephemeral ports across sequential runs;
# concurrency safety is proven by //:port_collision_test instead.
jq -se --argjson low "$low" --argjson high "$high" '
    add as $ports
    | ([$ports[] | select(.allocated != true)
        | "\(.example): unallocated port \(.port)/\(.proto)"]
       + [$ports[] | select(.port < $low or .port > $high)
          | "\(.example): port \(.port)/\(.proto) outside \($low)-\($high)"]) as $errors
    | if $errors | length > 0 then error($errors | join("\n"))
      else true end
' "$@" > /dev/null
