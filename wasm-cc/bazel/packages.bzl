load("@com_google_protobuf//bazel/private:proto_bazel_features.bzl", "proto_bazel_features")
load("@emsdk//:emscripten_deps.bzl", "emscripten_deps")
load("@envoy//bazel:repositories.bzl", "default_envoy_build_config")
load("@rules_fuzzing//fuzzing:repositories.bzl", "rules_fuzzing_dependencies")
load("@rules_python//python:pip.bzl", "pip_parse")
load("//bazel:versions.bzl", "VERSIONS")

def load_envoy_example_wasmcc_packages():
    # This is empty - it should be overridden in your repo
    pip_parse(
        name = "toolshed_pip3",
        requirements_lock = "@envoy_toolshed//:requirements.txt",
        python_interpreter_target = "@python3_12_host//:python",
    )
    emscripten_deps(emscripten_version = "4.0.6")
    default_envoy_build_config(name = "envoy_build_config")
    proto_bazel_features(name = "proto_bazel_features")
    rules_fuzzing_dependencies(
        oss_fuzz = True,
        honggfuzz = False,
    )
