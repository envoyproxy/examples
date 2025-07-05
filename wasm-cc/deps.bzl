load("@emsdk//:deps.bzl", emsdk_deps = "deps")
load("@envoy//bazel:api_binding.bzl", "envoy_api_binding")
load("@envoy_toolshed//sysroot:sysroot.bzl", "setup_sysroots")
load("@io_bazel_rules_go//go:deps.bzl", "go_rules_dependencies")
load("@rules_foreign_cc//foreign_cc:repositories.bzl", "rules_foreign_cc_dependencies")
load("@rules_fuzzing//fuzzing:repositories.bzl", "rules_fuzzing_dependencies")
load("@rules_perl//perl:deps.bzl", "perl_register_toolchains", "perl_rules_dependencies")
load("@rules_python//python:repositories.bzl", "py_repositories")
load("@toolchains_llvm//toolchain:deps.bzl", "bazel_toolchain_dependencies")
load("@toolchains_llvm//toolchain:rules.bzl", "llvm_toolchain")
load("//:versions.bzl", "VERSIONS")

def resolve_dependencies(
        cmake_version=None,
        llvm_version=None,
        ninja_version=None,
        setup_autotools_toolchain=True):

    envoy_api_binding()
    py_repositories()
    bazel_toolchain_dependencies()
    rules_foreign_cc_dependencies(
        register_preinstalled_tools = True,
        register_default_tools = True,
        cmake_version = cmake_version or VERSIONS["cmake"],
        ninja_version = ninja_version or VERSIONS["ninja"],
    )
    emsdk_deps()
    perl_rules_dependencies()
    perl_register_toolchains()
    rules_fuzzing_dependencies(
        oss_fuzz = True,
        honggfuzz = False,
    )
    setup_sysroots()

    llvm_toolchain(
        name = "llvm_toolchain",
        llvm_version = llvm_version or VERSIONS["llvm"],
        sysroot = {
            "linux-x86_64": "@sysroot_linux_amd64//:sysroot",
            "linux-aarch64": "@sysroot_linux_arm64//:sysroot",
        }
    )
    go_rules_dependencies()
