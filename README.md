# TPM Photo News Watcher

## What the system does
1. Checks the photo news and rumor sites every hour and keeps the headlines about cameras, lenses, editing software and gear.
2. Sends each new official launch to Slack at once. Rumors are sent only after a second site reports them.
3. Builds a carousel draft after an official alert, fact-checks it against the brand's own page, and waits for David.
4. Lets you review drafts in a dashboard. You approve or reject, and log each post after you post it by hand.
5. Never posts to social media, and sends at most one health message a day if the watcher stops working.

## Daily use for Kint
1. **Watch Slack.** Official launches arrive by themselves. A rumor arrives only when two sites report it.
2. **When a "Carousel draft ready" message arrives,** double-click **Open Review Dashboard.bat**. Type your name in the box at the top of the page.
3. **Open "Needs your attention."** Read the preview and `factcheck.md` in the draft's folder. Then press **Approve**, or type a reason and press **Reject**.
4. **After you post by hand** (Meta Business Suite), choose the account, paste the link and press **Log as posted**. If Slack sends a health message, check `data\watcher.log` and the Sources tab.
5. **Send to David.** Press **Export for David** in the top bar (or double-click **Export for David.bat**). Upload the contents of `output\share\latest\` to the web host and send him the link, or send him the zip from `output\share\`. When he says yes to a carousel, press **Approve** and type "David" as the name.
6. **Need the files?** Every finished carousel has **Download all slides (ZIP)** and one button per slide. **Download all approved carousels** is at the top of the Carousels page.

## Features

### News check
- **What it does:** reads every feed in `config/sources.yaml`, keeps stories from the last 72 hours, applies the free rules, groups the same story from several sites, and remembers what was sent.
- **Code:** `src/run.py` (the run), `src/fetch.py` (feeds), `src/classify.py` (rules and labels), `src/dedupe.py` (same-story matching and memory).
- **Config:** `config/sources.yaml` (feeds), `config/rules.yaml` (brands, software, words, categories, name guards).
- **Output:** `data/seen.sqlite` (memory and run history), `data/watcher.log` (the log), `output/dry-run-alerts-*.txt` (dry runs), `dashboard/index.html`.
- **Use:**
  - Practice run, sends nothing: `.venv\Scripts\python.exe src\run.py --dry-run`
  - Practice run without Claude: `.venv\Scripts\python.exe src\run.py --dry-run --no-claude`
  - Real run: `.venv\Scripts\python.exe src\run.py`. The Windows task "TPM Photo News Watcher" does this every hour while the PC is on.

### Slack alerts
- **What it does:** sends one message per story. Official news is labeled OFFICIAL. A rumor is labeled RUMOR and is held until two different sites report it. If Claude's second look is unavailable, the alert still goes out, marked "Not reviewed by Claude."
- **Code:** `src/alert.py` (message text and sending), `src/classify.py` (the labels and Claude's second look).
- **Config:** `.env` holds the Slack address (`SLACK_WEBHOOK_URL`). Keep it private and never commit it. `rumor_min_sources` in `config/rules.yaml` sets how many sites a rumor needs (2).
- **Output:** the Slack messages, and the dry-run files in `output/`.
- **Connecting Slack (free, once):**
  1. Go to api.slack.com/apps, click **Create New App**, choose **From scratch**, name it, and pick the workspace.
  2. Open **Incoming Webhooks** and turn it on.
  3. Click **Add New Webhook to Workspace**, pick where alerts go, and click **Allow**.
  4. Copy `.env.example` to `.env` and replace the placeholder with your webhook address.

### Carousel drafts
- **What it does:** after an official alert, builds a 1080 x 1440 carousel for that story. Facts come only from the brand's own page, and any claim the page does not support is removed. A draft that passes the fact check and the design check waits for David.
- **Caps:** at most 1 successful build a Manila day and 3 in any 7 days. A failed build does not use up the day. A story gets one retry at most. Official stories from the last 72 hours that have no draft are tried on later runs, best first (camera, lens, Photoshop, Lightroom, then the rest).
- **Code:** `src/carousel_auto.py` (automatic builds and caps), `src/carousel.py` (one build, and the samples), `src/carousel_plan.py`, `src/carousel_render.py`, `src/carousel_text.py`, `src/design_check.py`, `src/images.py`, `src/image_pick.py`, `src/official.py`, `src/official_index.py`, `src/carousel_status.py` (status files).
- **Config:** `config/carousel.yaml`. Fonts go in `assets/fonts/`. Manual product images go in `assets/official/`.
- **Output:** `output/carousels/<date>-<slug>/` with `01.png` and so on, the download zip, `captions.txt`, `sources.md`, `factcheck.md`, `plan.json`, `status.json`, `README-for-review.txt`, `images/`, `candidates.md`. Offline samples go to `output/samples/`, and they can't be approved or posted.
- **Statuses:** Draft, then Waiting for David when the checks pass, then Approved, Rejected or Posted.
- **Commands:**
  - Sent official stories that can make a carousel: `.venv\Scripts\python.exe src\carousel.py --list`
  - One story by its id: `.venv\Scripts\python.exe src\carousel.py --story 12`
  - The brand page was not found: add `--official-url https://...`
  - Offline sample, no network or Claude: `.venv\Scripts\python.exe src\carousel.py --sample` (or `--sample photoshop`)
  - Text only, no rendering: add `--skip-render`
  - An older story: `.venv\Scripts\python.exe src\carousel.py --settle 12` rebuilds it if its facts and images still check out against the official page, otherwise marks it rejected with the reason (shown on the dashboard)
