# Contributing an example

Examples in this repo are **documentation first**. Each one teaches a released Envoy
feature — or a combination of features toward one end — through a runnable sandbox. The documentation — the reader following the
steps by hand — is the product; everything else exists to serve and protect it.

## What qualifies

- **The feature is in a released Envoy.** This repo stores examples for features Envoy
  *supports*: the example pins the last *published* Envoy image (and, for `filter-cc` /
  `wasm-cc`, the published bzlmod module), not `envoyproxy/envoy:dev`. There is one bounded
  exception — a new filter headed for the next release — covered under **Keeping an example
  working**, below.
- **Stability matters, not the "alpha" label.** An alpha or experimental filter is *not*
  excluded for being alpha — many have been stable in practice for years, and such a filter
  may be exemplified (with a banner — see **Keeping an example working**). What *is* excluded
  is a filter under active churn: one still taking frequent correctness fixes, whose
  config/behaviour changes release-to-release, or where the example would carry workarounds
  for currently-open bugs. That is a conformance suite, not an example — it belongs in
  Envoy's integration and fuzz tests.
- **One sandbox, one PR.** A single example may combine features toward one end; the unit
  is the sandbox, not the feature. Don't bundle two separate sandboxes in one PR — split
  them, so each lands when it's ready.

## Docs first

- Every example has an `example.rst` that renders into Envoy's documentation under
  `/start/sandboxes/`. Write it as numbered **Steps** (`Step 1: Start the sandbox`,
  `Step 2: …`), each showing the exact command and the expected output, written for a human
  to run by hand.
- The Envoy config being demonstrated (`envoy.yaml`, or whatever the sandbox names it) is the
  star of the example. Keep everything around it minimal.
- Any screenshots live in the example's own `_static/` directory (e.g.
  `zipkin/_static/…png`); they are bundled into the docs automatically. Prefer text output
  over screenshots where you can — it is reproducible and nothing to maintain.

## `verify.sh` is CI-only, and mirrors the docs

- `verify.sh` is **not the example** — it exists only so CI can prove the documented steps
  still work. A reader never runs it.
- It must track the docs **one-to-one**: each documented Step that exercises Envoy maps to
  one `run_log "<that step>"` block that runs the step's command and asserts the documented
  result, and no verification runs a step the docs don't show. One exception: a permitted
  external-service setup step (see **Third-party / external services**) is documented for the
  reader but cannot run in CI, which has no real external accounts — `verify.sh` exercises
  that wiring against a mock/stub instead of reproducing the manual setup.
- Use the `verify-common.sh` framework — `run_log`, `_curl`, `responds_with` /
  `responds_without`, `wait_for`, asserted with `jq`. Keep it short and readable (see
  `ai-transcoder`).
- **No bespoke test harness.** No standalone test clients, `results.json` diffing,
  conformance/compliance matrices, or known-gap bookkeeping. That is a regression suite, not
  an example.

## Mechanics

- **Fixed ports, masked in CI — via the framework variable.** Envoy listener (container)
  ports in `envoy.yaml` are fixed, and that is correct. Publish each *host* port through the
  framework variable with that port as the default — `ports: ["${PORT_PROXY:-10000}:10000"]`
  — so the docs and end users get a stable `localhost:10000`, while CI reserves a free host
  port and overrides the variable. You only declare the mapping and the default; the
  framework does the masking, so examples run in parallel without colliding. `verify.sh` and
  the docs use the resolved variable (`$PORT_PROXY`), never a hardcoded host port.
- **Publish the proxy port.** A reader must be able to bring the sandbox up and reach it
  (`curl localhost:$PORT_PROXY/…`). A sealed rig that only talks to itself over the compose
  network via `docker compose exec` is not an example.
- **Self-contained.** Mock or stub any upstreams so the sandbox runs offline and
  deterministically in CI.
- **Add the example to `EXAMPLE_TESTS`** in `BUILD` so CI runs it.

## Third-party / external services

