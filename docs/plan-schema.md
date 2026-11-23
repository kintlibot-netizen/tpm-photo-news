# Carousel plan schema (builds without Claude)

A plan is one JSON file per story, saved as `data/plans/story-<id>.json` (data/ is never committed). It is the same
plan Claude used to draft, plus a few build fields. `scripts/build_from_plan.py` reads it, checks every rule in code
and renders the slides. Claude is never called.

## Commands

```
.venv\Scripts\python.exe scripts\pending_carousels.py --sync                 stories waiting for a carousel
.venv\Scripts\python.exe scripts\pending_carousels.py --json --locate        the same as JSON, plus each official page's text
.venv\Scripts\python.exe scripts\pending_carousels.py --story 72 --official-url URL   save that page's text and images
.venv\Scripts\python.exe scripts\build_from_plan.py --story 72 --dry-run     build into output/plan-previews only
.venv\Scripts\python.exe scripts\build_from_plan.py --story 72               real build: record, Slack, push state/
```

Options of `build_from_plan.py`: `--plan FILE` (default `data/plans/story-<id>.json`), `--verdicts FILE` (default
`story-<id>.verdicts.json` beside the plan, or the plan's own `verdicts`), `--skip-render`, `--allow-removed`,
`--rebuild` (replace a draft the story already has), `--ignore-cap` (the 1 a day cap), `--no-sync`.

`pending_carousels.py --locate` saves `data/plans/story-<id>.official.txt` (the fact source: every quote must be
copied from it) and `data/plans/story-<id>.images.txt` (the images on the official page).

The carousel bot and the watcher build from plans only, never with Claude:
`scripts\carousel_bot.py --no-claude` and `src\run.py --no-claude --plans-only` (or `--carousels-only --no-claude`).
A story with no plan is skipped. A plan that failed is tried again only after the plan file is saved again.

## Build fields (kept out of plan.json in the carousel folder)

| Field | Required | Meaning |
|---|---|---|
| `story` | no | The story id. When given it must match `--story`. |
| `official_url` | yes | The brand's own page. Every fact is quoted from this page. It must be on the brand's official domains in config/carousel.yaml. |
| `brand` | no | Only when the story was filed under the wrong brand or none (for example a Thypoch lens filed under Fujifilm). Its official domains must be in config/carousel.yaml. |
| `images` | yes | The official image for each feature slide, see below. A feature slide with no official image stops the build: find a real official image of that feature or drop the slide. |
| `verdicts` | no | The fact and image check verdicts, see below. |
| `author` | no | Who wrote the plan, shown in sources.md. Default: Grok Bot. |

## The plan (the same shape Claude drafted)

Every fact is `{"text": "...", "quote": "..."}`. The quote is copied word for word from the official page (at least
12 characters; case, spacing, curly quotes and dash variants are ignored). A fact whose quote is not on the page stops
the build (or is removed with `--allow-removed`).

- `product`: the product name, written exactly as the official page writes it.
- `cover`: `label` (short pill text, under 60 characters), `headline` (a fact, under 45 characters, the product name
  as the page writes it), `subline` (the hook, a fact, under 52 characters), optional `subline_alt` (a second hook).
- `slides`: 3 to 5 feature slides. Each has `template` (`left_body`, `stat_specs` or `stat_hero`), `label`,
  `headline` (a fact, under 45 characters, no brackets), optional `accent` (a fact), optional `body` (a fact, one
  sentence under 140 characters, no hyphenated words, does not repeat the product name), and `specs` (up to 3 of
  `{"value", "caption", "icon"}`, icon one of sensor, burst, focus, stabilize, video, battery, box, star).
- `comparison`: null, or `label`, `title` and up to 6 `rows` of `{"name", "new", "old"}`.
- `price`: null, or `label`, up to 2 `prices` of `{"value", "caption"}`, `availability`, optional `quick_take`
  `{"sentence", "question"}`.
- `captions`: `david` (first person) and `tpm` (we). Each has `hook` (under 10 words; an opinion needs no quote),
  2 or 3 `facts` and `closing` (a question or call to action; no quote needed). TPM Facebook and TPM Instagram share
  the `tpm` caption.

Copy rules checked in code: no em or en dashes, no spaced hyphens, no hashtags, text that fits its box at 1080 x 1440,
captions under 50 words. The YOUR TAKE closing slide is added by code when there is room (it states no product fact).

## Images

```json
"images": {
  "cover": {"image_url": "https://brand.com/img/hero.jpg", "page_url": "https://brand.com/news/post"},
  "ENHANCE": {"image_url": "https://media.brand.com/enhance.jpg", "page_url": "https://brand.com/enhance",
              "check": {"matches_product": true, "is_real_photo_or_official_screenshot": true,
                        "shows_slide_subject": true, "has_watermark": false, "has_people_as_subject": false,
                        "looks_ai_generated": false, "notes": "official Enhance result photo"}}
}
```

The key is `cover`, `price`, `comparison`, `comparison-old` or a feature slide's headline (the image follows its
feature). Code checks: both URLs on the brand's official domains (or the image on the page's own host), the image
really appears on that page, it downloads as a real JPEG, PNG or WebP of at least 1000px with no AI metadata, its file
name and alt text do not say AI, logo or people, and the `check` passes (the plan author looked at the image). The
same image is never used on two feature slides. Uniform side strips are trimmed; nothing else is edited.
With no cover image, the cover is a collage of the feature images.

