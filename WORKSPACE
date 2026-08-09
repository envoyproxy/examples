workspace(name = "envoy-examples")

load("@bazel_tools//tools/build_defs/repo:local.bzl", "local_repository")

local_repository(
    name = "envoy-example-wasm-cc",
    path = "wasm-cc",
)

load("//bazel:env.bzl", "envoy_examples_env")
envoy_examples_env()

load("//bazel:archives.bzl", "load_envoy_examples_archives")
load_envoy_examples_archives()

load("@envoy-example-wasm-cc//bazel:deps_pre.bzl", "resolve_envoy_example_wasmcc_pre_dependencies")
resolve_envoy_example_wasmcc_pre_dependencies()

load("//bazel:deps.bzl", "resolve_envoy_examples_dependencies")
resolve_envoy_examples_dependencies()

load("//bazel:toolchains.bzl", "load_envoy_examples_toolchains")
load_envoy_examples_toolchains()

load("//bazel:packages.bzl", "load_envoy_examples_packages")
load_envoy_examples_packages()
