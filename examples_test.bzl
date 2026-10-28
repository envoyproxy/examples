load("@bazel_skylib//lib:unittest.bzl", "analysistest", "asserts")

def _exclusion_test_impl(ctx):
    env = analysistest.begin(ctx)
    target = analysistest.target_under_test(env)
    files = target[DefaultInfo].files
    paths = [f.short_path for f in files.to_list()]
    for included in ctx.attr.included:
        asserts.true(env, any([included in path for path in paths]), "Missing " + included)
    for excluded in ctx.attr.excluded:
        asserts.false(env, any([excluded in path for path in paths]), "Unexpected " + excluded)
    return analysistest.end(env)

_attrs = {
    "excluded": attr.string_list(),
    "included": attr.string_list(),
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

_CompatibilityInfo = provider(fields = ["constraints"])

def _compatibility_aspect_impl(_target, ctx):
    return [_CompatibilityInfo(
        constraints = [constraint.label for constraint in ctx.rule.attr.target_compatible_with],
    )]

_compatibility_aspect = aspect(implementation = _compatibility_aspect_impl)

def _incompatible_test_impl(ctx):
    env = analysistest.begin(ctx)
    target = analysistest.target_under_test(env)
    expected = [Label("@platforms//:incompatible")] if ctx.attr.expect_incompatible else []
    asserts.equals(env, expected, target[_CompatibilityInfo].constraints)
    return analysistest.end(env)

_inc_attrs = {"expect_incompatible": attr.bool()}
_inspection_settings = {
    "//command_line_option:platforms": [str(Label("//:example_exclusion_test_platform"))],
}
_default_inc_test = analysistest.make(
    _incompatible_test_impl,
    attrs = _inc_attrs,
    config_settings = _inspection_settings,
    extra_target_under_test_aspects = [_compatibility_aspect],
)
_multiple_inc_test = analysistest.make(
    _incompatible_test_impl,
    attrs = _inc_attrs,
    config_settings = dict(_inspection_settings, **{
        "//:exclude": ["ai-transcoder", "filter-cc", "wasm-cc", "brotli"],
    }),
    extra_target_under_test_aspects = [_compatibility_aspect],
)

def example_exclusion_test_suite(name):
    tests = []
    for target in ["configs", "docs_rst", "files"]:
        for mode, test_rule, included, excluded in [
            ("default", _default_test, ["brotli/", "ai-transcoder/"], []),
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

    for example, mode, test_rule, expect in [
        ("brotli", "default", _default_inc_test, False),
        ("ai-transcoder", "default", _default_inc_test, False),
        ("brotli", "multiple", _multiple_inc_test, True),
        ("ai-transcoder", "multiple", _multiple_inc_test, True),
        ("gzip", "multiple", _multiple_inc_test, False),
    ]:
        test_name = name + "_" + example + "_" + mode
        test_rule(
            name = test_name,
            target_under_test = ":%s_result" % example,
            expect_incompatible = expect,
        )
        tests.append(test_name)

    native.test_suite(
        name = name,
        tests = tests,
    )
