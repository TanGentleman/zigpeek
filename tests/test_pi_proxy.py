"""The allowlist proxy publishes its address and stays quiet while doing it.

run.sh used to curl that address from the Mac. The proxy can be listening
and still fail that probe, which is the failure this guards against.
"""
from __future__ import annotations

import os
import socket
import subprocess
import textwrap
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "pi-container" / "run.sh"
PROXY = ROOT / "pi-container" / "proxy.py"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _source(cfg: Path, cli: Path, extra: str) -> str:
    return textwrap.dedent(
        f"""\
        set -euo pipefail
        export PI_SOURCE_ONLY=1
        export PI_CONFIG_DIR={cfg}
        export CONTAINER_CLI={cli}
        export PI_PROXY_PORT=8888
        source {RUN}
        {extra}
        """
    )


def test_proxy_publishes_address_without_openssl_noise(tmp_path: Path) -> None:
    private = tmp_path / "private"
    certs = tmp_path / "certs"
    private.mkdir()
    certs.mkdir()
    port = _free_port()
    env = os.environ.copy()
    env.update(
        {
            "OPENROUTER_API_KEY": "sk-or-v1-test",
            "PI_PROXY_BIND": "127.0.0.1",
            "PI_PROXY_PORT": str(port),
            "PI_PROXY_CERT": str(private / "openrouter.pem"),
            "PI_PROXY_KEY": str(private / "openrouter.key"),
            "PI_PROXY_CA": str(certs / "ca.pem"),
            "PI_PROXY_ADDR_FILE": str(private / "proxy.addr"),
        }
    )
    proc = subprocess.Popen(
        ["python3", str(PROXY)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert proc.stderr is not None
        seen: list[str] = []
        line = ""
        for _ in range(200):
            line = proc.stderr.readline()
            seen.append(line)
            if line.startswith("listening "):
                break
        else:
            pytest.fail(f"proxy did not listen; stderr so far: {''.join(seen)!r}")
        logged = "".join(seen)
        assert line.strip() == f"listening 127.0.0.1:{port}"
        assert "Certificate request self-signature ok" not in logged
        assert "++++" not in logged
        assert (private / "proxy.addr").read_text(encoding="utf-8") == "127.0.0.1\n"
        body = urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2).read()
        assert body == b"pi-container-proxy\n"
        denied = subprocess.run(
            [
                "python3",
                "-c",
                textwrap.dedent(
                    f"""\
                    import socket
                    s = socket.create_connection(("127.0.0.1", {port}), 2)
                    s.sendall(b"CONNECT example.com:443 HTTP/1.1\\r\\nHost: example.com:443\\r\\n\\r\\n")
                    data = s.recv(128)
                    raise SystemExit(0 if data.startswith(b"HTTP/1.1 403") else 1)
                    """
                ),
            ],
            check=False,
        )
        assert denied.returncode == 0
    finally:
        proc.terminate()
        if proc.stderr is not None:
            proc.stderr.read()
        proc.wait(timeout=5)


def test_readiness_uses_the_container_not_a_mac_curl(tmp_path: Path) -> None:
    cfg = tmp_path / "cfg"
    private = cfg / "private"
    private.mkdir(parents=True)
    (private / "proxy.addr").write_text("172.30.240.2\n", encoding="utf-8")
    log = tmp_path / "cli.log"
    cli = tmp_path / "container"
    cli.write_text(
        textwrap.dedent(
            f"""\
            #!/bin/bash
            printf '%s\\n' "$*" >> {log}
            exit 0
            """
        ),
        encoding="utf-8",
    )
    cli.chmod(0o755)
    script = _source(
        cfg,
        cli,
        'export PI_PROXY_WAIT=2; printf "%s\\n" "$(proxy_ip)"',
    )
    done = subprocess.run(["bash", "-c", script], check=True, capture_output=True, text=True)
    assert done.stdout.strip() == "172.30.240.2"
    recorded = log.read_text(encoding="utf-8")
    assert recorded.splitlines()[0].startswith("exec ")
    assert "curl" not in recorded


def test_proxy_state_accepts_current_and_older_inspect_json(tmp_path: Path) -> None:
    current = tmp_path / "current.json"
    older = tmp_path / "older.json"
    current.write_text(
        """
        {"status":{"networks":[{"network":"pi-locked","ipv4Address":"172.30.240.2/24"}],"state":"running"}}
        """,
        encoding="utf-8",
    )
    older.write_text(
        """
        {"status":"stopped","networks":[{"network":"pi-locked","address":"172.30.240.2/24"}]}
        """,
        encoding="utf-8",
    )
    cli = tmp_path / "container"
    cli.write_text(
        textwrap.dedent(
            f"""\
            #!/bin/bash
            if [ "$1" = inspect ]; then
              cat "${{INSPECT_JSON:?}}"
              exit 0
            fi
            exit 1
            """
        ),
        encoding="utf-8",
    )
    cli.chmod(0o755)

    def state(document: Path) -> str:
        env = os.environ.copy()
        env["INSPECT_JSON"] = str(document)
        done = subprocess.run(
            ["bash", "-c", _source(tmp_path / "cfg", cli, 'printf "%s" "$(proxy_state)"')],
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )
        return done.stdout

    assert state(current) == "running"
    assert state(older) == "stopped"
