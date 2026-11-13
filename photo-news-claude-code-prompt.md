# Claude Code prompt: Photo-news → carousel automation

How to use: open the `photo-news-kit/` folder in Claude Code and put your 6 original sample slides in `reference-slides/` (names listed in its README). Then paste everything below the line. Items marked `[CONFIRM WITH DAVID]` or `[FILL IN]` in Section 4 are still open; Claude Code will ask about them.

---

You're helping me (Kint, marketing VA for The Photo Mentorship, "TPM") build a **photo-news → social carousel automation** for TPM and photographer David Molnar. I'm not a developer. Build exactly what David asked for, follow his rules, and ask when something isn't covered. Don't fill gaps with generic "best practice" features.

## 1. Goal (David's words)

When there's photography news, the system finds it, alerts our team, and designs a ready-to-post Instagram/Facebook carousel, so we can post while it's timely.

> "...hey, this new camera came out, or Photoshop just released a new version, Here are the new features. Lightroom just did an update... [Claude] to alert us. and then just design a carousel for Instagram or Facebook... that's saying, here's the news. bam bam, bam. And for us to be able to be really timely with it." (huddle, Jul 15, 2026)
>
> "...as soon as we get the news, it designs a carousel for us... and then it can be posted quickly... so that we're a source of news." (Jul 15)

David calls this a long-term "dream" to build up to, with no deadline. Start small and safe.

## 2. David's rules (these are requirements, not suggestions)

**What it does**
- **R1 Watch news and trends:** new cameras, Photoshop versions and features, Lightroom updates, "popular topics". (Jul 15)
- **R2 Alert the team:** "[Claude] to alert us." (Jul 15)
- **R3 Make a carousel for Instagram/Facebook:** "here's the news. bam bam, bam." (Jul 15)
- **R4 Be timely:** "as soon as we get the news... posted quickly." (Jul 15)
- **R5 Claude does the searching and design:** "use Claude to... search the internet and find out photo news... Claude has a design tool now... other things you can plug into it to build a carousel." (Jul 15)
- **R6 Fit into a schedule:** "build a system to where we can schedule stuff out." Today Kint schedules in Meta Business Suite. (Jul 15)
- **R17 Use AI as much as possible:** "a lot of your stuff is gonna be trying to teach Claude to do stuff for you." (Jun 9)
- **R18 Build carousels "the way we like"**, using reusable Claude skills or shared projects. (Jun 9)
- **R19 (related, later phase):** "keep an eye on our industry... look for trending content... provide me a list of ideas each week." (Jun 9)

**Content quality**
- **R7 Facts must be correct.** David caught "R8 Mark two" printed on a camera that should just say "EOS". (Sep 16)
- **R8 Captions are short, casual and excited:** "I'm excited to check this out..." (Sep 16)
- **R15 Gut-check:** "make sure... it's correctly spelled and that it makes sense." (Jul 15)

**Images**
- **R11 Our own imagery only:** "I like the information that's in these types of slides. But I don't want to use any of their imagery." (Aug 6)
- **R12 Real photos, or AI images we generate ourselves.** Run AI images through Canva or Figma before posting. (Aug 6)
- **R13 Try to remove the "AI content" label** by re-exporting from Figma/Canva: "you can ask Claude how to do that." (Aug 6)
- **R14 No fake-looking AI people:** "I definitely don't want to use like super fake looking AI people." (Aug 6)
- No images with someone else's watermark. (Sep 11)
- Selfies or personal photos must really be of the person shown. (Aug 6)

**Accounts and voice**
- **R9 and R10 Post to David Molnar Facebook, TPM Facebook and TPM Instagram. Never David's personal Instagram:** "post it everywhere, Except my dm instagram." (Sep 16) His personal IG is curated: "I want it to be prettier." (Jul 15)
- David's Facebook speaks as **"I"**. TPM pages speak as **"we"**. (approved captions, Sep 16)
- Say **"TPM member"**, never "student". (Oct 29)
- Check the **photo opt-out list** before using any member's photo. (Oct 29)
- Credit **Images of Grace Photography** on David's family photos. (Sep 17)

**Approval**
- **R16 A person approves before anything is posted.** David approves image posts first, tracked in Figma "ready to post" and "posted" columns. (Sep 11) David never asked for posting without review.

## 3. Quality benchmark: Kint's R8 Mark II sample (visual target)

