"""Safe public-page inspection for Studio motion-video projects.

Static HTML first; empty application shells use an isolated browser whose
requests all pass through this public-address/redirect-validated fetcher.
"""
from __future__ import annotations

import concurrent.futures
import http.client
import ipaddress
import json
import os
import re
import socket
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import certifi
from PIL import Image

MAX_HTML = 3 * 1024 * 1024
MAX_SCRIPT = 12 * 1024 * 1024
MAX_IMAGE = 12 * 1024 * 1024
MAX_REDIRECTS = 5
USER_AGENT = "RafieiVideoStudio/1.0"


def _public_url(value: str) -> str:
    parsed = urllib.parse.urlsplit(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Only public HTTP/HTTPS URLs are supported")
    try:
        addresses = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror as exc:
        raise ValueError("The page hostname could not be resolved") from exc
    if not addresses:
        raise ValueError("The page hostname could not be resolved")
    for item in addresses:
        address = ipaddress.ip_address(item[4][0])
        if not address.is_global:
            raise ValueError("Private, loopback and reserved addresses are not allowed")
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path or "/", parsed.query, ""))


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


_DIRECT_FAILED: dict[str, float] = {}
DIRECT_WAIT_S = 4.0
_DIRECT_POOL = concurrent.futures.ThreadPoolExecutor(max_workers=8, thread_name_prefix="direct-fetch")


def _relay_configured() -> bool:
    from app.page_relay import config
    return bool(config()[0])


def _relay_public_url(value: str) -> str:
    """Validate syntax/literal addresses; relay independently checks DNS and redirects.

    Never connect locally to an address rejected by _public_url. A local DNS
    sinkhole must not prevent the authenticated relay resolving a public host.
    """
    p = urllib.parse.urlsplit(value.strip())
    if p.scheme not in {'http','https'} or not p.hostname or p.username or p.password:
        raise ValueError('Only public HTTP/HTTPS URLs are supported')
    host=p.hostname.lower()
    if host=='localhost' or host.endswith(('.localhost','.local','.internal')):
        raise ValueError('Private host is not allowed')
    try: address=ipaddress.ip_address(host)
    except ValueError: address=None
    if address is not None and not address.is_global:
        raise ValueError('Private address is not allowed')
    return urllib.parse.urlunsplit((p.scheme,p.netloc,p.path or '/',p.query,''))


_STATIC_TTL_S = 7 * 24 * 3600
_STATIC_KINDS = {"application/javascript", "text/javascript", "text/css", "font/woff2", "font/woff", "application/font-woff2"}


def _static_cache_path(url: str) -> Path:
    from app.config import settings
    import hashlib
    return Path(settings.JOBS_DIR) / "relay_cache" / (hashlib.sha256(url.encode()).hexdigest() + ".bin")


def _relay_fetch(url: str, *, max_bytes: int, accept: str, allow_http_error: bool, with_status: bool):
    """The Vercel relay fetches the page from outside the blocked network. Same limits, same result shape as the direct fetch.
    The link back from the relay is slow (a 2 MB script takes half a minute), so scripts, styles and fonts are kept for a week:
    a site's bundle is named after its content, and only its first reading pays for it."""
    import httpx
    from app.page_relay import config
    relay_url, relay_secret = config()
    cached = _static_cache_path(url)
    try:
        if cached.is_file() and time.time() - cached.stat().st_mtime < _STATIC_TTL_S:
            meta, _, body = cached.read_bytes().partition(b"\n")
            kind, final = json.loads(meta)
            result = (body, final, kind, 200)
            return result if with_status else result[:3]
    except (OSError, ValueError):
        pass
    response = None
    for attempt in range(3):                                      # a name lookup or connection can fail once on a busy host
        try:
            with httpx.Client(timeout=httpx.Timeout(45, connect=10)) as client:
                response = client.post(relay_url, json={"url": url, "mode": "page"},
                                       headers={"x-relay-secret": relay_secret, "x-relay-accept": accept})
            break
        except httpx.TransportError:
            if attempt == 2:
                raise
            time.sleep(1.5)
    if response.status_code != 200:
        raise ValueError(f"The relay could not fetch the page (HTTP {response.status_code})")
    data = response.content
    if len(data) > max_bytes:
        raise ValueError("The remote resource is too large")
    status = int(response.headers.get("x-upstream-status") or 200)
    if status >= 400 and not allow_http_error:
        raise ValueError(f"The page returned HTTP {status}")
    final = urllib.parse.unquote(response.headers.get("x-final-url") or url)
    content_type = (response.headers.get("content-type") or "").split(";")[0].strip().lower()
    if status == 200 and content_type in _STATIC_KINDS and len(data) > 20_000:
        try:
            cached.parent.mkdir(parents=True, exist_ok=True)
            temporary = cached.with_suffix(".tmp")
            temporary.write_bytes(json.dumps([content_type, final]).encode() + b"\n" + data)
            temporary.replace(cached)
        except OSError:
            pass
    return (data, final, content_type, status) if with_status else (data, final, content_type)


