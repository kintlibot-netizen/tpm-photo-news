# Style guide: photo-news carousels (TPM / David Molnar)

This guide is based on Kint's 6-slide Canon EOS R8 Mark II sample set (Sep 2026). Kint's originals go in `reference-slides/`, and **they are the visual target**: Kint wants new carousels to look like them. Where this guide and the reference files disagree, the files win on the look, and the accuracy rules below win on the content.

## 1. Format
- **Export size: 1080 × 1350 px (4:5 portrait).** This size is inferred: the sample previews were about 622×819 and 656×819, which is roughly 4:5. Check it against the original files in `reference-slides/` when they're added.
- PNG, sRGB. One file per slide, numbered in carousel order (`01-…png`, `02-…png`).
- The sample has 6 slides. Treat that as the default shape, not a fixed count. Use fewer slides when the news is smaller (Kint to confirm).

## 2. Common look (every slide)
- **Background:** dark navy fading to black, with a **blue radial glow behind the product**.
- **Image first (Kint's standing rule, Nov 27 2026, for every carousel from now on):** the official image is always bigger than the text. On every slide with an image, the image takes clearly more of the slide than the text: about 55 to 65 percent where the image allows (a product shot on a flat white or black background fills the full width image area on a card of its own colour), and a screenshot or busy photo is shown whole, edge to edge. The design check fails any slide whose text covers as much as its image.
- **Every slide has a real official graphic (Kint, Nov 28 2026):** the YOUR TAKE closing slide shows the carousel's own official feature images (up to four, whole, in rows under a moderate question), and the price slide its official product image. The design check fails a closing or call to action slide with no official image.
- **Headlines:** a heavy condensed or grotesk display font, bold but moderate (feature names about 72 to 84px, cover name about 100px, body about 27px), in white with **light-blue gradient** accent words. Never so big that the text competes with the image.
- **Sublines:** UPPERCASE with wide letter-spacing.
- **Body:** a clean sans-serif, one short line at most.
- **Accent colors:** light blue, cyan, and **gold, used only on the comparison slide** (new-model values and headers).
- **Pill label** at the top of most slides: an outlined rounded rectangle with an uppercase spaced label.
- **Footer:** a thin cyan line with uppercase spaced text. The cover says "SWIPE FOR THE BIGGEST UPGRADES →"; the other slides show the product name ("CANON EOS R8 MARK II").
- **Product imagery:** a hero shot of the actual product, lit against the glow, on a dark reflective surface where it fits.
- **Copy:** very short and punchy. One idea per slide, informative and direct.

## 3. Slide-by-slide template (from the R8 Mark II sample)

| # | File | Role | Contents |
|---|---|---|---|
| 1 | `01-cover.png` | Cover / hook | Pill "JUST ANNOUNCED". Headline "CANON EOS" (white) + "R8 MARK II" (light-blue gradient). Spaced subline "FULL-FRAME. NOW STABILIZED." Camera hero with the screen flipped out, on a reflective surface with a blue glow. Footer "SWIPE FOR THE BIGGEST UPGRADES →". |
| 2 | `02-biggest-upgrade.png` | #1 upgrade | Pill "THE BIGGEST UPGRADE". Headline "5-AXIS IN-BODY STABILIZATION" (white + light blue). Cyan subhead "UP TO 7.5 STOPS". One body line explaining why it matters. Body-only shot with blue motion arrows over the sensor. Product-name footer. |
| 3 | `03-comparison.png` | New vs. previous model | Title "EOS R8 MARK II vs EOS R8" ("vs" in blue), "SIDE-BY-SIDE COMPARISON", "SAME DNA. A BIGGER LEAP." Two body-only cameras. Dark table: gold headers for the new model ("2ND GENERATION"), light-blue for the old ("1ST GENERATION"). Center icon column for the rows: Resolution, Image Stabilization, AF System, Shooting Speed, Video, Other Features, Battery, Size + Weight. New values in gold, old in white, all uppercase. |
| 4 | `04-40fps.png` | Speed / stills feature | Pill "FAST WHEN THE MOMENT MOVES". Headline "40 FPS" + "ELECTRONIC BURST". Three icon stat columns (24.2MP full-frame sensor; pre-continuous capture up to 20 frames; Dual Pixel CMOS AF II recognizing people, animals, vehicles). Camera with lens + three stacked kingfisher burst frames, one with an AF box. Product-name footer. |
| 5 | `05-4k60p.png` | Video / body features | Pill "BUILT FOR HYBRID CREATORS". Headline "4K" (white) "60P" (light blue) + "PLUS 1080P UP TO 180 FPS". Rear view on a tripod with the screen out, callout lines to "NEW AF JOYSTICK", "SIDE-ACCESS SD SLOT", "RETRO-INSPIRED BODY". One small sentence. Product-name footer. |
| 6 | `06-price.png` | Price, availability, engagement | Pill "PRICE + AVAILABILITY". Two big prices ("$1,899 BODY ONLY" / "$2,099 WITH RF 24–50MM IS STM") with a thin divider. "EXPECTED LATE OCTOBER" between thin lines. Camera-with-lens hero. "OUR QUICK TAKE" with one sentence. A bold question with the key model in light blue ("…step up to the R6 Mark III?"). Pill CTA "SHARE YOUR TAKE IN THE COMMENTS." Product-name footer. |

General pattern: **hook cover → biggest upgrade → comparison with the previous model → 1–2 key feature slides → price/availability + quick take + question CTA.**

## 4. Accuracy rules (these override the look)
- Every spec, name, price and date has to match an **official source** (the brand announcement, spec page or press release). Keep the source URL for every claim.
- **Product images have to show the real product correctly:** the right badge and model name, buttons, ports and screen. David's own fix: the price-slide camera was badged "R8 Mark II", but the real camera just says "EOS".
- Never copy a spec from social posts or other accounts.
- Rumors are allowed (Kint, Nov 11), but they have to come from credible sources with links and be presented truthfully. The exact rumor labeling still needs confirming (see the prompt's open items).

### Problems found in the sample set (don't repeat them)
1. **Price slide:** the camera is badged "R8 Mark II". The real body only says "EOS" (David, Sep 16).
2. **Comparison, Resolution row:** both 24.2 MP cells say "Same as EOS R6 Mark II", which is suspect. Verify against Canon's spec sheets.
3. **Comparison, Shooting Speed row:** the values differ from the third-party post this slide was modeled on. Verify against Canon's official specs for both bodies.
4. **Em dashes in copy** on slides 2 and 6 ("…most—sensor-shift…", "Would you choose this—or…"). David banned em dashes in emails because they read as AI. Avoid them on slides until Kint or David confirms otherwise.

## 5. Captions (Kint, Nov 11)
- Engaging, and it has to **open with a hook**.
- Short, casual and excited, in David's style (R8): "I'm excited to check this out!…"
- **"I"** on David Molnar Facebook, **"we"** on TPM Facebook and Instagram.
- End with a question that invites comments (as in the approved R8 captions and the slide 6 CTA).
- No em dashes (pending confirmation). Hashtags: not decided yet.
- Every fact in the caption has to be backed by the same sources as the slides.

## 6. Never
- Use another account's imagery or watermarked images (David, Aug 6 / Sep 11).
- Use fake-looking AI people (Aug 6).
- Use AI product renders that get badges, ports or controls wrong.
- Post to David's personal Instagram.
