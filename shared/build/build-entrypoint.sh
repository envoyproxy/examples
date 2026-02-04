#!/usr/bin/env bash

set -e

if [[ $(id -u envoybuild) != "${BUILD_UID}" ]]; then
    usermod -u "${BUILD_UID}" envoybuild
    chown envoybuild /home/envoybuild
    chown envoybuild /home/envoybuild/.cache
fi

chown envoybuild /output

# Generate config files from templates if they exist
if [ -f MODULE.bazel.tpl ]; then
    envsubst '${ENVOY_COMMIT}' < MODULE.bazel.tpl > MODULE.bazel
fi

if [ -f registry.bazelrc.tpl ]; then
    envsubst '${REGISTRY_URL}' < registry.bazelrc.tpl > registry.bazelrc
fi

exec gosu envoybuild "$@"