def _relay_or_direct(url: str, *, max_bytes: int, accept: str, headers: dict[str, str] | None, timeout: float,
                     allow_http_error: bool, with_status: bool):
    """The relay answers for hosts this network cannot reach. A host the relay cannot reach itself (an Iranian shop that refuses foreign addresses)
    was only given a few seconds directly, which a busy server can miss: when the relay fails too, ask the host directly once more, with the full timeout."""
    host = urllib.parse.urlsplit(url).hostname or ""
    try:
        return _relay_fetch(url, max_bytes=max_bytes, accept=accept, allow_http_error=allow_http_error, with_status=with_status)
    except Exception as relay_error:
        try:
            result = _fetch_direct(url, max_bytes=max_bytes, accept=accept, headers=headers, timeout=timeout,
                                   allow_http_error=allow_http_error, with_status=with_status)
        except Exception:
            raise relay_error
        _DIRECT_FAILED.pop(host, None)          # it does answer directly: stop sending it to the relay
        return result


def _fetch(url: str, *, max_bytes: int, accept: str,
           headers: dict[str, str] | None = None, timeout: float = 20, allow_http_error: bool = False, with_status: bool = False):
    """Directly first; when this network cannot reach the host (reset, timeout) the relay outside it answers instead."""
    if not _relay_configured():
        return _fetch_direct(url, max_bytes=max_bytes, accept=accept, headers=headers, timeout=timeout,
                             allow_http_error=allow_http_error, with_status=with_status)
    url = _relay_public_url(url)
    host = urllib.parse.urlsplit(url).hostname or ""
    if time.monotonic() < _DIRECT_FAILED.get(host, 0):          # this host just failed directly: do not wait for it again for every image and script
        return _relay_or_direct(url, max_bytes=max_bytes, accept=accept, headers=headers, timeout=timeout,
                                allow_http_error=allow_http_error, with_status=with_status)
    # A host this network half-reaches answers slowly rather than failing: give the direct attempt a hard wall-clock limit.
    attempt = _DIRECT_POOL.submit(_fetch_direct, url, max_bytes=max_bytes, accept=accept, headers=headers, timeout=min(timeout, 8),
                                  allow_http_error=allow_http_error, with_status=with_status)
    try:
        return attempt.result(timeout=DIRECT_WAIT_S)
    except (urllib.error.URLError, OSError, http.client.HTTPException, TimeoutError, concurrent.futures.TimeoutError):
        _DIRECT_FAILED[host] = time.monotonic() + 300
        return _relay_or_direct(url, max_bytes=max_bytes, accept=accept, headers=headers, timeout=timeout,
                                allow_http_error=allow_http_error, with_status=with_status)
    except ValueError as exc:
        if str(exc) not in {'Private, loopback and reserved addresses are not allowed', 'The page hostname could not be resolved', 'The page returned HTTP 403'}:
            raise
        _DIRECT_FAILED[host] = time.monotonic() + 300
        return _relay_or_direct(url, max_bytes=max_bytes, accept=accept, headers=headers, timeout=timeout,
                                allow_http_error=allow_http_error, with_status=with_status)


def _render_relay_or_direct(url: str, output: Path) -> dict:
    """The relay's browser first; a site it cannot reach is rendered by this server's own browser instead."""
    from .public_page_browser import render_page, render_page_via_relay
    host = urllib.parse.urlsplit(url).hostname or ""
    try:
        return render_page_via_relay(url, output)
    except Exception as relay_error:
        try:
            result = render_page(url, output)
        except Exception:
            raise relay_error
        _DIRECT_FAILED.pop(host, None)
        return result