- **One-time setup for rendering:** `.venv\Scripts\python.exe -m playwright install chromium`, and `.venv\Scripts\python.exe scripts\fetch_fonts.py` for the free Inter font.
- **Product images:** each build saves candidate photos to `images\candidates\` with `candidates.md`. Copy the one you want to `images\01.jpg`, `02.jpg` and so on. Nothing is generated or cut out.

### Review dashboard and approvals
- **What it does:** shows every draft and sent story. The review buttons approve, reject, or log a post. Nothing is posted anywhere.
- **Code:** `src/review_server.py` (the local server for the buttons), `src/review.py` (the approve, reject and posted steps), `src/dashboard.py` (the page).
- **Output:** `dashboard/index.html`, `output/post-log.csv` (every logged post), and `ready-to-post\` inside an approved folder (the slides and one caption file per account).
- **Use:**
  - **Open Review Dashboard.bat** starts the review server and opens http://127.0.0.1:8765/. Keep its window open while you review. Type your name at the top first.
  - **Open TPM News Dashboard.bat** rebuilds the page and opens it as a file. Its buttons copy the PowerShell command instead. Paste it into PowerShell in the project folder.
  - Command line: `.venv\Scripts\python.exe src\review.py --list`, `--approve <folder> --by "Name"`, `--reject <folder> --reason "..."`, `--posted <folder> --account tpm-facebook --url "https://..."`.
- **Rules:** only TPM Facebook, TPM Instagram and David Molnar Facebook can be logged (`config/accounts.yaml`). David's personal Instagram is refused in the code. Samples are refused. Posting is always done by hand in Meta Business Suite.

### Health alerts
- **What it does:** sends one Slack message to Kint if every feed failed in two runs in a row, or if no feed has worked for more than 6 hours. It is checked when the watcher next runs. At most one health message is sent in 24 hours.
- **Code:** `src/health.py`, called from `src/run.py`.
- **Config:** the limits are set in `src/health.py` (2 runs, 6 hours, 24 hours).
- **Output:** a row in `health_alerts` in `data/seen.sqlite`, and the message in Slack. The webhook is never written to the log.

### Activity
- **What it does:** writes one row for every event, with the Manila time, the type and the details: each hourly check (articles read, alerts sent, errors), each Slack alert, each carousel build (built or failed, and why), each fact check, each review step (approved, rejected, waiting for David, posted, with the name and the account), each download, each Export for David (with its size) and each health message.
- **Code:** `src/activity.py`. Secrets and file paths from this PC are removed before a row is written.
- **Output:** `data/activity-log.csv` (open it in Excel). The Activity page shows it as a table with filters (type, words, time range) and the counts for this week: alerts sent, carousels built, approved and posted.
- **Is it alive?** The top of every page shows **Last check** (from the run history) and **Next check at** (from the Windows task, or estimated when the task can't be read).

### Downloads
- **What it does:** each finished carousel has **Download all slides (ZIP)** and a button per slide. The zip holds the slides in order (`01-cover.png`, `02-<feature>.png` ...), one caption file per account (`captions-tpm-facebook.txt`, `captions-tpm-instagram.txt`, `captions-david-facebook.txt`), `sources.txt` with the official links, and a short `README.txt`. **Download all approved carousels** puts every approved carousel in one zip. A sample's zip name starts with `SAMPLE-`.
- **Code:** `src/downloads.py`, and `GET /api/download/...` in `src/review_server.py`.
- **Through the review server** the buttons are real downloads. **As a plain file** they link to the prebuilt zip that each build writes into its carousel folder, and to `output/carousels/TPM-approved-carousels.zip`.
- **Rebuild every zip:** `.venv\Scripts\python.exe src\downloads.py --all`
- Every download through the server is written to the activity log.

### Share with David
- **What it does:** builds `output\share\TPM-News-Dashboard-<date>\`, a matching zip, and refreshes `output\share\latest\` with the same contents. It is a read only copy of the dashboard and a fully static website: `index.html` at the top, relative links only, no server, no database.
- **Two ways to send it:**
  1. **Web link (best for a phone):** upload everything inside `output\share\latest\`, as it is, to any static web host (for example Netlify Drop, GitHub Pages or Cloudflare Pages), then send David the link. The page is marked "noindex", so search engines skip it.
  2. **Zip:** send the zip. David unzips it and double-clicks `index.html`.
- **What is in it:** a read only twin of Kint's dashboard: the same look, sidebar, pages and sections (Start here, Overview, Needs your attention, Stories, Carousels, Activity, Sources, How it works), rendered from the same template with `read_only=True`. Only these are left out: the approve, reject, review, export and command copy buttons (each carousel shows its status badge where they were), every command, and every path from this PC. The note "Read only copy. To approve a carousel, tell Kint." is at the top. Samples and rejected carousels are left out. The images and downloads are copied in and linked relatively. The slides show as JPEG previews (720 px wide), so they load fast; every download (single slide or zip) is the full 1080 x 1440 PNG. The export checks every file (secrets, `.env` values, PC paths, commands, PowerShell wording) and stops, deleting the copy, if it finds one. It stays under 100 MB.
- **Use:** the **Export for David** button in the top bar (review server), or double-click **Export for David.bat**, or `.venv\Scripts\python.exe scripts\export_share_pack.py`.
- **Code:** `src/share_pack.py`, `src/previews.py` (the previews, made with the same Chromium that renders the slides; without it the page shows the full PNGs), `scripts/export_share_pack.py`. The size is written to the activity log.

### Sources and brands
- **What it does:** the Sources tab on the dashboard lists the feeds with their last result, the brands, and the editing software the watcher knows.
- **Code and config:** `config/sources.yaml` (feeds: name, type `news` or `rumor`, and address) and `config/rules.yaml` (brands, software, name guards and categories).
- **Adding a feed:** copy one line under `sources:` in `config/sources.yaml` and change the name, type and address. A feed that fails is listed as failed and skipped. Nothing else stops.
- **Adding a brand or software name:** add it under `brands:` or `software_words:` in `config/rules.yaml`. A name that is also an ordinary word needs a context word in `name_guards:`.

Camera and lens brands: Canon, Nikon, Sony, Fujifilm, Panasonic (Lumix), OM System (Olympus), Leica, Hasselblad, DJI, Sigma, Tamron, Tokina, Viltrox, Samyang, Ricoh (Pentax), Zeiss, Voigtlander, Laowa (Venus Optics), TTArtisan, 7Artisans, Meike, Sirui, Phase One, Kodak, Ilford, Blackmagic Design, RED, Insta360, GoPro.

Lighting: Godox, Profoto, Nanlite, Aputure. Storage: SanDisk, Lexar, ProGrade.

Adobe: Photoshop, Lightroom, Camera Raw, Bridge, and Firefly when the headline is about photo editing. Unrelated Adobe news (Premiere, Acrobat, company results) is skipped.

Editing software: Capture One, Luminar (Skylum), DxO (PhotoLab, PureRAW, Nik Collection), Affinity Photo (and Affinity by Canva), ON1, Topaz Labs (Photo AI, Gigapixel), Photomator, Pixelmator, Darktable, GIMP.

Feeds, news sites: DPReview, PetaPixel, Fstoppers, Digital Camera World, Amateur Photographer, Camera Jabber, Imaging Resource.

Feeds, rumor sites: Canon Rumors, Nikon Rumors, Sony Alpha Rumors, Fuji Rumors, L-Rumors, 43 Rumors, Photo Rumors.

Photo Rumors and Imaging Resource (added in the functional round) loaded in the dry run. PhotographyBlog and the Capture One, Skylum, DxO and Topaz Labs blogs failed (404, 403 or not a well-formed feed) and were removed. The editing software keywords above stay, so their news still matches from the other feeds.

## Cloud (24/7)
The watcher also runs in the cloud, on GitHub, so it keeps working while the laptop is off. The repository is **public**, so nothing secret or personal is ever committed.

- **What the cloud does, every hour:** checks the news with the free rules (no Claude in the cloud), sends the Slack alerts, marks each official story that needs a carousel as **Needs Kint**, and publishes the read only copy for David.
- **The link for David:** `https://<your GitHub name>.github.io/<repository name>/` (also shown on the repository's **Settings, Pages** screen). It is read only: no approve buttons, and the note "Read only copy. To approve a carousel, tell Kint." is at the top.
- **See the runs:** the repository's **Actions** tab, then **TPM photo news watcher**. A green tick means the run worked.
- **Run it now by hand:** Actions tab, **TPM photo news watcher**, **Run workflow**.
- **Pause it:** Actions tab, **TPM photo news watcher**, the **...** menu, **Disable workflow**. Turn it back on with **Enable workflow**.
- **Carousels stay on the laptop.** The fact check and the official image check need Claude, which runs only on the laptop, and nothing else may stand in for a real official image. So the cloud never builds a carousel. It marks the story **Needs Kint** (on the dashboard and in one Slack message). Double-click **Sync with cloud.bat** on the laptop. It gets the latest from the cloud, builds those carousels, opens the review dashboard, and then saves your carousels and approvals back to the cloud. David's link updates at the next hourly run.
- **No alert is ever sent twice.** Once the cloud is on (the file `state\CLOUD-ON` exists), the laptop's hourly check does nothing. Only the cloud sends news alerts. You can also remove the laptop task: `Unregister-ScheduledTask -TaskName "TPM Photo News Watcher"`.
- **The shared memory** is the small `state\` folder (`src/cloud_state.py`). Each side writes only its own files, so the two never clash. The cloud writes `seen.sqlite` (stories, alerts sent, run history) and `activity-cloud.csv`. The laptop writes `carousels\` (slides, captions, approvals), `laptop-builds.csv`, `post-log.csv` and `activity-laptop.csv`. The cloud commits its files as github-actions[bot], only when they changed.
- **Safety check:** `python scripts\check_public_safe.py` fails if any file git would commit holds the Slack address, a token, a value from `.env`, your git email or a folder path from your PC. The cloud and **Sync with cloud.bat** run it before every commit.
- **Setup (once):**
  1. Double-click **Start cloud (first time).bat**, then run the git commands it shows.
  2. On GitHub: **Settings, Secrets and variables, Actions, New repository secret**. Name it `SLACK_WEBHOOK_URL`, and paste the Slack address from `.env`.
  3. On GitHub: **Settings, Pages, Source: GitHub Actions**.
  4. Actions tab, **TPM photo news watcher**, **Run workflow**. After the green tick, the link for David works.

## Dashboard sections
The page is an app with a sidebar. The sections, in this order: **Start here** (what the system does, in one minute), **Overview** (the counts, the pipeline, Last check and Next check at, the run history, and Export for David), **Needs your attention** (drafts to review, official stories with no carousel and why, feeds that failed), **Stories** (every story, with filters), **Carousels** (the gallery: slides, captions, fact check, sources, downloads and the review buttons), **Activity** (every event, with filters and this week's counts), **Sources** (feeds, brands and software), and **How it works** (the steps in plain words).

Two ways to open it: **Open Review Dashboard.bat** (through the review server, the buttons work) or **Open TPM News Dashboard.bat** (a plain file, read only, the buttons copy the command instead). It needs no internet: the fonts, icons, CSS and JS are inside the page (`src/dashboard_assets.py`).

David's copy (Share with David, and the GitHub Pages link) is the same page with the same sections, rendered from the same template with `read_only=True`. It opens on Start here, and leaves out only the review, approve, reject, export and command copy buttons (each carousel shows its status badge instead) and every command.

## Setup and tests (once)
```powershell
cd <the project folder>
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```
- Run the tests: `.venv\Scripts\python.exe -m pytest`
- Turn on the hourly task (after Slack works): `powershell -ExecutionPolicy Bypass -File scripts\setup-hourly-task.ps1`. Running it again replaces the task and keeps its settings: run on battery, wake the PC, catch up after a missed start, and stop a run after 45 minutes.
- Rebuild the dashboard page alone: `.venv\Scripts\python.exe src\dashboard.py`

Checks run only while this PC is on. The hourly task catches up when the PC wakes.

**Costs:** everything is free. Claude's second look uses your signed-in Claude plan. The code removes any paid API key before calling it. Keep any "extra usage" option off in your Claude settings.

## Folder map
| Folder or file | What is in it |
|---|---|
| `src/` | The code. Start with `run.py` (the run), `review_server.py` and `dashboard.py` |
| `config/` | `sources.yaml` (feeds), `rules.yaml` (brands, software, words), `carousel.yaml`, `accounts.yaml` |
| `scripts/` | `setup-hourly-task.ps1` (the hourly task), `fetch_fonts.py` (font download), and older helper scripts |
| `tests/` | The tests. Run them with pytest. None of them use the network |
| `dashboard/` | `index.html`, the page (rebuilt every run) |
| `output/` | Carousel drafts (`carousels/`), samples (`samples/`), the copies for David (`share/`), dry-run alert files, `post-log.csv` |
| `data/` | `seen.sqlite` (memory and history), `watcher.log`, `activity-log.csv` (every event) |
| `assets/` | Fonts and manual official images |
| `docs/history/` | Old round reports and consoles, kept for reference |
| `backups/` | Old backups, kept for reference |
| `fixtures/` | Sample data for the offline carousel samples |
| `.env` | Your Slack address. Private, never committed |
| `Open Review Dashboard.bat` | Starts the review server and opens the review page |
| `Open TPM News Dashboard.bat` | Rebuilds the page and opens it as a file |
| `Export for David.bat` | Builds the read only copy for David in `output\share\` |
| `run-*.ps1` | Helpers that run a Claude Code round and then the tests (kept on this PC only, never committed) |
| `state/` | The shared memory of the cloud and the laptop (committed; see Cloud (24/7)) |
| `.github/workflows/watch.yml` | The hourly cloud run and the GitHub Pages site for David |
| `Sync with cloud.bat` | Laptop: get the latest, build the "needs Kint" carousels, review, save back |
| `Start cloud (first time).bat` | Run once to start the cloud from the laptop's memory |
