"""The runner of the MCP JSON-REST bridge end-to-end test.

Runs the cases of rest_cases.py against Envoy's two listeners: C, the MCP filter in front of the
bridge, and B, the bridge alone. A case sends raw HTTP requests, or uses the official MCP Python
SDK (mcp==2.2.0), and checks the answers, the REST backend's request log and Envoy's access log
against the requirements of requirements.py. Every request carries an X-E2E-Case header with the
case's name, which the bridge forwards: that is how the runner finds a case's entries in both logs,
and Envoy's debug lines, by connection.

A check is a regression check, which must pass; a compliance check, one that names a known gap and
fails on the current Envoy; or a diagnostic check, one that names a diagnostic: how the bridge alone
behaves where the MCP filter in front of it meets the requirement in the supported chain. Prints
each case's checks as they run, then a summary, the details of every regression failure, the known
gaps with their failing checks, and the diagnostics. Writes report.txt (all failures and diagnostic
deviations in detail, with HTTP exchanges and logs) and results.json to the run directory.

Exits 1 on a regression failure, on a known gap's check that passes (the gap is fixed: update
rest_cases.py), or with --compliance strict, on a known gap's check that fails. Diagnostic checks
never fail the run. See README.md.
"""
import argparse
import contextlib
import dataclasses
import http.client
import json
import pathlib
import sys
import time
import traceback
import urllib.request

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
from requirements import DIAGNOSTICS, KNOWN_GAPS, REQUIREMENTS  # noqa: E402

PROTOCOL_VERSION = "2026-07-28"
CLIENT_INFO = {"name": "envoy-mcp-rest-e2e-client", "version": "1.0.0"}
# How long a raw request may take, and an SDK session.
RAW_TIMEOUT_SECONDS = 5
SDK_TIMEOUT_SECONDS = 15
# How much of a body the reports quote.
QUOTE_BYTES = 600
# The requirement of the check that a case ran to its end, without an exception.
HARNESS = "HARNESS"


@dataclasses.dataclass
class Exchange:
    """A raw HTTP request to Envoy, and what came back."""
    label: str
    listener: str
    port: int
    method: str
    path: str
    headers: list
    body: bytes | None
    status: int | None = None
    response_headers: list = dataclasses.field(default_factory=list)
    response_body: bytes = b""
    error: str | None = None
    elapsed_ms: int = 0

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
        lines = [f"{self.method} {self.path} HTTP/1.1"]
        for name, value in self.headers:
            value = value.decode("utf-8", "replace") if isinstance(value, bytes) else value
            lines.append(f"{name}: {value}")
        body = (self.body or b"").decode("utf-8", "replace")
        return "\n".join(lines) + "\n\n" + quote(body, 2000)

    def to_json(self):
        return {
            "label": self.label,
            "listener": self.listener,
            "request": self.request_text(),
            "status": self.status,
            "response_headers": self.response_headers,
            "response_body": quote(self.text, 4000),
            "error": self.error,
            "elapsed_ms": self.elapsed_ms,
        }


@dataclasses.dataclass
class CheckResult:
    case: str
    name: str
    requirement: str
    gap: str | None
    ok: bool
    expected: str
    actual: str
    diagnostic: str | None = None

    @property
    def outcome(self):
        """pass or fail (regression checks), gap (fails as known) or fixed (a known gap passes),
        diag (a diagnostic check that deviates from its requirement) or diag-ok (one that does not).
        """
        if self.diagnostic is not None:
            return "diag-ok" if self.ok else "diag"
        if self.gap is None:
            return "pass" if self.ok else "fail"
        return "fixed" if self.ok else "gap"

    def requirement_text(self):
        if self.requirement == HARNESS:
            return "HARNESS: the case runs to its end."
        r = REQUIREMENTS[self.requirement]
        return f"{self.requirement} ({r.level}): {r.text} [{r.source}]"


def quote(text, limit=QUOTE_BYTES):
    return text if len(text) <= limit else text[:limit] + f"... ({len(text)} chars)"


