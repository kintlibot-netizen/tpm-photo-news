from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import requests
from conftest import ROOT, make_item

import json

import alert
import run
from classify import OFFICIAL, RUMOR, Review
from dedupe import Store, Story

REVIEW = Review(True, "camera", "A summary.", True)

# Exact headlines from the round 3 dry run.
XT6_DELAY = ("Camera Jabber", "news", "Fujifilm X-T6 delayed again as 19 November launch date is scrapped")
XT6_SENSOR_RUMOR = ("Fuji Rumors", "rumor", "RUMOR: Fujifilm X-T6 Powered by a New 40MP Sensor!")
PHOTOSHOP_RELIGHT = (
    "Digital Camera World", "news",
    "Photoshop can now relight photos – and adjusting the camera angle is coming next. "
    "These are the 6 biggest updates in Photoshop 2027",
)
LIGHTROOM_GLOW = (
    "Digital Camera World", "news",
    "A new cinematic glow tool is coming to Lightroom – and no, it’s not GenAI. "
    "These are the 4 biggest updates to Adobe Lightroom 2027",
)
PREMIERE = ("DPReview", "news", "Adobe’s Premiere updates bring more AI into the editing timeline")
MAX_LIVE_BLOG = (
    "Digital Camera World", "news",
    "The biggest Lightroom and Photoshop updates are here. Follow live for the biggest announcements at Adobe Max",
)


def no_claude_story(title="Canon R6 III"):
    made = Story(title=title, brand="Canon", kind="product", tokens=frozenset())
    made.sources = [{"url": "https://a/1", "link": "https://a/1", "source": "PetaPixel"}]
    return made


def test_official_alert_text():
    text = alert.format_alert(no_claude_story(), OFFICIAL, REVIEW, "new")
    assert "OFFICIAL (reported by PetaPixel, not yet checked against the brand)" in text
    assert "https://a/1" in text and "Category: Camera" in text


def test_rumor_alert_says_no_carousel():
    text = alert.format_alert(no_claude_story(), RUMOR, REVIEW, "rumor reached the source minimum")
    assert text.count("RUMOR") == 1 and "no carousel until the brand confirms" in text


def test_unreviewed_alert_is_marked():
    review = Review(True, "camera", "A summary.", False)
    assert "Not reviewed by Claude" in alert.format_alert(no_claude_story(), OFFICIAL, review, "new")


def test_rumor_site_release_is_marked_like_news():
    story = no_claude_story("Firmware Updates for Fujifilm X-T5, X-H2 and X-H2S")
    story.sources = [{"url": "https://f/1", "link": "https://f/1", "source": "Fuji Rumors"}]
    text = alert.format_alert(story, OFFICIAL, REVIEW, "new")
    assert "OFFICIAL (reported by Fuji Rumors, not yet checked against the brand)" in text


def test_rumor_turned_official_is_called_out():
    text = alert.format_alert(no_claude_story(), OFFICIAL, REVIEW, "rumor is now reported as official")
    assert text.startswith("UPDATE:")


def test_feed_text_cannot_trigger_slack_mentions():
    text = alert.format_alert(no_claude_story("<!channel> Canon"), OFFICIAL, REVIEW, "new")
    assert "<!channel>" not in text and "&lt;!channel&gt;" in text


@pytest.mark.parametrize(
    "value", ["", "https://hooks.slack.com/services/REPLACE/WITH/YOURS", "https://evil.example/x"]
)
def test_placeholder_or_wrong_webhook_is_refused(monkeypatch, value):
    monkeypatch.setenv("SLACK_WEBHOOK_URL", value)
    with pytest.raises(RuntimeError):
        alert.webhook_url()


def test_env_example_holds_only_a_placeholder():
    assert "REPLACE" in (ROOT / ".env.example").read_text(encoding="utf-8")


def test_second_run_sends_no_duplicate(rules, now):
    store = Store()
    item = make_item("Canon Announces R6 Mark III")
    first = run.process([item], store, rules, False, now)
    assert len(first["ready"]) == 1
    story, label, _ = first["ready"][0]
    store.mark_alerted(story, label)
    assert run.process([item], store, rules, False, now + timedelta(hours=1))["ready"] == []


def test_failed_send_is_retried_next_run(rules, now):
    store = Store()
    item = make_item("Canon Announces R6 Mark III")
    assert len(run.process([item], store, rules, False, now)["ready"]) == 1
    assert len(run.process([item], store, rules, False, now + timedelta(hours=1))["ready"]) == 1


def test_rumor_lifecycle(rules, now):
    store = Store()
    first = make_item("Canon R6 Mark III rumored specs", source="Canon Rumors", source_type="rumor")
    result = run.process([first], store, rules, False, now)
    assert result["ready"] == [] and len(result["held"]) == 1

    second = make_item("Canon R6 III Leaked", source="DPReview")
    result = run.process([first, second], store, rules, False, now + timedelta(hours=1))
    assert result["ready"][0][1] == RUMOR
    store.mark_alerted(result["ready"][0][0], RUMOR)

    third = make_item("Canon Announces R6 Mark III", source="PetaPixel")
    result = run.process([first, second, third], store, rules, False, now + timedelta(hours=2))
    assert result["ready"][0][1] == OFFICIAL
    store.mark_alerted(result["ready"][0][0], OFFICIAL)
    assert run.process([first, second, third], store, rules, False, now + timedelta(hours=3))["ready"] == []


