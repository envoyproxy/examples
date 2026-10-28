load("@bazel_skylib//rules:common_settings.bzl", "BuildSettingInfo")
load("@rules_shell//shell:sh_binary.bzl", "sh_binary")

def _example_name(f):
    workspace = f.owner.workspace_name
    if "envoy-example-" in workspace:
        return workspace.split("envoy-example-", 1)[1].split("~", 1)[0].split("+", 1)[0]
    return f.owner.name.split("/")[0]

def _example_files_impl(ctx):
    excluded = ctx.attr._exclude[BuildSettingInfo].value
    return [DefaultInfo(files = depset([
        f
        for f in ctx.files.srcs
        if _example_name(f) not in excluded
    ]))]

example_files = rule(
    implementation = _example_files_impl,
    attrs = {
        "srcs": attr.label_list(allow_files = True),
        "_exclude": attr.label(default = Label("//:exclude")),
    },
)

def _example_runner_impl(ctx):
    excluded = ctx.attr._exclude[BuildSettingInfo].value
    inputs = [
        f
        for target, example in ctx.attr.outputs.items()
        if example not in excluded
        for f in target[DefaultInfo].files.to_list()
        if f.basename.endswith(ctx.attr.suffix)
    ]
    out = ctx.actions.declare_file(ctx.label.name + ".txt")
    ctx.actions.run_shell(
        inputs = inputs + [ctx.file.runner],
        outputs = [out],
        command = '"$1" "${@:3}" 2>&1 | tee "$2"; exit "${PIPESTATUS[0]}"',
        arguments = [ctx.file.runner.path, out.path] + [f.path for f in inputs],
        mnemonic = "ExampleRunner",
        progress_message = "Running %s" % ctx.label.name,
        execution_requirements = {"no-remote-exec": "1", "no-cache": "1"},
    )
    return [DefaultInfo(files = depset([out]))]

example_runner = rule(
    implementation = _example_runner_impl,
    attrs = {
        "outputs": attr.label_keyed_string_dict(allow_files = True),
        "runner": attr.label(allow_single_file = True),
        "suffix": attr.string(mandatory = True),
        "_exclude": attr.label(default = Label("//:exclude")),
    },
)

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

    results = {":%s_result" % example: example for example in examples}

    example_runner(
        name = "verify_examples",
        runner = ":verify_examples.sh",
        outputs = results,
        suffix = "_result.txt",
    )

    example_runner(
        name = "check_example_ports",
        runner = "tools/check_port_manifests.sh",
        outputs = results,
        suffix = ".ports.json",
    )
