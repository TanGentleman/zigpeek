#!/usr/bin/env python3
"""Allowlist proxy for the Pi container. It runs in its own container, not on the Mac.

Tunnels GitHub. Terminates TLS for openrouter.ai and adds the real API key,
which never enters the Pi container. Refuses every other destination.
"""
from __future__ import annotations

import asyncio
import os
import socket
import ssl
import struct
import subprocess
import sys
import time

GITHUB = {
    "github.com",
    "api.github.com",
    "codeload.github.com",
    "objects.githubusercontent.com",
    "raw.githubusercontent.com",
    "uploads.github.com",
}
MAX_BODY = 64 * 1024 * 1024
ENV_FILE = os.environ.get("PI_ENV_FILE", "")
CERT = os.environ.get("PI_PROXY_CERT", "/private/openrouter.pem")
KEY = os.environ.get("PI_PROXY_KEY", "/private/openrouter.key")
CA = os.environ.get("PI_PROXY_CA", "/certs/ca.pem")
ADDR = os.environ.get("PI_PROXY_ADDR_FILE", "/private/proxy.addr")
PORT = int(os.environ.get("PI_PROXY_PORT", "8888"))
UPSTREAM_HOST = os.environ.get("PI_PROXY_OPENROUTER_HOST", "")
UPSTREAM_PORT = int(os.environ.get("PI_PROXY_OPENROUTER_PORT", "443"))
UPSTREAM_TLS = os.environ.get("PI_PROXY_OPENROUTER_TLS", "1") != "0"


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def file_mode(path: str) -> int:
    return os.stat(path).st_mode & 0o777


def check_key(value: str) -> str:
    if not value or any(c in value for c in "\r\n\x00 "):
        raise RuntimeError("OPENROUTER_API_KEY is missing or not a single token")
    return value


