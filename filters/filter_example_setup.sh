#!/usr/bin/env bash

# Configure environment for Envoy Filter Example build and test.

set -e

# shellcheck disable=SC2034
ENVOY_FILTER_EXAMPLE_TESTS=(
    "//:echo2_integration_test"
    "//http-filter-example:http_filter_integration_test"
    "//:envoy_binary_test")

mkdir -p "${ENVOY_FILTER_EXAMPLE_SRCDIR}"/bazel
ln -sf "${ENVOY_SRCDIR}"/bazel/get_workspace_status "${ENVOY_FILTER_EXAMPLE_SRCDIR}"/bazel/
ln -sf "${ENVOY_SRCDIR}"/bazel/platform_mappings "${ENVOY_FILTER_EXAMPLE_SRCDIR}"/bazel/
cp -a "${ENVOY_SRCDIR}"/bazel/protoc "${ENVOY_FILTER_EXAMPLE_SRCDIR}"/bazel/
cp -f "${ENVOY_SRCDIR}"/.bazelrc "${ENVOY_FILTER_EXAMPLE_SRCDIR}"/
rm -f "${ENVOY_FILTER_EXAMPLE_SRCDIR}"/.bazelversion
cp -f "${ENVOY_SRCDIR}"/.bazelversion "${ENVOY_FILTER_EXAMPLE_SRCDIR}"/
cp -f "${ENVOY_SRCDIR}"/*.bazelrc "${ENVOY_FILTER_EXAMPLE_SRCDIR}"/

export FILTER_WORKSPACE_SET=1