**Kint's requirement (Nov 11):** "I want the output to look exactly like that": short but direct, informative, and showing everything correctly. The 6 originals are in `reference-slides/`, and `STYLE-GUIDE.md` describes them in detail. **Read both before designing anything.**

- **Size:** 1080 × 1350 px (4:5 portrait), inferred from the sample previews. Confirm it from the original files.
- **Look:** dark navy-to-black background with a blue radial glow behind the product. Heavy condensed/grotesk headlines in white with light-blue gradient accent words. Uppercase, wide-spaced sublines. Pill labels, a thin cyan footer, light blue and cyan accents, and gold only on the comparison slide.
- **Slide order:** 1 cover ("JUST ANNOUNCED" + model + one-line hook, swipe cue) → 2 biggest upgrade → 3 side-by-side comparison with the previous model (icon rows: Resolution, Image Stabilization, AF System, Shooting Speed, Video, Other Features, Battery, Size + Weight) → 4–5 key features (speed, video/body callouts) → 6 price + availability + "OUR QUICK TAKE" + a question + "SHARE YOUR TAKE IN THE COMMENTS."
- **David's fixes on the Sep 16 version:** (1) the price-slide camera was badged "R8 Mark II", but the real one just says "EOS"; (2) use the red "JUST ANNOUNCED" image as slide 1; (3) add the comparison (R8 II vs R8) as slide 3, modeled on another account's post but redrawn in our own style. Note: the sample cover is dark blue, not red. Ask me which cover style to follow.
- **Errors in the sample set to avoid repeating:** the wrong badge on the price-slide camera; both 24.2 MP comparison cells saying "Same as EOS R6 Mark II" (suspect); the Shooting Speed row differing from the post it was modeled on; em dashes on slides 2 and 6. Copy the look, not these errors.
- **Approved captions (Sep 16):** David FB: "I'm excited to check this out! Canon just announced the new EOS R8 Mark II, and it looks like they packed some serious upgrades into this camera. What do you think—would you upgrade?" TPM FB & IG: "We're excited to check this out! Canon just announced the new EOS R8 Mark II, with some serious upgrades over the original R8. What do you think—would you upgrade?" (These contain an em dash; see Q8.)
- **Lesson:** verify every spec, price, date and product image against the **official brand announcement**, never social posts.

## 4. Answers (Kint's, Nov 11, plus what's still open)

**Rule for you, Claude Code:** if an item you need is still `[FILL IN]` or `[CONFIRM WITH DAVID]`, **stop and ask me**. Don't guess. You may propose a default, labeled as a suggestion.

1. **Sources:** official announcements **and** rumors. Kint: "always make sure that everything is accurate and authentic news, as well as the images of the cameras, gears, lenses, equipments." Every item must have sources. How rumors are labeled on slides and captions, and how many independent sources a rumor needs: `[FILL IN]`. Specific sites/brands list: `[FILL IN]` (propose one for my approval).
2. **Alerts:** to Kint's Slack, `https://app.slack.com/client/T02R9AUFL/D0B5S55LKU4` (workspace `T02R9AUFL`, conversation `D0B5S55LKU4`). It has to be a free method; tell me exactly what setup it needs. Recipients: Kint. Others `[CONFIRM WITH DAVID]`.
3. **Check frequency:** `[FILL IN]`
4. **Post-worthy:** "the new product and update, the big launches that will play a big role to the photographers", worthy of social and attention-grabbing for TPM's audience. Volume cap: `[FILL IN]`
5. **Approval flow:** David approves image posts before posting (his Sep 11 rule). Who covers when he's away: `[CONFIRM WITH DAVID]`
6. **Slides:** match the sample exactly. 1080 × 1350 (inferred), 6-slide structure by default; fewer slides for smaller news `[FILL IN]`. Template owner (Rich?): `[CONFIRM WITH DAVID]`
7. **Product images:** they must show the real product accurately (badges, controls, ports). Whether brand press images are allowed (with credit), given David's "our own imagery" rule: `[CONFIRM WITH DAVID]`
8. **Captions:** "make an engaging caption and should have a hook." "I" on David FB, "we" on TPM. Hashtags: `[FILL IN]`. Source credit in the caption: `[FILL IN]`. Em dashes: `[CONFIRM WITH DAVID]` (banned in emails; present in the approved Sep 16 captions). Until confirmed, use none.
9. **Accounts:** TPM Facebook, TPM Instagram, David Molnar Facebook only.
10. **Claude setup:** Claude Code (what Kint already has). No paid API keys.
11. **Budget:** **$0. Free tools only, no paid APIs.** Free RSS feeds, free Slack incoming webhooks, local scripts and free scheduling are fine. Anything that costs money: stop and ask.

