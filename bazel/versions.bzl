VERSIONS = {
    "go": "1.24.9",
    "python": "3.12",
    "io_bazel_rules_go": {
        "type": "github_archive",
        "repo": "bazelbuild/rules_go",
        "version": "0.53.0",
        "sha256": "b78f77458e77162f45b4564d6b20b6f92f56431ed59eaaab09e7819d1d850313",
        "url": "https://github.com/bazelbuild/rules_go/releases/download/v{version}/rules_go-v{version}.zip",
    },
    "rules_pkg": {
        "type": "github_archive",
        "repo": "bazelbuild/rules_pkg",
        "version": "1.2.0",
        "sha256": "b5c9184a23bb0bcff241981fd9d9e2a97638a1374c9953bb1808836ce711f990",
        "url": "https://github.com/bazelbuild/rules_pkg/releases/download/{version}/rules_pkg-{version}.tar.gz",
    },
    "rules_python": {
        "type": "github_archive",
        "repo": "bazelbuild/rules_python",
        "version": "1.4.1",
        "sha256": "9f9f3b300a9264e4c77999312ce663be5dee9a56e361a1f6fe7ec60e1beef9a3",
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
}
