load("@emsdk//:toolchains.bzl", "register_emscripten_toolchains")
load("@envoy//bazel:api_repositories.bzl", "envoy_api_dependencies")
load("@io_bazel_rules_go//go:deps.bzl", "go_register_toolchains")
load("@llvm_toolchain//:toolchains.bzl", "llvm_register_toolchains")
load("@rules_proto_grpc//:repositories.bzl", "rules_proto_grpc_toolchains")
load("@rules_python//python:repositories.bzl", "python_register_toolchains")
load("//:versions.bzl", "VERSIONS")

def load_toolchains():
    envoy_api_dependencies()
    register_emscripten_toolchains()
    llvm_register_toolchains()
    python_register_toolchains(
        name = "python%s" % VERSIONS["python"].replace(".", "_"),
        python_version = VERSIONS["python"].replace("-", "_"),
    )
    go_register_toolchains(VERSIONS["go"])
    rules_proto_grpc_toolchains()
