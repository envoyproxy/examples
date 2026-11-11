"""The test run in the rest-client service, with docker compose exec (see docker-compose.yaml).

Checks the image's MCP Python SDK version, waits for Envoy to be ready, says which Envoy it is,
runs rest_client.py, and checks that Envoy and the REST server did not exit during the test. Tees
everything to client_output.txt in the run directory. See README.md.
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

HERE = pathlib.Path(__file__).resolve().parent.parent
ENVOY_HOST = os.environ["ENVOY_HOST"]
ENVOY_PORT = os.environ["ENVOY_PORT"]
ENVOY_BRIDGE_ONLY_PORT = os.environ["ENVOY_BRIDGE_ONLY_PORT"]
ENVOY_ADMIN_PORT = os.environ["ENVOY_ADMIN_PORT"]
REST_SERVER_HOST = os.environ["REST_SERVER_HOST"]
REST_SERVER_PORT = os.environ["REST_SERVER_PORT"]
RUN_DIR = pathlib.Path(os.environ["E2E_RUN_DIR"])
# The SDK version that the suite is pinned to: ../docker/requirements.txt's.
MCP_SDK_VERSION = "2.2.0"
STARTUP_TIMEOUT_SECONDS = 30


def envoy_ready():
    try:
        url = f"http://{ENVOY_HOST}:{ENVOY_ADMIN_PORT}/ready"
        with urllib.request.urlopen(url, timeout=1) as response:
            return response.status == 200
    except OSError:
        return False


def server_up():
    try:
        socket.create_connection((REST_SERVER_HOST, int(REST_SERVER_PORT)), timeout=2).close()
        return True
    except OSError:
        return False


def main():
    with open(RUN_DIR / "client_output.txt", "w", encoding="utf-8") as output:

        def say(text=""):
            print(text, flush=True)
            output.write(text + "\n")
            output.flush()

        version = importlib.metadata.version("mcp")
        if version != MCP_SDK_VERSION:
            say(f"ERROR: the image has mcp {version}, but this suite is pinned to mcp=="
                f"{MCP_SDK_VERSION}. Rebuild it: docker compose build.")
            return 1
        deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
        while not envoy_ready():
            if time.monotonic() > deadline:
                say(f"ERROR: Envoy did not become ready in {STARTUP_TIMEOUT_SECONDS}s; see "
                    f"{RUN_DIR}/envoy.log")
                return 1
            time.sleep(0.2)
        with urllib.request.urlopen(f"http://{ENVOY_HOST}:{ENVOY_ADMIN_PORT}/server_info",
                                    timeout=10) as response:
            server_info = json.load(response)
        (RUN_DIR / "server_info.json").write_text(json.dumps(server_info, indent=2) + "\n")
        envoy_version = server_info.get("version", "unknown")
        say(f"==> Envoy {envoy_version}: listener C at {ENVOY_HOST}:{ENVOY_PORT} (MCP filter, "
            f"bridge), listener B at {ENVOY_HOST}:{ENVOY_BRIDGE_ONLY_PORT} (bridge), in front of "
            f"the REST backend at {REST_SERVER_HOST}:{REST_SERVER_PORT}")

        command = [
            sys.executable, "-u", str(HERE / "rest_client.py"), "--envoy-host", ENVOY_HOST,
            "--port", ENVOY_PORT, "--bridge-only-port", ENVOY_BRIDGE_ONLY_PORT, "--admin-port",
            ENVOY_ADMIN_PORT, "--run-dir", str(RUN_DIR), "--only", os.environ.get("ONLY", ""),
            "--skip", os.environ.get("SKIP_CASES", ""), "--compliance",
            os.environ.get("COMPLIANCE", "")
        ]
        process = subprocess.Popen(command, cwd=HERE, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, text=True)
        for line in process.stdout:
            say(line.rstrip("\n"))
        failed = process.wait() != 0

        say()
        say("Processes")
        processes = (("Envoy", envoy_ready(), f"{RUN_DIR}/envoy.log"),
                     ("The REST server", server_up(), "docker compose logs rest-server"))
        for name, up, where in processes:
            say(f"  ok    {name} is still running" if up else
                f"  FAIL  {name} is no longer running; see {where}")
            failed = failed or not up
        say()
        where = f"the run directory, {RUN_DIR}, in the rest-client container (see README.md)"
        say(f"FAIL. Logs and files: {where}" if failed else f"PASS. Logs and files: {where}")
        return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
