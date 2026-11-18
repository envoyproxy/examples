"""The runner of the MCP JSON-REST bridge end-to-end test.

Runs the cases of rest_cases.py against Envoy's two listeners: C, the MCP filter in front of the
bridge, and B, the bridge alone. A case sends raw HTTP requests, or uses the official MCP Python
SDK (mcp==2.2.0), and checks the answers and the REST backend's request log against the
requirements of requirements.py. Every request carries an X-E2E-Case header with the case's name,
which the bridge forwards: that is how the runner finds a case's entries in the request log.

A check is a regression check, which must pass, or a compliance check, one that names a known gap
and fails on the current Envoy. Prints each case's checks as they run, with the HTTP exchanges of a
case whose regression check fails, then a summary with the known gaps and their failing checks.

Exits 1 on a regression failure. A known gap's check that passes (FIXED) is a warning, not a
failure: the gap is fixed, so remove it from the check. See README.md.
"""
import argparse
import contextlib
import dataclasses
import http.client
import json
import pathlib
import sys
import traceback

import anyio
import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.types import Implementation
from mcp_types.methods import validate_server_result

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
# The MCP filter test's helpers: one line for an exception, and a JSON-lines file's objects.
from mcp_client import describe, read_json_lines  # noqa: E402

import rest_cases  # noqa: E402
from requirements import KNOWN_GAPS, REQUIREMENTS  # noqa: E402

PROTOCOL_VERSION = "2026-07-28"
CLIENT_INFO = {"name": "envoy-mcp-rest-e2e-client", "version": "1.0.0"}
# How long a raw request may take, and an SDK session.
RAW_TIMEOUT_SECONDS = 5
SDK_TIMEOUT_SECONDS = 15
# How much of a body the output quotes.
QUOTE_BYTES = 600
# The requirement of the check that a case ran to its end, without an exception.
HARNESS = "HARNESS"


@dataclasses.dataclass
class Exchange:
    """A raw HTTP POST to Envoy's /mcp, and what came back."""
    listener: str
    port: int
    headers: list
    body: bytes
    status: int | None = None
    response_headers: list = dataclasses.field(default_factory=list)
    response_body: bytes = b""
    error: str | None = None

    @property
    def text(self):
        return self.response_body.decode("utf-8", "replace")

    @property
    def json(self):
        try:
            return json.loads(self.response_body)
        except ValueError:
            return None

    def header(self, name):
        return next((v for n, v in self.response_headers if n.lower() == name.lower()), None)

    def summary(self):
        if self.status is None:
            return self.error or "no response"
        text = f"HTTP {self.status}, {self.header('content-type') or 'no content-type'}, "
        text += f"body {quote(self.text, 300)!r}" if self.response_body else "no body"
        return text + (f" [{self.error}]" if self.error else "")

    def request_text(self):
        """The request as an HTTP/1.1 message, to reproduce it."""
        lines = ["POST /mcp HTTP/1.1"]
        for name, value in self.headers:
            value = value.decode("utf-8", "replace") if isinstance(value, bytes) else value
            lines.append(f"{name}: {value}")
        return "\n".join(lines) + "\n\n" + quote(self.body.decode("utf-8", "replace"), 2000)


@dataclasses.dataclass
class CheckResult:
    case: str
    name: str
    requirement: str
    gap: str | None
    ok: bool
    expected: str
    actual: str

    @property
    def outcome(self):
        """pass or fail (regression checks), gap (fails as known) or fixed (a known gap passes)."""
        if self.gap is None:
            return "pass" if self.ok else "fail"
        return "fixed" if self.ok else "gap"


def quote(text, limit=QUOTE_BYTES):
    return text if len(text) <= limit else text[:limit] + f"... ({len(text)} chars)"


def leaf(error):
    """The innermost exception of the exception groups that anyio may wrap an error in."""
    while getattr(error, "exceptions", None):
        error = error.exceptions[0]
    return error


