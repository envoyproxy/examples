
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

    "bazel_features": {
        "type": "github_archive",
        "repo": "bazel-contrib/bazel_features",
        "version": "1.51.0",
        "sha256": "5450bfb2c8b4bc961c75368838f86156f563cc9adef1be7d504fc5619d54daab",
        "url": "https://github.com/{repo}/releases/download/v{version}/{name}-v{version}.tar.gz",
        "strip_prefix": "{name}-{version}",
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
        "version": "1.39.0",
        "sha256": "a6c5b2af8387f7e9eb953d5ea66d61a57ecb1c2bef698ef154631092195b84b7",
        "url": "https://github.com/{repo}/archive/refs/tags/v{version}.tar.gz",
        "strip_prefix": "envoy-{version}",
    },

    "envoy_toolshed": {
        "type": "github_archive",
        "repo": "envoyproxy/toolshed",
        "version": "0.4.0",
        "sha256": "71b0b8ca1e230e624577ec74989c9b855acbeff9696d7398ab476bfbbadf854c",
        "url": "https://github.com/{repo}/archive/bazel-v{version}.tar.gz",
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
        "version": "f2db56af443571e92a31c0b877106d9ea96e19ef",
        "sha256": "34dac5bcebf0b156e435bf8dd9bdac5be60b95f967c420c680578d73af28c604",
        "strip_prefix": "proxy-wasm-cpp-host-{version}",
        "url": "https://github.com/proxy-wasm/proxy-wasm-cpp-host/archive/{version}.tar.gz",
        "patch_args": ["-p1"],
        "patches": ["@envoy//bazel:proxy_wasm_cpp_host.patch"],
    },

    "proxy_wasm_cpp_sdk": {
        "type": "github_archive",
        "repo": "proxy-wasm/proxy-wasm-cpp-sdk",
        "version": "e5256b0c5463ea9961965ad5de3e379e00486640",
        "sha256": "b560a1da27a0d3ab374527e9c7dfa4fe6493887299945be2762a0518ce35570e",
        "strip_prefix": "proxy-wasm-cpp-sdk-{version}",
        "url": "https://github.com/proxy-wasm/proxy-wasm-cpp-sdk/archive/{version}.tar.gz",
    },

    "rules_cc": {
        "type": "github_archive",
        "repo": "bazelbuild/rules_cc",
        "version": "0.2.22",
        "sha256": "81c10a95a5c22d838276ee90d712635d6042419fdfca5ef88328226b6321e53b",
        "url": "https://github.com/{repo}/releases/download/{version}/{name}-{version}.tar.gz",
        "strip_prefix": "{name}-{version}",
    },

    "rules_foreign_cc": {
        "type": "github_archive",
        "repo": "bazelbuild/rules_foreign_cc",
        "version": "0.15.1",
        "sha256": "32759728913c376ba45b0116869b71b68b1c2ebf8f2bcf7b41222bc07b773d73",
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

    "rules_java": {
        "type": "github_archive",
        "repo": "bazelbuild/rules_java",
        "version": "9.7.0",
        "sha256": "68794ca344c1caf13dca65f90c06660823013fa080931266e2625103904a664e",
        "url": "https://github.com/{repo}/releases/download/{version}/rules_java-{version}.tar.gz",
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
        "patch_args": ["-p1"],
        "patches": ["@envoy//bazel:rules_python.patch"],
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
        "version": "1.8.0",
        "sha256": "3b05826f256040f91c24dcaad673eb1c91e4cc93f4043d0205f2512327640205",
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
