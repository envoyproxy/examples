#!/usr/bin/env bash

set -euo pipefail

if [[ ! "${NEXT_VERSION}" =~ ^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]]; then
    echo "NEXT_VERSION must be a plain semantic version" >&2
    exit 1
fi

MODULE_VERSION_SED="/^module(/,/^)/s/version = \"[^\"]*\"/version = \"${NEXT_VERSION}\"/"
DEP_VERSION_SED="/^bazel_dep(name = \"envoy-example-\(filter\|wasm\)-cc\"/s/version = \"[^\"]*\"/version = \"${NEXT_VERSION}\"/"

for module in MODULE.bazel filter-cc/MODULE.bazel wasm-cc/MODULE.bazel; do
    printf '$ sed -i %q %q\n' "${MODULE_VERSION_SED}" "${module}" >> "${TMP_OUTPUT}"
    sed -i "${MODULE_VERSION_SED}" "${module}"
done
printf '$ sed -i %q MODULE.bazel\n' "${DEP_VERSION_SED}" >> "${TMP_OUTPUT}"
sed -i "${DEP_VERSION_SED}" MODULE.bazel

printf '%s\n' MODULE.bazel filter-cc/MODULE.bazel wasm-cc/MODULE.bazel