def _render(url: str, output: Path) -> dict:
    """Render a page that needs a browser. A host this network cannot reach (or a local browser that failed) is rendered by the relay instead."""
    from .public_page_browser import render_page, render_page_via_relay
    if not _relay_configured():
        return render_page(url, output)
    host = urllib.parse.urlsplit(url).hostname or ""
    if time.monotonic() < _DIRECT_FAILED.get(host, 0):
        return _render_relay_or_direct(url, output)
    try:
        return render_page(url, output)
    except (OSError, ValueError):
        return _render_relay_or_direct(url, output)


def _fetch_direct(url: str, *, max_bytes: int, accept: str,
                  headers: dict[str, str] | None = None, timeout: float = 20, allow_http_error: bool = False, with_status: bool = False):
    # The python.org macOS runtime does not always inherit the system Keychain
    # roots. Use certifi's maintained CA bundle while keeping verification and
    # hostname checks fully enabled (never fall back to an unverified context).
    tls_context = ssl.create_default_context(cafile=certifi.where())
    opener = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=tls_context),
        _NoRedirect,
    )
    current = _public_url(url)
    for _ in range(MAX_REDIRECTS + 1):
        request_headers = {"User-Agent": USER_AGENT, "Accept": accept, **(headers or {})}
        request = urllib.request.Request(current, headers=request_headers)
        try:
            response = opener.open(request, timeout=timeout)
        except urllib.error.HTTPError as exc:
            if exc.code in {301, 302, 303, 307, 308}:
                target = exc.headers.get("Location")
                if not target:
                    raise ValueError("The page returned an invalid redirect") from exc
                current = _public_url(urllib.parse.urljoin(current, target))
                continue
            if not allow_http_error:
                raise ValueError(f"The page returned HTTP {exc.code}") from exc
            response = exc  # Browser evidence may show a real blocked/error page, never a fabricated success.
        content_type = (response.headers.get_content_type() or "").lower()
        status = int(getattr(response, "status", None) or getattr(response, "code", 200) or 200)
        declared = response.headers.get("Content-Length")
        if declared and int(declared) > max_bytes:
            raise ValueError("The remote resource is too large")
        data = response.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise ValueError("The remote resource is too large")
        return (data, current, content_type, status) if with_status else (data, current, content_type)
    raise ValueError("The page redirected too many times")


def _candidate_from_srcset(value: str) -> list[str]:
    return [part.strip().split()[0] for part in value.split(",") if part.strip()]


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.description = ""
        self.text: list[str] = []
        self.images: list[dict[str, str]] = []
        self.structured: list[Any] = []
        self.scripts: list[str] = []
        self._capture: str | None = None
        self._buffer: list[str] = []
        self._json_ld = False

    def handle_starttag(self, tag: str, attrs_list: list[tuple[str, str | None]]) -> None:
        attrs = {k.lower(): (v or "") for k, v in attrs_list}
        tag = tag.lower()
        if tag == "title":
            self._capture, self._buffer = "title", []
        elif tag in {"h1", "h2", "h3", "p", "li"}:
            self._capture, self._buffer = "text", []
        elif tag == "script" and attrs.get("type", "").lower() == "application/ld+json":
            self._capture, self._buffer, self._json_ld = "json", [], True
        elif tag == "script" and attrs.get("src"):
            self.scripts.append(attrs["src"])
        elif tag == "meta":
            key = (attrs.get("property") or attrs.get("name") or "").lower()
            content = attrs.get("content", "").strip()
            if key in {"description", "og:description", "twitter:description"} and content and not self.description:
                self.description = content
            if key in {"og:image", "twitter:image", "twitter:image:src"} and content:
                self.images.append({"url": content, "alt": "social preview"})
        elif tag in {"img", "source"}:
            alt = attrs.get("alt", "").strip()
            for candidate in [attrs.get("src", ""), attrs.get("data-src", ""), attrs.get("data-lazy-src", ""), *_candidate_from_srcset(attrs.get("srcset", ""))]:
                if candidate:
                    self.images.append({"url": candidate, "alt": alt})

    def handle_endtag(self, tag: str) -> None:
        if self._capture == "title" and tag.lower() == "title":
            self.title = " ".join(self._buffer).strip()
            self._capture = None
        elif self._capture == "text" and tag.lower() in {"h1", "h2", "h3", "p", "li"}:
            value = re.sub(r"\s+", " ", " ".join(self._buffer)).strip()
            if len(value) >= 2:
                self.text.append(value)
            self._capture = None
        elif self._capture == "json" and tag.lower() == "script":
            try:
                self.structured.append(json.loads("".join(self._buffer)))
            except (TypeError, ValueError):
                pass
            self._capture, self._json_ld = None, False

    def handle_data(self, data: str) -> None:
        if self._capture:
            self._buffer.append(data)