def test_claude_rejection_is_not_alerted_or_asked_again(rules, now):
    store = Store()
    item = make_item("Canon Announces Printer Ink Refill")
    calls = []

    def reject(prompt, model):
        calls.append(1)
        return ('[{"id": 0, "relevant": false, "category": "gear", "summary": "Not for us.", '
                '"label": "OFFICIAL", "reason": "Brand announced it."}]')

    result = run.process([item], store, rules, True, now, asker=reject)
    assert result["ready"] == [] and len(result["rejected"]) == 1
    run.process([item], store, rules, True, now + timedelta(hours=1), asker=reject)
    assert len(calls) == 1


def claude_reply(label, reason="Reason line."):
    return json.dumps([{
        "id": 0, "relevant": True, "category": "lightroom", "summary": "Short line.",
        "label": label, "reason": reason,
    }])


def test_claude_rumor_label_holds_an_official_looking_story(rules, now):
    store = Store()
    item = make_item(LIGHTROOM_GLOW[2], source="Digital Camera World")
    calls = []

    def say_rumor(prompt, model):
        calls.append(1)
        return claude_reply("RUMOR", "Speculative wording about a future feature.")

    result = run.process([item], store, rules, True, now, asker=say_rumor)
    assert result["ready"] == [] and len(result["held"]) == 1
    saved = store.recent_stories(30, now)[0]
    assert saved.claude_label == RUMOR

    # The saved label stops Claude being asked again on the next run.
    run.process([item], store, rules, True, now + timedelta(hours=1), asker=say_rumor)
    assert len(calls) == 1


def test_claude_official_label_alerts_a_news_launch(rules, now):
    store = Store()
    item = make_item(PHOTOSHOP_RELIGHT[2], source="Digital Camera World")
    result = run.process(
        [item], store, rules, True, now, asker=lambda p, m: claude_reply("OFFICIAL", "Reports an Adobe release."),
    )
    assert len(result["ready"]) == 1
    _, label, text = result["ready"][0]
    assert label == OFFICIAL
    assert "Label check: Reports an Adobe release." in text


def test_claude_rumor_label_on_a_rumor_site_is_not_upgraded(rules, now):
    store = Store()
    item = make_item("RUMOR: Fujifilm X-T6 Powered by a New 40MP Sensor!", source="Fuji Rumors", source_type="rumor")
    result = run.process(
        [item], store, rules, True, now, asker=lambda p, m: claude_reply("OFFICIAL", "Sounds confirmed."),
    )
    assert result["ready"] == [] and len(result["held"]) == 1


def test_delay_report_alone_is_held_not_alerted(rules, now):
    store = Store()
    delay = make_item(XT6_DELAY[2], source="Camera Jabber")
    sensor = make_item(XT6_SENSOR_RUMOR[2], source="Fuji Rumors", source_type="rumor")
    result = run.process([delay, sensor], store, rules, False, now)
    assert result["ready"] == []
    assert len(result["held"]) == 2


def test_live_blog_and_premiere_never_reach_the_alert_list(rules, now):
    store = Store()
    items = [
        make_item(MAX_LIVE_BLOG[2], source="Digital Camera World"),
        make_item(PREMIERE[2], source="DPReview"),
    ]
    result = run.process(items, store, rules, False, now)
    assert result["ready"] == [] and result["held"] == []


def test_dry_run_writes_file_and_never_posts(monkeypatch, tmp_path, now):
    item = make_item("Canon Announces R6 Mark III", hours_old=1)
    current = datetime.now(timezone.utc)
    item.published = current - timedelta(hours=1)

    def forbidden(*args, **kwargs):
        raise AssertionError("dry run tried to post")

    monkeypatch.setattr(requests, "post", forbidden)
    monkeypatch.setattr(run, "ROOT", tmp_path)
    (tmp_path / "config").mkdir()
    for name in ("sources.yaml", "rules.yaml"):
        (tmp_path / "config" / name).write_text((ROOT / "config" / name).read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setattr(run.fetch, "fetch_all", lambda config: ([item], {"Broken": "down"}))
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/services/A/B/C")

    assert run.main(["--dry-run", "--no-claude"]) == 0
    output = next((tmp_path / "output").glob("dry-run-alerts-*.txt")).read_text(encoding="utf-8")
    assert "Nothing was sent" in output and "Canon Announces R6 Mark III" in output and "Broken" in output

    # The dry run left the real memory empty.
    assert not Store(tmp_path / "data" / "seen.sqlite", read_only_copy=True).recent_stories(30, current)


def test_real_run_without_webhook_stops_safely(monkeypatch, tmp_path):
    monkeypatch.setattr(run, "ROOT", tmp_path)
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    assert run.main(["--no-claude"]) == 2


def test_no_social_posting_code():
    """Phase 1 must contain no way to publish to social media."""
    banned = ["graph.facebook", "instagram.com", "business.facebook", "media_publish", "instagram_business"]
    for path in Path(ROOT, "src").glob("*.py"):
        text = path.read_text(encoding="utf-8").lower()
        for word in banned:
            assert word not in text, f"{path.name} contains {word}"


def test_only_slack_address_is_allowed_for_posting():
    text = (ROOT / "src" / "alert.py").read_text(encoding="utf-8")
    assert text.count("requests.post") == 1
    assert "https://hooks.slack.com/services/" in text
