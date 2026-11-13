"""The scheduled task script keeps the settings Kint chose, so a re-register does not undo them."""
import pytest
from conftest import ROOT

SCRIPT = (ROOT / "scripts" / "setup-hourly-task.ps1").read_text(encoding="utf-8")


@pytest.mark.parametrize("setting", [
    "-AllowStartIfOnBatteries",
    "-DontStopIfGoingOnBatteries",
    "-StartWhenAvailable",
    "-WakeToRun",
    "-ExecutionTimeLimit (New-TimeSpan -Minutes 45)",
])
def test_script_sets_the_chosen_task_settings(setting):
    assert setting in SCRIPT


def test_re_register_replaces_the_task_instead_of_failing():
    assert "Register-ScheduledTask" in SCRIPT and "-Force" in SCRIPT


def test_the_task_still_runs_the_watcher_hourly():
    assert "src\\run.py" in SCRIPT and "-RepetitionInterval (New-TimeSpan -Hours 1)" in SCRIPT