def openrouter_key() -> str:
    env = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if env:
        return check_key(env)
    if not ENV_FILE:
        raise RuntimeError("OPENROUTER_API_KEY is not set")
    if file_mode(ENV_FILE) & 0o077:
        raise RuntimeError("env file is readable by group or other")
    value = ""
    with open(ENV_FILE, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, raw = line.split("=", 1)
            if name.strip() == "OPENROUTER_API_KEY":
                value = raw.strip()
    return check_key(value)


def allowed_github(host: str) -> bool:
    return host.lower().rstrip(".") in GITHUB


def allowed_openrouter(host: str) -> bool:
    host = host.lower().rstrip(".")
    return host == "openrouter.ai" or host.endswith(".openrouter.ai")


async def pipe(src: asyncio.StreamReader, dst: asyncio.StreamWriter) -> None:
    try:
        while chunk := await src.read(65536):
            dst.write(chunk)
            await dst.drain()
    except Exception:
        pass
    finally:
        try:
            dst.close()
        except Exception:
            pass


async def read_headers(reader: asyncio.StreamReader) -> list[bytes]:
    lines: list[bytes] = []
    size = 0
    while True:
        line = await asyncio.wait_for(reader.readline(), 30)
        if line in (b"", b"\r\n", b"\n"):
            if not line and not lines:
                raise EOFError
            break
        size += len(line)
        if len(line) > 16384 or size > 65536:
            raise ValueError("headers too large")
        lines.append(line)
    return lines


async def read_body(reader: asyncio.StreamReader, headers: list[bytes]) -> bytes:
    length = None
    chunked = False
    for line in headers:
        name, _, value = line.decode("latin1").partition(":")
        if name.lower() == "content-length":
            length = int(value.strip())
        elif name.lower() == "transfer-encoding" and "chunked" in value.lower():
            chunked = True
    if length is not None:
        if length > MAX_BODY:
            raise ValueError("body too large")
        return await reader.readexactly(length)
    if not chunked:
        return b""
    body = b""
    while True:
        size_line = await reader.readline()
        size = int(size_line.split(b";", 1)[0], 16)
        if size == 0:
            await reader.readline()
            return body
        if len(body) + size > MAX_BODY:
            raise ValueError("body too large")
        body += await reader.readexactly(size)
        await reader.readline()


def header_map(headers: list[bytes]) -> list[tuple[str, str]]:
    pairs = []
    for line in headers:
        name, sep, value = line.decode("latin1").partition(":")
        if sep:
            pairs.append((name.strip(), value.strip()))
    return pairs


async def tunnel(client_r: asyncio.StreamReader, client_w: asyncio.StreamWriter, host: str) -> None:
    try:
        remote_r, remote_w = await asyncio.wait_for(asyncio.open_connection(host, 443), 20)
    except Exception as exc:
        log(f"github connect failed {host}: {exc}")
        client_w.write(b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\n\r\n")
        await client_w.drain()
        return
    client_w.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
    await client_w.drain()
    await asyncio.gather(pipe(client_r, remote_w), pipe(remote_r, client_w))


def server_context() -> ssl.SSLContext:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(CERT, KEY)
    ctx.set_alpn_protocols(["http/1.1"])
    return ctx


async def forward_openrouter(host: str, method: str, target: str, headers: list[bytes], body: bytes, writer: asyncio.StreamWriter) -> None:
    key = openrouter_key()
    upstream = UPSTREAM_HOST or host
    pairs = [(n, v) for n, v in header_map(headers) if n.lower() not in {
        "authorization", "proxy-authorization", "proxy-connection", "connection",
        "transfer-encoding", "content-length", "host",
    }]
    pairs.append(("Host", upstream))
    pairs.append(("Authorization", "Bearer " + key))
    pairs.append(("Content-Length", str(len(body))))
    pairs.append(("Connection", "close"))
    request = (method + " " + target + " HTTP/1.1\r\n").encode()
    request += "".join(f"{n}: {v}\r\n" for n, v in pairs).encode() + b"\r\n" + body
    ssl_ctx = ssl.create_default_context() if UPSTREAM_TLS else None
    remote_r, remote_w = await asyncio.wait_for(
        asyncio.open_connection(upstream, UPSTREAM_PORT if UPSTREAM_HOST else 443, ssl=ssl_ctx), 20)
    try:
        remote_w.write(request)
        await remote_w.drain()
        while chunk := await asyncio.wait_for(remote_r.read(65536), 600):
            writer.write(chunk)
            await writer.drain()
    finally:
        remote_w.close()


async def mitm(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, host: str) -> None:
    writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
    await writer.drain()
    await writer.start_tls(server_context())
    while True:
        try:
            head = await read_headers(reader)
        except (EOFError, asyncio.IncompleteReadError, ConnectionError):
            return
        parts = head[0].decode("latin1").split()
        if len(parts) < 2:
            return
        method, target = parts[0], parts[1]
        path = target.split("?", 1)[0]
        if ".." in path or not path.startswith("/"):
            writer.write(b"HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
            await writer.drain()
            return
        body = await read_body(reader, head[1:])
        log(f"openrouter {method} {path}")
        try:
            await forward_openrouter(host, method, target, head[1:], body, writer)
        except Exception as exc:
            log(f"openrouter failed {type(exc).__name__}")
            writer.write(b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
            await writer.drain()
        return


async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        head = await read_headers(reader)
        parts = head[0].decode("latin1").split()
        if len(parts) < 2:
            return
        method, target = parts[0], parts[1]
        if method == "CONNECT":
            host, _, port = target.partition(":")
            if port != "443" or not host or any(c in host for c in " /\\"):
                raise PermissionError(target)
            if allowed_github(host):
                log(f"allow {host}")
                await tunnel(reader, writer, host)
                return
            if allowed_openrouter(host):
                await mitm(reader, writer, host.lower().rstrip("."))
                return
            raise PermissionError(host)
        if method == "GET" and target.split("?", 1)[0] == "/health":
            body = b"pi-container-proxy\n"
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: %d\r\nConnection: close\r\n\r\n%s" % (len(body), body))
            await writer.drain()
            return
        raise PermissionError(target)
    except PermissionError as exc:
        log(f"deny {exc}")
        writer.write(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
        await writer.drain()
    except Exception as exc:
        log(f"error {type(exc).__name__}")
        try:
            writer.write(b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
            await writer.drain()
        except Exception:
            pass
    finally:
        try:
            writer.close()
        except Exception:
            pass


def openssl(args: list[str]) -> None:
    # Key generation writes a progress meter to stderr. That is the wall of
    # symbols in `container logs`, and it is not a failure.
    subprocess.run(args, check=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def ensure_certs() -> None:
    if os.path.isfile(CERT) and os.path.isfile(KEY) and os.path.isfile(CA):
        return
    os.makedirs(os.path.dirname(CERT), exist_ok=True)
    os.makedirs(os.path.dirname(CA), exist_ok=True)
    openssl(
        ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-sha256", "-days", "3650", "-nodes",
         "-keyout", os.path.join(os.path.dirname(CERT), "ca.key"), "-out", CA, "-subj", "/CN=pi-container proxy"])
    csr = os.path.join(os.path.dirname(CERT), "openrouter.csr")
    ext = os.path.join(os.path.dirname(CERT), "openrouter.ext")
    openssl(
        ["openssl", "req", "-newkey", "rsa:2048", "-nodes", "-keyout", KEY, "-out", csr, "-subj", "/CN=openrouter.ai"])
    with open(ext, "w", encoding="utf-8") as fh:
        fh.write("subjectAltName=DNS:openrouter.ai,DNS:*.openrouter.ai\nbasicConstraints=CA:FALSE\nextendedKeyUsage=serverAuth\n")
    openssl(
        ["openssl", "x509", "-req", "-in", csr, "-CA", CA,
         "-CAkey", os.path.join(os.path.dirname(CERT), "ca.key"),
         "-CAserial", os.path.join(os.path.dirname(CERT), "ca.srl"), "-CAcreateserial",
         "-out", CERT, "-days", "825", "-sha256", "-extfile", ext])
    os.chmod(CA, 0o644)
    for path in (KEY, CERT, os.path.join(os.path.dirname(CERT), "ca.key")):
        os.chmod(path, 0o600)
    os.remove(csr)
    os.remove(ext)


def iface_ipv4(name: str) -> str | None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        packed = struct.pack("256s", name.encode()[:15])
        return socket.inet_ntoa(fcntl_ioctl(sock, packed)[20:24])
    except OSError:
        return None
    finally:
        sock.close()


def fcntl_ioctl(sock: socket.socket, packed: bytes) -> bytes:
    import fcntl
    return fcntl.ioctl(sock.fileno(), 0x8915, packed)


def default_iface() -> str | None:
    try:
        lines = open("/proc/net/route", encoding="utf-8").read().splitlines()[1:]
    except OSError:
        return None
    for line in lines:
        iface, dest, *_rest = line.split()
        if dest == "00000000":
            return iface
    return None


def locked_ip() -> str | None:
    """Address on the interface that is not the default route.

    The proxy container is on two networks. The first, the default route, is
    the one with internet. Pi shares only the other network, and that is the
    only address this proxy listens on.
    """
    forced = os.environ.get("PI_PROXY_BIND", "")
    if forced:
        return forced
    default = default_iface()
    if not default:
        return None
    try:
        names = sorted(os.listdir("/sys/class/net"))
    except OSError:
        return None
    chosen = None
    for name in names:
        if name == "lo" or name == default:
            continue
        ip = iface_ipv4(name)
        if ip and ip != "0.0.0.0":
            chosen = ip
    return chosen


def clear_addr() -> None:
    try:
        os.remove(ADDR)
    except OSError:
        pass


def publish_addr(bind: str) -> None:
    """Tell the Mac which address this process bound, so Pi can use it as its proxy."""
    directory = os.path.dirname(ADDR)
    if directory:
        os.makedirs(directory, exist_ok=True)
    tmp = ADDR + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(bind + "\n")
        fh.flush()
        os.fsync(fh.fileno())
    os.chmod(tmp, 0o644)
    os.replace(tmp, ADDR)


def main() -> None:
    clear_addr()
    try:
        openrouter_key()
        ensure_certs()
    except Exception as exc:
        raise SystemExit(f"proxy: {exc}") from exc
    bind = None
    for _ in range(50):
        bind = locked_ip()
        if bind:
            break
        time.sleep(0.1)
    if not bind:
        raise SystemExit("proxy: no address on the locked network")

    async def serve() -> None:
        server = await asyncio.start_server(handle, bind, PORT)
        publish_addr(bind)
        log(f"listening {bind}:{PORT}")
        async with server:
            await server.serve_forever()

    asyncio.run(serve())


if __name__ == "__main__":
    main()
