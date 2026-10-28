load("@rules_shell//shell:sh_test.bzl", "sh_test")

def envoy_example(name, shared = ":shared_files", common_fun = ":verify-common.sh"):
    native.filegroup(
        name = "%s_files" % name,
        srcs = native.glob(
            ["%s/**/*" % name],
            exclude = [
                "%s/**/node_modules/**" % name,
                "%s/**/dist/**" % name,
                "%s/**/target/**" % name,
            ],
        ),
    )

    native.genrule(
        name = "%s_dir" % name,
        outs = ["%s_dir.tar" % name],
        cmd = """
        read -ra SHARED_PATHS <<< "$(locations %s)"
        SHARED_DIR=$$(echo $${SHARED_PATHS[0]} | cut -d/ -f1)
        # This is a bit hacky and may not work in all bazel situations, but works for now
        if [[ $$SHARED_DIR == "external" ]]; then
            SHARED_DIR=$$(echo $${SHARED_PATHS[0]} | cut -d/ -f-3)
        fi
        EXAMPLE=%s
        read -ra EXAMPLE_PATHS <<< "$(locations %s_files)"
        EXAMPLE_DIR=$$(echo $${EXAMPLE_PATHS[0]} | cut -d/ -f1)
        # This is a bit hacky and may not work in all bazel situations, but works for now
        if [[ $$EXAMPLE_DIR == "external" ]]; then
            EXAMPLE_DIR=$$(echo $$EXAMPLE_PATHS | cut -d/ -f-3)
        fi
        TARGET_DIR=$$(dirname $$EXAMPLE_DIR)
        tar chf $@ -C $$TARGET_DIR --exclude="$$(basename "$@")" .
        """ % (shared, name, name),
        tools = [
            common_fun,
            shared,
            "%s_files" % name,
        ],
    )

def envoy_examples(examples):
    native.filegroup(
        name = "shared_files",
        srcs = native.glob(
            ["shared/**/*"],
            exclude = [
                "**/*~",
                "**/.*",
                "**/#*",
                ".*/**/*",
            ],
        ),
    )

    for example in examples:
        envoy_example(name = example, shared = ":shared_files")
        sh_test(
            name = "%s_result" % example,
            srcs = [":verify_example.sh"],
            args = [example, "$(location :%s_dir)" % example],
            data = [":%s_dir" % example],
            env = {"BUILDX_BAKE_ENTITLEMENTS_FS": "0"},
            tags = ["requires-docker", "no-sandbox", "no-remote-exec", "local"],
            size = "large",
            timeout = "long",
        )

    native.test_suite(
        name = "verify_examples",
        tests = [":%s_result" % example for example in examples],
    )
