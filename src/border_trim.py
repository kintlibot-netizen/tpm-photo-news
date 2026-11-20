"""Trims flat uniform strips (grey, white or dark) off the edges of an official image, each side on its own.

Adobe's demo poster frames come inside a plain grey bezel (about 106px at the sides, 68px at the top and 70px at the
bottom on a 1920 x 1080 frame), sometimes with a second, slightly different grey strip beside it, and some official
screenshots sit on white bars. On a slide that looks like an unfinished mockup, so when an image is saved the strips
are cropped away and only the inner picture is kept.

Each of the four sides is judged on its own: a strip on one side only is trimmed and the other sides stay as they are.
A side has a strip when:
- its outermost line of pixels has a neutral colour (every channel within 24 of each other: grey, white or near black)
  as one of its two most common colours. The line is read by those two colours, not by its median, so an app panel
  laid over half of the edge (the Layers panel on the Generative Restyle poster) cannot hide the strip beside it,
- at least MIN_SIDE lines in a row are mostly that colour (every channel within TOLERANCE of it; the share is
  BORDER_SHARE, 40 percent, so a glow, a cursor or an app panel over part of the edge does not stop the trim; it is
  clipped),
- the strip is not wider than MAX_SHARE of the image (light colours) or DARK_MAX_SHARE (dark or mid grey, so a dark
  app panel is never cut into). A mostly grey picture is never eaten.
Up to MAX_PASSES passes run: after a side is trimmed it is looked at again, because the posters have a second, slightly
different grey strip beside the bezel (the 12 to 15px strip on the right of the Generative Restyle poster). Later
passes only look at sides already trimmed, and the total per side stays under the same width cap.
The crop keeps INSET extra pixels off each trimmed edge to drop the soft pixels where the picture meets the strip.

Nothing is repainted, scaled or filtered: the result is a rectangular crop of the decoded pixels, saved as PNG
(lossless). The pixels are read and cropped in Chromium through Playwright (already used for rendering), because
this project has no image library. If Playwright or Chromium is not available, the image is kept untouched.
"""
from __future__ import annotations

import base64

TRIM_NOTE = "uniform border trimmed, no content changed"

TRIM_SCRIPT = """async (args) => {
  const [dataUrl, TOL, BORDER_SHARE, MIN_SIDE, MAX_SHARE, INSET, DARK_MAX_SHARE, MAX_PASSES] = args;
  const img = new Image();
  img.src = dataUrl;
  try { await img.decode(); } catch (e) { return {trimmed: false, reason: 'the image could not be decoded'}; }
  const w = img.naturalWidth, h = img.naturalHeight;
  if (w < 100 || h < 100) return {trimmed: false, reason: 'the image is too small'};
  const canvas = document.createElement('canvas');
  canvas.width = w; canvas.height = h;
  const ctx = canvas.getContext('2d', {willReadFrequently: true});
  ctx.drawImage(img, 0, 0);
  const px = ctx.getImageData(0, 0, w, h).data;
  const median = (values) => values.sort((a, b) => a - b)[values.length >> 1];
  // One side. n = lines deep the area is, len = length of a line, idx(k, j) = index of pixel j of line k,
  // used = pixels of this side already trimmed by an earlier pass, full = the whole image size on this axis
  // (the width cap is a share of it).
  const side = (n, len, idx, used, full) => {
    const step = Math.max(1, Math.floor(len / 64));
    // The outer line is judged by its two most common colours, not its median: an app panel laid over half of the
    // edge must not hide the strip beside it.
    const buckets = new Map();
    let total = 0;
    for (let j = 0; j < len; j += step) {
      const i = idx(0, j);
      const key = (px[i] >> 3) * 1024 + (px[i + 1] >> 3) * 32 + (px[i + 2] >> 3);
      if (!buckets.has(key)) buckets.set(key, []);
      buckets.get(key).push(i);
      total++;
    }
    const modes = [...buckets.values()].sort((a, b) => b.length - a.length).slice(0, 2)
      .filter((m) => m.length >= total * 0.25);
    let best = 0;
    for (const members of modes) {
      const base = [0, 1, 2].map((c) => median(members.map((i) => px[i + c])));
      if (Math.max(...base) - Math.min(...base) > 24) continue;
      const cap = Math.floor(full * (Math.min(...base) >= 150 ? MAX_SHARE : DARK_MAX_SHARE)) - used;
      const mostly = (k) => {
        let near = 0;
        for (let j = 0; j < len; j++) {
          const i = idx(k, j);
          if (Math.abs(px[i] - base[0]) <= TOL && Math.abs(px[i + 1] - base[1]) <= TOL
              && Math.abs(px[i + 2] - base[2]) <= TOL) near++;
        }
        return near >= len * BORDER_SHARE;
      };
      let k = 0;
      while (k <= cap && k < n && mostly(k)) k++;
      if (k <= cap && k >= MIN_SIDE && k > best) best = k;
    }
    return best;
  };
  // Pass 1 looks at all four sides. A later pass only looks again at the sides already trimmed, because the posters
  // have a second, slightly different grey strip right beside the bezel.
  // A later pass starts its scan INSET pixels past the strip already cut (those are the soft pixels where two strips
  // meet). When it finds a second strip there, the skipped INSET pixels sat between the two strips, so they are
  // counted as strip too: the side's total is then the full width of both strips.
  const cut = {left: 0, right: 0, top: 0, bottom: 0};   // strip pixels trimmed per side
  const hits = {left: 0, right: 0, top: 0, bottom: 0};  // passes that trimmed this side (INSET soft pixels each)
  const skip = (name) => (cut[name] > 0 ? INSET : 0);    // soft pixels skipped before this pass's scan
  let passes = 0;
  for (let pass = 0; pass < MAX_PASSES; pass++) {
    const x0 = cut.left + skip('left'), y0 = cut.top + skip('top');
    const x1 = w - cut.right - skip('right'), y1 = h - cut.bottom - skip('bottom');
    const rw = x1 - x0, rh = y1 - y0;
    const only = (name) => pass === 0 || cut[name] > 0;
    const used = (name) => cut[name] + skip(name);
    const found = {
      left: only('left') ? side(rw, rh, (k, j) => ((y0 + j) * w + x0 + k) * 4, used('left'), w) : 0,
      right: only('right') ? side(rw, rh, (k, j) => ((y0 + j) * w + (x1 - 1 - k)) * 4, used('right'), w) : 0,
      top: only('top') ? side(rh, rw, (k, j) => ((y0 + k) * w + x0 + j) * 4, used('top'), h) : 0,
      bottom: only('bottom') ? side(rh, rw, (k, j) => ((y1 - 1 - k) * w + x0 + j) * 4, used('bottom'), h) : 0,
    };
    if (!(found.left || found.right || found.top || found.bottom)) break;
    for (const name of Object.keys(found)) {
      if (found[name]) { cut[name] += skip(name) + found[name]; hits[name]++; }
    }
    passes++;
  }
  if (!passes) return {trimmed: false, reason: 'no uniform strip on any side'};
  const x0 = cut.left + INSET * hits.left, y0 = cut.top + INSET * hits.top;
  const x1 = w - cut.right - INSET * hits.right, y1 = h - cut.bottom - INSET * hits.bottom;
  if (x1 - x0 < 100 || y1 - y0 < 100) return {trimmed: false, reason: 'the strips leave too little picture'};
  const out = document.createElement('canvas');
  out.width = x1 - x0; out.height = y1 - y0;
  out.getContext('2d').drawImage(canvas, x0, y0, out.width, out.height, 0, 0, out.width, out.height);
  return {trimmed: true, left: cut.left, right: cut.right, top: cut.top, bottom: cut.bottom, inset: INSET, passes,
          width: out.width, height: out.height, source_width: w, source_height: h,
          png: out.toDataURL('image/png').split(',')[1]};
}"""

