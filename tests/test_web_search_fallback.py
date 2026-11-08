"""When a linked page cannot be read the studio searches the web through the AI router and reads the best results instead."""
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


def _responses(text, urls=(), calls_only=False):
    if calls_only:
        return {"output": [{"type": "function_call", "name": "web_search", "arguments": "{}"}]}
    notes = [{"type": "url_citation", "url": url, "title": "t" + str(i), "start_index": 0, "end_index": len(text)} for i, url in enumerate(urls)]
    return {"output": [{"type": "web_search_call"}, {"type": "message", "content": [{"type": "output_text", "text": text, "annotations": notes}]}]}


def _route(monkeypatch, models, outcomes):
    monkeypatch.setattr(lm_gateway, "configured", lambda: True)
    monkeypatch.setattr(lm_gateway, "defaults", lambda: {"web_search": {"enabled": True, "models": models, "max_tokens": 1500}})
    asked = []
    def complete(route, messages, **kwargs):
        asked.append((route, kwargs["model_override"], kwargs["endpoint"], kwargs["extra"]))
        outcome = outcomes[len(asked) - 1]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome, {}
    monkeypatch.setattr(lm_gateway, "complete", complete)
    return asked


def test_search_returns_the_cited_sources_with_their_passages(monkeypatch):
    asked = _route(monkeypatch, ["m1"], [_responses("The R50i has 10 mm drivers.", ["https://a.test/x?utm_source=z", "https://b.test/y", "https://a.test/x"])])
    rows = lm_gateway.search("soundcore r50i", count=5)
    assert [r["url"] for r in rows] == ["https://a.test/x?utm_source=z", "https://b.test/y"]        # the same page cited twice is one source
    assert "10 mm" in rows[0]["content"]
    assert asked == [("web_search", "m1", "responses", {"tools": [{"type": "web_search"}]})]


def test_a_model_that_only_hands_back_a_tool_call_is_skipped(monkeypatch):
    asked = _route(monkeypatch, ["m1", "m2"], [_responses("", calls_only=True), _responses("facts", ["https://good.test/p"])])
    assert [r["url"] for r in lm_gateway.search("anything")] == ["https://good.test/p"]
    assert [a[1] for a in asked] == ["m1", "m2"]


def test_search_fails_clearly_when_no_model_produces_sources_or_the_route_is_missing(monkeypatch):
    _route(monkeypatch, ["m1"], [lm_gateway.GatewayError("boom", 502)])
    with pytest.raises(lm_gateway.GatewayError, match="boom"):
        lm_gateway.search("anything")
    monkeypatch.setattr(lm_gateway, "defaults", lambda: {})
    with pytest.raises(lm_gateway.GatewayError, match="not set up"):
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
