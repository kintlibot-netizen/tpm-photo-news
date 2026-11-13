import pytest
import requests

import fetch

SOURCE = {"name": "Test", "type": "news", "url": "https://example.com/feed"}
SETTINGS = {"user_agent": "test", "retries": 1, "timeout_seconds": 1, "retry_pause_seconds": 0}

RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>T</title>
<item><title>Canon Announces &lt;b&gt;R6&lt;/b&gt;</title><link>https://a.example/1</link>
<pubDate>Tue, 10 Nov 2026 16:00:00 +0000</pubDate>
<description>&lt;p&gt;Hello &amp;amp; welcome&lt;/p&gt;</description></item>
<item><title>No date</title><link>https://a.example/2</link></item>
<item><title>Bad link</title><link>javascript:alert(1)</link></item>
<item><title></title><link>https://a.example/3</link></item>
</channel></rss>"""

ATOM = b"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><title>T</title>
<entry><title>Atom story</title><link rel="alternate" href="https://a.example/atom"/>
<updated>2026-11-10T16:00:00Z</updated><summary>Text</summary></entry></feed>"""


def test_parses_rss_and_cleans_html():
    items = fetch.parse_feed(RSS, SOURCE)
    assert items[0].title == "Canon Announces R6"
    assert items[0].summary == "Hello & welcome"
    assert items[0].published.isoformat() == "2026-11-10T16:00:00+00:00"


def test_missing_date_stays_missing():
    assert fetch.parse_feed(RSS, SOURCE)[1].published is None


def test_skips_unsafe_links_and_empty_titles():
    assert [i.url for i in fetch.parse_feed(RSS, SOURCE)] == ["https://a.example/1", "https://a.example/2"]


def test_parses_atom():
    assert fetch.parse_feed(ATOM, SOURCE)[0].url == "https://a.example/atom"


def test_garbage_raises():
    with pytest.raises(ValueError):
        fetch.parse_feed(b"<html><not closed", SOURCE)


def test_one_broken_feed_does_not_stop_the_others(monkeypatch):
    good = dict(SOURCE, name="Good", url="https://good.example")
    bad = dict(SOURCE, name="Bad", url="https://bad.example")

    def fake_download(url, settings):
        if "bad" in url:
            raise requests.ConnectionError("down")
        return RSS

    monkeypatch.setattr(fetch, "_download", fake_download)
    items, failures = fetch.fetch_all({"sources": [bad, good], "fetch": SETTINGS})
    assert {i.source for i in items} == {"Good"}
    assert list(failures) == ["Bad"]


def test_retries_once(monkeypatch):
    calls = []

    def flaky(url, settings):
        calls.append(url)
        if len(calls) == 1:
            raise requests.Timeout("slow")
        return RSS

    monkeypatch.setattr(fetch, "_download", flaky)
    assert fetch.fetch_source(SOURCE, SETTINGS)
    assert len(calls) == 2


def test_retry_waits_a_short_pause_before_the_second_try(monkeypatch):
    # (d) A DNS or network blip gets one retry after a pause, not an instant one.
    pauses, calls = [], []

    def dns_blip_then_ok(url, settings):
        calls.append(url)
        if len(calls) == 1:
            raise requests.ConnectionError("DNS lookup failed")
        return RSS

    monkeypatch.setattr(fetch, "_download", dns_blip_then_ok)
    monkeypatch.setattr(fetch.time, "sleep", lambda seconds: pauses.append(seconds))
    assert fetch.fetch_source(SOURCE, dict(SETTINGS, retry_pause_seconds=3))
    assert pauses == [3] and len(calls) == 2


def test_feed_failing_twice_is_reported_after_one_pause(monkeypatch):
    pauses, calls = [], []

    def always_down(url, settings):
        calls.append(url)
        raise requests.ConnectionError("DNS lookup failed")

    monkeypatch.setattr(fetch, "_download", always_down)
    monkeypatch.setattr(fetch.time, "sleep", lambda seconds: pauses.append(seconds))
    with pytest.raises(RuntimeError, match="Test"):
        fetch.fetch_source(SOURCE, dict(SETTINGS, retry_pause_seconds=2))
    assert len(calls) == 2 and pauses == [2]


def test_no_pause_before_the_first_try(monkeypatch):
    pauses = []
    monkeypatch.setattr(fetch, "_download", lambda url, settings: RSS)
    monkeypatch.setattr(fetch.time, "sleep", lambda seconds: pauses.append(seconds))
    fetch.fetch_source(SOURCE, dict(SETTINGS, retry_pause_seconds=5))
    assert pauses == []
