"""Small JPEG previews of the slides, so David's copy loads fast on a phone.

The page shows the previews (720 px wide, about a tenth of the size). The full 1080 x 1440 PNGs stay in the pack for
the downloads and the single slide links. The previews are made with the same headless Chromium that renders the
slides (Playwright), so nothing new has to be installed. Nothing is generated or changed: each preview is the same
slide, only smaller.

If Chromium can't be started, make_previews returns 0 and share_pack uses the full PNGs on the page instead.
"""
from __future__ import annotations

import base64
from pathlib import Path

PREVIEW_WIDTH = 720
QUALITY = 0.84

_SCRIPT = """async ([data, width, quality]) => {
  const img = new Image();
  img.src = 'data:image/png;base64,' + data;
  await img.decode();
  const w = Math.min(width, img.naturalWidth);
  const h = Math.round(img.naturalHeight * w / img.naturalWidth);
  const canvas = document.createElement('canvas');
  canvas.width = w; canvas.height = h;
  const ctx = canvas.getContext('2d');
  ctx.imageSmoothingEnabled = true; ctx.imageSmoothingQuality = 'high';
  ctx.fillStyle = '#ffffff'; ctx.fillRect(0, 0, w, h);
  ctx.drawImage(img, 0, 0, w, h);
  return canvas.toDataURL('image/jpeg', quality);
}"""


def preview_name(slide: str) -> str:
    """01.png -> 01.jpg"""
    return Path(slide).with_suffix(".jpg").name


def make_previews(jobs: list[tuple[Path, Path]], width: int = PREVIEW_WIDTH, quality: float = QUALITY) -> int:
    """Writes each (png, jpg) pair. Returns how many previews were made; 0 when Chromium is not available.
    One browser is started for every slide, which keeps the export fast."""
    if not jobs:
        return 0
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return 0
    made = 0
    try:
        with sync_playwright() as play:
            browser = play.chromium.launch()
            try:
                page = browser.new_page()
                page.set_content("<!doctype html><html><body></body></html>")
                for source, target in jobs:
                    try:
                        data = base64.b64encode(Path(source).read_bytes()).decode("ascii")
                        url = page.evaluate(_SCRIPT, [data, width, quality])
                        payload = url.split(",", 1)[1] if isinstance(url, str) and url.startswith("data:image/jpeg") else ""
                        if not payload:
                            continue
                        Path(target).parent.mkdir(parents=True, exist_ok=True)
                        Path(target).write_bytes(base64.b64decode(payload))
                        made += 1
                    except Exception:  # one bad slide keeps its full PNG on the page; the others still get previews
                        continue
            finally:
                browser.close()
    except Exception:
        return made
    return made
