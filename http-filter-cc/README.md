# HTTP Filter Example (C++ / bzlmod)

This example demonstrates how to build a custom Envoy HTTP filter using bzlmod.

## Overview

This example creates a simple HTTP decoder filter that adds a custom header to incoming requests.
The filter is statically linked into a custom Envoy binary.

## Prerequisites

- Bazel 7.6.2 or later
- A C++ toolchain (clang recommended)

## Building

```bash
cd http-filter-cc
bazel build //:envoy
```

## Running

```bash
bazel-bin/envoy -c envoy.yaml
```

## How it works

The example filter (`sample`) is configured in `envoy.yaml` with two parameters:
- `key`: The header name to add
- `val`: The header value to add

Every request passing through the filter will have the specified header added.

## Files

- `MODULE.bazel` - Bazel module definition with Envoy as a dependency
- `BUILD` - Build targets for the filter and custom Envoy binary
- `http_filter.proto` - Protobuf definition for filter configuration
- `http_filter.h/cc` - Filter implementation
- `http_filter_config.cc` - Filter factory registration
- `envoy.yaml` - Example Envoy configuration

## Note

This example currently pins to the Envoy bzlmod branch. Once bzlmod support is merged
to Envoy main and published to a registry, the `git_override` in MODULE.bazel can be
removed.
