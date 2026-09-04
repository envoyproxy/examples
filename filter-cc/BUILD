load("@envoy//bazel:envoy_build_system.bzl", "envoy_cc_binary", "envoy_cc_library", "envoy_cc_test")
load("@envoy_api//bazel:api_build_system.bzl", "api_proto_package")
load("@rules_pkg//pkg:pkg.bzl", "pkg_tar")

licenses(["notice"])  # Apache 2

exports_files(["example.rst"])

filegroup(
    name = "configs",
    srcs = glob(
        [
            "**/*.yaml",
        ],
        exclude = [
            "**/*docker-compose*.yaml",
        ],
    ),
    visibility = ["//visibility:public"],
)

api_proto_package()

envoy_cc_library(
    name = "http_filter_lib",
    srcs = ["http_filter.cc"],
    hdrs = ["http_filter.h"],
    repository = "@envoy",
    deps = [
        ":pkg_cc_proto",
        "@envoy//source/extensions/filters/http/common:pass_through_filter_lib",
    ],
)

envoy_cc_library(
    name = "http_filter_config",
    srcs = ["http_filter_config.cc"],
    repository = "@envoy",
    deps = [
        ":http_filter_lib",
        "@envoy//envoy/registry",
        "@envoy//envoy/server:filter_config_interface",
        "@envoy//source/extensions/filters/http/common:factory_base_lib",
    ],
)

envoy_cc_binary(
    name = "envoy",
    repository = "@envoy",
    deps = [
        ":http_filter_config",
        "@envoy//source/exe:envoy_main_entry_lib",
    ],
)

envoy_cc_test(
    name = "http_filter_integration_test",
    srcs = ["http_filter_integration_test.cc"],
    repository = "@envoy",
    deps = [
        ":http_filter_config",
        "@envoy//test/integration:http_integration_lib",
    ],
)

filegroup(
    name = "files",
    srcs = glob(
        ["**/*"],
        exclude = [
            "**/*~",
            "**/.*",
            ".*/**/*",
            "bazel-*/**/*",
            "bin/**/*",
            "example.rst",
            "BUILD",
            "README.md",
        ],
    ) + ["//bazel/build_config:extensions_build_config.bzl"],
)

pkg_tar(
    name = "includes",
    srcs = [":files"],
    package_dir = "_include/filter-cc",
    visibility = ["//visibility:public"],
)
