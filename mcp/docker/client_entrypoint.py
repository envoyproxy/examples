"""The test run in the mcp-client service, with docker compose exec (see docker-compose.yaml).

Waits until Envoy is ready, and records which Envoy it is. Then runs the 17 regression cases
(mcp_client.py) or, with DEMO=1, the developer demo (demo_client.py), against the envoy and
mcp-server services. Finally checks that Envoy and the MCP server are still up, and exits with the
result: 0 for PASS, 1 for FAIL. Everything that it prints also goes to client_output.txt in the run
directory. See README.md.
"""
import importlib.metadata
import json
import os
import pathlib
import socket
import subprocess
import sys
import time
import urllib.request

E2E_DIR = pathlib.Path(__file__).resolve().parent.parent
# Where the services find each other, and the run directory that they share: docker-compose.yaml's
# x-e2e-environment.
ENVOY_HOST = os.environ["ENVOY_HOST"]
ENVOY_PORT = os.environ["ENVOY_PORT"]
ENVOY_CAPPED_PORT = os.environ["ENVOY_CAPPED_PORT"]
ENVOY_ADMIN_PORT = os.environ["ENVOY_ADMIN_PORT"]
MCP_SERVER_HOST = os.environ["MCP_SERVER_HOST"]
MCP_SERVER_PORT = os.environ["MCP_SERVER_PORT"]
RUN_DIR = pathlib.Path(os.environ["E2E_RUN_DIR"])
# The MCP Python SDK version that the suite is pinned to. The image installs it from
# docker/requirements.txt.
MCP_SDK_VERSION = "2.2.0"
# How long Envoy gets to become ready.
STARTUP_TIMEOUT_SECONDS = 30


def envoy_ready():
    """Whether Envoy's admin endpoint says that Envoy is ready."""
    try:
        url = f"http://{ENVOY_HOST}:{ENVOY_ADMIN_PORT}/ready"
        with urllib.request.urlopen(url, timeout=1) as response:
            return response.status == 200
    except OSError:
        return False


def server_up():
    """Whether the MCP server accepts connections."""
    try:
        socket.create_connection((MCP_SERVER_HOST, int(MCP_SERVER_PORT)), timeout=2).close()
        return True
    except OSError:
        return False


def main():
    demo = os.environ.get("DEMO", "0")
    skip_cases = os.environ.get("SKIP_CASES", "")
    with open(RUN_DIR / "client_output.txt", "w", encoding="utf-8") as output:

        def say(text=""):
            print(text, flush=True)
            output.write(text + "\n")
            output.flush()

        if demo not in ("0", "1"):
            say(f"ERROR: DEMO must be 0 or 1, not {demo}.")
            return 1
        if demo == "1" and skip_cases:
            say("ERROR: SKIP_CASES selects regression cases, which DEMO=1 does not run.")
            return 1
        version = importlib.metadata.version("mcp")
        if version != MCP_SDK_VERSION:
            say(f"ERROR: the image has mcp {version}, but this suite is pinned to mcp=="
                f"{MCP_SDK_VERSION}. Rebuild it: docker compose build.")
            return 1

        deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
        while not envoy_ready():
            if time.monotonic() > deadline:
                say(f"ERROR: Envoy did not become ready in {STARTUP_TIMEOUT_SECONDS}s; see "
                    "docker compose logs envoy")
                return 1
            time.sleep(0.2)
        with urllib.request.urlopen(f"http://{ENVOY_HOST}:{ENVOY_ADMIN_PORT}/server_info",
                                    timeout=10) as response:
            server_info = json.load(response)
        (RUN_DIR / "server_info.json").write_text(json.dumps(server_info, indent=2) + "\n")
        envoy_version = server_info.get("version", "unknown")
        say(f"==> Envoy {envoy_version}, at {ENVOY_HOST}:{ENVOY_PORT}, in front of the MCP server "
            f"at {MCP_SERVER_HOST}:{MCP_SERVER_PORT}")

        script = "demo_client.py" if demo == "1" else "mcp_client.py"
        command = [
            sys.executable, "-u", str(E2E_DIR / script), "--envoy-host", ENVOY_HOST, "--port",
            ENVOY_PORT, "--capped-port", ENVOY_CAPPED_PORT, "--admin-port", ENVOY_ADMIN_PORT,
            "--backend-host", MCP_SERVER_HOST, "--backend-port", MCP_SERVER_PORT, "--run-dir",
            str(RUN_DIR)
        ]
        if demo == "0":
            command += ["--skip", skip_cases]
        say()
        process = subprocess.Popen(command, cwd=E2E_DIR, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, text=True)
        for line in process.stdout:
            say(line.rstrip("\n"))
        failed = process.wait() != 0

        # Envoy and the server must not have exited, or crashed, during the test.
        say()
        say("Processes")
        for name, up, logs in (("Envoy", envoy_ready(), "envoy"),
                               ("The MCP server", server_up(), "mcp-server")):
            say(f"  ok    {name} is still running" if up else
                f"  FAIL  {name} is no longer running; see docker compose logs {logs}")
            failed = failed or not up

        say()
        where = f"the run directory, {RUN_DIR}, in the mcp-client container (see README.md)"
        if failed:
            say(f"FAIL. Logs and files: {where}")
            return 1
        skipped = f", with cases skipped (SKIP_CASES={skip_cases})" if skip_cases else ""
        say(f"PASS{skipped}. Logs and files: {where}")
        return 0


if __name__ == "__main__":
    sys.exit(main())