TOLERANCE, BORDER_SHARE, MIN_SIDE, MAX_SHARE, INSET, DARK_MAX_SHARE, MAX_PASSES = 12, 0.4, 4, 0.25, 2, 0.04, 3


def _mime(data: bytes) -> str:
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "image/png"


def describe(info: dict) -> str:
    """The line recorded in sources.md for a trimmed image."""
    passes = f" in each of {info['passes']} passes" if info.get("passes", 1) > 1 else ""
    return (f"{TRIM_NOTE}: {info['left']}px left, {info['right']}px right, {info['top']}px top, "
            f"{info['bottom']}px bottom (plus {info['inset']}px of soft edge on each trimmed side{passes}), "
            f"{info['source_width']}x{info['source_height']} became {info['width']}x{info['height']}")


def trim_many(datas: list[bytes]) -> list[tuple[bytes, dict]]:
    """For each image: (bytes to use, info). info["trimmed"] is True when a strip was cropped (the bytes are then a
    PNG of the inner area); otherwise the bytes are the original and info["reason"] says why nothing was trimmed."""
    if not datas:
        return []
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return [(d, {"trimmed": False, "reason": "Playwright is not installed"}) for d in datas]
    results: list[tuple[bytes, dict]] = []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                page = browser.new_page()
                page.goto("about:blank")
                for data in datas:
                    url = f"data:{_mime(data)};base64," + base64.b64encode(data).decode("ascii")
                    info = page.evaluate(TRIM_SCRIPT, [url, TOLERANCE, BORDER_SHARE, MIN_SIDE, MAX_SHARE, INSET,
                                                       DARK_MAX_SHARE, MAX_PASSES])
                    if info.get("trimmed"):
                        results.append((base64.b64decode(info.pop("png")), info))
                    else:
                        results.append((data, info))
            finally:
                browser.close()
    except Exception as exc:  # the browser could not start: keep every image as it is
        done = len(results)
        reason = f"the browser could not run ({type(exc).__name__})"
        results += [(d, {"trimmed": False, "reason": reason}) for d in datas[done:]]
    return results


def trim_border(data: bytes) -> tuple[bytes, dict]:
    """One image. See trim_many."""
    return trim_many([data])[0]


# images.trim_all hands every poster of a build to trim_many at once: one Chromium start for all of them.
trim_border.many = trim_many
