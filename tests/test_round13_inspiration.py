"""Round 13: the Inspiration section. Credited, link only Nat Geo reference cards on Kint's page and David's copy."""
import json
import re

from conftest import ROOT
from test_dashboard import sample_db
from test_round12_dashboard import DASHES, build

import inspiration

BOARD = ROOT / "data" / "inspiration" / "natgeo-poy-2026.json"


def test_the_board_file_has_every_field_and_only_official_links():
    board = json.loads(BOARD.read_text(encoding="utf-8"))
    assert 15 <= len(board["items"]) <= 20
    assert "copyright" in board["copyright_note"].lower() and "permission" in board["copyright_note"].lower()
    for item in board["items"]:
        for key in inspiration.REQUIRED:
            assert item.get(key), (item.get("title"), key)
        assert item["url"].startswith("https://www.nationalgeographic.com/")
    text = BOARD.read_text(encoding="utf-8")
    assert not any(d in text for d in DASHES)
    assert not re.search(r"\.(jpe?g|png|webp|gif)\b", text, re.I)  # no image file or hot link


def test_both_pages_show_the_inspiration_section_with_credits_and_no_images(tmp_path):
    db = sample_db(tmp_path / "seen.sqlite")
    board = json.loads(BOARD.read_text(encoding="utf-8"))
    for page in (build(tmp_path, db), build(tmp_path, db, read_only=True)):
        assert 'data-nav="inspiration" data-label="Inspiration"' in page
        section = page.split('data-page="inspiration"', 1)[1].split('<section class="page"', 1)[0]
        assert section.index("insp-note") < section.index("insp-card")  # the copyright note comes first
        assert section.count('class="insp-card"') == len(board["items"])
        for item in board["items"]:
            assert inspiration.esc(f"Photo by {item['photographer']} for National Geographic") in section
        assert "<img" not in section and "natgeofe.com" not in section
        assert section.count('href="https://www.nationalgeographic.com/') >= len(board["items"])
        assert not any(d in section for d in DASHES)


def test_a_card_without_an_official_link_or_a_field_is_left_out(tmp_path):
    (tmp_path / "b.json").write_text(json.dumps({"name": "x", "copyright_note": "c", "items": [
        {"title": "A", "photographer": "P", "location": "L", "category": "C", "lesson": "l", "tpm_idea": "i",
         "url": "https://example.com/a"},
        {"title": "B", "photographer": "", "location": "L", "category": "C", "lesson": "l", "tpm_idea": "i",
         "url": "https://www.nationalgeographic.com/b"},
        {"title": "C", "photographer": "P", "location": "L", "category": "C", "lesson": "l", "tpm_idea": "i",
         "url": "https://www.nationalgeographic.com/c"}]}), encoding="utf-8")
    boards = inspiration.load_boards(tmp_path)
    assert [i["title"] for i in boards[0]["items"]] == ["C"]
    assert inspiration.panel([]) == ""
