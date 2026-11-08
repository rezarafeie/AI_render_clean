"""When a linked page cannot be read the studio searches the web through the AI router and reads the best results instead."""
import httpx
import pytest

from app import studio_orchestrator as orchestrator
from brain import lm_gateway

DIGIKALA = ("https://www.digikala.com/product/dkp-11801878/%D9%87%D8%AF%D9%81%D9%88%D9%86%20%D8%A8%D9%84%D9%88%D8%AA%D9%88%D8%AB%DB%8C%20"
            "%D8%A7%D9%86%DA%A9%D8%B1%20%D9%85%D8%AF%D9%84%20SoundCore%20R50i%20A3949/?variant_id=68550739")


def test_the_query_is_the_product_named_in_the_address_without_its_numeric_ids():
    query = orchestrator._search_query(DIGIKALA, "برای این محصول یه ریل بساز")
    assert "هدفون" in query and "SoundCore R50i A3949" in query and "digikala.com" in query
    assert "11801878" not in query and "dkp" not in query.lower()


def test_a_bare_address_borrows_the_start_of_the_request():
    query = orchestrator._search_query("https://example.com/p/42", "درباره‌ی دستگاه قهوه‌ساز https://example.com/p/42 توضیح بده")
    assert "قهوه‌ساز" in query and "https://" not in query


def _fake_gateway(monkeypatch, handler):
    monkeypatch.setattr(lm_gateway, "configured", lambda: True)
    monkeypatch.setattr(lm_gateway, "headers", lambda: {})
    monkeypatch.setattr(lm_gateway, "_url", lambda path: "https://router.test/v1/" + path)
    monkeypatch.setattr(lm_gateway, "_client", lambda timeout: httpx.Client(transport=httpx.MockTransport(handler)))


def test_router_search_returns_clean_results(monkeypatch):
    seen = {}
    def handler(request):
        seen["url"], seen["body"] = str(request.url), request.read().decode()
        return httpx.Response(200, json={"query": "q", "provider": "x", "results": [
            {"title": "A", "url": "https://a.test/x", "content": "alpha"}, {"title": "no url"}, {"title": "B", "url": "ftp://b", "content": "b"}]})
    _fake_gateway(monkeypatch, handler)
    rows = lm_gateway.search("soundcore r50i", count=4)
    assert rows == [{"title": "A", "url": "https://a.test/x", "content": "alpha"}]
    assert seen["url"].endswith("/v1/search") and '"max_results":4' in seen["body"].replace(" ", "")


def test_router_search_without_an_engine_raises(monkeypatch):
    _fake_gateway(monkeypatch, lambda request: httpx.Response(503, json={"error": {"message": "No search key configured", "code": "no_search_keys"}}))
    with pytest.raises(lm_gateway.GatewayError, match="503"):
        lm_gateway.search("anything")


def test_the_alternative_skips_the_failed_host_and_reads_the_first_page_that_works(monkeypatch):
    emitted, read = [], []
    monkeypatch.setattr(orchestrator, "_emit", lambda *a, **k: emitted.append((a, k)))
    monkeypatch.setattr(lm_gateway, "search", lambda query, count=5: [
        {"title": "same host", "url": "https://www.digikala.com/other", "content": ""},
        {"title": "dead", "url": "https://dead.test/p", "content": ""},
        {"title": "good", "url": "https://good.test/p", "content": ""}])
    def read_page(conversation_id, user_key, url, **kwargs):
        read.append((url, kwargs.get("allow_search"), kwargs.get("quiet")))
        return {"url": url, "title": "t", "text": "x" * 100, "images": ["i.jpg"]} if "good" in url else None
    monkeypatch.setattr(orchestrator, "_read_page", read_page)
    item = orchestrator._read_alternative("c", "u", DIGIKALA, "request", None, False)
    assert item["url"] == "https://good.test/p" and item["found_by_search"] and item["requested_url"] == DIGIKALA
    assert [r[0] for r in read] == ["https://dead.test/p", "https://good.test/p"]      # the failed host itself is never retried
    assert all(r[1] is False and r[2] is True for r in read)                            # no second search, no failure noise for alternatives
    assert emitted and emitted[0][1]["tool"] == "inspect_url"


def test_no_search_engine_means_no_alternative_and_the_old_failure_message(monkeypatch):
    def refuse(query, count=5):
        raise lm_gateway.GatewayError("no engine", 503)
    monkeypatch.setattr(lm_gateway, "search", refuse)
    assert orchestrator._read_alternative("c", "u", DIGIKALA, "", None, False) is None


def test_read_page_tries_the_search_fallback_when_the_page_does_not_open(monkeypatch, tmp_path):
    from app import studio_tools
    def unreachable(name, arguments):
        raise ValueError("This site can’t be reached")
    monkeypatch.setattr(orchestrator, "execute", unreachable)
    monkeypatch.setattr(orchestrator, "_emit", lambda *a, **k: None)
    monkeypatch.setattr(orchestrator, "_read_alternative", lambda *a, **k: {"url": "https://good.test/p", "found_by_search": True})
    assert orchestrator._read_page("c", "u", DIGIKALA, directory=tmp_path)["found_by_search"] is True
    called = []
    monkeypatch.setattr(orchestrator, "_read_alternative", lambda *a, **k: called.append(1))
    from app import studio_narrator
    monkeypatch.setattr(studio_narrator, "narrate", lambda *a, **k: None)
    assert orchestrator._read_page("c", "u", DIGIKALA, directory=tmp_path, allow_search=False, quiet=True) is None and called == []
