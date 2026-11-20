# Copilot review instructions — envoyproxy/examples

The examples in this repo are **documentation-first sandboxes**: each teaches a
released Envoy feature — or a combination of features toward one end (e.g. `single-page-app`) —
and `verify.sh` exists only so CI can prove the documented steps
still work. The authoritative guidelines are in `CONTRIBUTING.md`; this file is the review
rubric derived from them.

When reviewing a pull request that **adds or changes an example** — a top-level sandbox
directory with a docker-compose file, one or more Envoy configs, an `example.rst`, and a
`verify.sh` (exact filenames vary: e.g. `single-page-app` uses `docker-compose.yml` /
`envoy.yml`, `opentelemetry` uses `envoy-front-proxy.yaml` plus numbered proxy configs) —
assess it against the points below and raise anything that fails. Weight these over
generic style nits.

1. **Released feature only, with one bounded exception.** The feature must be in a
   *released* Envoy; the example's image and bzlmod module should be the last published
   version, not a dev snapshot. Flag `envoyproxy/envoy:dev` or a dependency on a filter/config
   not in a published release — EXCEPT for a new filter bound for the *next* release: there is
   no published container for it yet, so a `:dev` runtime image is acceptable there (to be
   repinned to the published image when the release ships), and if the example builds against
   the bazel module, that side pins an interim registry module, which counts as published.
2. **Stability, not the alpha label.** Do NOT flag an example merely for exemplifying an
   alpha/experimental filter — alpha is fine when the filter is stable in practice, provided
   the example carries a banner noting it is alpha and not covered by Envoy's security
   policy. DO flag a filter under active churn: frequent correctness fixes, config/behaviour
   changing release-to-release, or an example carrying workarounds for known, currently-open
   bugs (e.g. encoding open Envoy bugs as "known gaps"). That conformance testing belongs in
   Envoy's integration and fuzz tests. Acceptance of a still-evolving (but released) feature is a
   case-by-case maintainer decision — surface it for human judgement rather than approving
   or rejecting it outright, and note that keeping it working (shims for breaking Envoy
   changes, landed here first) is the contributor's burden.
3. **One sandbox per PR.** The unit is the sandbox, not the feature — a single example may
   combine features toward one end. Flag a PR that adds more than one sandbox (e.g. two
   separate `docker-compose.yaml` stacks). Ask for a split.
4. **Docs-first and 1:1 with `verify.sh`.** There must be an `example.rst` written as
   numbered human-followable Steps. Each documented Step that exercises Envoy must
   correspond to one `run_log "<step>"` block in `verify.sh`, and vice versa — flag
   verification logic with no documented step, or Envoy steps `verify.sh` does not check.
   Do NOT flag a documented external-service setup step permitted by the exception in
   point 7 (e.g. creating a GitHub OAuth app) for lacking a CI step: CI cannot perform real
   external setup and is expected to exercise that wiring against a mock/stub instead.
5. **Framework shape, no bespoke harness.** `verify.sh` must source `verify-common.sh` and
   use its helpers (`run_log`, `_curl`, `responds_with`/`responds_without`, `wait_for`)
   with `jq` assertions. Flag standalone test clients, `results.json`/report diffing,
   compliance/known-gap bookkeeping, or any parallel test framework.
6. **Ports: fixed container ports, framework-variable host bindings.** Fixed Envoy
   listener (container) ports in `envoy.yaml` are correct — do NOT flag them. But every
   *host-published* port must use the framework variable with a fixed default (e.g.
   `ports: ["${PORT_PROXY:-10000}:10000"]`) so CI can mask all host ports to reserved free
   ports and examples run in parallel without conflict. Flag a host-port publication whose
   host side is hardcoded with no `${PORT_…:-}` variable, and any `verify.sh`/docs request
   that uses a hardcoded host port instead of the resolved variable. The proxy's host port
   must be published so a reader can reach it; flag sealed `docker compose exec`-only setups
   with no published port.
7. **Self-contained.** Flag dependencies on third-party/external services (accounts, SaaS,
   live network). The sole exception is a real external-service hookup placed as an optional
   "next steps" section at the **very end**, after the Envoy feature is fully demonstrated
   and verified against a mock/stub and stands complete without it (e.g. GitHub OAuth in
   `single-page-app`). Flag it when the external hookup is woven into the Envoy
   demonstration rather than appended as reader next-steps, or when the example would not
   demonstrate the Envoy feature with the external service removed.
8. **Consistent with existing examples.** Take the existing sandboxes as the reference:
   flag an example that diverges noticeably from their established structure and conventions.
   The specifics are obvious from the other examples and need not be spelled out here.