def _walk_json_images(value: Any) -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key.lower() in {"image", "images", "contenturl", "thumbnailurl"}:
                if isinstance(item, str):
                    found.append(item)
                elif isinstance(item, list):
                    found.extend(x for x in item if isinstance(x, str))
            found.extend(_walk_json_images(item))
    elif isinstance(value, list):
        for item in value:
            found.extend(_walk_json_images(item))
    return found


def _structured_products(value: Any) -> list[dict]:
    items: list[dict] = []
    if isinstance(value, dict):
        kind = value.get("@type")
        kinds = kind if isinstance(kind, list) else [kind]
        if any(str(item).lower() == "product" for item in kinds):
            items.append({k: value.get(k) for k in ("name", "description", "brand", "sku", "offers", "category") if value.get(k)})
        for child in value.values():
            items.extend(_structured_products(child))
    elif isinstance(value, list):
        for child in value:
            items.extend(_structured_products(child))
    return items


def _spa_product(parser: PageParser, base: str) -> dict | None:
    """Resolve a public product from a Supabase-backed SPA without running JS.

    Some storefronts expose only an empty app shell but load a public product
    row through Supabase. We inspect same-origin bundles for the public project
    URL and anon token, then issue the exact read that the storefront performs.
    The token is never persisted or returned.
    """
    match = re.search(r"/product/([0-9a-f-]{36})(?:/|$)", urllib.parse.urlsplit(base).path, re.I)
    if not match:
        return None
    product_id = match.group(1)
    page_host = urllib.parse.urlsplit(base).hostname
    for script in parser.scripts[:8]:
        script_url = urllib.parse.urljoin(base, script)
        if urllib.parse.urlsplit(script_url).hostname != page_host:
            continue
        try:
            raw, _resolved, _kind = _fetch(script_url, max_bytes=MAX_SCRIPT, accept="application/javascript,text/javascript")
        except (OSError, ValueError, urllib.error.URLError):
            continue
        source = raw.decode("utf-8", errors="ignore")
        credentials = re.search(
            r'"(https://[a-z0-9-]+\.supabase\.co)".{0,300}?"(eyJ[A-Za-z0-9._-]{100,})"',
            source,
        )
        if not credentials:
            continue
        endpoint, anon_key = credentials.groups()
        query = urllib.parse.urlencode({"id": f"eq.{product_id}", "status": "eq.active", "select": "*"})
        try:
            payload, _url, _kind = _fetch(
                f"{endpoint}/rest/v1/products?{query}", max_bytes=MAX_HTML, accept="application/json",
                headers={"apikey": anon_key, "Authorization": f"Bearer {anon_key}"},
            )
            rows = json.loads(payload)
        except (OSError, ValueError, urllib.error.URLError, json.JSONDecodeError):
            continue
        if isinstance(rows, list) and rows and isinstance(rows[0], dict):
            row = rows[0]
            # Never return arbitrary embedded HTML/JS from a remote row.
            return {key: value for key, value in row.items()
                    if key not in {"landing_page_html", "custom_html", "custom_js"}}
    return None


