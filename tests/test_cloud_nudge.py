"""The laptop backup for the cloud watcher (run.py --nudge-cloud). subprocess is mocked: no network, no gh."""
import json
import subprocess
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

import activity
import cloud_nudge
import run

NOW = datetime(2026, 11, 24, 12, 0, tzinfo=timezone.utc)


def stamp(minutes_ago: int) -> str:
    return (NOW - timedelta(minutes=minutes_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


class Fake:
    """Stands in for subprocess.run: answers by command, records every call and its timeout."""

    def __init__(self, runs=None, auth=0, remote="https://github.com/someone/photo-news.git"):
        self.runs, self.auth, self.remote, self.calls = runs, auth, remote, []

    def __call__(self, command, **kwargs):
        self.calls.append((command, kwargs))
        text = " ".join(command)
        ok = lambda out="": SimpleNamespace(returncode=0, stdout=out, stderr="")  # noqa: E731
        if "auth status" in text:
            return SimpleNamespace(returncode=self.auth, stdout="", stderr="")
        if "remote get-url" in text:
            return ok(self.remote + "\n")
        if "run list" in text:
            return ok(json.dumps(self.runs))
        return ok()

    def started(self):
        return [c for c, _ in self.calls if "workflow" in c and "run" in c]


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(activity, "LOG_PATH", tmp_path / "activity.csv")
    monkeypatch.setattr(cloud_nudge, "find_gh", lambda: "gh")

    def install(fake):
        monkeypatch.setattr(cloud_nudge.subprocess, "run", fake)
        return fake
    return install


def test_a_quiet_cloud_is_nudged_once_and_logged(env):
    fake = env(Fake(runs=[{"status": "completed", "createdAt": stamp(600)}]))
    message = cloud_nudge.nudge(NOW)
    assert message == "Nudged the cloud: no run for 600 minutes"
    assert len(fake.started()) == 1 and "someone/photo-news" in fake.started()[0]
    event = activity.read_events()[-1]
    assert event["type"] == "cloud" and event["outcome"] == "nudged" and "600 minutes" in event["details"]


@pytest.mark.parametrize("runs", [
    [{"status": "completed", "createdAt": stamp(30)}],  # the newest run is recent
    [{"status": "completed", "createdAt": stamp(600)}, {"status": "in_progress", "createdAt": stamp(5)}],
    [{"status": "queued", "createdAt": stamp(700)}],
])
def test_a_recent_or_active_run_means_nothing_is_done(env, runs):
    fake = env(Fake(runs=runs))
    cloud_nudge.nudge(NOW)
    assert fake.started() == [] and activity.read_events() == []


def test_without_gh_or_without_a_sign_in_it_logs_one_line_and_does_nothing(env, monkeypatch):
    fake = env(Fake(runs=[], auth=1))
    assert "not signed in" in cloud_nudge.nudge(NOW) and fake.started() == []
    monkeypatch.setattr(cloud_nudge, "find_gh", lambda: None)
    assert "not installed" in cloud_nudge.nudge(NOW)


def test_every_subprocess_call_has_a_timeout_and_no_secret_is_printed(env, capsys):
    fake = env(Fake(runs=[{"status": "completed", "createdAt": stamp(600)}]))
    cloud_nudge.nudge(NOW)
    assert fake.calls and all(kw.get("timeout") for _, kw in fake.calls)
    assert "token" not in capsys.readouterr().out.lower()


def test_a_failing_gh_never_raises(env, monkeypatch):
    def boom(*a, **k):
        raise subprocess.TimeoutExpired("gh", 60)
    monkeypatch.setattr(cloud_nudge.subprocess, "run", boom)
    assert "nothing was done" in cloud_nudge.nudge(NOW)


@pytest.mark.parametrize("url, repo", [
    ("https://github.com/owner/name.git", "owner/name"),
    ("git@github.com:owner/name.git", "owner/name"),
    ("https://user@github.com/owner/name", "owner/name"),
    ("https://example.com/owner/name", None),
])
def test_the_repo_comes_from_the_origin_address(env, url, repo):
    env(Fake(remote=url))
    assert cloud_nudge.repo_from_remote() == repo


def test_run_nudge_cloud_checks_no_news_and_exits_zero(monkeypatch, tmp_path):
    called = []
    monkeypatch.setattr(cloud_nudge, "nudge", lambda **kw: called.append("nudge"))
    monkeypatch.setattr(run.fetch, "fetch_all", lambda *a, **k: called.append("news"))
    monkeypatch.setattr(run, "ROOT", tmp_path)
    assert run.main(["--nudge-cloud"]) == 0
    assert called == ["nudge"]
    monkeypatch.setattr(cloud_nudge, "nudge", lambda **kw: 1 / 0)
    assert run.main(["--nudge-cloud"]) == 0  # a failing backup still exits 0
