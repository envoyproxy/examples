load("@bazel_skylib//lib:selects.bzl", "selects")
# load("@envoy//bazel/wasm:wasm.bzl", "envoy_wasm_cc_binary")

licenses(["notice"])  # Apache 2

exports_files(["example.rst"])

selects.config_setting_group(
    name = "include_wasm_config",
    match_all = [
        "//bazel:x86",
        "//bazel:wasm_v8",
    ],
)

filegroup(
    name = "configs",
    srcs = glob([
        "**/*.wasm",
    ]) + select({
        ":include_wasm_config": glob(
            [
                "**/*.yaml",
            ],
            exclude = [
                "**/*docker-compose*.yaml",
            ],
        ),
        "//conditions:default": [],
    }),
    visibility = ["//visibility:public"],
)

# envoy_wasm_cc_binary(
#     name = "envoy_filter_http_wasm_example.wasm",
#     srcs = ["envoy_filter_http_wasm_example.cc"],
# )

# envoy_wasm_cc_binary(
#     name = "envoy_filter_http_wasm_updated_example.wasm",
#     srcs = ["envoy_filter_http_wasm_updated_example.cc"],
# )

filegroup(
    name = "files",
    srcs = glob(["**/*"], exclude = ["example.rst", "BUILD"]),
    visibility = ["//visibility:public"],
)
