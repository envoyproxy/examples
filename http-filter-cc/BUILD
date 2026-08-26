load("@envoy//bazel:envoy_build_system.bzl", "envoy_cc_binary", "envoy_cc_library")
load("@envoy_api//bazel:api_build_system.bzl", "api_proto_package")
load("@rules_pkg//pkg:pkg.bzl", "pkg_tar")

licenses(["notice"])  # Apache 2

package(default_visibility = ["//visibility:public"])

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
        "@envoy//envoy/server:filter_config_interface",
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

filegroup(
    name = "files",
    srcs = glob(
        ["**/*"],
        exclude = [
            "**/*~",
            "**/.*",
            ".*/**/*",
            "BUILD",
            "README.md",
            "WORKSPACE",
        ],
    ),
)

pkg_tar(
    name = "includes",
    srcs = [":files"],
    package_dir = "_include/http-filter-cc",
    visibility = ["//visibility:public"],
)
