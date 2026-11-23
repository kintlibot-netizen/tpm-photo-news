"""Round 7: the Carousels page shows every real carousel and preview with a plain status chip, never the layout
samples (fixtures with no official images), and flags any slide without an official image. The cloud publish step
carries previews without notes or secrets and removes old sample copies. Temporary data only."""
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


def test_every_real_carousel_is_listed_then_previews_and_never_samples(tmp_path):
    real, samples, previews = folders(tmp_path)
    cards = dashboard.read_carousels(real, samples, previews)
    assert [(c["name"], c["kind"]) for c in cards] == [(REAL, "draft"), (DRAFT, "draft"), (PREVIEW, "preview")]
    assert [dashboard.chip_key(c) for c in cards] == ["waiting_for_david", "rejected", "preview"]
    assert not dashboard.is_real(cards[2])


def test_an_old_sample_folder_among_the_real_carousels_is_not_shown(tmp_path):
    carousel(tmp_path / "carousels", name=REAL)
    carousel(tmp_path / "carousels", name="2026-11-11-photoshop-2027-sample")
    assert [c["name"] for c in dashboard.read_carousels(tmp_path / "carousels")] == [REAL]


def test_a_slide_without_an_official_image_is_flagged_on_its_card(tmp_path):
    folder = carousel(tmp_path / "carousels", name=REAL, build=dict(PASSING, missing=["01.jpg", "03.jpg"]))
    card = dashboard.read_carousels(tmp_path / "carousels")[0]
    assert dashboard.slides_without_image(card) == [1, 3]
    page = dashboard.carousels_panel([card])
    assert "No official image on slides 1, 3" in page and page.count(">NO IMAGE<") == 2
    carousel_status.write_build(folder, dict(PASSING, missing=["01.jpg"], cover_collage=True))
    card = dashboard.read_carousels(tmp_path / "carousels")[0]
    assert dashboard.slides_without_image(card) == []  # the cover is a collage of the official feature images
    assert "NO IMAGE" not in dashboard.carousels_panel([card])


def test_each_card_has_a_plain_chip_and_the_filter_offers_every_status(tmp_path):
    cards = dashboard.read_carousels(*folders(tmp_path))
    page = dashboard.carousels_panel(cards)
    for chip in ("Waiting for David", "Rejected: Wrong product", "Preview, not sent for approval yet"):
        assert chip in page
    for value in ("all", "waiting_for_david", "draft", "preview", "approved", "rejected", "posted"):
        assert f'<option value="{value}"' in page
    assert '<option value="sample"' not in page and SAMPLE not in page
    assert '<option value="all" selected>All carousels (3)</option>' in page
    assert "Previews, not sent for approval yet" in page
    assert page.index(f'id="car-{REAL}"') < page.index(f'id="car-{PREVIEW}"')
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


def test_publish_carries_previews_never_samples_notes_or_secrets(tmp_path):
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
    assert not (root / "state" / "samples").exists()
    old = root / "state" / "samples" / SAMPLE  # a copy an older push left behind is removed
    old.mkdir(parents=True)
    (old / "captions.txt").write_text("x", encoding="utf-8")
    cloud_state.push("laptop", root)
    assert not (root / "state" / "samples").exists()
    cloud = tmp_path / "cloud"
    (cloud / "state").mkdir(parents=True)
    import shutil
    shutil.copytree(root / "state" / "previews", cloud / "state" / "previews")
    cloud_state.pull("cloud", cloud)
    assert (cloud / "output" / "plan-previews" / PREVIEW / "01.png").exists()


def test_a_new_preview_of_a_rejected_carousel_replaces_it_on_the_page(tmp_path):
    real, samples, previews = folders(tmp_path)
    carousel(previews, name=DRAFT)  # DRAFT is rejected in the real folder
    cards = dashboard.read_carousels(real, samples, previews)
    assert [(c["name"], c["kind"]) for c in cards if c["name"] == DRAFT] == [(DRAFT, "preview")]


def test_a_new_preview_of_a_plain_draft_replaces_it_but_never_one_sent_for_review(tmp_path):
    real, samples, previews = folders(tmp_path)
    plain = carousel(real, name="2026-11-13-plain-draft", build=dict(PASSING, lint_passed=False))  # stays Draft
    carousel(previews, name=plain.name)
    carousel(previews, name=REAL)  # REAL is Waiting for David: its preview is not shown
    cards = {c["name"]: c["kind"] for c in dashboard.read_carousels(real, samples, previews)}
    assert cards[plain.name] == "preview" and cards[REAL] == "draft"

def test_a_cover_with_no_room_for_a_readable_collage_shows_the_first_feature_image_whole(tmp_path):
    import carousel_render
    from test_phase3_fix3c import cover_view, tiles_in, wide
    view = cover_view(hook="2026 IFA INNOVATION AWARD WINNER", headline="DJI ROMO P2")
    view["features"] = ["EDGE CLEANING", "8.5CM CROSSING", "SHARPER SENSING"]
    images_ = [wide(tmp_path, f"0{n}.jpg", (1388, 960)) for n in (2, 3, 4)]
    slot = {"main": None, "collage": images_}
    assert carousel_render.collage_tiles(images_, 848) == []  # three 1.45 tiles would be under 300px wide
    tiles = tiles_in(carousel_render.cover_body(view, slot))
    assert len(tiles) == 1 and tiles[0][2] >= 600  # one large, whole image: never a cover with only the glow
    assert carousel_render.cover_hero_images(view, slot) == [images_[0]]
    assert carousel_render.cover_hero_images(cover_view(), {"main": None, "collage": []}) == []
