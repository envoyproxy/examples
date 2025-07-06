load("@io_bazel_rules_go//go:deps.bzl", "go_register_toolchains")
load("@rules_python//python:repositories.bzl", "python_register_toolchains")
load("//bazel:versions.bzl", "VERSIONS")

def load_envoy_examples_toolchains():
    go_register_toolchains(VERSIONS["go"])
    python_register_toolchains(
        name = "python%s" % VERSIONS["python"].replace(".", "_"),
        python_version = VERSIONS["python"].replace("-", "_"),
    )