def leaf(error):
    """The innermost exception of the exception groups that anyio may wrap an error in."""
    while getattr(error, "exceptions", None):
        error = error.exceptions[0]
    return error


def sdk_error_info(error):
    error = leaf(error)
    return {
        "type": type(error).__name__,
        "code": getattr(error, "code", None),
        "message": quote(str(getattr(error, "message", None) or error), 1000),
        "data": getattr(error, "data", None),
    }


class Ctx:
    """What a case uses: requests, SDK sessions, checks, and the logs of its requests."""

    def __init__(self, runner, case):
        self.runner = runner
        self.case = case
        self.name = case.name
        self.listener = case.listener
        self.exchanges = []
        self.checks = []
        self.sdk_errors = []
        self.notes = []
        self.used_sdk = False
        self._ids = 0

    def next_id(self):
        self._ids += 1
        return self._ids

    # Requests.

    def post(self, body=None, headers=(), *, raw=None, listener=None, method="POST",
             path="/mcp", timeout=RAW_TIMEOUT_SECONDS):
        """Sends one request on its own connection: body as JSON, or raw bytes."""
        listener = listener or self.listener
        data = raw if raw is not None else (None if body is None else json.dumps(body).encode())
        exchange = Exchange(f"#{len(self.exchanges) + 1}", listener, self.runner.port(listener),
                            method, path, [*headers, ("X-E2E-Case", self.name)], data)
        self.exchanges.append(exchange)
        send(exchange, self.runner.host, timeout)
        return exchange

    @contextlib.asynccontextmanager
    async def sdk(self, listener=None, mode=PROTOCOL_VERSION):
        """An SDK client of a listener, with no response cache, whose requests carry X-E2E-Case."""
        self.used_sdk = True
        url = f"http://{self.runner.host}:{self.runner.port(listener or self.listener)}/mcp"
        async with httpx2.AsyncClient(headers={"X-E2E-Case": self.name},
                                      timeout=httpx2.Timeout(SDK_TIMEOUT_SECONDS)) as http:
            async with Client(streamable_http_client(url, http_client=http), mode=mode, cache=None,
                              client_info=Implementation(**CLIENT_INFO),
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
            self.sdk_errors.append(sdk_error_info(error))
            return None, leaf(error)

    # Checks.

    def check(self, name, ok, expected, actual, requirement, gap=None, diagnostic=None):
        if requirement not in REQUIREMENTS and requirement != HARNESS:
            raise ValueError(f"unknown requirement {requirement}")
        if gap is not None and gap not in KNOWN_GAPS:
            raise ValueError(f"unknown gap {gap}")
        if diagnostic is not None and (diagnostic not in DIAGNOSTICS or gap is not None):
            raise ValueError(f"unknown diagnostic {diagnostic}, or one with a gap")
        if not isinstance(expected, str):  # e.g. isError's bool: quote() needs a string
            expected = json.dumps(expected, default=str)
        self.checks.append(
            CheckResult(self.name, name, requirement, gap, bool(ok), expected, str(actual),
                        diagnostic))
        return bool(ok)

    def note(self, text):
        """An observation that is not a check: printed, and kept in the results."""
        self.notes.append(text)

    def schema(self, method, result, requirement="RESULT-SCHEMA", gap=None):
        """Checks a result against the 2026-07-28 schema of its method."""
        try:
            validate_server_result(method, PROTOCOL_VERSION, result)
            actual = "valid"
        except Exception as error:  # pylint: disable=broad-exception-caught
            actual = quote(" | ".join(str(error).splitlines()), 300)
        return self.check(f"the result matches the 2026-07-28 {method} schema", actual == "valid",
                          "valid", actual, requirement, gap)

    # Logs.

    def backend(self):
        """The REST backend's request log entries of this case's requests."""
        return [
            entry for entry in read_json_lines(self.runner.run_dir / "rest_requests.jsonl")
            if entry.get("e2e_case") == self.name
        ]

    def access(self, count=1, timeout=3.0):
        """Envoy's access log entries of this case, once there are count of them (or timeout)."""
        deadline = time.monotonic() + timeout
        while True:
            entries = [
                entry for entry in read_json_lines(self.runner.run_dir / "access.log")
                if entry.get("e2e_case") == self.name
            ]
            if len(entries) >= count or time.monotonic() > deadline:
                return entries
            time.sleep(0.1)

    def envoy_log(self, entries, limit=30, timeout=1.0):
        """Envoy's debug lines for the connections of these access log entries.

        Envoy writes its log out periodically, so this waits up to timeout for the lines to appear.
        """
        ids = {str(e.get("connection_id")) for e in entries if e.get("connection_id")}
        path = self.runner.run_dir / "envoy.log"
        if not ids or not path.exists():
            return []
        tags = tuple(f'"ConnectionId":"{i}"' for i in ids)
        deadline = time.monotonic() + timeout
        while True:
            lines = [line for line in path.read_text(errors="replace").splitlines() if tags and
                     any(tag in line for tag in tags)]
            if lines or time.monotonic() > deadline:
                return [quote(line, 400) for line in lines[-limit:]]
            time.sleep(0.1)


def send(exchange, host, timeout):
    """Sends a request on a new connection, and reads its response, or what arrives in time."""
    start = time.monotonic()
    connection = http.client.HTTPConnection(host, exchange.port, timeout=timeout)
    try:
        connection.putrequest(exchange.method, exchange.path, skip_accept_encoding=True)
        names = {name.lower() for name, _ in exchange.headers}
        for name, value in exchange.headers:
            connection.putheader(name, value)
        if exchange.body is not None and "content-length" not in names:
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
        exchange.elapsed_ms = int((time.monotonic() - start) * 1000)
        connection.close()


class Runner:

    def __init__(self, args):
        self.host = args.envoy_host
        self.ports = {"C": args.port, "B": args.bridge_only_port}
        self.admin_port = args.admin_port
        self.run_dir = args.run_dir
        self.only = [item for item in args.only.split(",") if item]
        self.skip = [item for item in args.skip.split(",") if item]
        self.strict = args.compliance == "strict"
        self.results = []
        self.skipped = []

    def port(self, listener):
        return self.ports[listener]

    def selected(self, case):

        def matches(items):
            return any(case.name == item or case.name.startswith(item) for item in items)

        return (not self.only or matches(self.only)) and not matches(self.skip)

    def run(self):
        for case in rest_cases.CASES:
            if self.selected(case):
                self.run_case(case)
            else:
                self.skipped.append(case.name)

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
        entries = ctx.access(len(ctx.exchanges) + (1 if ctx.used_sdk else 0), timeout=2.0)
        failed = any(c.outcome not in ("pass", "diag-ok") for c in ctx.checks)
        record = {
            "name": case.name,
            "area": case.area,
            "listener": case.listener,
            "what": case.what,
            "checks": [dataclasses.asdict(c) | {"outcome": c.outcome} for c in ctx.checks],
            "notes": ctx.notes,
            "exchanges": [e.to_json() for e in ctx.exchanges],
            "sdk_errors": ctx.sdk_errors,
            "access_log": entries,
            "backend_requests": ctx.backend(),
            "envoy_log": ctx.envoy_log(entries) if failed else [],
        }
        self.results.append(record)
        for c in ctx.checks:
            if c.requirement == HARNESS and c.ok:
                continue
            tag = {"pass": "ok   ", "fail": "FAIL ", "fixed": "FIXED", "diag-ok": "diag "}
            tag = tag.get(c.outcome) or (f"DIAG {c.diagnostic:<3}" if c.diagnostic else
                                         f"GAP {c.gap:<3}")
            line = f"  {tag} {c.name} ({c.requirement})"
            if c.outcome not in ("pass", "diag-ok"):
                line += f": expected {quote(c.expected, 160)}; got {quote(c.actual, 240)}"
            print(line)
        for note in ctx.notes:
            print(f"  note  {note}")

    # Reports.

    def checks(self, outcome):
        return [(r, c) for r in self.results for c in r["checks"] if c["outcome"] == outcome]

    def detail(self, record, check):
        """A failed check in full: expectation, exchanges, SDK exceptions, logs, gap, repro."""
        c = CheckResult(**{k: v for k, v in check.items() if k != "outcome"})
        lines = [f"--- {c.outcome.upper()}: {record['name']} / {c.name}",
                 f"Test: {record['what']} (listener {record['listener'] or 'B and C'})",
                 f"Expected: {c.expected}", f"Requirement: {c.requirement_text()}",
                 f"Actual: {c.actual}"]
        if c.diagnostic:
            diagnostic = DIAGNOSTICS[c.diagnostic]
            lines.append(f"Diagnostic, not an endpoint compliance failure: {c.diagnostic}, "
                         f"{diagnostic.title}. {diagnostic.detail}")
        elif c.gap:
            gap = KNOWN_GAPS[c.gap]
            lines.append(f"Suspected implementation gap: {c.gap}, {gap.title}. {gap.detail}")
        else:
            lines.append("Suspected implementation gap: none known (a regression, or a new gap: "
                         "see requirements.py)")
        for e in record["exchanges"]:
            lines.append(f"HTTP exchange {e['label']} (listener {e['listener']}, "
                         f"{e['elapsed_ms']} ms):")
            lines += ["  > " + line for line in e["request"].splitlines()]
            if e["status"] is None:
                lines.append(f"  < {e['error']}")
                continue
            lines.append(f"  < HTTP {e['status']}" + (f" [{e['error']}]" if e["error"] else ""))
            lines += [f"  < {n}: {v}" for n, v in e["response_headers"]]
            lines.append("  < " + quote(e["response_body"]))
        for error in record["sdk_errors"]:
            lines.append(f"SDK exception: {error['type']}: code {error['code']}, "
                         f"{error['message']!r}, data {json.dumps(error['data'])}")
        lines.append("Envoy access log:" if record["access_log"] else "Envoy access log: none")
        lines += ["  " + quote(json.dumps(entry), 700) for entry in record["access_log"]]
        if record["envoy_log"]:
            lines.append("Envoy log (debug lines of these connections):")
            lines += ["  " + line for line in record["envoy_log"]]
        backend = record["backend_requests"]
        lines.append("REST backend requests:" if backend else "REST backend requests: none")
        for entry in backend:
            query = f"?{entry['query']}" if entry["query"] else ""
            lines.append(f"  {entry['method']} {entry['raw_path']}{query} -> {entry['status']}, "
                         f"body {quote(entry['body'], 200)!r}, headers "
                         f"{quote(json.dumps(entry['headers']), 400)}")
        lines.append(f"Reproduce: ONLY={record['name']} (see README.md), or the request above.")
        return lines

    def report(self, envoy_version):
        regressions, gaps, fixed = self.checks("fail"), self.checks("gap"), self.checks("fixed")
        passed = self.checks("pass")
        diagnostics = self.checks("diag") + self.checks("diag-ok")
        out = []
        out.append("")
        out.append("=" * 100)
        out.append(f"Envoy {envoy_version}")
        out.append(f"Cases: {len(self.results)} run, {len(self.skipped)} not selected")
        out.append(f"Regression checks: {len(passed)} passed, {len(regressions)} failed")
        out.append(f"Compliance checks (known gaps): {len(gaps)} failing as known, {len(fixed)} "
                   "now passing")
        by_gap = {}
        for record, check in gaps + fixed:
            by_gap.setdefault(check["gap"], []).append((record, check))
        for gap_id in sorted(by_gap, key=lambda g: int(g[1:])):
            levels = sorted({REQUIREMENTS[c["requirement"]].level for _, c in by_gap[gap_id]})
            out.append(f"  {gap_id:<4} {KNOWN_GAPS[gap_id].title}: {len(by_gap[gap_id])} checks "
                       f"({', '.join(levels)})")
        deviations = self.checks("diag")
        out.append(f"Diagnostic checks (the bridge alone; not endpoint compliance): "
                   f"{len(deviations)} deviating, {len(diagnostics) - len(deviations)} as required")
        by_diagnostic = {}
        for record, check in diagnostics:
            by_diagnostic.setdefault(check["diagnostic"], []).append((record, check))
        for diagnostic_id in sorted(by_diagnostic):
            out.append(f"  {diagnostic_id:<4} {DIAGNOSTICS[diagnostic_id].title}: "
                       f"{len(by_diagnostic[diagnostic_id])} checks")
        if regressions:
            out.append("")
            out.append("Regression failures")
            for record, check in regressions:
                out += self.detail(record, check)
        if fixed:
            out.append("")
            out.append("Known gaps whose checks now pass (remove the gap from these checks)")
            for record, check in fixed:
                out.append(f"  {check['gap']}: {record['name']} / {check['name']}")
        if gaps:
            out.append("")
            out.append("Known gaps: compliance checks that fail on this Envoy")
            for gap_id in sorted(by_gap, key=lambda g: int(g[1:])):
                failing = [(r, c) for r, c in by_gap[gap_id] if c["outcome"] == "gap"]
                if not failing:
                    continue
                out.append(f"  {gap_id} {KNOWN_GAPS[gap_id].title}. {KNOWN_GAPS[gap_id].detail}")
                for record, check in failing:
                    out.append(f"    {record['name']} / {check['name']}: got "
                               f"{quote(check['actual'], 200)}")
        if deviations:
            out.append("")
            out.append("Diagnostics: the bridge alone, where the MCP filter in front of it meets "
                       "the requirement in the supported chain")
            for diagnostic_id in sorted(by_diagnostic):
                diagnostic = DIAGNOSTICS[diagnostic_id]
                out.append(f"  {diagnostic_id} {diagnostic.title}. {diagnostic.detail}")
                for record, check in by_diagnostic[diagnostic_id]:
                    if check["outcome"] == "diag":
                        out.append(f"    {record['name']} / {check['name']}: got "
                                   f"{quote(check['actual'], 200)}")
        report = [*out, "", "Failure details", ""]
        for record, check in regressions + fixed + gaps + deviations:
            report += self.detail(record, check) + [""]
        (self.run_dir / "report.txt").write_text("\n".join(report) + "\n")
        (self.run_dir / "results.json").write_text(
            json.dumps({
                "envoy": envoy_version,
                "summary": {
                    "passed": len(passed),
                    "failed": len(regressions),
                    "known_gap_failures": len(gaps),
                    "known_gap_passes": len(fixed),
                    "diagnostic_deviations": len(deviations),
                    "diagnostic_as_required": len(diagnostics) - len(deviations),
                    "not_selected": self.skipped,
                },
                "cases": self.results
            }, indent=1) + "\n")
        out.append("")
        out.append(f"Every failure and diagnostic deviation in full, with its HTTP exchanges and "
                   f"logs: {self.run_dir / 'report.txt'}; all results: "
                   f"{self.run_dir / 'results.json'}")
        print("\n".join(out))
        failed = bool(regressions or fixed or (self.strict and gaps))
        if gaps and not self.strict:
            print("The known-gap failures do not fail the run; with COMPLIANCE=strict they do.")
        return 1 if failed else 0


def parse_args():
    parser = argparse.ArgumentParser(description="The client of the bridge E2E test.")
    parser.add_argument("--envoy-host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True, help="listener C: MCP filter, bridge")
    parser.add_argument("--bridge-only-port", type=int, required=True, help="listener B: bridge")
    parser.add_argument("--admin-port", type=int, required=True)
    parser.add_argument("--run-dir", type=pathlib.Path, required=True)
    parser.add_argument("--only", default="", help="comma-separated case names or prefixes to run")
    parser.add_argument("--skip", default="", help="comma-separated case names or prefixes to skip")
    parser.add_argument("--compliance", default="", choices=["", "strict"])
    return parser.parse_args()


def main():
    args = parse_args()
    runner = Runner(args)
    try:
        with urllib.request.urlopen(f"http://{args.envoy_host}:{args.admin_port}/server_info",
                                    timeout=10) as response:
            envoy_version = json.load(response).get("version", "unknown")
    except OSError as error:
        envoy_version = f"unknown ({error})"
    runner.run()
    return runner.report(envoy_version)


if __name__ == "__main__":
    sys.exit(main())
