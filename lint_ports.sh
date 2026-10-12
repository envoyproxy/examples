#!/bin/bash -e
#
# Every published host port in an example compose file must be of the form
# "${PORT_<ROLE>:-<default>}:<container>[/proto]" so that CI can override it
# with an ephemeral port. Bare "NNNN:MMMM" mappings cannot be made ephemeral.

HOST_RE='^\$\{PORT_[A-Z0-9_]+:-[0-9]+\}$'
FAILED=0

mapfile -t files < <(find . -mindepth 2 -path '*/node_modules' -prune -o \
    \( -name 'docker-compose*.yaml' -o -name 'docker-compose*.yml' \) -print | sort)

for file in "${files[@]}"; do
    bad=$(yq -o=json '.' "$file" | jq -r --arg re "$HOST_RE" '
        [.services // {} | to_entries[] | .key as $svc
         | (.value.ports // [])[]
         | if type == "object" then (.published // "" | tostring)
           else (tostring | capture("^(?<h>.*):[0-9]+(/[a-z]+)?$").h? // .) end
         | select(test($re) | not)
         | "\($svc): \(.)"] | .[]')
    if [[ -n "$bad" ]]; then
        echo "ERROR: ${file}: host ports must be \${PORT_<ROLE>:-<default>}:" >&2
        echo "$bad" >&2
        FAILED=1
    fi
done

exit "$FAILED"