class Ctx:
    """What a case uses: requests, SDK sessions, checks, and the REST backend's request log."""

    def __init__(self, runner, case):
        self.runner = runner
        self.name = case.name
        self.listener = case.listener
        self.exchanges = []
        self.checks = []
        self._ids = 0

    def next_id(self):
        self._ids += 1
        return self._ids

    # Requests.

    def post(self, body=None, headers=(), *, raw=None, timeout=RAW_TIMEOUT_SECONDS):
        """Sends a POST to /mcp on its own connection: body as JSON, or raw bytes."""
        exchange = Exchange(self.listener, self.runner.ports[self.listener],
                            [*headers, ("X-E2E-Case", self.name)],
                            raw if raw is not None else json.dumps(body).encode())
        self.exchanges.append(exchange)
        send(exchange, self.runner.host, timeout)
        return exchange

    @contextlib.asynccontextmanager
    async def sdk(self):
        """An SDK client of the listener, with no response cache, that sends X-E2E-Case."""
        url = f"http://{self.runner.host}:{self.runner.ports[self.listener]}/mcp"
        async with httpx2.AsyncClient(headers={"X-E2E-Case": self.name},
                                      timeout=httpx2.Timeout(SDK_TIMEOUT_SECONDS)) as http:
            async with Client(streamable_http_client(url, http_client=http), mode=PROTOCOL_VERSION,
                              cache=None, client_info=Implementation(**CLIENT_INFO),
                              read_timeout_seconds=SDK_TIMEOUT_SECONDS) as client:
                yield client

    def run_sdk(self, function):
        """Runs an async function. Returns (its value, None), or (None, the exception it raised)."""

        async def run():
            with anyio.fail_after(SDK_TIMEOUT_SECONDS * 2):
                return await function()

        try:
            return anyio.run(run), None
        except Exception as error:  # pylint: disable=broad-exception-caught
            return None, leaf(error)

    # Checks.

    def check(self, name, ok, expected, actual, requirement, gap=None):
        if requirement not in REQUIREMENTS and requirement != HARNESS:
            raise ValueError(f"unknown requirement {requirement}")
        if gap is not None and gap not in KNOWN_GAPS:
            raise ValueError(f"unknown gap {gap}")
        if not isinstance(expected, str):  # e.g. isError's bool: quote() needs a string
            expected = json.dumps(expected, default=str)
        self.checks.append(
            CheckResult(self.name, name, requirement, gap, bool(ok), expected, str(actual)))
        return bool(ok)

    def schema(self, method, result, gap=None):
        """Checks a result against the 2026-07-28 schema of its method."""
        try:
            validate_server_result(method, PROTOCOL_VERSION, result)
            actual = "valid"
        except Exception as error:  # pylint: disable=broad-exception-caught
            actual = quote(" | ".join(str(error).splitlines()), 300)
        return self.check(f"the result matches the 2026-07-28 {method} schema", actual == "valid",
                          "valid", actual, "RESULT-SCHEMA", gap)

    def backend(self):
        """The REST backend's request log entries of this case's requests."""
        return [
            entry for entry in read_json_lines(self.runner.run_dir / "rest_requests.jsonl")
            if entry.get("e2e_case") == self.name
        ]


def send(exchange, host, timeout):
    """Sends a request on a new connection, and reads its response, or what arrives in time."""
    connection = http.client.HTTPConnection(host, exchange.port, timeout=timeout)
    try:
        connection.putrequest("POST", "/mcp", skip_accept_encoding=True)
        for name, value in exchange.headers:
            connection.putheader(name, value)
        connection.putheader("Content-Length", str(len(exchange.body)))
        connection.endheaders(exchange.body)
        try:
            response = connection.getresponse()
        except TimeoutError:
            exchange.error = f"no response in {timeout}s"
            return
        exchange.status = response.status
        exchange.response_headers = response.getheaders()
        chunks = []
        try:
            chunk = response.read1(65536)
            while chunk:
                chunks.append(chunk)
                chunk = response.read1(65536)
        except TimeoutError:
            length = response.getheader("content-length")
            exchange.error = (f"body incomplete after {timeout}s: {sum(map(len, chunks))} of "
                              f"{length if length is not None else 'unknown'} bytes")
        except http.client.IncompleteRead as error:
            chunks.append(error.partial)
            exchange.error = f"body incomplete: {error}"
        exchange.response_body = b"".join(chunks)
    except OSError as error:
        exchange.error = f"{type(error).__name__}: {error}"
    finally:
        connection.close()


