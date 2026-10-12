load("@rules_shell//shell:sh_binary.bzl", "sh_binary")

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

    sh_binary(
        name = "verify_%s" % name,
        srcs = [":verify_example.sh"],
        args = [
            name,
            "$(location :%s_dir)" % name,
        ],
        data = [":%s_dir" % name],
    )

def envoy_examples(examples):
    RESULTS = []
    RESULT_OUTS = []
    RESULT_FILES = []
    MANIFEST_OUTS = []
    MANIFEST_FILES = []

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
        native.genrule(
            name = "%s_result" % example,
            outs = [
                "%s_result.txt" % example,
                "%s.ports.json" % example,
            ],
            cmd = """
                export PORT_MANIFEST_DIR=$$(mktemp -d)
                trap 'rm -rf "$$PORT_MANIFEST_DIR"' EXIT
                ./$(location :verify_%s) %s $(location :%s_dir) >> $(location :%s_result.txt)
                shopt -s nullglob
                manifests=("$$PORT_MANIFEST_DIR"/*.ports.json)
                if [[ $${#manifests[@]} -gt 0 ]]; then
                    jq -s --arg example %s 'add | map(.example = $$example)' \\
                        "$${manifests[@]}" > $(location :%s.ports.json)
                else
                    echo '[]' > $(location :%s.ports.json)
                fi
            """ % (example, example, example, example, example, example, example),
            tools = [
                "verify_%s" % example,
                "%s_dir" % example,
            ],
            tags = ["no-remote-exec", "no-sandbox"],
        )
        RESULTS.append(":%s_result" % example)
        RESULT_OUTS.append(":%s_result.txt" % example)
        RESULT_FILES.append("$(location :%s_result.txt)" % example)
        MANIFEST_OUTS.append(":%s.ports.json" % example)
        MANIFEST_FILES.append("$(location :%s.ports.json)" % example)

    sh_binary(
        name = "verify_examples",
        srcs = [":verify_examples.sh"],
        args = RESULT_FILES,
        data = RESULTS + RESULT_OUTS,
    )

    sh_binary(
        name = "check_example_ports",
        srcs = ["tools/check_port_manifests.sh"],
        args = MANIFEST_FILES,
        data = RESULTS + MANIFEST_OUTS,
    )
