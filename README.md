# TPM Photo News Watcher

## What the system does
1. The cloud (GitHub) checks the photo news and rumor sites every hour and keeps the headlines about cameras, lenses, editing software and gear.
2. It sends each new official launch to Slack at once. Rumors are sent only after a second site reports them.
3. Each official launch becomes a carousel made by hand from the brand's own page: a written plan (`data\plans\story-N.json`, schema in `docs\plan-schema.md`) built with `scripts\build_from_plan.py`. Every fact is a word for word quote of the official page, and every image is a real official image. The code checks it. No automatic job calls Claude.
4. A build starts as a preview (a dry run: no Slack, not on the dashboard as a real carousel). Kint reviews it. It is sent to David only when Kint says so. David approves by telling Kint.
5. Kint posts by hand in Meta Business Suite and logs the post. The system never posts to social media, and sends at most one health message a day if the watcher stops working.

## Daily use for Kint
1. **Watch Slack.** Official launches arrive by themselves. A rumor arrives only when two sites report it.
2. **Make the carousel** for an official story: write the plan, then `.venv\Scripts\python.exe scripts\build_from_plan.py --story 72 --plan data/plans/story-72.json --dry-run` for a preview. Without `--dry-run` it is a real build: Slack says **Carousel ready for approval**.
3. **Review.** Double-click **Open Review Dashboard.bat**, type your name at the top, open **Carousels** (the home page), read the slides and `factcheck.md`, then press **Approve**, or type a reason and press **Reject**. A rejected carousel stays rejected; a new version is made by hand from the reason.
4. **After you post by hand** (Meta Business Suite), choose the account, paste the link and press **Log as posted**. If Slack sends a health message, check `data\watcher.log` and the Sources tab.
5. **Send to David.** Press **Export for David** in the top bar (or double-click **Export for David.bat**). Upload `output\share\latest\` to the web host, or send the zip. When he says yes, press **Approve** and type "David" as the name.
6. **Need the files?** Every finished carousel has **Download all slides (ZIP)** and a button per slide.

## Features

### News check
- **What it does:** reads every feed in `config/sources.yaml`, keeps stories from the last 72 hours, applies the free rules, groups the same story from several sites, and remembers what was sent. The rules are free: no Claude is used.
- **Code:** `src/run.py` (the run), `src/fetch.py` (feeds), `src/classify.py` (rules and labels), `src/dedupe.py` (same story matching and memory).
- **Config:** `config/sources.yaml` (feeds), `config/rules.yaml` (brands, software, words, categories, name guards).
- **Output:** `data/seen.sqlite` (memory and run history), `data/watcher.log`, `output/dry-run-alerts-*.txt` (dry runs), `dashboard/index.html`.
- **Use:** practice run, sends nothing: `.venv\Scripts\python.exe src\run.py --dry-run --no-claude`. The real run is the cloud's hourly job (see Cloud).

### Slack alerts
- **What it does:** sends one message per story. Official news is labeled OFFICIAL. A rumor is labeled RUMOR and is held until two different sites report it.
- **Code:** `src/alert.py` (message text and sending), `src/classify.py` (the labels).
- **Config:** `SLACK_WEBHOOK_URL` is a GitHub secret for the cloud and lives in `.env` on this PC. Keep it private and never commit it. `rumor_min_sources` in `config/rules.yaml` sets how many sites a rumor needs (2).
- **Connecting Slack (free, once):** api.slack.com/apps, **Create New App**, **From scratch**, turn on **Incoming Webhooks**, **Add New Webhook to Workspace**, pick the channel, then put the address in `.env` (copy `.env.example`).

### Carousels
- **What it does:** builds a 1080 x 1440 carousel for an official story from a written plan. Facts come only from the brand's own page; a claim the page does not support is removed. A real build that passes the fact check, the image rules, the text lint and the design check waits for David.
- **Plan and build:** `data\plans\story-N.json` (schema: `docs\plan-schema.md`), `scripts\build_from_plan.py`, `src/plan_build.py`. `pending_carousels.py --locate` saves the official page text and the page's images next to the plan. A dry run writes to `output\plan-previews\` only.
- **Code:** `src/carousel.py` (one build), `src/carousel_plan.py`, `src/carousel_render.py`, `src/carousel_text.py`, `src/design_check.py`, `src/images.py`, `src/image_pick.py`, `src/official.py`, `src/official_index.py`, `src/carousel_status.py` (status files), `src/carousel_auto.py` (caps, Slack texts).
- **Config:** `config/carousel.yaml`. Fonts go in `assets/fonts/`.
- **Output:** `output/carousels/<date>-<slug>/` with `01.png` and so on, the download zip, `captions.txt`, `sources.md`, `factcheck.md`, `plan.json`, `status.json`, `README-for-review.txt`, `images/`, `candidates.md`.
- **Statuses:** Draft, then Waiting for David when the checks pass, then Approved, Rejected or Posted. A preview is shown as "Preview, not sent for approval yet".
- **Last slide:** a call to action slide (a recap of up to 5 confirmed feature names, "Save this post. Share your take.", The Photo Mentorship). It states no product fact.
- **Official page:** the page is chosen by the story's product words (title, headings, URL). A home page or an unrelated page is never used; if nothing matches, the build stops with a clear message. `--official-url` names the page by hand.
- **One-time setup for rendering:** `.venv\Scripts\python.exe -m playwright install chromium`, and `.venv\Scripts\python.exe scripts\fetch_fonts.py` for the free Inter font.

### Review dashboard and approvals
- **What it does:** shows every story and every carousel (real, preview, rejected) with a plain status chip. The review buttons approve, reject, or log a post. Nothing is posted anywhere.
- **Code:** `src/review_server.py` (the local server for the buttons), `src/review.py` (the approve, reject and posted steps), `src/dashboard.py` (the page).
- **Output:** `dashboard/index.html`, `output/post-log.csv` (every logged post), and `ready-to-post\` inside an approved folder.
- **Use:** **Open Review Dashboard.bat** starts the review server (http://127.0.0.1:8765/). **Open TPM News Dashboard.bat** opens the page as a file; its buttons copy the PowerShell command instead. Command line: `src\review.py --list`, `--approve <folder> --by "Name"`, `--reject <folder> --reason "..."`, `--posted <folder> --account tpm-facebook --url "https://..."`.
- **Rules:** only TPM Facebook, TPM Instagram and David Molnar Facebook can be logged (`config/accounts.yaml`). David's personal Instagram is refused in the code. Posting is always done by hand.

### Health alerts
- **What it does:** sends one Slack message to Kint if every feed failed in two runs in a row, or if no feed has worked for more than 6 hours. At most one health message is sent in 24 hours.
- **Code:** `src/health.py`, called from `src/run.py`. The webhook is never written to the log.

### Activity
- **What it does:** writes one row for every event (hourly check, Slack alert, carousel build, fact check, review step, download, export, health message, cloud backup) with the Manila time and details. Secrets and PC paths are removed first.
- **Code and output:** `src/activity.py`, `data/activity-log.csv`. It is the record of every step; the dashboard no longer shows it.

### Downloads
- **What it does:** each finished carousel has **Download all slides (ZIP)** and a button per slide. The zip holds the slides in order, one caption file per account (`captions-tpm-facebook.txt`, `captions-tpm-instagram.txt`, `captions-david-facebook.txt`), `sources.txt` and a short `README.txt`. **Download all approved carousels** puts every approved carousel in one zip.
- **Code:** `src/downloads.py`, and `GET /api/download/...` in `src/review_server.py`. Rebuild every zip: `.venv\Scripts\python.exe src\downloads.py --all`.

### Share with David
- **What it does:** builds `output\share\TPM-News-Dashboard-<date>\`, a matching zip, and refreshes `output\share\latest\`. It is a read only copy of the dashboard and a static website (relative links only, no server).
- **What is in it:** the same sections as Kint's page. Left out: the approve, reject, review, export and command copy buttons, every command, and every path from this PC. Every carousel is shown with its status chip, including previews and rejected ones. Slides show as 720 px JPEG previews; downloads are the full PNGs. The export scans every file for secrets, `.env` values, PC paths and commands, and deletes the copy if it finds one. It stays under 100 MB.
- **Use:** the **Export for David** button, **Export for David.bat**, or `scripts\export_share_pack.py`. Code: `src/share_pack.py`, `src/previews.py`.

### Sources and brands
- The Sources tab lists the feeds with their last result, the brands and the editing software. Feeds are in `config/sources.yaml` (name, type `news` or `rumor`, address); brands and software in `config/rules.yaml` (`brands:`, `software_words:`, `name_guards:`). A feed that fails is listed as failed and skipped.
- Camera and lens brands: Canon, Nikon, Sony, Fujifilm, Panasonic (Lumix), OM System (Olympus), Leica, Hasselblad, DJI, Sigma, Tamron, Tokina, Viltrox, Samyang, Ricoh (Pentax), Zeiss, Voigtlander, Laowa, TTArtisan, 7Artisans, Meike, Sirui, Phase One, Kodak, Ilford, Blackmagic Design, RED, Insta360, GoPro. Lighting: Godox, Profoto, Nanlite, Aputure. Storage: SanDisk, Lexar, ProGrade.
- Adobe: Photoshop, Lightroom, Camera Raw, Bridge, and Firefly when the headline is about photo editing. Editing software: Capture One, Luminar (Skylum), DxO, Affinity, ON1, Topaz Labs, Photomator, Pixelmator, Darktable, GIMP.
- News feeds: DPReview, PetaPixel, Fstoppers, Digital Camera World, Amateur Photographer, Camera Jabber, Imaging Resource. Rumor feeds: Canon Rumors, Nikon Rumors, Sony Alpha Rumors, Fuji Rumors, L-Rumors, 43 Rumors, Photo Rumors.

## Cloud (24/7)
The watcher runs in the cloud, on GitHub, so it keeps working while the laptop is off. The repository is **public**, so nothing secret or personal is ever committed.

- **What the cloud does, every hour:** checks the news with the free rules, sends the Slack alerts, marks each official story that needs a carousel as **Waiting for a carousel**, and publishes the read only copy for David. The cloud never builds a carousel and never calls Claude.
- **The link for David:** `https://<your GitHub name>.github.io/<repository name>/` (also on the repository's **Settings, Pages** screen). It is read only, with the note "Read only copy. To approve a carousel, tell Kint."
- **See the runs:** the repository's **Actions** tab, **TPM photo news watcher**. **Run it now:** **Run workflow**. **Pause it:** the **...** menu, **Disable workflow**.
- **Laptop backup (`--nudge-cloud`):** GitHub sometimes skips hourly runs. The Windows task "TPM Photo News Watcher" runs `.venv\Scripts\python.exe src\run.py --nudge-cloud` every hour (`scripts\setup-hourly-task.ps1`). It asks GitHub (with `gh`, which must be installed and signed in) for the last runs of `watch.yml`. If one is running, or the newest started less than 90 minutes ago, it does nothing. Otherwise it starts one run and writes a "Cloud backup" row to the activity log. It checks no news, builds nothing, sends no Slack message, and always exits 0. Code: `src/cloud_nudge.py`.
- **No alert is sent twice.** Once the cloud is on (the file `state\CLOUD-ON` exists), a live check on the laptop does nothing.
- **Review on the laptop:** double-click **Sync with cloud.bat** to get the latest from the cloud, review in the dashboard, and save your approvals back to `state\`.
- **The shared memory** is the small `state\` folder (`src/cloud_state.py`). Each side writes only its own files. The cloud writes `seen.sqlite` and `activity-cloud.csv`. The laptop writes `carousels\` (slides, captions, approvals), `previews\` (plan previews), `laptop-builds.csv`, `post-log.csv` and `activity-laptop.csv`. Never copied into `state\`: `.env` files, keys, `official.txt`, `images.txt`, candidate images.
- **Safety check:** `python scripts\check_public_safe.py` fails if any file git would commit holds the Slack address, a token, a value from `.env`, your git email or a folder path from your PC. The cloud and **Sync with cloud.bat** run it before every commit.
- **Setup (done once, Nov 2026):** the laptop's memory was copied to `state/` and `state/CLOUD-ON` was created. On GitHub add the secret `SLACK_WEBHOOK_URL` (Settings, Secrets and variables, Actions), set **Pages** to **GitHub Actions**, then run the workflow once.

## Dashboard sections
The page is an app with a sidebar and five sections, in this order: **Carousels** (the home page: the carousels to review, each with a big cover, every slide to enlarge, the captions to copy, the downloads, and the fact check and sources folded away; Kint approves or rejects here), **Photo news** (the big brand stories sent to Slack in the last two weeks, with rumors waiting for a second site folded below), **Inspiration** (credited, link only reference photos from official sources such as National Geographic's Pictures of the Year, each with the photographer's credit, the photo lesson and a TPM content idea; the data is in `data/inspiration/`, and no image is copied or embedded), **System** (is the watcher running, the feed health and the brands it follows), and **How it works** (four steps and the rules that never change). A short health line at the top says when the last check was, how many feeds worked and when the next check is.

Rejected and skipped stories, practice runs, rejected carousels, the run history and the activity log are not on the page. Their data stays in `data/` and `state/`. A story can be hidden by hand with `hidden_story_ids` in `config/rules.yaml`.

David's copy is the same page rendered with `read_only=True`. It also opens on Carousels, with the read only note at the top and a status badge where Kint has the review buttons. It needs no internet: fonts, icons, CSS and JS are inside the page (`src/dashboard_assets.py`).

## Setup and tests (once)
```powershell
cd <the project folder>
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```
- Run the tests: `.venv\Scripts\python.exe -m pytest`
- Turn on the laptop backup task: `powershell -ExecutionPolicy Bypass -File scripts\setup-hourly-task.ps1`. Running it again replaces the task.
- Rebuild the dashboard page alone: `.venv\Scripts\python.exe src\dashboard.py`

**Costs:** everything is free. No automatic job calls Claude.

## Folder map
| Folder or file | What is in it |
|---|---|
| `src/` | The code. Start with `run.py` (the run), `plan_build.py`, `review_server.py` and `dashboard.py` |
| `config/` | `sources.yaml` (feeds), `rules.yaml` (brands, software, words), `carousel.yaml`, `accounts.yaml` |
| `scripts/` | `build_from_plan.py`, `setup-hourly-task.ps1`, `fetch_fonts.py`, `check_public_safe.py` and helpers |
| `data/` | `seen.sqlite` (memory and history), `watcher.log`, `activity-log.csv`, `plans/` (the written carousel plans) |
| `output/` | `carousels/`, `plan-previews/`, the copies for David (`share/`), dry-run alert files, `post-log.csv` |
| `state/` | The shared memory of the cloud and the laptop (committed; see Cloud) |
| `dashboard/` | `index.html`, the page |
| `tests/` | The tests (pytest, no network) |
| `docs/` | `plan-schema.md` and old round reports in `docs/history/` |
| `.github/workflows/watch.yml` | The hourly cloud run and the GitHub Pages site for David |
| `.env` | Your Slack address. Private, never committed |
| `Open Review Dashboard.bat`, `Open TPM News Dashboard.bat`, `Export for David.bat`, `Sync with cloud.bat` | The double-click helpers |