class Runner:

    def __init__(self, args):
        self.host = args.envoy_host
        self.ports = {"C": args.port, "B": args.bridge_only_port}
        self.run_dir = args.run_dir
        self.only = [item for item in args.only.split(",") if item]
        self.skip = [item for item in args.skip.split(",") if item]
        self.checks = []
        self.run_count = 0
        self.skipped = 0

    def selected(self, case):

        def matches(items):
            return any(case.name == item or case.name.startswith(item) for item in items)

        return (not self.only or matches(self.only)) and not matches(self.skip)

    def run(self):
        for case in rest_cases.CASES:
            if self.selected(case):
                self.run_case(case)
            else:
                self.skipped += 1

    def run_case(self, case):
        ctx = Ctx(self, case)
        print(f"\n[{case.name}] {case.what}")
        try:
            case.function(ctx)
            ctx.check("the case ran to its end", True, "no exception", "none", HARNESS)
        except Exception as error:  # pylint: disable=broad-exception-caught
            where = traceback.extract_tb(error.__traceback__)[-1]
            ctx.check("the case ran to its end", False, "no exception",
                      f"{describe(error)} at {pathlib.Path(where.filename).name}:{where.lineno}",
                      HARNESS)
        self.run_count += 1
        self.checks += ctx.checks
        for c in ctx.checks:
            if c.requirement == HARNESS and c.ok:
                continue
            tag = {"pass": "ok   ", "fail": "FAIL ", "fixed": "FIXED"}
            tag = tag.get(c.outcome) or f"GAP {c.gap:<3}"
            line = f"  {tag} {c.name} ({c.requirement})"
            if c.outcome != "pass":
                line += f": expected {quote(c.expected, 160)}; got {quote(c.actual, 240)}"
            print(line)
        if any(c.outcome == "fail" for c in ctx.checks):
            for number, e in enumerate(ctx.exchanges, 1):
                print(f"  HTTP exchange {number}, on listener {e.listener}:")
                print("\n".join("    > " + line for line in e.request_text().splitlines()))
                print(f"    < {e.summary()}")

    def report(self):
        """Prints the summary. Returns the exit code: 1 if a regression check failed."""
        outcomes = {}
        for c in self.checks:
            outcomes.setdefault(c.outcome, []).append(c)
        regressions, gaps, fixed = (outcomes.get(o, []) for o in ("fail", "gap", "fixed"))
        print("\n" + "=" * 100)
        print(f"Cases: {self.run_count} run, {self.skipped} not selected")
        print(f"Regression checks: {len(outcomes.get('pass', []))} passed, {len(regressions)} "
              "failed")
        print(f"Compliance checks (known gaps): {len(gaps)} failing as known, {len(fixed)} now "
              "passing")
        by_gap = {}
        for c in gaps + fixed:
            by_gap.setdefault(c.gap, []).append(c)
        for gap_id in sorted(by_gap, key=lambda g: int(g[1:])):
            levels = sorted({REQUIREMENTS[c.requirement].level for c in by_gap[gap_id]})
            print(f"  {gap_id:<4} {KNOWN_GAPS[gap_id].title}: {len(by_gap[gap_id])} checks "
                  f"({', '.join(levels)})")
        if regressions:
            print("\nRegression failures (to run a case again, see README.md)")
            for c in regressions:
                print(f"  {c.case} / {c.name} ({c.requirement}): expected "
                      f"{quote(c.expected, 160)}; got {quote(c.actual, 240)}")
        if gaps:
            print("\nKnown gaps: compliance checks that fail on this Envoy")
            for gap_id in sorted(by_gap, key=lambda g: int(g[1:])):
                failing = [c for c in by_gap[gap_id] if c.outcome == "gap"]
                if failing:
                    print(f"  {gap_id} {KNOWN_GAPS[gap_id].title}. {KNOWN_GAPS[gap_id].detail}")
                for c in failing:
                    print(f"    {c.case} / {c.name}: got {quote(c.actual, 200)}")
        if fixed:
            print("\nWARNING: known gaps' checks now pass (FIXED). Remove the gap from these "
                  "checks in rest_cases.py, and from requirements.py when no check names it:")
            for c in fixed:
                print(f"  {c.gap}: {c.case} / {c.name}")
        return 1 if regressions else 0


def parse_args():
    parser = argparse.ArgumentParser(description="The client of the bridge E2E test.")
    parser.add_argument("--envoy-host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True, help="listener C: MCP filter, bridge")
    parser.add_argument("--bridge-only-port", type=int, required=True, help="listener B: bridge")
    parser.add_argument("--run-dir", type=pathlib.Path, required=True)
    parser.add_argument("--only", default="", help="comma-separated case names or prefixes to run")
    parser.add_argument("--skip", default="", help="comma-separated case names or prefixes to skip")
    return parser.parse_args()


def main():
    runner = Runner(parse_args())
    runner.run()
    return runner.report()


if __name__ == "__main__":
    sys.exit(main())
