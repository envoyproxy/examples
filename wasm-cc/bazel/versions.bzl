
VERSIONS = {
    "cmake": "3.23.2",
    "go": "1.24.9",
    "llvm": "18.1.8",
    "ninja": "1.12.0",
    "python": "3.12",

    "aspect_bazel_lib": {
        "type": "github_archive",
        "repo": "aspect-build/bazel-lib",
        "version": "2.16.0",
        "sha256": "092f841dd9ea8e736ea834f304877a25190a762d0f0a6c8edac9f94aac8bbf16",
        "strip_prefix": "bazel-lib-{version}",
        "url": "https://github.com/{repo}/archive/v{version}.tar.gz",
    },

    "bazel_skylib": {
        "type": "github_archive",
        "repo": "bazelbuild/bazel-skylib",
        "version": "1.9.2",
        "sha256": "37cdfbc6faefea94f7b37760a305c98c08981116c2bc9e821e3b423221fad8c8",
        "url": "https://github.com/{repo}/releases/download/{version}/bazel-skylib-{version}.tar.gz",
    },

    "com_github_grpc_grpc": {
        "type": "github_archive",
        "repo": "grpc/grpc",
        "version": "1.72.0",
        "sha256": "4a8aa99d5e24f80ea6b7ec95463e16af5bd91aa805e26c661ef6491ae3d2d23c",
        "strip_prefix": "grpc-{version}",
        "url": "https://github.com/{repo}/archive/v{version}.tar.gz",
    },

    "emsdk": {
        "type": "github_archive",
        "repo": "emscripten-core/emsdk",
        "strip_prefix": "emsdk-{version}/bazel",
        "version": "4.0.6",
        "sha256": "2d3292d508b4f5477f490b080b38a34aaefed43e85258a1de72cb8dde3f8f3af",
        "url": "https://github.com/emscripten-core/emsdk/archive/refs/tags/{version}.tar.gz",
        "patch_args": ["-p2"],
        "patches": ["@envoy//bazel:emsdk.patch"],
    },

    "envoy": {
        "type": "github_archive",
        "repo": "envoyproxy/envoy",
        "version": "b230d0459019af6fd27d0f0dbbf896d73cb6695b",
        "sha256": "b5a5758000f89712fb6cd9ad914615305790ab301aa0f8c073306501d67c1e91",
        "url": "https://github.com/{repo}/archive/{version}.tar.gz",
        "strip_prefix": "envoy-{version}",
    },

    "envoy_toolshed": {
        "type": "github_archive",
        "repo": "envoyproxy/toolshed",
        "version": "0.3.34",
        "sha256": "4bcf8ea8ca52fe27287b42fd10f01fb9d99b0c76c58383a8fbdaa33c4a6b2713",
        "url": "https://github.com/{repo}/archive/bazel-v{version}.tar.gz",
        "patch_args": ["-p1"],
        "strip_prefix": "toolshed-bazel-v{version}/bazel",
    },

    "io_bazel_rules_go": {
        "type": "github_archive",
        "repo": "bazelbuild/rules_go",
        "version": "0.61.1",
        "sha256": "763f4a3f6b03469fdb00a77a333dd0b5546d3ee1fa29db373128c08fee73e0e8",
        "url": "https://github.com/bazelbuild/rules_go/releases/download/v{version}/rules_go-v{version}.zip",
    },

    "platforms": {
        "type": "github_archive",
        "repo": "bazelbuild/platforms",
        "version": "1.1.0",
        "sha256": "324f5381753a610e472f79563d44e2026438195042aae4dc660b8c021f7de7f5",
        "url": "https://github.com/{repo}/archive/{version}.tar.gz",
        "strip_prefix": "platforms-{version}",
    },

    "proxy_wasm_cpp_host": {
        "type": "github_archive",
        "repo": "proxy-wasm/proxy-wasm-cpp-host",
        "version": "c4d7bb0fda912e24c64daf2aa749ec54cec99412",
        "sha256": "3ea005e85d2b37685149c794c6876fd6de7f632f0ad49dc2b3cd580e7e7a5525",
        "strip_prefix": "proxy-wasm-cpp-host-{version}",
        "url": "https://github.com/proxy-wasm/proxy-wasm-cpp-host/archive/{version}.tar.gz",
        "patch_args": ["-p1"],
        "patches": ["@envoy//bazel:proxy_wasm_cpp_host.patch"],
    },

    "proxy_wasm_cpp_sdk": {
        "type": "github_archive",
        "repo": "proxy-wasm/proxy-wasm-cpp-sdk",
        "version": "dc4f37efacd2ff7bf2e8f36632f22e1e99347f3e",
        "sha256": "487aef94e38eb2b717eb82aa5e3c7843b7da0c8b4624a5562c969050a1f3fa33",
        "strip_prefix": "proxy-wasm-cpp-sdk-{version}",
        "url": "https://github.com/proxy-wasm/proxy-wasm-cpp-sdk/archive/{version}.tar.gz",
    },

    "rules_cc": {
        "type": "github_archive",
        "repo": "bazelbuild/rules_cc",
        "version": "0.1.1",
        "sha256": "712d77868b3152dd618c4d64faaddefcc5965f90f5de6e6dd1d5ddcd0be82d42",
        "url": "https://github.com/{repo}/releases/download/{version}/rules_cc-{version}.tar.gz",
        "strip_prefix": "{name}-{version}",
    },

    "rules_foreign_cc": {
        "type": "github_archive",
        "repo": "bazelbuild/rules_foreign_cc",
        "version": "0.14.0",
        "sha256": "e0f0ebb1a2223c99a904a565e62aa285bf1d1a8aeda22d10ea2127591624866c",
        "url": "https://github.com/{repo}/releases/download/{version}/{name}-{version}.tar.gz",
        "strip_prefix": "{name}-{version}",
    },

    "rules_fuzzing": {
        "type": "github_archive",
        "repo": "bazelbuild/rules_fuzzing",
        "version": "0.5.3",
        "sha256": "08274422c4383416df5f982943e40d58141f749c09008bb780440eece6b113e4",
        "url": "https://github.com/{repo}/archive/v{version}.tar.gz",
        "strip_prefix": "{name}-{version}",
    },

    "rules_perl": {
        "type": "github_archive",
        "repo": "bazel-contrib/rules_perl",
        "version": "0.4.1",
        "sha256": "e09ba7ab6a52059a5bec71cf9a8a5b4e512c8592eb8d15af94ed59e048a2ec6d",
        "url": "https://github.com/{repo}/archive/refs/tags/{version}.tar.gz",
        "strip_prefix": "{name}-{version}",
    },

    "rules_pkg": {
        "type": "github_archive",
        "repo": "bazelbuild/rules_pkg",
        "version": "1.2.0",
        "sha256": "b5c9184a23bb0bcff241981fd9d9e2a97638a1374c9953bb1808836ce711f990",
        "url": "https://github.com/bazelbuild/rules_pkg/releases/download/{version}/rules_pkg-{version}.tar.gz",
    },

    "rules_proto_grpc": {
        "type": "github_archive",
        "repo": "rules-proto-grpc/rules_proto_grpc",
        "version": "4.6.0",
        "sha256": "2a0860a336ae836b54671cbbe0710eec17c64ef70c4c5a88ccfd47ea6e3739bd",
        "url": "https://github.com/{repo}/releases/download/{version}/rules_proto_grpc-{version}.tar.gz",
        "strip_prefix": "{name}-{version}",
    },

    "rules_python": {
        "type": "github_archive",
        "repo": "bazelbuild/rules_python",
        "version": "2.2.0",
        "sha256": "e11d2e1efce1589e5bdfa93986712c74fc7467a0f093143d489d2ef5ebb1ed2a",
        "url": "https://github.com/{repo}/releases/download/{version}/{name}-{version}.tar.gz",
        "strip_prefix": "{name}-{version}",
    },

    "rules_shell": {
        "type": "github_archive",
        "repo": "bazelbuild/rules_shell",
        "version": "0.8.0",
        "sha256": "20721f63908879c083f94869e618ea8d4ff5edb91ff9a72a2ebee357fdbc352d",
        "url": "https://github.com/{repo}/releases/download/v{version}/{name}-v{version}.tar.gz",
        "strip_prefix": "{name}-{version}",
    },

    "toolchains_llvm": {
        "type": "github_archive",
        "repo": "bazel-contrib/toolchains_llvm",
        "version": "1.4.0",
        "sha256": "fded02569617d24551a0ad09c0750dc53a3097237157b828a245681f0ae739f8",
        "url": "https://github.com/{repo}/releases/download/v{version}/{name}-v{version}.tar.gz",
        "strip_prefix": "{name}-v{version}",
    },

    "rules_rust": {
        "type": "github_archive",
        "repo": "bazelbuild/rules_rust",
        "version": "0.69.0",
        "sha256": "bbc764c252d061281b2359277a4d46480e2dcfaf72afc1ce6e00ada58ccbfd4c",
        "url": "https://github.com/bazelbuild/rules_rust/releases/download/{version}/rules_rust-{version}.tar.gz",
    },
}
