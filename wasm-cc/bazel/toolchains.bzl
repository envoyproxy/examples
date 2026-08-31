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
            extra_llvm_distributions = {
                "LLVM-22.1.8-Linux-ARM64.tar.xz": "805efad2bb91cb4967fa569e0881d10c0f69c04461cf671cccbae19f547acc34",
                "LLVM-22.1.8-Linux-X64.tar.xz": "df0e1ecf16caf3489a272a5eea4eec9b0d82878f6477fa309504f918a0006384",
                "LLVM-22.1.8-macOS-ARM64.tar.xz": "f260f4f7c0d430828a81ae8a3826a1d63fc0963ec2459489308cc23b1f7eab4f",
            },
            sysroot = {
                "linux-x86_64": "@sysroot_linux_amd64//:sysroot",
                "linux-aarch64": "@sysroot_linux_arm64//:sysroot",
            },
            toolchain_roots = {
                "linux-x86_64": "@llvm_minimal_linux_x64//",
                "linux-aarch64": "@llvm_minimal_linux_arm64//",
                "darwin-aarch64": "@llvm_minimal_macos_arm64//",
            },
        )
