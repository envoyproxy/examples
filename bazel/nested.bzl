
def _example_repo_impl(ctx):
    example_path = ctx.path(ctx.attr.examples_root).dirname.get_child(ctx.attr.path)

    # Read directory contents
    result = ctx.execute(["ls", "-A", str(example_path)])
    if result.return_code != 0:
        fail("Failed to list directory: " + result.stderr)

    files = [f for f in result.stdout.strip().split("\n") if f]

    for f in files:
        ctx.symlink(example_path.get_child(f), f)

example_repository = repository_rule(
    implementation = _example_repo_impl,
    attrs = {
        "examples_root": attr.label(default = "@envoy_examples//:BUILD"),
        "path": attr.string(mandatory=True),
    },
)

def load_envoy_nested_examples():
    example_repository(
        name = "envoy-example-wasmcc",
        path = "wasm-cc",
    )
    example_repository(
        name = "envoy-example-http-filter-cc",
        path = "http-filter-cc",
    )
