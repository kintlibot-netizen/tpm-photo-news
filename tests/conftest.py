from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

import classify
from fetch import Item

ROOT = Path(__file__).resolve().parent.parent
NOW = datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def rules():
    with open(ROOT / "config" / "rules.yaml", encoding="utf-8") as handle:
        return classify.normalize_rules(yaml.safe_load(handle))


@pytest.fixture
def now():
    return NOW


@pytest.fixture(autouse=True)
def isolated_dashboard_root(tmp_path_factory, monkeypatch):
    """Tests never read the real output/carousels folder, so the dashboard looks the same on every machine."""
    import dashboard
    monkeypatch.setattr(dashboard, "ROOT", tmp_path_factory.mktemp("dashboard-root"))
    # The page never asks Windows Task Scheduler during a test; the next check is estimated from the run history.
    monkeypatch.setattr(dashboard, "read_next_run", lambda: None)


@pytest.fixture(autouse=True)
def fake_slide_previews(monkeypatch):
    """Tests never start Chromium for the share pack previews: each 'preview' is a copy of the slide bytes."""
    import previews

    def fake(jobs, *args, **kwargs):
        for source, target in jobs:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"jpg " + source.read_bytes())
        return len(jobs)

    monkeypatch.setattr(previews, "make_previews", fake)


@pytest.fixture(autouse=True)
def isolated_activity_log(tmp_path_factory, monkeypatch):
    """Every test writes its activity rows to its own temporary log, never to data/activity-log.csv."""
    import activity
    path = tmp_path_factory.mktemp("activity") / "activity-log.csv"
    monkeypatch.setattr(activity, "LOG_PATH", path)
    return path


def make_item(title, source="PetaPixel", source_type="news", slug=None, hours_old=1, summary="Summary text."):
    slug = slug or title.lower().replace(" ", "-")
    return Item(
        source=source, source_type=source_type, title=title,
        url=f"https://{source.lower().replace(' ', '')}.example.com/{slug}",
        summary=summary, published=NOW - timedelta(hours=hours_old),
    )
