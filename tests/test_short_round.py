"""Short round: the official page must match the story's product, the closing recap holds 5 features,
and story titles in markdown headings carry no en or em dashes. No network, no Claude, no browser."""
import pytest

import carousel
import carousel_plan
import carousel_render
import design_check
import official
from dedupe import Story

DASH_EM, DASH_EN = "—", "–"
CONFIG = {"official_domains": {"Skylum": ["skylum.com"]}, "official_indexes": {}, "official_pages": {}}
FILLER = "<p>" + "Skylum makes photo editing software for creators and photographers. " * 12 + "</p>"
NEWS = "https://news.example/story"


def page(title: str, heading: str = "", body: str = "") -> str:
    return f"<html><head><title>{title}</title></head><body><h1>{heading}</h1>{FILLER}<p>{body}</p></body></html>"


def story_for(title: str) -> Story:
    story = Story(title=title, brand="Skylum", kind="product", tokens=frozenset())
    story.sources = [{"url": NEWS, "link": NEWS, "source": "News", "source_type": "news", "title": title,
                      "summary": "", "published": None}]
    return story


def serve(monkeypatch, links: list[str], pages: dict[str, str]):
    anchors = "".join(f'<a href="{u}">x</a>' for u in links)

    def fetch(url, *a, **k):
        if url == NEWS:
            return f"<html><body>{anchors}</body></html>"
        return pages.get(url, "<p>nothing</p>")

    monkeypatch.setattr(carousel.official, "fetch_html", fetch)


# ---- 1. the official page matches the product ----

def test_the_page_naming_the_product_wins_over_the_first_official_link(monkeypatch):
    wrong = "https://skylum.com/blog/other-news"
    right = "https://skylum.com/blog/luminar-neo-relight-ai"
    serve(monkeypatch, [wrong, right], {
        wrong: page("Skylum Blog: a different post", "Portrait tips"),
        right: page("Luminar Neo Relight AI is here", "Relight AI"),
    })
    found = carousel.locate_official(story_for("Skylum launches Luminar Neo Relight AI"), "Skylum", CONFIG, None)
    assert found.url == right


def test_a_home_page_is_never_used_and_no_match_gives_a_clear_refusal(monkeypatch):
    home = "https://skylum.com/"
    wrong = "https://skylum.com/blog/other-news"
    wrong2 = "https://skylum.com/blog/portrait-tips"
    serve(monkeypatch, [home, wrong, wrong2], {home: page("Skylum", "Luminar Neo Relight AI"),
                                               wrong: page("Skylum Blog: a different post", "Portrait tips"),
                                               wrong2: page("Skylum Blog: tips", "Tips")})
    with pytest.raises(carousel.Refused, match="No official page matches the product") as info:
        carousel.locate_official(story_for("Skylum launches Luminar Neo Relight AI"), "Skylum", CONFIG, None)
    assert "--official-url" in str(info.value)


def test_an_explicit_official_url_is_not_filtered_by_product(monkeypatch):
    url = "https://skylum.com/blog/other-news"
    serve(monkeypatch, [], {url: page("Skylum Blog: a different post")})
    found = carousel.locate_official(story_for("Skylum launches Luminar Neo Relight AI"), "Skylum", CONFIG, url)
    assert found.url == url


def test_product_match_helpers():
    assert carousel.product_match_terms("Skylum launches Luminar Neo Relight AI", "Skylum") == [
        "luminar", "neo", "relight"]
    assert official.is_home_page("https://www.dji.com/") and official.is_home_page("https://dji.com")
    assert not official.is_home_page("https://www.dji.com/avata-360")
    assert official.product_match_score(page("DJI Avata 360", "Avata 360"), ["avata", "360"]) > 0
    assert official.product_match_score(page("DJI", "Home"), ["avata", "360"]) == 0
    assert official.product_match_score(page("DJI", "Home"), []) == 0


# ---- 2. the closing recap ----

def views(features: int):
    return ([{"type": "cover", "headline": "COVER"}]
            + [{"type": "feature", "headline": f"FEATURE {n}"} for n in range(features)])


def test_the_closing_recap_holds_up_to_five_features_the_first_five_when_there_are_more():
    five = carousel_plan.closing_view(views(5), design_check.MAX_SLIDES + 5)
    assert five["features"] == [f"FEATURE {n}" for n in range(5)]
    seven = carousel_plan.closing_view(views(7), design_check.MAX_SLIDES + 5)
    assert seven["features"] == [f"FEATURE {n}" for n in range(5)]


def test_five_recap_lines_render_clear_of_the_call_to_action():
    view = carousel_plan.closing_view(views(5), design_check.MAX_SLIDES + 5)
    html = carousel_render.closing_body(view, {"main": None, "old": None})
    assert all(f"FEATURE {n}" in html for n in range(5))
    # Image first (Nov 28 2026): the recap is at most two light-blue lines under the question, then the image grid.
    assert html.count('class="abs feat"') <= 2
    assert carousel_render.closing_grid_top(view) + 400 < carousel_render.CLOSING_CTA_TOP
    four = carousel_render.closing_body(carousel_plan.closing_view(views(4), 7), {"main": None, "old": None})
    assert "FEATURE 3" in four and "FEATURE 4" not in four


# ---- 3. no dashes in headings ----

def test_story_titles_in_headings_lose_en_and_em_dashes():
    assert carousel.heading_title(f"Photoshop 2027 {DASH_EM} Relight") == "Photoshop 2027, Relight"
    assert carousel.heading_title(f"Lightroom{DASH_EN}Classic update") == "Lightroom, Classic update"
    assert carousel.heading_title(f"Adobe {DASH_EM}: Firefly") == "Adobe: Firefly"
    assert carousel.heading_title("Plain title - with hyphen") == "Plain title - with hyphen"
    for title in (f"A {DASH_EM} B", f"A {DASH_EN} B"):
        assert DASH_EM not in carousel.heading_title(title) and DASH_EN not in carousel.heading_title(title)


# ---- round 7: a real product page still qualifies, a home page or an unrelated page does not ----

def test_the_only_deep_official_link_of_the_article_is_used_but_never_a_home_page(monkeypatch):
    story = story_for("Adobe Releases Photoshop 27.1")
    cfg = {"official_domains": {"Adobe": ["adobe.com"]}, "official_indexes": {}, "official_pages": {}}
    body = "<p>" + "Adobe text. " * 40 + "</p>"
    only = "https://blog.adobe.com/en/relight"
    serve(monkeypatch, [only], {only: body})
    assert carousel.locate_official(story, "Adobe", cfg, None).url == only
    home = "https://www.adobe.com/"
    serve(monkeypatch, [home], {home: body})
    with pytest.raises(carousel.Refused, match="No official page matches"):
        carousel.locate_official(story, "Adobe", cfg, None)


def test_words_in_the_url_path_count_as_a_match():
    plain = page("News", "News")
    assert official.product_match_score(plain, ["luminar", "neo"]) == 0
    assert official.product_match_score(plain, ["luminar", "neo"], "https://skylum.com/blog/luminar-neo-update") > 0
