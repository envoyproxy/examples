load("@bazel_tools//tools/build_defs/repo:http.bzl", "http_archive")
load("//bazel:versions.bzl", "VERSIONS")

def load_github_archives():
    for k, v in VERSIONS.items():
        if type(v) == type("") or v.get("type") != "github_archive":
            continue
        kwargs = dict(name = k, **v)
        # Format string values, but not lists
        formatted_kwargs = {}
        for arg_k, arg_v in kwargs.items():
            if arg_k in ["repo", "type", "version"]:
                continue
            if type(arg_v) == type(""):
                formatted_kwargs[arg_k] = arg_v.format(**kwargs)
            else:
                formatted_kwargs[arg_k] = arg_v
        http_archive(**formatted_kwargs)

def load_http_archives():
    for k, v in VERSIONS.items():
        if type(v) == type("") or v.get("type") != "http_archive":
            continue
        kwargs = dict(name = k, **v)
        # Format string values, but not lists
        formatted_kwargs = {}
        for arg_k, arg_v in kwargs.items():
            if arg_k in ["type", "version"]:
                continue
            if type(arg_v) == type(""):
                formatted_kwargs[arg_k] = arg_v.format(**kwargs)
            else:
                formatted_kwargs[arg_k] = arg_v
        http_archive(**formatted_kwargs)

def load_envoy_examples_archives():
    load_github_archives()
    load_http_archives()
