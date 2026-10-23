#!/usr/bin/env python3
"""Host proxy for the Pi container.

Tunnels GitHub. Terminates TLS for openrouter.ai and adds the real API key,
which never enters the container. Refuses every other destination.
"""
from __future__ import annotations

import asyncio
import os
import ssl
import sys

GITHUB = {
    "github.com",
    "api.github.com",
    "codeload.github.com",
    "objects.githubusercontent.com",
    "raw.githubusercontent.com",
    "uploads.github.com",
}
MAX_BODY = 64 * 1024 * 1024
ENV_FILE = os.environ["PI_ENV_FILE"]
CERT = os.environ["PI_PROXY_CERT"]
KEY = os.environ["PI_PROXY_KEY"]
PORT = int(os.environ.get("PI_PROXY_PORT", "8888"))
BIND = os.environ.get("PI_PROXY_BIND", "127.0.0.1")
UPSTREAM_HOST = os.environ.get("PI_PROXY_OPENROUTER_HOST", "")
UPSTREAM_PORT = int(os.environ.get("PI_PROXY_OPENROUTER_PORT", "443"))
UPSTREAM_TLS = os.environ.get("PI_PROXY_OPENROUTER_TLS", "1") != "0"


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def file_mode(path: str) -> int:
    return os.stat(path).st_mode & 0o777


def openrouter_key() -> str:
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
    if not value or any(c in value for c in "\r\n\x00 "):
        raise RuntimeError("OPENROUTER_API_KEY is missing or not a single token")
    return value


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


def main() -> None:
    if file_mode(ENV_FILE) & 0o077:
        raise SystemExit(f"proxy: chmod 600 {ENV_FILE}")
    openrouter_key()
    if not os.path.isfile(CERT) or not os.path.isfile(KEY):
        raise SystemExit("proxy: missing TLS certificate; start it from run.sh")

    async def serve() -> None:
        server = await asyncio.start_server(handle, BIND, PORT)
        log(f"listening {BIND}:{PORT}")
        async with server:
            await server.serve_forever()

    asyncio.run(serve())


if __name__ == "__main__":
    main()
