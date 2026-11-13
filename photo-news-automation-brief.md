# Build brief: Photo-news → carousel automation (The Photo Mentorship / David Molnar)

Prepared Nov 8, 2026 (Asia/Manila) from Kint's Slack DM with David Molnar (channel `D0B6C704TMH`): messages, threads, AI huddle notes and huddle transcripts. Times are Asia/Manila (PHT).

> **Read this first.** David has described this automation as a *long-term dream*, not a finished spec. Everything under "Requirements from David" comes from his own words. Anything not in his words is labeled as an open question or as **my suggestion**. Huddle transcripts are Slack's auto-transcription, which often writes "Claude" as "cloud", "clawed" or "quad". Those spots are marked `[Claude]` in the quotes.

---

## 1. Goal

When there's photography news (a new camera, a new Photoshop version, a Lightroom update), Claude should **find it, alert the team, and design a ready-to-post carousel** for Instagram/Facebook, so TPM and David can be a timely *source of photo news*.

> "...build, like there's some social media kind of systems that you can build and [Claude] to where it's looking for popular topics. and news, like, hey, this new camera came out, or Photoshop just released a new version, Here are the new features. Lightroom just, just did an update. Here are the new features like photo news. Eventually I want us to be able to, like, [Claude] to alert us. and then just design a carousel for Instagram or Facebook or whatever, that's saying, here's the news. bam bam, bam. And for us to be able to be really timely with it."
> David, huddle Jul 15, 2026 (transcript ~0:48–0:53) · [transcript](https://davidmolnar.slack.com/files/USLACKBOT/F0BHNQ4BZQC/huddle_transcript) · [huddle notes](https://davidmolnar.slack.com/docs/T02R9AUFL/F0BHK30C21G) · [huddle in channel](https://davidmolnar.slack.com/archives/D0B6C704TMH/p1784126722816789)

> "...when there's photo news like it'd be good for you know, our [Claude] accounts to get alerted. and then to auto generate content for it. that's like helpful news... That's my, that's my dream. I don't know how to make that happen. but that would be amazing. And I would love for you to be able to build up over time to that."
> David, huddle Jul 15 (~0:53:38)

> "We could use Claude to find out like, hey... here's photo news, like to search the internet and find out photo news, right? And then we could use Claude to... because Claude has a design tool now, and then there's other things you can plug into it to build a carousel with that news. and then as soon as we get the news, it designs a carousel for us or whatever and then it can be posted quickly. you know, so that we're a source of news."
> David, huddle Jul 15 (~0:56:29)

> "we wanna be a source of like of inspiration and help and humor and news."
> David, huddle Jul 15 (~0:54:33)

AI huddle notes summary (Jul 15): *"Long-term vision includes AI-powered systems to monitor photography news and auto-generate carousel posts for timely distribution."*

**Priority / pressure:** David said this is something to build up to, with no deadline: "I'm not saying I, I don't want to stress you out. I'm just saying that's my dream for us to, to kind of eventually work our way up to." (Jul 15, ~0:57:41)

---

## 2. Requirements from David (verbatim, with sources)

| # | Requirement | David's words | Date / source |
|---|---|---|---|
| R1 | Watch for photo news and popular topics | "looking for popular topics. and news, like, hey, this new camera came out, or Photoshop just released a new version... Lightroom just did an update" | Jul 15 huddle transcript ~0:48 |
| R2 | Alert the team | "[Claude] to alert us" / "our [Claude] accounts to get alerted" | Jul 15 ~0:48, ~0:53 |
| R3 | Auto-generate a carousel for the news | "design a carousel for Instagram or Facebook or whatever, that's saying, here's the news. bam bam, bam" | Jul 15 ~0:48 |
| R4 | Be fast / timely | "for us to be able to be really timely with it" / "as soon as we get the news, it designs a carousel... posted quickly" | Jul 15 ~0:48, ~0:56 |
| R5 | Use Claude to search and to design | "use Claude to... search the internet and find out photo news... Claude has a design tool now, and then there's other things you can plug into it to build a carousel" | Jul 15 ~0:56 |
| R6 | Fits a scheduling system | "I think we should build a system to where we can schedule stuff out and then when there's photo news..." | Jul 15 ~0:53 |
| R7 | Facts on slides must be correct | "The only problem is the slide with the prices on it actually, you see the name R8 Mark two on the camera which isn't true it would just say EOS there." | [Sep 16 message](https://davidmolnar.slack.com/archives/D0B6C704TMH/p1789564484488749) |
| R8 | Short, casual first-person caption | "...the rest are good with a short caption of 'I'm excited to check this out. Can't announce a new you know, Camera, blah blah blah.'" (dictated; he approved Kint's polished versions) | [Sep 16](https://davidmolnar.slack.com/archives/D0B6C704TMH/p1789564484488749), [approval](https://davidmolnar.slack.com/archives/D0B6C704TMH/p1789572878003209) |
| R9 | Platforms: everywhere except David's personal Instagram | "yea post it everywhere, Except my dm instagram." | [Sep 16](https://davidmolnar.slack.com/archives/D0B6C704TMH/p1789572182453569) |
| R10 | David's personal IG is curated | "I just don't like my personal Instagram. I want it to be prettier. than a bunch of ugly memes" ... "The David Molnar Facebook page, the TPM Facebook page, and the TPM Instagram I'm fine for you to post as much as you want." | Jul 15 huddle ~0:48:36–0:48:52 |
| R11 | Use our own imagery, not other accounts' | "I like the information that's in these types of slides. But I don't, I don't want to use any of their imagery." / "We want to use all of our own imagery." | Aug 6 huddle transcript ~0:28:45–0:29:36 |
| R12 | Real or our-own-AI images are both OK, but run AI images through Canva/Figma | "I want to have our own images here, either real images. or images that, that AI generates for us, and then I like your idea of using, putting it in Canva or someplace first so that it's not, hopefully it takes the AI info out of it." | Aug 6 ~0:28:45 |
| R13 | Try to avoid the "AI content" label | "even if we like make an AI content version, but then we pull it into [Figma] and then tweak stuff and then re-export it, maybe it can remove the AI content label, I don't know, but you can ask Claude how to do that." | Aug 6 ~1:09:32 |
| R14 | No super-fake AI people | "where we can't, especially for like... I definitely don't want to use like super fake looking AI people." | Aug 6 ~1:06:56 |
| R15 | Gut-check spelling and sense before posting | "just do what I call a gut check on it to make sure that it's like it's correctly spelled and that it, it makes sense" | Jul 15 ~0:48:52 |
| R16 | Image posts need David's approval first (latest rule) | Huddle notes Sep 11: "David requires approval before posting images"; use "ready to post" and "posted" columns. | [Sep 11 huddle notes](https://davidmolnar.slack.com/docs/T02R9AUFL/F0C12JK9R5H) |
| R17 | Use AI as much as possible; teach Claude | "I want us to use AI as much as possible... I think a lot of your stuff is gonna be trying to teach Claude to do stuff for you." | Jun 9 huddle transcript ~1:07 · [transcript](https://davidmolnar.slack.com/files/USLACKBOT/F0B9APP23FG/huddle_transcript) |
| R18 | Carousels "the way we like" via Claude skills / shared projects | "there's skills that people create where it's like, hey, we can build out a social media calendar for you. It can automatically create [carousels] on Instagram... it knows how to build carousels in the way that we like and it just goes, builds a carousel for you that it can post." | Jun 9 ~1:07 |
| R19 | Related: weekly trend scouting | "teach it like you're an expert social media manager. and I want you to basically keep an eye on our industry, and like, look for trending content... provide me a list of ideas each week" | Jun 9 ~1:07 |

Other social rules from David that apply to any post (from the same DM):
- Selfies or personal photos must really be of the person shown (Aug 6 huddle notes).
- No images with someone else's watermark (Sep 11).
- Credit Images of Grace Photography on David's family photos ([Sep 17](https://davidmolnar.slack.com/archives/D0B6C704TMH/p1789658424949759)).
- Say "TPM member", not "student" (Josh, relayed Oct 29).
- Check the photo opt-out list (Oct 29).

---

## 3. Inputs / sources to monitor

**From David:** only *categories*: new camera releases, Photoshop new versions/features, Lightroom updates/features, "popular topics", "trending content" in the photography industry. **He didn't name any brands, sites, or feeds.** Brands that show up in the chat's examples: Canon (EOS R8 Mark II), Adobe (Photoshop, Lightroom).

The R8 Mark II example started from (a) an announcement-style image Kint posted in the DM on Sep 16 ("JUST ANNOUNCED / CREATED TO EXPLORE / EOS R8 Mark II", [file](https://davidmolnar.slack.com/archives/D0B6C704TMH/p1789563708932789)) and (b) a screenshot David shared of a third-party Instagram comparison post (@kldslr_malaysia, "R8 II & R8 side-by-side comparison"), with "Might be good to make a slide like this too" ([Sep 16](https://davidmolnar.slack.com/archives/D0B6C704TMH/p1789566894342469)). So social posts from other accounts can be *idea* sources, but their imagery can't be reused (R11).

**Candidate sources (my research, not David's; confirm with him):**
- Photo news RSS feeds: DPReview `https://www.dpreview.com/feeds/news.xml`, PetaPixel `https://petapixel.com/feed/`, Fstoppers `https://fstoppers.com/feed`, Digital Camera World `https://www.digitalcameraworld.com/feeds.xml`, Amateur Photographer `https://amateurphotographer.com/feed/`, Camera Jabber `https://camerajabber.com/feed` (feeds listed by Feedspot / fornews.ai directories, checked Oct–Nov 2026).
- Brand newsrooms / release notes: Canon, Nikon, Sony, Fujifilm, Panasonic, OM System, Leica, DJI press pages; Adobe's Photoshop and Lightroom "what's new" pages and the Adobe blog. Feed URLs not verified here; check each.
- Rumor sites (Canon Rumors, Nikon Rumors, Sony Alpha Rumors, Fuji Rumors) are fast but unconfirmed. Ask David whether rumors are allowed or only official announcements.

---

## 4. Output content spec

What David specified:
- **Format:** carousel for Instagram and/or Facebook (R3).
- **Content:** "here's the news. bam bam, bam": the headline facts and new features (R1, R3).
- **Accuracy:** every spec and name on the slides has to be right (R7).
- **Caption:** short, casual, excited, first person on David's page (R8). Approved examples (Sep 16):
  - David Molnar Facebook: "I'm excited to check this out! Canon just announced the new EOS R8 Mark II, and it looks like they packed some serious upgrades into this camera. What do you think—would you upgrade?"
  - TPM Facebook & Instagram: "We're excited to check this out! Canon just announced the new EOS R8 Mark II, with some serious upgrades over the original R8. What do you think—would you upgrade?"
  - Note: David asked for **no em dashes** in email copy because they read as AI ([Oct 3](https://davidmolnar.slack.com/archives/D0B6C704TMH/p1790969883452809)). The approved captions above have one. Ask whether the rule covers social captions too.
- **Imagery:** our own (real, or AI-made by us), run through Canva/Figma; no other accounts' imagery, no watermarks, no fake-looking AI people (R11–R14).
- **Accounts:** David Molnar FB (first-person "I"), TPM FB + TPM IG (brand "we"); never David's personal IG (R9, R10).

Not specified by David (open): number of slides, image size/aspect ratio, brand colors/fonts/template, hashtags, CTA or link in caption, whether to mention TPM courses, whether to credit sources.

What the R8 example looked like (observed from the files, not a rule): Kint's generated set was 5 portrait slides with a dark blue "CAMERA NEWS • SEPTEMBER 2026" header, a "JUST ANNOUNCED" pill, a big headline (e.g. "CANON EOS R8 MARK II / FULL-FRAME. NOW STABILIZED."), feature slides (e.g. "4K 60P / PLUS 1080P UP TO 180 FPS" with callouts), a price slide, a "SWIPE FOR THE BIGGEST UPGRADES →" cue, and an "04 / 05" counter. David's edits: use the red announcement image as slide 1, add a side-by-side comparison slide as slide 3 (modeled on the third-party post, redrawn in our style), fix the camera name on the price slide.

---

## 5. Workflow / approval steps

As described or practiced in the chat:
1. Claude finds the news (search the internet / watch trends). (R1, R5)
2. Claude alerts the team. (R2) *Where (Slack, email) wasn't specified.*
3. Claude designs the carousel. (R3, R5)
4. Kint gut-checks spelling, facts and sense, and runs AI images through Canva/Figma. (R12, R13, R15)
5. David approves before image posts go out; track in Figma "ready to post" / "posted" columns. (R16) In the R8 case: Kint posted the slides in the DM, David gave fixes, Kint shared captions, and David replied "looks great. Post them." ([Sep 16](https://davidmolnar.slack.com/archives/D0B6C704TMH/p1789572878003209)) Kint also put the slides in Figma.
6. Post or schedule to David Molnar FB, TPM FB, TPM IG. Kint currently schedules in **Meta Business Suite** (Jul 15 ~0:58:28). (R6, R9)

David never said the system should post *automatically without review*. He talked about it being "posted quickly", and his current rule is approval before posting image content.

---

## 6. Tools mentioned in the chat

| Tool | What David/Kint said |
|---|---|
| Claude | Search the internet for photo news, alert the team, generate content; "Claude has a design tool now"; plug-ins/MCPs; skills; shared Claude projects that know TPM's style; Claude Code / Claude Cowork (Jun 9, Jul 15) |
| ChatGPT (images) | Remaking visuals, e.g. "chat GPT images or [Claude] design or whatever" (Jul 15 ~0:58:34); Kint builds blog images in ChatGPT (Sep 25); ChatGPT Pro access given for image generation (Jun 17) |
| Midjourney | Named as an AI image option (Jun 17 huddle notes) |
| Canva | Pass AI images through it so they're not flagged as AI (Aug 6, Sep 16) |
| Figma | Social content board, approval columns, re-export to strip AI label (Aug 6, Sep 11); team cheat sheets live in Figma (Jul 15) |
| Meta Business Suite | Kint's scheduler for FB/IG (Jul 15) |
| ManyChat | David mentioned comment-to-DM automation "via mini chat" (Jun 9). A separate idea, not this pipeline |
| Opus Clip | For video clips from live trainings (Jun 17). Not this pipeline |
| Zapier / Make / n8n | **Never mentioned** |

---

## 7. Example: Canon EOS R8 Mark II carousel (Sep 16, 2026)

Timeline (PHT), all in the DM:
- 21:01: Kint posts the announcement image ([msg](https://davidmolnar.slack.com/archives/D0B6C704TMH/p1789563708932789)).
- 21:05: Kint: "These are the results of the generation I created... I will also paste this to the figma." 5 slides IG 1–5 ([msg](https://davidmolnar.slack.com/archives/D0B6C704TMH/p1789563924493859)). The chat doesn't say which tool made them.
- 21:14: David: "The only problem is the slide with the prices on it actually, you see the name R8 Mark two on the camera which isn't true it would just say EOS there. Otherwise. Use the first red image as the first slide in the carousel and then the rest are good with a short caption of 'I'm excited to check this out...'" ([msg](https://davidmolnar.slack.com/archives/D0B6C704TMH/p1789564484488749))
- 21:54: David shares the third-party comparison screenshot: "Might be good to make a slide like this too;" ([msg](https://davidmolnar.slack.com/archives/D0B6C704TMH/p1789566894342469))
- 23:02: Kint shares her own-style comparison slide "EOS R8 MARK II vs EOS R8, side-by-side comparison" and adds it to Figma ([msg](https://davidmolnar.slack.com/archives/D0B6C704TMH/p1789570953519139)).
- 23:19–23:23: David: "you already posted this to social?" Kint: not yet; "I'll still need to put this on Canva, so it won't be flagged as an AI content." David: "ok also add the recent comparison image. Let's put it as the 3rd slide." / "yea post it everywhere, Except my dm instagram." ([msg](https://davidmolnar.slack.com/archives/D0B6C704TMH/p1789572091080769))
- 23:29: Kint proposes the two captions (Section 4). 23:34 David: "looks great. Post them." ([msg](https://davidmolnar.slack.com/archives/D0B6C704TMH/p1789572878003209))

Lesson for the build: David caught a factual error on a generated slide, so **spec accuracy checking is a must**. (When I compared the images, the R8 "shooting speed" row on Kint's comparison slide also differs from the third-party source. Claude Code should verify specs against the official announcement, not against social posts.)

---

## 8. Open questions for David

1. **Sources:** which brands, sites or accounts should it watch? Official announcements only, or rumors too? Software beyond Photoshop/Lightroom (Capture One, Luminar, phone cameras, DJI drones)?
2. **What counts as news worth posting?** Every product, or only big launches? Max posts per day/week?
3. **Alerts:** where should they go (Slack channel, DM, email)? Who gets them (Kint, David, Rich)?
4. **Approval:** is David's sign-off still needed for every news carousel, or can Kint approve after a gut-check (Jul 15 rule) to keep it fast? Who approves when David is away?
5. **Auto-posting:** generate and queue for a human only, or eventually publish automatically (Meta Graph API) after approval?
6. **Design:** slide count, size (e.g. 1080×1350 portrait), template, brand colors/fonts. Should Rich (art department) set the template? (Rich owns blog design since Oct 9; social isn't stated.)
7. **Images:** official press images from the brand OK to use (with credit), or only AI-generated/our own? (R11 says no other accounts' imagery; brand press kits weren't discussed.)
8. **Captions:** hashtags? Source credit/link? A soft TPM mention or CTA? Does the no-em-dash rule apply to captions?
9. **Accounts:** confirm David Molnar FB + TPM FB + TPM IG only (no YouTube Community, Threads, etc.).
10. **Claude setup:** Claude Team account / shared project? Which Claude design tool did David mean?
11. **Budget/hosting:** OK to pay for APIs or hosting (a small server/cron, image generation API)?

---

## 9. Suggested build plan (my suggestion, not from David)

> None of this was requested by David. It's one reasonable way to meet his requirements; check it against the open questions above.

**Phase 0: Decide (1 short call with David).** Answer open questions 1–6.

**Phase 1: News watcher (no posting).**
- Small Python or TypeScript service, run on a schedule (e.g. every 30–60 min via cron / GitHub Actions).
- Pull RSS feeds (Section 3) and maybe brand newsroom pages; store seen items in SQLite/JSON to dedupe (by URL + normalized title).
- Use Claude (API) to classify each item: relevant? category (camera / lens / software update / industry)? importance score; one-line summary; key facts with source links.
- Alert: post a short digest to a Slack channel or email with the top items. Never post publicly.

**Phase 2: Carousel draft generator.**
- For an approved item, Claude drafts slide copy (cover "JUST ANNOUNCED" + headline, 3–5 feature slides, optional comparison vs. predecessor, price/availability, a closing slide), with every fact tied to a cited source URL.
- Fact-check pass: a second Claude call checks each slide claim against the official source text and flags anything it can't confirm (R7).
- Render slides from an HTML/CSS template (Playwright screenshot or Satori/resvg) at the size David picks, or export into a Figma/Canva template. Imagery: our own or AI-generated by us, never third-party posts (R11–R14).
- Draft two captions: David Molnar FB ("I'm excited…") and TPM FB/IG ("We're excited…") (R8).
- Output a folder per news item (slides PNG + captions.txt + sources.md) and drop it into the review spot (Figma "ready to post" or a Drive folder).

**Phase 3: Review & publish.**
- Human gut-check plus David's approval (R15, R16). Then schedule in Meta Business Suite manually, or later via the Meta Graph API (Facebook Pages support `scheduled_publish_time`; Instagram has no native scheduling, so carousels are created as child containers + a CAROUSEL container and published at the time you choose, and containers expire after 24 h). Never David's personal IG (R9).

**Phase 4 (later, related David ideas):** weekly trending-ideas list (R19), Claude filling in the post-performance spreadsheet (Jul 15), cheat-sheet posts every other day (Jul 15).

**Guardrails:** human approval before anything public; source links on every draft; no third-party images; no posting to David's personal Instagram; keep secrets in a `.env`, never in the repo (the Slack DM has plaintext passwords; don't copy them into this project).

---

## 10. Update, Nov 11, 2026: Kint's answers and visual target

These are Kint's answers. Items marked "needs David" are still open.

| Question | Answer | Status |
|---|---|---|
| Sources | Official announcements **and** rumors. Everything must be accurate, authentic and sourced, including the product images. | Rumor labeling and the source list are still open |
| Alerts | Kint's Slack: https://app.slack.com/client/T02R9AUFL/D0B5S55LKU4 | Answered |
| Post-worthy | Big new launches and updates that matter to photographers and attract TPM's audience | Volume cap open |
| Look / size | Exactly like Kint's 6-slide R8 Mark II sample (`reference-slides/`, `STYLE-GUIDE.md`). 1080 × 1350 px (4:5), **inferred from the samples** | Confirm the size from the originals |
| Captions | Engaging, opening with a hook | Hashtags, credit and em dashes open |
| Accounts | TPM Facebook, TPM Instagram, David Molnar Facebook only | Answered |
| Budget | Free tools only, no paid APIs | Answered |
| Not answered | Check frequency, approval backup, press-image policy, template owner, cover style (red vs. dark sample) | Needs Kint/David |

Factual problems in the sample set, to use as QA lessons: the price-slide camera is badged "R8 Mark II" (the real body just says "EOS"); both 24.2 MP comparison cells say "Same as EOS R6 Mark II" (suspect); the Shooting Speed row differs from the source post; em dashes on slides 2 and 6.

Free-only consequences (my suggestion, not David's): there's no Claude/OpenAI API. Classification and drafting run inside Claude Code sessions or with free rules. Alerts go through a free Slack incoming webhook (`D0B5S55LKU4` is a DM-type ID, so a webhook may need to post to a channel or to Kint's DM via a Slack app). Publishing is manual in Meta Business Suite.
