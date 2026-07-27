load("@emsdk//:toolchains.bzl", "register_emscripten_toolchains")
load("@envoy//bazel:api_repositories.bzl", "envoy_api_dependencies")
load("@io_bazel_rules_go//go:deps.bzl", "go_register_toolchains")
load("@rules_perl//perl:deps.bzl", "perl_register_toolchains")
load("@rules_proto_grpc//:repositories.bzl", "rules_proto_grpc_toolchains")
load("@rules_python//python:repositories.bzl", "python_register_toolchains")
load("@toolchains_llvm//toolchain:rules.bzl", "llvm_toolchain")
load("//bazel:versions.bzl", "VERSIONS")

def load_envoy_example_wasmcc_toolchains(go=True, llvm_version=VERSIONS["llvm"]):
    envoy_api_dependencies()
    register_emscripten_toolchains()
    python_register_toolchains(
        name = "python%s" % VERSIONS["python"].replace(".", "_"),
        python_version = VERSIONS["python"].replace("-", "_"),
    )
    if go:
        go_register_toolchains(VERSIONS["go"])
    rules_proto_grpc_toolchains()
    perl_register_toolchains()
    if llvm_version != False:
        llvm_toolchain(
            name = "llvm_toolchain",
            llvm_version = llvm_version,
            sysroot = {
                "linux-x86_64": "@sysroot_linux_amd64//:sysroot",
                "linux-aarch64": "@sysroot_linux_arm64//:sysroot",
            }
        )
