load("@bazel_features//:deps.bzl", "bazel_features_deps")

def resolve_envoy_example_wasmcc_pre_dependencies():
    bazel_features_deps()
