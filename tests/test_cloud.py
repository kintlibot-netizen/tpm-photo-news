"""Cloud round: the shared state/ folder, the laptop guard (no Slack alert sent twice), "needs Kint" carousels, the
public safety check, .gitignore and the GitHub Actions workflow. Temporary folders only; no network, no git push."""
import csv
import io
import sqlite3
import zipfile
from datetime import datetime, timedelta, timezone

import pytest
from conftest import ROOT
from test_round7_downloads import PASSING, carousel

import activity
import carousel_auto
import cloud_state
import dashboard
import public_safe
import run
import runlog

NOW = datetime(2026, 11, 13, 15, 0, tzinfo=timezone.utc)
FAKE_WEBHOOK = "https://hooks.slack.com/services/T0CLOUD/B0CLOUD/cloudtoken42"  # made up, shorter than a real one
REAL_FORMAT_WEBHOOK = "https://hooks.slack.com/services/" + "T01ABCDEFG/B01ABCDEFGH/" + "a1B2c3D4e5F6g7H8i9J0k1L2"


# ---- helpers ----

def laptop(tmp_path):
    """A laptop project: its database (with a carousel build saved under a full PC path), an activity log, a real
    carousel with candidate images, and a sample."""
    root = tmp_path / "laptop"
    db = runlog.connect(root / "data" / "seen.sqlite")
    with db:
        db.execute("INSERT INTO carousel_builds(story_id,built_at,status,folder,message) VALUES(?,?,?,?,?)",
                   (7, NOW.isoformat(), "ok", r"D:\Work\photo-news\output\carousels\2026-11-11-photoshop-2027",
                    "draft ready"))
    db.close()
    activity.log_event("review", "approved", "Photoshop 2027", who="Kint", now=NOW,
                       path=root / "data" / "activity-log.csv")
    base = root / "output" / "carousels"
    folder = carousel(base)
    (folder / "candidates").mkdir()
    (folder / "candidates" / "big.jpg").write_bytes(b"x" * 1000)
    (folder / "images").mkdir()
    (folder / "images" / "01.jpg").write_bytes(b"img")
    carousel(base, name="2026-11-11-canon-eos-r8-mark-ii-sample", build=dict(PASSING, sample=True))
    (root / "output" / "post-log.csv").write_text("time,account,url\n", encoding="utf-8")
    return root


def copy_state(source_root, target_root):
    import shutil
    shutil.copytree(source_root / "state", target_root / "state")


