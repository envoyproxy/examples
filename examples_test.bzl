load("@bazel_skylib//lib:unittest.bzl", "analysistest", "asserts")

def _exclusion_test_impl(ctx):
    env = analysistest.begin(ctx)
    target = analysistest.target_under_test(env)
    files = target[DefaultInfo].default_runfiles.files if ctx.attr.runfiles else target[DefaultInfo].files
    paths = [f.short_path for f in files.to_list()]
    for included in ctx.attr.included:
        asserts.true(env, any([included in path for path in paths]), "Missing " + included)
    for excluded in ctx.attr.excluded:
        asserts.false(env, any([excluded in path for path in paths]), "Unexpected " + excluded)
    return analysistest.end(env)

_attrs = {
    "excluded": attr.string_list(),
    "included": attr.string_list(),
    "runfiles": attr.bool(),
}

_default_test = analysistest.make(_exclusion_test_impl, attrs = _attrs)
_empty_test = analysistest.make(
    _exclusion_test_impl,
    attrs = _attrs,
    config_settings = {"//:exclude": [""]},
)
_multiple_test = analysistest.make(
    _exclusion_test_impl,
    attrs = _attrs,
    config_settings = {"//:exclude": ["ai-transcoder", "filter-cc", "wasm-cc", "brotli"]},
)
_comma_test = analysistest.make(
    _exclusion_test_impl,
    attrs = _attrs,
    config_settings = {"//:exclude": ["ai-transcoder,brotli"]},
)

def example_exclusion_test_suite(name):
    tests = []
    for target in ["configs", "docs_rst", "files"]:
        for mode, test_rule, included, excluded in [
            ("default", _default_test, ["brotli/"], ["ai-transcoder/"]),
            ("empty", _empty_test, ["brotli/", "ai-transcoder/"], []),
        ]:
            test_name = name + "_" + target + "_" + mode
            test_rule(
                name = test_name,
                target_under_test = ":" + target,
                included = included + (["envoy-example-filter-cc", "envoy-example-wasm-cc"] if target == "docs_rst" else []),
                excluded = excluded,
            )
            tests.append(test_name)

    test_name = name + "_external"
    _multiple_test(
        name = test_name,
        target_under_test = ":docs_rst",
        included = ["gzip/"],
        excluded = ["ai-transcoder/", "brotli/", "envoy-example-filter-cc", "envoy-example-wasm-cc"],
    )
    tests.append(test_name)

    for target, suffix, other_suffix, runner in [
        ("verify_examples", "_result.txt", ".ports.json", "verify_examples_sh"),
        ("check_example_ports", ".ports.json", "_result.txt", "check_example_ports_sh"),
    ]:
        for mode, test_rule, included, excluded in [
            ("default", _default_test, ["brotli" + suffix], ["ai-transcoder" + suffix]),
            ("empty", _empty_test, ["brotli" + suffix, "ai-transcoder" + suffix], []),
            ("multiple", _multiple_test, ["gzip" + suffix], ["brotli" + suffix, "ai-transcoder" + suffix]),
            ("comma", _comma_test, ["brotli" + suffix, "ai-transcoder" + suffix], []),
        ]:
            test_name = name + "_" + target + "_" + mode
            test_rule(
                name = test_name,
                target_under_test = ":" + target,
                runfiles = True,
                included = included + [runner],
                excluded = excluded + [other_suffix],
            )
            tests.append(test_name)

    native.test_suite(
        name = name,
        tests = tests,
    )
