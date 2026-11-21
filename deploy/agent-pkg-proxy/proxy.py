"""A forward proxy for the agent network that opens ONLY the package registries (npm, PyPI), so bare Claude can install packages the way Claude
does elsewhere. The agent network has no internet; this container sits on it and on a normal network. HTTPS only (CONNECT); every other host,
port or method is refused and logged."""
import asyncio
import logging
import os

ALLOWED = {h.strip().lower() for h in os.environ.get("ALLOWED_HOSTS", "registry.npmjs.org,registry.yarnpkg.com,pypi.org,files.pythonhosted.org").split(",") if h.strip()}
PORT = int(os.environ.get("PORT", "3128"))
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("pkg-proxy")


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


async def handle(reader, writer):
    peer = writer.get_extra_info("peername")
    try:
        head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 20)
        method, target, _ = head.split(b"\r\n", 1)[0].decode("latin-1").split(" ", 2)
        host, _, port = target.rpartition(":")
        host = host.strip("[]").lower()
        if method != "CONNECT" or port != "443" or host not in ALLOWED:
            log.info("refused %s %s from %s", method, target, peer)
            writer.write(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n")
            await writer.drain()
            writer.close()
            return
        upstream_reader, upstream_writer = await asyncio.wait_for(asyncio.open_connection(host, 443), 20)
        writer.write(b"HTTP/1.1 200 Connection established\r\n\r\n")
        await writer.drain()
        log.info("open %s", host)
        await asyncio.gather(pipe(reader, upstream_writer), pipe(upstream_reader, writer))
    except Exception as exc:
        log.info("error from %s: %s", peer, type(exc).__name__)
        try:
            writer.close()
        except Exception:
            pass


async def main():
    server = await asyncio.start_server(handle, "0.0.0.0", PORT)
    log.info("package proxy on %d for %s", PORT, sorted(ALLOWED))
    async with server:
        await server.serve_forever()


asyncio.run(main())
