"""Phase 3 round 3d: a draft without cover.label is repaired and the build continues."""
import copy
import json

import pytest

import carousel
import carousel_plan
from test_phase3_fix2 import TEXT, make_plan


def broken(label):
    data = copy.deepcopy(make_plan())
    if label is None:
        del data["cover"]["label"]
    else:
        data["cover"]["label"] = label
    return data


def fake_claude(monkeypatch, replies):
    prompts = []

    def ask(prompt, model, timeout=300):
        prompts.append(prompt)
        return json.dumps(replies[min(len(prompts) - 1, len(replies) - 1)])

    monkeypatch.setattr(carousel.classify, "ask_claude", ask)
    return prompts


def test_the_current_prompt_and_example_include_cover_label():
    prompt = carousel_plan.draft_prompt("Story", "https://x", "text", ["Photoshop"])
    assert '"cover": {"label": "ADOBE MAX 2026"' in prompt
    assert "Label = a plain string" in prompt


def test_a_label_written_as_a_fact_pair_is_accepted():
    plan = carousel_plan.load_plan(broken({"text": "NEW IN PHOTOSHOP", "quote": ""}))
    assert plan["cover"]["label"] == "NEW IN PHOTOSHOP"


def test_a_missing_label_is_retried_with_the_errors(monkeypatch, capsys):
    prompts = fake_claude(monkeypatch, [broken(None), make_plan()])
    data = carousel.draft_checked("T", "https://x", TEXT, "sonnet", ["Photoshop"])
    assert data["cover"]["label"] == "NEW IN PHOTOSHOP"
    assert len(prompts) == 2 and "cover.label: needs a short label" in prompts[1]
    assert "fixed by Claude after 1 retry" in capsys.readouterr().out


def test_a_label_that_stays_missing_falls_back_to_the_product_name(monkeypatch, capsys):
    prompts = fake_claude(monkeypatch, [broken(None)])
    data = carousel.draft_checked("T", "https://x", TEXT, "sonnet", ["Photoshop"])
    assert data["cover"]["label"] == "PHOTOSHOP"
    assert len(prompts) == 1 + carousel.DRAFT_RETRIES
    assert "Fallback used" in capsys.readouterr().out
    carousel_plan.load_plan(data)  # the build can continue


def test_another_error_that_stays_is_still_reported(monkeypatch):
    data = broken("NEW IN PHOTOSHOP")
    del data["captions"]
    fake_claude(monkeypatch, [data])
    with pytest.raises(carousel_plan.PlanError, match="captions"):
        carousel.draft_checked("T", "https://x", TEXT, "sonnet", ["Photoshop"])
