load("@bazel_skylib//rules:common_settings.bzl", "BuildSettingInfo")
load("@rules_shell//shell:sh_test.bzl", "sh_test")

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
        native.config_setting(
            name = "%s_excluded" % example,
            flag_values = {"//:exclude": example},
        )
        sh_test(
            name = "%s_result" % example,
            srcs = [":verify_example.sh"],
            args = [
                example,
                "$(location :%s_dir)" % example,
                "$(rootpath tools/check_port_manifests.sh)",
            ],
            data = [
                ":%s_dir" % example,
                "tools/check_port_manifests.sh",
            ],
            env = {"BUILDX_BAKE_ENTITLEMENTS_FS": "0"},
            tags = ["requires-docker", "no-sandbox", "no-remote-exec", "local", "external"],
            size = "large",
            timeout = "long",
            target_compatible_with = select({
                ":%s_excluded" % example: ["@platforms//:incompatible"],
                "//conditions:default": [],
            }),
        )

    native.test_suite(
        name = "verify_examples",
        tests = [":%s_result" % example for example in examples],
    )
