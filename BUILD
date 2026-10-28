load("@aspect_bazel_lib//lib:jq.bzl", "jq")
load("@aspect_bazel_lib//lib:yq.bzl", "yq")
load("@bazel_skylib//rules:build_test.bzl", "build_test")
load("@bazel_skylib//rules:common_settings.bzl", "repeatable_string_flag")
load("@rules_pkg//pkg:mappings.bzl", "pkg_files")
load("@rules_pkg//pkg:pkg.bzl", "pkg_tar")
load("@rules_shell//shell:sh_test.bzl", "sh_test")
load("//:examples.bzl", "envoy_examples", "example_files")
load("//:examples_test.bzl", "example_exclusion_test_suite")

licenses(["notice"])  # Apache 2

# Examples to drop from docs, config validation and verification.
# Repeatable: `--@envoy-examples//:exclude=foo --@envoy-examples//:exclude=bar`
repeatable_string_flag(
    name = "exclude",
    build_setting_default = [],
    visibility = ["//visibility:public"],
)

# Excluding build tests - eg wasm - these should be run directly
EXAMPLE_TESTS = [
    "ai-transcoder",
    "brotli",
    "cache",
    "cors",
    "csrf",
    "double-proxy",
    # "dynamic-config-cp",
    "dynamic-config-fs",
    "dynamic-mod-rust",
    "ext_authz",
    # "fault-injection",
    "front-proxy",
    "golang-http",
    # "golang-network",
    "grpc-bridge",
    "gzip",
    "jaeger-tracing",
    "kafka",
    "kafka-mesh",
    "load-reporting-service",
    "locality-load-balancing",
    "local_ratelimit",
    "lua",
    "lua-cluster-specifier",
    "mysql",
    "opentelemetry",
    "postgres",
    "rbac",
    "redis",
    "route-mirror",
    "single-page-app",
    "skywalking",
    "tls",
    "tls-inspector",
    "tls-sni",
    "udp",
    "websocket",
    "zipkin",
    "zstd",
]

example_files(
    name = "configs",
    srcs = glob(
        [
            "**/*.yaml",
        ],
        exclude = [
            "cache/ci-responses.yaml",
            "cache/responses.yaml",
            "dynamic-config-fs/**/*",
            # The dynamic module is only built when the sandbox is run, so the
            # config cannot be validated with a stock Envoy binary.
            "dynamic-mod-rust/*.yaml",
            "jaeger-native-tracing/*",
            "opentelemetry/otel-collector-config.yaml",
            "**/*docker-compose*.yaml",
            # Contrib extensions tested over in contrib.
            "golang-http/*.yaml",
            "golang-network/*.yaml",
            "mysql/*",
            "postgres/*",
            "kafka/*.yaml",
            "kafka-mesh/*.yaml",
        ],
    ) + [
        "@envoy-example-filter-cc//:configs",
        "@envoy-example-wasm-cc//:configs",
    ],
    visibility = ["//visibility:public"],
)

filegroup(
    name = "contrib_configs",
    srcs = glob(
        [
            "golang-http/*.yaml",
            "golang-network/*.yaml",
            "mysql/*.yaml",
            "postgres/*.yaml",
            "kafka/*.yaml",
            "kafka-mesh/*.yaml",
        ],
        exclude = [
            "**/*docker-compose*.yaml",
        ],
    ),
    visibility = ["//visibility:public"],
)

filegroup(
    name = "certs",
    srcs = glob(["_extra_certs/*.pem"]),
    visibility = ["//visibility:public"],
)

example_files(
    name = "docs_rst",
    srcs = glob(["**/example.rst"]) + [
        "@envoy-example-filter-cc//:example.rst",
        "@envoy-example-wasm-cc//:example.rst",
    ],
)

pkg_files(
    name = "examples_files",
    srcs = [":files"],
    prefix = "_include",
    strip_prefix = "/",
)

genrule(
    name = "examples_docs",
    srcs = [":docs_rst"],
    outs = ["examples_docs.tar.gz"],
    cmd = """
    TEMP=$$(mktemp -d)
    for location in $(locations :docs_rst); do
        if [[ "$$location" == *filter-cc* ]]; then
            example="filter-cc"
        elif [[ "$$location" == *wasm-cc* ]]; then
            example="wasm-cc"
        else
            example="$$(basename "$$(dirname "$$location")")"
        fi
        cp -aL "$$location" "$${TEMP}/$${example}.rst"
        echo "    $${example}" >> "$${TEMP}/_toctree.rst"
    done
    echo ".. toctree::" > "$${TEMP}/toctree.rst"
    echo "    :maxdepth: 1" >> "$${TEMP}/toctree.rst"
    echo "" >> "$${TEMP}/toctree.rst"
    cat "$${TEMP}/_toctree.rst" | sort >> "$${TEMP}/toctree.rst"
    rm "$${TEMP}/_toctree.rst"
    tar chzf $@ -C $${TEMP} .
    """,
)

filegroup(
    name = "lua",
    srcs = glob(["**/*.lua"]),
    visibility = ["//visibility:public"],
)

example_files(
    name = "files",
    srcs = glob(
        ["**/*"],
        exclude = [
            "**/*~",
            "**/.*",
            "**/#*",
            ".*/**/*",
            "BUILD",
            "README.md",
            "WORKSPACE",
            "bazel-*/**/*",
            "**/node_modules/**",
            "**/target/**",
            "**/*.rst",
            "win32*",
        ],
    ),
)

pkg_tar(
    name = "docs",
    srcs = [":examples_files"],
    extension = "tar.gz",
    package_dir = "start/sandboxes",
    deps = [
        ":examples_docs",
        "@envoy-example-filter-cc//:includes",
        "@envoy-example-wasm-cc//:includes",
    ],
    visibility = ["//visibility:public"],
)

yq(
    name = "compose_ports_json",
    srcs = glob(
        [
            "*/docker-compose*.y*ml",
            "*/*/docker-compose*.y*ml",
        ],
        exclude = ["**/node_modules/**"],
    ) + [
        "@envoy-example-filter-cc//:compose_files",
        "@envoy-example-wasm-cc//:compose_files",
    ],
    expression = '{"file": filename, "config": .} as $item ireduce ({}; . * {($item.file): $item.config})',
    args = ["-o=json"],
)

jq(
    name = "lint_ports_check",
    srcs = [":compose_ports_json"],
    filter_file = "tools/lint_ports.jq",
)

build_test(
    name = "lint_ports",
    targets = [":lint_ports_check"],
)

sh_test(
    name = "port_collision_test",
    srcs = ["tools/port_collision_test.sh"],
    args = ["$(location :gzip_dir)"],
    data = [":gzip_dir"],
    env = {"BUILDX_BAKE_ENTITLEMENTS_FS": "0"},
    tags = ["manual", "requires-docker", "no-sandbox", "no-remote-exec"],
    timeout = "long",
)

sh_test(
    name = "port_harness_test",
    srcs = ["tools/port_harness_test.sh"],
    args = ["$(location :compose_ports_json)"],
    data = [
        ":compose_ports_json",
        "verify-common.sh",
        "tools/check_port_manifests.sh",
        "tools/lint_ports.jq",
    ],
)

envoy_examples(
    examples = EXAMPLE_TESTS,
)

example_exclusion_test_suite(name = "example_exclusion_tests")
