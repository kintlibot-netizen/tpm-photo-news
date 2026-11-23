"""Round 7: the Carousels page shows every carousel (real, preview, sample) with a plain status chip, and the cloud
publish step carries previews and samples without notes or secrets. Temporary data only."""
import dashboard
import carousel_status
import cloud_state
from test_round7_downloads import PASSING, carousel

REAL = "2026-11-11-photoshop-can-now-relight"
DRAFT = "2026-11-11-all-of-adobe-camera-raw"
PREVIEW = "2026-11-12-skylum-luminar-neo"
SAMPLE = "2026-11-11-canon-eos-r8-mark-ii-sample"


def folders(tmp_path):
    carousel(tmp_path / "carousels", name=REAL)  # passes the checks: Waiting for David
    rejected = carousel(tmp_path / "carousels", name=DRAFT)
    carousel_status.set_status(rejected, "rejected", reason="Wrong product")
    carousel(tmp_path / "previews", name=PREVIEW)  # a dry run also passes the checks, but it is only a preview
    carousel(tmp_path / "samples", name=SAMPLE, build=dict(PASSING, sample=True))
    return tmp_path / "carousels", tmp_path / "samples", tmp_path / "previews"


def test_every_carousel_is_listed_real_first_then_previews_then_samples(tmp_path):
    real, samples, previews = folders(tmp_path)
    cards = dashboard.read_carousels(real, samples, previews)
    assert [(c["name"], c["kind"]) for c in cards] == [
        (REAL, "draft"), (DRAFT, "draft"), (PREVIEW, "preview"), (SAMPLE, "sample")]
    assert [dashboard.chip_key(c) for c in cards] == ["waiting_for_david", "rejected", "preview", "sample"]
    assert not dashboard.is_real(cards[2]) and not dashboard.is_real(cards[3])


def test_each_card_has_a_plain_chip_and_the_filter_offers_every_status(tmp_path):
    cards = dashboard.read_carousels(*folders(tmp_path))
    page = dashboard.carousels_panel(cards)
    for chip in ("Waiting for David", "Rejected: Wrong product", "Preview, not sent for approval yet",
                 "Layout sample not for posting"):
        assert chip in page
    for value in ("all", "waiting_for_david", "draft", "preview", "approved", "rejected", "posted", "sample"):
        assert f'<option value="{value}"' in page
    assert '<option value="all" selected>All carousels (4)</option>' in page
    assert "Layout samples, not for posting" in page and "Previews, not sent for approval yet" in page
    assert page.index(f'id="car-{REAL}"') < page.index(f'id="car-{PREVIEW}"') < page.index(f'id="car-{SAMPLE}"')
    assert "—" not in page and "–" not in page


def test_previews_and_samples_are_never_counted_or_linked_as_real(tmp_path):
    cards = dashboard.read_carousels(*folders(tmp_path))
    story = {"status": "x", "title": "t"}
    dashboard.link_carousels([story], cards, [])
    assert story["carousel"] is None or dashboard.is_real(story["carousel"])
    items = dashboard.attention_items(cards, [], [], "local")
    assert all(PREVIEW not in str(item) and SAMPLE not in str(item) for item in items)


def test_a_preview_of_a_story_that_was_built_for_real_is_shown_once(tmp_path):
    real, samples, previews = folders(tmp_path)
    carousel(previews, name=REAL)
    names = [c["name"] for c in dashboard.read_carousels(real, samples, previews)]
    assert names.count(REAL) == 1


def test_publish_carries_previews_and_samples_and_never_notes_or_secrets(tmp_path):
    root = tmp_path / "laptop"
    preview = carousel(root / "output" / "plan-previews", name=PREVIEW)
    carousel(root / "output" / "samples", name=SAMPLE, build=dict(PASSING, sample=True))
    for name in ("official.txt", "images.txt", ".env", "secret-notes.txt", "story-72.official.txt", "key.pem"):
        (preview / name).write_text("private", encoding="utf-8")
    cloud_state.push("laptop", root)
    saved = root / "state" / "previews" / PREVIEW
    assert (saved / "01.png").exists() and (saved / "captions.txt").exists()
    assert sorted(p.name for p in saved.iterdir() if "." in p.name and p.name not in
                  {"01.png", "02.png", "03.png", "04.png", "captions.txt", "plan.json", "sources.md",
                   "status.json"}) == []
    assert (root / "state" / "samples" / SAMPLE / "01.png").exists()
    cloud = tmp_path / "cloud"
    (cloud / "state").mkdir(parents=True)
    import shutil
    shutil.copytree(root / "state" / "previews", cloud / "state" / "previews")
    cloud_state.pull("cloud", cloud)
    assert (cloud / "output" / "plan-previews" / PREVIEW / "01.png").exists()