## Verdicts (optional)

```json
{"facts": {"slide1.body": {"verdict": "CONFIRMED", "quote": "exact words from the page"}},
 "images": {"ENHANCE": {"matches_product": true, "...": "..."}}}
```

Fact ids: `product`, `cover.headline`, `cover.subline`, `slide1.headline`, `slide1.accent`, `slide1.body`,
`slide1.spec1.value`, `price.1.value`, `price.availability`, `captions.david.hook`, `captions.tpm.fact2` and so on.
A verdict is CONFIRMED, NOT CONFIRMED or NOT A FACT. Facts with no verdict are decided by the quote check alone.

## Filled example: story 61, DJI ROMO P2 (the existing plan, wrapped with the build fields)

This is the plan.json of output/carousels/2026-11-19-dji-romo-p2-uk-price-and-availability-announced with the build
fields added. Note: that draft quoted the dji.com home page, not a ROMO P2 page, so its slides are about other DJI
products. It shows the format only; it is not a good carousel for that story.

```json
{
  "story": 61,
  "brand": "DJI",
  "official_url": "https://www.dji.com",
  "author": "Grok Bot",
  "product": {
    "text": "DJI",
    "quote": "DJI - Official Website"
  },
  "cover": {
    "label": "NEW IN DJI",
    "headline": {
      "text": "DJI",
      "quote": "DJI - Official Website"
    },
    "subline": {
      "text": "8K FLAGSHIP 360° DRONE",
      "quote": "8K Flagship 360° Drone"
    },
    "subline_alt": {
      "text": "8K 360° CAMERA",
      "quote": "8K 360° Camera"
    }
  },
  "slides": [
    {
      "template": "left_body",
      "label": "NEW DRONE",
      "headline": {
        "text": "AVATA 360",
        "quote": "Shot on DJI Avata 360"
      },
      "accent": {
        "text": "8K FLAGSHIP 360° DRONE",
        "quote": "8K Flagship 360° Drone"
      },
      "body": {
        "text": "Its tagline promises you can see it all from above.",
        "quote": "Above It All, See It All"
      },
      "specs": []
    },
    {
      "template": "left_body",
      "label": "NEW CAMERA",
      "headline": {
        "text": "OSMO POCKET 4P",
        "quote": "Shot on Osmo Pocket 4P"
      },
      "accent": {
        "text": "DUAL LENS CINEMATIC GIMBAL CAMERA",
        "quote": "Dual-Lens Cinematic Pocket Gimbal Camera"
      },
      "body": {
        "text": "A pocket gimbal camera with two lenses made for cinematic shots.",
        "quote": "Dual-Lens Cinematic Pocket Gimbal Camera"
      },
      "specs": []
    },
    {
      "template": "left_body",
      "label": "NEW CAMERA",
      "headline": {
        "text": "OSMO 360 II",
        "quote": "Shot on Osmo 360 II"
      },
      "accent": {
        "text": "8K 360° CAMERA",
        "quote": "8K 360° Camera"
      },
      "body": {
        "text": "The tagline promises all angles and all epic.",
        "quote": "All Angles. All Epic."
      },
      "specs": []
    },
    {
      "template": "left_body",
      "label": "NEW MIC",
      "headline": {
        "text": "MIC MINI 2S",
        "quote": "mic-mini-2s"
      },
      "accent": {
        "text": "INTERNAL RECORDING MIC",
        "quote": "Internal Recording Mini Wireless Mic"
      },
      "body": {
        "text": "A mini wireless mic that records internally.",
        "quote": "Internal Recording Mini Wireless Mic"
      },
      "specs": []
    }
  ],
  "comparison": null,
  "price": null,
  "captions": {
    "david": {
      "hook": {
        "text": "My pick from DJI is the Avata 360.",
        "quote": ""
      },
      "facts": [
        {
          "text": "Avata 360 is an 8K flagship 360° drone.",
          "quote": "8K Flagship 360° Drone"
        },
        {
          "text": "Osmo Pocket 4P is a dual lens cinematic pocket gimbal camera.",
          "quote": "Dual-Lens Cinematic Pocket Gimbal Camera"
        }
      ],
      "closing": {
        "text": "Which DJI camera would you take on your next trip?",
        "quote": ""
      }
    },
    "tpm": {
      "hook": {
        "text": "We think the Avata 360 is the one to watch.",
        "quote": ""
      },
      "facts": [
        {
          "text": "You get an 8K flagship 360° drone with Avata 360.",
          "quote": "8K Flagship 360° Drone"
        },
        {
          "text": "Osmo 360 II gives you an 8K 360° camera.",
          "quote": "8K 360° Camera"
        }
      ],
      "closing": {
        "text": "Drone or camera, which would you pick first?",
        "quote": ""
      }
    }
  },
  "images": {}
}
```
