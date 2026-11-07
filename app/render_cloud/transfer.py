"""Bounded streaming of signed object URLs; no redirects or arbitrary hosts."""
from __future__ import annotations

import hashlib
import ipaddress
import socket
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlsplit

import httpx


class TransientTransferError(RuntimeError):
    pass


def retry_transfer(operation, should_cancel=None, *, sleep=time.sleep):
    """Retry only idempotent per-object transfers, never Pod creation/rendering."""
    for attempt in range(3):
        if should_cancel and should_cancel():
            raise InterruptedError('Asset transfer cancelled')
        try:
            return operation()
        except (httpx.HTTPError, TransientTransferError):
            if attempt==2:
                raise RuntimeError('Object transfer unavailable after bounded retries') from None
            for _ in range(10 * 2**attempt):
                if should_cancel and should_cancel():
                    raise InterruptedError('Asset transfer cancelled')
                sleep(.1)


def validate_url(url: str, allowed_hosts: set[str], *, resolve=socket.getaddrinfo):
    parsed = urlsplit(url)
    if (parsed.scheme != 'https' or parsed.username or parsed.password or parsed.fragment
            or parsed.port not in {None, 443} or parsed.hostname not in allowed_hosts):
        raise ValueError('Unapproved object-storage URL')
    addresses = resolve(parsed.hostname, 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
        raise ValueError('Object storage must resolve to public addresses')
    # Deployment egress policy must also block private/metadata addresses: DNS can
    # change between validation and connection (application checks alone are not a firewall).


def download(spec, urls: dict, workspace: Path, allowed_hosts: set[str], *, client=None, should_cancel=None):
    if set(urls) != {asset.path for asset in spec.assets}:
        raise ValueError('Signed asset manifest mismatch')
    for url in urls.values():
        validate_url(url, allowed_hosts)
    own_client = client is None
    client = client or httpx.Client(timeout=60, follow_redirects=False, trust_env=False)

    def fetch(asset):
        target = workspace / asset.path
        if not target.resolve().is_relative_to(workspace.resolve()) or target.exists():
            raise ValueError('Unsafe download destination')
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_name('.transfer-' + uuid.uuid4().hex)
        count, digest = 0, hashlib.sha256()
        try:
            with client.stream('GET', urls[asset.path]) as response:
                if response.status_code != 200:
                    if response.status_code in {408,429,500,502,503,504}:
                        raise TransientTransferError('Temporary download failure')
                    raise RuntimeError('Asset download failed')
                with partial.open('xb') as output:
                    for block in response.iter_bytes(1024 * 1024):
                        if should_cancel and should_cancel():
                            raise InterruptedError('Asset transfer cancelled')
                        count += len(block)
                        if count > asset.size:
                            raise ValueError('Asset exceeds declared size')
                        digest.update(block)
                        output.write(block)
            if count != asset.size or digest.hexdigest() != asset.sha256:
                raise ValueError('Downloaded asset integrity failed')
            partial.replace(target)
        finally:
            partial.unlink(missing_ok=True)
    try:
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda asset:retry_transfer(lambda:fetch(asset),should_cancel), spec.assets))
    finally:
        if own_client:
            client.close()


def upload(path: Path, url: str, allowed_hosts: set[str], *, should_cancel=None):
    validate_url(url, allowed_hosts)
    def blocks():
        with path.open('rb') as source:
            for block in iter(lambda: source.read(1024 * 1024), b''):
                if should_cancel and should_cancel():
                    raise InterruptedError('Output upload cancelled')
                yield block
    with httpx.Client(timeout=120, follow_redirects=False, trust_env=False) as client:
        def put():
            response = client.put(url, content=blocks(), headers={'Content-Length': str(path.stat().st_size)})
            if response.status_code in {408,429,500,502,503,504}:
                raise TransientTransferError('Temporary upload failure')
            if not response.is_success:
                raise RuntimeError('Output upload failed')
        retry_transfer(put,should_cancel)
