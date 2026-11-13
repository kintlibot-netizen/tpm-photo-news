"""Functional round, item 11: a feed that fails is skipped and listed as failed, and the others still load.
Nothing here touches the network: the download is replaced with a fake."""
import requests

import fetch

GOOD_RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>Good</title>
<link>https://good.example</link>
<item><title>Canon Announces R6 Mark III</title><link>https://good.example/r6</link>
<description>Canon says it is out.</description></item>
</channel></rss>"""
SETTINGS = {"timeout_seconds": 5, "retries": 0, "retry_pause_seconds": 0,
            "max_feed_megabytes": 10, "user_agent": "test"}


def config(*sources):
    return {"sources": list(sources), "fetch": SETTINGS}


def test_a_feed_that_cannot_connect_is_skipped_and_the_others_load(monkeypatch):
    def fake_download(url, settings):
        if "broken" in url:
            raise requests.ConnectionError("no route to host")
        return GOOD_RSS

    monkeypatch.setattr(fetch, "_download", fake_download)
    items, failures = fetch.fetch_all(config(
        {"name": "Broken", "type": "news", "url": "https://broken.example/feed"},
        {"name": "Good", "type": "news", "url": "https://good.example/feed"},
    ))
    assert [item.source for item in items] == ["Good"]
    assert "no route to host" in failures["Broken"]


def test_a_page_that_is_not_a_feed_gives_no_items_and_no_crash(monkeypatch):
    monkeypatch.setattr(fetch, "_download", lambda url, settings: b"<html><body>Not a feed</body></html>")
    items, _ = fetch.fetch_all(config({"name": "Html", "type": "news", "url": "https://html.example/"}))
    assert items == []


def test_an_unexpected_error_inside_one_feed_does_not_stop_the_run(monkeypatch):
    def fake_download(url, settings):
        if "odd" in url:
            raise KeyError("something the library did not expect")
        return GOOD_RSS

    monkeypatch.setattr(fetch, "_download", fake_download)
    items, failures = fetch.fetch_all(config(
        {"name": "Odd", "type": "news", "url": "https://odd.example/feed"},
        {"name": "Good", "type": "news", "url": "https://good.example/feed"},
    ))
    assert [item.source for item in items] == ["Good"]
    assert "Odd" in failures


def test_a_source_without_a_name_is_still_reported(monkeypatch):
    monkeypatch.setattr(fetch, "_download", lambda url, settings: (_ for _ in ()).throw(requests.ConnectionError("x")))
    items, failures = fetch.fetch_all(config({"type": "news", "url": "https://nameless.example/feed"}))
    assert items == [] and "unnamed feed" in failures