## 5. Phases (each one gated on my sign-off)

Don't start the next phase until I write "Phase N approved."

**Phase 1: News watcher + alerts (no posting of any kind)**
- [ ] Checks the agreed sources (Q1) on the agreed schedule (Q3), using free methods only (Q11).
- [ ] Dedupes: the same story never alerts twice.
- [ ] Each item is classified as relevant or not, by category, with a one-line summary, its source link(s), and a label of official or rumor, applying Q4. Classification runs without a paid API (Q10, Q11), for example inside Claude Code or with free rules. Propose how.
- [ ] Sends alerts to Kint's Slack conversation (Q2) through a free method.
- [ ] Contains no code that posts to social media.
- [ ] Has tests for fetching, deduping and classifying, plus exact run commands. I've run it and seen a real alert.

**Phase 2: Carousel drafts with a fact-check pass**
- [ ] For an item I pick, it makes slides at 1080 × 1350 that match `reference-slides/` and `STYLE-GUIDE.md` (Q6): same look, same slide pattern, same short and punchy copy.
- [ ] Every fact on a slide is tied to an official source URL.
- [ ] A separate fact-check step compares each claim to the official announcement and flags anything it can't confirm. Nothing unconfirmed goes on a slide unmarked.
- [ ] Images follow R11–R14 and Q7: no other accounts' images, no watermarks, no fake-looking AI people, and product images that show the real badge, controls and ports.
- [ ] Writes two captions that open with a hook: David's FB ("I") and TPM FB/IG ("we"), following R8 and Q8, each fact sourced.
- [ ] Outputs one folder per item: slides, `captions.txt`, `sources.md`, `factcheck.md`.
- [ ] Still posts nothing.

**Phase 3: Review and publish**
- [ ] Drafts go to the agreed review spot (for example the Figma "ready to post" column), and nothing moves forward without approval (R16, Q5).
- [ ] Publishing is done by hand in Meta Business Suite (free), only after approval. Any automatic publishing needs my OK first and must be free.
- [ ] David's personal Instagram can't be selected. It's hard-blocked in code.
- [ ] Every post is logged (what, where, when, who approved).

## 6. How to work with me

- **Plan first.** Before any code: architecture, phases, tech stack, confirmation that every tool is free, and your questions on Section 4. Wait for my answers.
- **Small steps.** One piece at a time. After each, tell me what changed and how to check it.
- **Explain every file** in plain words for a non-developer: what it does and when I'd touch it.
- **Secrets go in `.env`**, which is never committed (add it to `.gitignore`). Never copy any passwords from the Slack DM into this project. I'll set up proper keys.
- **Tests and exact commands:** give copy-paste commands to install, run and test.
- **Costs:** the budget is $0. Use free tools only. If something would cost money, stop and ask; don't sign up for anything.
- **Don't invent requirements.** Keep "David's rules" separate from "my suggestion" in everything you write, and label suggestions clearly.

## 7. Self-review before every handover

Before you tell me a phase is done, go through Section 2 rule by rule and Section 4 answer by answer, and report pass, fail or not applicable for each, with a one-line reason. Also confirm:
- [ ] No other accounts' images, no watermarks, no fake AI people.
- [ ] "TPM member", not "student"; "I" on David's FB and "we" on TPM.
- [ ] The opt-out list is respected, and David's personal Instagram is excluded.
- [ ] Slides match `reference-slides/` and `STYLE-GUIDE.md`, every claim has an official source, and none of the sample-set errors are repeated.
- [ ] Everything used is free.
- [ ] Nothing posts without approval.
- [ ] No secrets in code or in git.
- [ ] The phase checklist in Section 5 is fully ticked.

Fix anything that fails before handing over.

**Start now:** confirm you've read this prompt, `STYLE-GUIDE.md`, the files in `reference-slides/` and `photo-news-automation-brief.md`. Then give me the plan and list every Section 4 item still marked `[FILL IN]` or `[CONFIRM WITH DAVID]` as a question.
