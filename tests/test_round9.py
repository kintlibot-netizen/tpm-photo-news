"""Round 9 cleanup (Nov 24): one Start here page (with how it works), old automatic builder rows hidden, no sample
generator."""
from datetime import datetime, timezone

import carousel
import dashboard

NOW = datetime(2026, 11, 24, 15, 0, tzinfo=timezone.utc)


def test_the_carousels_come_first_and_how_it_works_is_short():
    # Round 12 redesign: Start here, Overview, Needs your attention, Stories, Activity and Sources made way for four
    # pages. The carousels to review are the home page; How it works is a short page of four steps and the rules.
    keys = [key for key, _, _ in dashboard.PAGES]
    assert keys == ["review", "news", "inspiration", "system", "how"]
    page = dashboard.how_panel()
    assert page.count('class="step"') == 4 and "The rules that never change" in page


def test_the_sample_generator_is_gone():
    assert not hasattr(carousel, "run_sample") and not hasattr(carousel, "SAMPLE_ROOT")