def rows(path):
    with open(path, encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


# ---- the shared state ----

def test_the_first_laptop_push_writes_the_state_without_paths_samples_or_candidates(tmp_path):
    root = laptop(tmp_path)
    cloud_state.push("laptop", root, first_time=True)
    state = root / "state"
    assert (state / "seen.sqlite").exists() and (state / "laptop-builds.csv").exists()
    db = sqlite3.connect(state / "seen.sqlite")
    assert db.execute("SELECT folder FROM carousel_builds").fetchall() == [("2026-11-11-photoshop-2027",)]
    db.close()
    assert b"D:\\Work" not in (state / "seen.sqlite").read_bytes()
    assert rows(state / "laptop-builds.csv")[0]["folder"] == "2026-11-11-photoshop-2027"
    saved = state / "carousels" / "2026-11-11-photoshop-2027"
    assert (saved / "01.png").exists() and (saved / "status.json").exists() and (saved / "captions.txt").exists()
    assert not (saved / "candidates").exists() and not (saved / "images").exists()
    assert not (state / "carousels" / "2026-11-11-canon-eos-r8-mark-ii-sample").exists()
    assert rows(state / "activity-laptop.csv")[0]["who"] == "Kint"
    assert (state / "post-log.csv").exists()


def test_the_cloud_reads_the_state_and_writes_only_its_own_two_files(tmp_path, monkeypatch):
    root = laptop(tmp_path)
    cloud_state.push("laptop", root, first_time=True)
    cloud = tmp_path / "cloud"
    copy_state(root, cloud)
    cloud_state.pull("cloud", cloud)
    assert (cloud / "data" / "seen.sqlite").exists()
    assert (cloud / "output" / "carousels" / "2026-11-11-photoshop-2027" / "01.png").exists()
    assert len(activity.read_events(cloud / "data" / "activity-log.csv")) == 1

    before = {p.relative_to(cloud).as_posix(): p.read_bytes() for p in (cloud / "state").rglob("*") if p.is_file()}
    activity.log_event("check", "ok", "Live check: 40 articles read", now=NOW + timedelta(hours=1),
                       path=cloud / "data" / "activity-log.csv")
    cloud_state.push("cloud", cloud)
    after = {p.relative_to(cloud).as_posix(): p.read_bytes() for p in (cloud / "state").rglob("*") if p.is_file()}
    changed = {name for name in after if before.get(name) != after[name]}
    assert changed <= {"state/seen.sqlite", "state/activity-cloud.csv"}  # so a git pull never has a conflict
    cloud_rows = rows(cloud / "state" / "activity-cloud.csv")
    assert [r["details"] for r in cloud_rows] == ["Live check: 40 articles read"]  # not the laptop's row again


def test_a_laptop_pull_keeps_its_builds_and_brings_the_clouds_news(tmp_path, monkeypatch):
    root = laptop(tmp_path)
    cloud_state.push("laptop", root, first_time=True)
    # the cloud adds a "needs Kint" mark and a new activity row
    cloud = tmp_path / "cloud"
    copy_state(root, cloud)
    cloud_state.pull("cloud", cloud)
    monkeypatch.setattr(activity, "LOG_PATH", cloud / "data" / "activity-log.csv")  # the cloud's own log
    carousel_auto.mark_needs_kint(cloud / "data" / "seen.sqlite", [(9, "Canon R6 Mark III")], NOW, FAKE_WEBHOOK,
                                  notify=lambda text, url: None)
    cloud_state.push("cloud", cloud)
    for name in ("seen.sqlite", "activity-cloud.csv"):
        (root / "state" / name).write_bytes((cloud / "state" / name).read_bytes())  # what git pull does
    # meanwhile the laptop built a carousel it has not pushed yet
    db = runlog.connect(root / "data" / "seen.sqlite")
    with db:
        db.execute("INSERT INTO carousel_builds(story_id,built_at,status,folder,message) VALUES(?,?,?,?,?)",
                   (9, (NOW + timedelta(hours=2)).isoformat(), "ok", "2026-11-13-canon-r6-mark-iii", "draft ready"))
    db.close()
    cloud_state.pull("laptop", root)
    db = sqlite3.connect(root / "data" / "seen.sqlite")
    statuses = sorted(r[0] for r in db.execute("SELECT status FROM carousel_builds WHERE story_id=9"))
    db.close()
    assert statuses == ["needs_kint", "ok"]  # the cloud's mark arrived and the laptop's build was not lost
    details = [e["details"] for e in activity.read_events(root / "data" / "activity-log.csv")]
    assert any("Canon R6 Mark III" in d for d in details) and any(d == "Photoshop 2027" for d in details)
    # the laptop never writes the cloud's files
    cloud_db = (root / "state" / "seen.sqlite").read_bytes()
    cloud_state.push("laptop", root)
    assert (root / "state" / "seen.sqlite").read_bytes() == cloud_db


def test_the_laptop_build_reaches_the_cloud_so_it_is_never_marked_or_built_twice(tmp_path):
    root = laptop(tmp_path)
    cloud_state.push("laptop", root, first_time=True)
    cloud = tmp_path / "cloud"
    copy_state(root, cloud)
    cloud_state.pull("cloud", cloud)
    assert carousel_auto.already_built(cloud / "data" / "seen.sqlite", 7)
    outcome = carousel_auto.mark_needs_kint(cloud / "data" / "seen.sqlite", [(7, "Photoshop 2027")], NOW,
                                            FAKE_WEBHOOK, notify=lambda *a: pytest.fail("no message"))
    assert outcome == ["7: already built"]
    cloud_state.pull("cloud", cloud)  # a second pull adds no duplicate row
    db = sqlite3.connect(cloud / "data" / "seen.sqlite")
    assert db.execute("SELECT COUNT(*) FROM carousel_builds WHERE story_id=7").fetchone()[0] == 1
    db.close()


# ---- no Slack alert sent twice ----

def test_with_the_cloud_on_the_laptop_check_sends_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(run, "ROOT", tmp_path)
    (tmp_path / "state").mkdir()
    (tmp_path / "state" / cloud_state.CLOUD_FLAG).write_text("on", encoding="utf-8")
    monkeypatch.setenv("SLACK_WEBHOOK_URL", FAKE_WEBHOOK)
    monkeypatch.setattr(run.fetch, "fetch_all", lambda config: pytest.fail("the laptop must not check the news"))
    monkeypatch.setattr(run.alert_step, "send_to_slack", lambda *a: pytest.fail("the laptop must not send alerts"))
    assert run.main(["--no-claude"]) == 0


def test_the_cloud_run_itself_is_not_stopped_by_the_flag(tmp_path, monkeypatch):
    class Args:
        cloud, dry_run, carousels_only = True, False, False
    monkeypatch.setattr(run, "ROOT", tmp_path)
    (tmp_path / "state").mkdir()
    (tmp_path / "state" / cloud_state.CLOUD_FLAG).write_text("on", encoding="utf-8")
    assert run.laptop_must_skip(Args) is False
    Args.cloud = False
    assert run.laptop_must_skip(Args) is True
    Args.dry_run = True  # a practice run on the laptop is still allowed: it sends nothing
    assert run.laptop_must_skip(Args) is False
    (tmp_path / "state" / cloud_state.CLOUD_FLAG).unlink()
    Args.dry_run = False
    assert run.laptop_must_skip(Args) is False  # without the cloud, the laptop works as before


def test_the_cloud_never_builds_a_carousel(monkeypatch, tmp_path):
    import carousel
    monkeypatch.setattr(carousel, "run_story", lambda *a, **k: pytest.fail("the cloud must not build"))
    db_path = tmp_path / "seen.sqlite"
    runlog.connect(db_path).close()
    sent = []
    monkeypatch.setattr(carousel_auto.alert, "send_to_slack", lambda text, url: sent.append(text))
    run.cloud_carousel_step(db_path, [(3, "Sony A7 V announced")], FAKE_WEBHOOK)
    assert len(sent) == 1 and sent[0].startswith("Carousel needs Kint: Sony A7 V announced")


# ---- needs Kint ----

def test_needs_kint_is_marked_once_and_is_not_a_failed_build(tmp_path):
    db_path = tmp_path / "seen.sqlite"
    runlog.connect(db_path).close()
    sent = []
    first = carousel_auto.mark_needs_kint(db_path, [(5, "Nikon Z5 III")], NOW, FAKE_WEBHOOK,
                                          notify=lambda text, url: sent.append(text))
    second = carousel_auto.mark_needs_kint(db_path, [(5, "Nikon Z5 III")], NOW + timedelta(hours=1), FAKE_WEBHOOK,
                                           notify=lambda text, url: sent.append(text))
    assert first == ["5: needs Kint"] and second == ["5: needs Kint (already marked)"] and len(sent) == 1
    assert carousel_auto.failed_attempts(db_path, 5) == 0 and not carousel_auto.already_built(db_path, 5)
    assert carousel_auto.may_build(db_path, NOW)[0]  # a mark uses up no cap: the laptop can still build it
    event = next(e for e in activity.read_events() if e["type"] == "carousel")
    assert event["outcome"] == "needs Kint" and "Nikon Z5 III" in event["details"]
    assert FAKE_WEBHOOK not in sent[0] and "Nothing is posted" in sent[0]


def test_the_dashboard_says_needs_kint_with_the_reason():
    story = {"carousel": None, "build_row": {"status": "needs_kint", "message": carousel_auto.NEEDS_KINT_REASON},
             "first_seen": NOW}
    words, cls = dashboard.coverage_reason(story, NOW)
    assert words.startswith("Needs Kint: Waiting for Kint to build it on her laptop") and cls == "st-held"


# ---- public repo safety ----

def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    (path.write_bytes if isinstance(data, bytes) else lambda d: path.write_text(d, encoding="utf-8"))(data)
    return path


def test_the_safety_check_finds_secrets_paths_and_env_values(tmp_path, monkeypatch):
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    monkeypatch.setattr(public_safe, "personal_values", lambda root: [b"someone@example.org"])
    write(tmp_path / ".env", "SLACK_WEBHOOK_URL=https://example.org/private-value-123\n")
    # The paths are put together here, so this test file itself never holds a real looking path.
    windows_path = "C:" + "\\" + "Users" + "\\" + "kint" + "\\Documents\\photo-news-automation"
    mac_path = "/" + "Users" + "/kint/project/"
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("captions.txt", "Folder: " + windows_path)
    files = [
        write(tmp_path / "a.md", f"webhook {REAL_FORMAT_WEBHOOK}"),
        write(tmp_path / "b.txt", "see https://example.org/private-value-123 here"),
        write(tmp_path / "c.ps1", "cd " + windows_path),
        write(tmp_path / "state" / "seen.sqlite", b"SQLite format 3\x00 " + mac_path.encode() + b" \x00"),
        write(tmp_path / "d.zip", archive.getvalue()),
        write(tmp_path / "e.md", "mail someone@example.org"),
        write(tmp_path / "f.txt", "token " + "ghp_" + "A" * 36),
        tmp_path / ".env",
    ]
    problems = public_safe.scan(files, tmp_path)
    text = "\n".join(problems)
    for expected in ("a.md: contains a Slack webhook address", "b.txt: contains a private value",
                     "c.ps1: contains a folder path from a PC", "state/seen.sqlite: contains a folder path from a PC",
                     "d.zip (captions.txt): contains a folder path from a PC", "e.md: contains a private value",
                     "f.txt: contains a GitHub token", ".env: is a .env file"):
        assert expected in text, expected
    assert "private-value-123" not in text and "someone@example.org" not in text  # never printed


def test_the_safety_check_passes_clean_files_and_the_made_up_test_addresses(tmp_path, monkeypatch):
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    monkeypatch.setattr(public_safe, "personal_values", lambda root: [])
    files = [write(tmp_path / "ok.py", f'WEBHOOK = "{FAKE_WEBHOOK}"\nassert "C:\\\\Users" not in text\n'),
             write(tmp_path / ".env.example", "SLACK_WEBHOOK_URL=https://hooks.slack.com/services/REPLACE/WITH/YOURS")]
    assert public_safe.scan(files, tmp_path) == []


def test_the_project_files_that_will_be_public_are_safe(monkeypatch):
    """The code, tests, config, scripts, README and workflow hold no secret, .env value or PC path."""
    monkeypatch.setattr(public_safe, "personal_values", lambda root: [])
    files = [p for folder in ("src", "tests", "scripts", "config", ".github") for p in (ROOT / folder).rglob("*")
             if p.is_file() and "__pycache__" not in p.parts and not p.name.startswith("run-")]
    files += [ROOT / name for name in ("README.md", ".gitignore", "requirements.txt", "pytest.ini", ".env.example")
              if (ROOT / name).exists()]
    assert public_safe.scan(files, ROOT) == []


def test_gitignore_keeps_secrets_and_pc_files_out_of_the_public_repo():
    lines = {line.strip() for line in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()}
    for needed in (".env", ".venv/", "data/", "output/", "dashboard/", "*.log", "backups/", "docs/history/",
                   "claude-*.md", "*-pytest*.txt", "*-dryrun*.txt", "*-export*.txt", "*-msg*.txt", "run-*.ps1",
                   "scripts/run-*.ps1"):
        assert needed in lines, needed
    assert "state/" not in lines  # the shared memory is committed on purpose


# ---- the workflow ----

def test_the_workflow_runs_hourly_never_overlaps_and_keeps_the_secret_hidden():
    text = (ROOT / ".github" / "workflows" / "watch.yml").read_text(encoding="utf-8")
    for needed in ('cron: "7 * * * *"', "workflow_dispatch:", "cancel-in-progress: false", "ubuntu-latest",
                   'python-version: "3.12"', "playwright install --with-deps chromium",
                   "SLACK_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK_URL }}", "src/run.py --cloud --no-claude",
                   "cloud_state.py pull --side cloud", "cloud_state.py push --side cloud",
                   "scripts/check_public_safe.py", "git add state/seen.sqlite state/activity-cloud.csv",
                   "[skip ci]", "github-actions[bot]", "git diff --cached --quiet",
                   "actions/upload-pages-artifact", "path: output/share/latest", "actions/deploy-pages"):
        assert needed in text, needed
    assert "echo $SLACK" not in text and "echo ${{ secrets" not in text
    assert "\u2014" not in text and "\u2013" not in text
    assert text.index("check_public_safe.py") < text.index("git commit")  # checked before anything is committed


def test_the_public_site_is_read_only_and_nothing_is_ever_posted():
    import share_pack
    assert share_pack.dashboard.SHARE_NOTE == "Read only copy. To approve a carousel, tell Kint."
    for name in ("cloud_state.py", "public_safe.py", "run.py", "carousel_auto.py"):
        source = (ROOT / "src" / name).read_text(encoding="utf-8").lower()
        assert "graph.facebook" not in source and "instagram.com" not in source
