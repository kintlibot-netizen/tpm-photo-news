"""Round 9 cleanup (Nov 24): one Start here page (with how it works), old automatic builder rows hidden, no sample
generator."""
from datetime import datetime, timedelta, timezone

import carousel
import dashboard

NOW = datetime(2026, 11, 24, 15, 0, tzinfo=timezone.utc)


def test_how_it_works_is_part_of_start_here_and_not_a_page_of_its_own():
    keys = [key for key, _, _ in dashboard.PAGES]
    assert "how" not in keys and keys[0] == "start"
    page = dashboard.start_panel("local", {"waiting_david": 0})
    assert "The steps in plain words" in page and "The rules that never change" in page


def test_old_builder_rows_are_hidden_but_real_failures_still_show():
    old = {"carousel": None, "build_row": {"status": "failed", "message": "Claude Code exited with code 1"},
           "first_seen": NOW - timedelta(days=5)}
    words, _ = dashboard.coverage_reason(old, NOW)
    assert "Claude" not in words and words.startswith("Not made")
    real = {"carousel": None, "build_row": {"status": "failed", "message": "Design check: headline lines"},
            "first_seen": NOW}
    assert dashboard.coverage_reason(real, NOW)[0] == "Not made: Design check: headline lines"
    assert dashboard.is_legacy_noise("Story 71: Being made by the carousel bot on the laptop")
    assert not dashboard.is_legacy_noise("Story 72: draft ready")


def test_the_sample_generator_is_gone():
    assert not hasattr(carousel, "run_sample") and not hasattr(carousel, "SAMPLE_ROOT")