- **Generally not allowed.** Examples must be self-contained — no dependence on external
  accounts, SaaS, or network availability.
- **Narrow exception — and it is genuinely exceptional.** An example may point the reader at
  wiring up a real external service (e.g. `single-page-app` and GitHub OAuth), but only as an
  optional **"next steps"** section at the very end — after the Envoy feature has been fully
  demonstrated and verified against a mock/stub and stands complete on its own. The external
  hookup must **never be part of demonstrating how Envoy works**: it is reader follow-on, not
  the demonstration. If removing it would leave the example not actually demonstrating the
  Envoy feature, or the example is mainly a mock-OAuth/backend wiring demo, it doesn't belong
  here.

## Keeping an example working — the version cycle

An example pins and ships the **last published** Envoy. Envoy's own `verify_examples` job
runs the examples against Envoy **`main`** (via a local override of this checkout), so each
side tests a *different* Envoy: examples = the published release (what the example ships),
envoy = `main` (early warning that a change is about to break an example). `verify_examples`
is **advisory** — it goes red, it does not hard-block an Envoy PR — but a red example is the
standing expectation that the Envoy change waits until the example is accommodated.

**Docs and `verify.sh` track `main`.** When a change on `main` alters what an example shows —
an endpoint that returned `foo` now returns `bar` — update the docs and `verify.sh` to match
`main` promptly, so drift doesn't accumulate. The published release is what ultimately has to
be right; tracking `main` continuously is what makes each release's docs already correct by
the time `main` becomes that release.

**The shim dance** — when an Envoy `main` change would break an example that still builds
against the published release:

1. **examples PR first** — make the example work against *both* the published release and
   `main` (the shim).
2. **envoy PR** — make the change; `verify_examples` is now green because the example already
   handles the new behaviour.
3. **examples PR later** — once the change is in a published release, drop the shim, move the
   example to the new behaviour only, and repin to the released version.

`verify_examples` picks the shim up through its local override, so **no registry publish is
needed in the normal case**. Publish an **interim registry module** only when the fix must
exist as a registry version before the normal publish cadence. #1640 is the full runbook. The
upkeep is the contributor's — a filter that changes often means doing this dance often, which
is the real cost of exemplifying something still in motion.

**A new filter headed for the next release** can be exemplified ahead of it, as a bounded
exception. There is no published *container* for a brand-new filter yet, so the runtime image
is `envoyproxy/envoy:dev` until the release ships (repin to the published image when it
lands). If the example builds against the bazel module, publish an **interim registry module**
so that side pins a *published* module. It goes in `EXAMPLE_TESTS` like any other example
and is tested against `:dev` until the release, then repinned to the published image.

**Banners for alpha.** A stable-in-practice alpha filter is exemplified with a banner: an
`.. warning::` near the top of `example.rst` noting the filter is alpha and not covered by
Envoy's security policy. Accepting a still-churning feature at all is a case-by-case
maintainer decision. The line held firmly: never exemplify a feature that is not stable
enough to *stay* in a release — a filter that ships in a release and is yanked days later is
exactly what this avoids.

## Checklist

- [ ] Feature is in a released Envoy; image/module is the published one — or, for a new
      filter headed to the next release, `:dev` + an interim module, per the version cycle.
- [ ] Filter is stable (not under active correctness churn); if alpha, it carries a banner.
- [ ] One sandbox, one PR.
- [ ] `example.rst` written as human-followable numbered Steps.
- [ ] `verify.sh` sources `verify-common.sh`, mirrors the Envoy-demonstration Steps 1:1
      (permitted external-service setup steps are documented-only, exercised via a mock), uses
      framework helpers + `jq`, no bespoke harness.
- [ ] Host ports published via framework variables with fixed defaults (`${PORT_x:-…}:…`), so
      CI masks them; proxy port published; reader can `curl` it.
- [ ] Self-contained (mocked upstreams); no third-party service unless the narrow exception
      applies.
- [ ] Listed in `EXAMPLE_TESTS` (every example is — that is how CI runs it).