def inspect_page(url: str, output_dir: Path) -> dict:
    try:
        html, final_url, content_type = _fetch(url, max_bytes=MAX_HTML, accept="text/html,application/xhtml+xml")
    except ValueError as exc:
        if 'page returned HTTP' not in str(exc): raise
        html, final_url, content_type = b'', _public_url(url), 'text/html'
    if "html" not in content_type:
        raise ValueError("The URL did not return an HTML page")
    parser = PageParser()
    parser.feed(html.decode("utf-8", errors="replace"))
    base = final_url
    spa_product = None
    if not parser.text and not _structured_products(parser.structured):
        spa_product = _spa_product(parser, base)
        if spa_product:
            name = spa_product.get("name_fa") or spa_product.get("name_en") or spa_product.get("name")
            description = (spa_product.get("description_fa") or spa_product.get("description_en")
                           or spa_product.get("description"))
            normalized_product = {
                "@type": "Product",
                "name": name,
                "description": description,
                "sku": spa_product.get("sku"),
                "category": spa_product.get("category"),
                "offers": {"price": spa_product.get("price"), "currency": spa_product.get("currency")},
                "images": spa_product.get("images") or spa_product.get("image") or [],
            }
            parser.structured.append({key: value for key, value in normalized_product.items() if value not in (None, "", [])})
            parser.text.extend(str(value) for value in (name, description) if value)
    screenshots = []
    browser_error = None
    if sum(len(t) for t in parser.text) < 80 and not _structured_products(parser.structured):
        try:
            rendered = _render(base, output_dir / 'page_screenshots')
            screenshots = rendered.get('screenshots', [])
            parser.title = rendered.get('title') or parser.title
            parser.text.extend(line.strip() for line in rendered.get('content', '').splitlines() if len(line.strip()) >= 2)
            parser.images.extend(rendered.get('images', []))
        except (OSError, ValueError) as exc:
            browser_error = str(exc)[:300]
    # Product evidence outranks site-wide social previews (often a screenshot
    # of the SaaS homepage rather than the requested product).
    candidates = []
    for document in parser.structured:
        candidates.extend({"url": item, "alt": "structured product image", "role": "product"} for item in _walk_json_images(document))
    if spa_product:
        embedded = PageParser()
        # Locale descriptions can contain different media. Do not discard the
        # Persian gallery merely because an English description also exists.
        for field in ('description_fa', 'description_en', 'description'):
            embedded.feed(str(spa_product.get(field) or ''))
        candidates.extend({**item, "role": "product"} for item in embedded.images)
    candidates.extend(item for item in parser.images if item.get("alt") != "social preview")
    if not candidates and not _structured_products(parser.structured):
        candidates.extend(parser.images)

    image_dir = output_dir / "url_images"
    image_dir.mkdir(parents=True, exist_ok=True)
    images: list[dict] = []
    seen: set[str] = set()
    seen_content: set[str] = set()
    for candidate in candidates:
        if len(images) >= 12:
            break
        absolute = urllib.parse.urljoin(base, candidate["url"])
        if absolute in seen or absolute.startswith("data:"):
            continue
        seen.add(absolute)
        try:
            raw, resolved, media_type = _fetch(absolute, max_bytes=MAX_IMAGE, accept="image/*")
            if not media_type.startswith("image/"):
                continue
            import hashlib
            digest = hashlib.sha256(raw).hexdigest()
            if digest in seen_content:
                continue
            suffix = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}.get(media_type, ".img")
            path = image_dir / f"image_{len(images) + 1:02d}{suffix}"
            path.write_bytes(raw)
            with Image.open(path) as image:
                image.verify()
            with Image.open(path) as image:
                width, height = image.size
            if width < 280 or height < 280:
                path.unlink(missing_ok=True)
                continue
            seen_content.add(digest)
            images.append({"url": resolved, "file": str(path), "alt": candidate.get("alt", "")[:300], "width": width, "height": height, "role": candidate.get("role", "page_image"), "sha256": digest})
        except (OSError, ValueError, urllib.error.URLError):
            continue

    text = []
    seen_text: set[str] = set()
    for item in parser.text:
        normalized = item.strip()
        if normalized and normalized not in seen_text:
            seen_text.add(normalized)
            text.append(normalized)
        if sum(len(part) for part in text) > 18_000:
            break
    products = []
    for document in parser.structured:
        products.extend(_structured_products(document))
    if not text and not products and not screenshots:
        raise ValueError("متن صفحه قابل استخراج نبود و گرفتن اسکرین‌شات هم کامل نشد: " + (browser_error or 'صفحه محتوای قابل‌خواندن نداشت'))
    return {
        "url": final_url,
        "host": urllib.parse.urlsplit(final_url).hostname,
        "title": parser.title[:500],
        "description": parser.description[:1500],
        "content": text,
        "structured_products": products[:10],
        "images": images,
        "screenshots": screenshots,
        "extraction": "browser" if screenshots else "html",
    }
