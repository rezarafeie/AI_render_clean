"""A forward proxy for the agent network (which has no internet of its own), so bare Claude reaches the web the way Claude does elsewhere.

ALLOW_ALL=1 (the owner's choice, 2026-11-21): every public host, HTTPS (CONNECT) and plain HTTP. Otherwise only ALLOWED_HOSTS (npm, PyPI).
Never allowed in either mode: an address inside the server - loopback, private ranges (the database, Redis, the app, the other containers),
link-local / metadata, multicast, reserved - checked on the resolved address, so a public name that points inside is refused too."""
import asyncio
import ipaddress
import logging
import os
import socket

ALLOW_ALL = os.environ.get("ALLOW_ALL", "") == "1"
ALLOWED = {h.strip().lower() for h in os.environ.get("ALLOWED_HOSTS", "registry.npmjs.org,registry.yarnpkg.com,pypi.org,files.pythonhosted.org").split(",") if h.strip()}
PORT = int(os.environ.get("PORT", "3128"))
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("pkg-proxy")


def public_address(host: str, port: int) -> str | None:
    """The first public IP the host resolves to, or None when any resolved address is inside (private, loopback, link-local...)."""
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError:
        return None
    chosen = None
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global or ip.is_multicast:
            return None
        chosen = chosen or str(ip)
    return chosen


def allowed(host: str, port: int) -> bool:
    if port not in (80, 443) and not ALLOW_ALL:
        return False
    return ALLOW_ALL or host in ALLOWED


async def pipe(reader, writer):
    try:
        while data := await reader.read(65536):
            writer.write(data)
            await writer.drain()
    except Exception:
        pass
    finally:
        try:
            writer.close()
        except Exception:
            pass


async def refuse(writer, why, target, peer):
    log.info("refused %s (%s) from %s", target, why, peer)
    writer.write(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
    await writer.drain()
    writer.close()


async def handle(reader, writer):
    peer = writer.get_extra_info("peername")
    try:
        head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 20)
        first, rest = head.split(b"\r\n", 1)
        method, target, version = first.decode("latin-1").split(" ", 2)
        if method == "CONNECT":
            host, _, port = target.rpartition(":")
            host, port = host.strip("[]").lower(), int(port or 443)
        else:                                        # plain HTTP: an absolute URL in the request line
            if not target.startswith("http://"):
                return await refuse(writer, "not a proxy request", target, peer)
            hostport, _, path = target[7:].partition("/")
            host, _, port = hostport.partition(":")
            host, port = host.lower(), int(port or 80)
        if port not in (80, 443) or not allowed(host, port):
            return await refuse(writer, "not allowed", f"{host}:{port}", peer)
        address = await asyncio.to_thread(public_address, host, port)
        if not address:
            return await refuse(writer, "inside the server or unresolvable", f"{host}:{port}", peer)
        upstream_reader, upstream_writer = await asyncio.wait_for(asyncio.open_connection(address, port), 20)
        if method == "CONNECT":
            writer.write(b"HTTP/1.1 200 Connection established\r\n\r\n")
            await writer.drain()
        else:
            upstream_writer.write(f"{method} /{path} {version}\r\n".encode("latin-1") + rest)
            await upstream_writer.drain()
        log.info("open %s:%d", host, port)
        await asyncio.gather(pipe(reader, upstream_writer), pipe(upstream_reader, writer))
    except Exception as exc:
        log.info("error from %s: %s", peer, type(exc).__name__)
        try:
            writer.close()
        except Exception:
            pass


async def main():
    server = await asyncio.start_server(handle, "0.0.0.0", PORT)
    log.info("proxy on %d: %s", PORT, "every public host" if ALLOW_ALL else sorted(ALLOWED))
    async with server:
        await server.serve_forever()


asyncio.run(main())
