load("@envoy-examples-env//:llvm_flag.bzl", "LLVM_ENABLED")
load("@envoy-example-wasm-cc//bazel:packages.bzl", "load_envoy_example_wasmcc_packages")
load("@envoy-example-wasm-cc//bazel:toolchains_extra.bzl", "load_envoy_example_wasmcc_toolchains_extra")

def load_envoy_examples_packages():
    load_envoy_example_wasmcc_packages()
    if LLVM_ENABLED:
        load_envoy_example_wasmcc_toolchains_extra()
