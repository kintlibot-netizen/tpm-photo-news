"""Simple step timing for carousel builds, so the slow steps can be measured.

    clock = timing.Clock("Photoshop 2027")
    with clock.step("official page"):
        ...
    clock.summary()  -> "Timing total 84.2 s: official page 3.1 s, draft 21.0 s, ..."

Each finished step writes one line to the run log (logger "watcher", the same log as data/watcher.log) and prints it,
for example "Timing: Photoshop 2027: image check took 41.3 s". The totals are also saved in status.json ("timings").
Nothing here reads or writes a secret.
"""
from __future__ import annotations

import logging
import time
from contextlib import contextmanager

log = logging.getLogger("watcher")


class Clock:
    def __init__(self, label: str = "", echo: bool = True, now=time.perf_counter):
        self.label = label
        self.echo = echo
        self._now = now
        self.started = now()
        self.steps: dict[str, float] = {}

    @contextmanager
    def step(self, name: str):
        start = self._now()
        try:
            yield
        finally:
            took = self._now() - start
            self.steps[name] = round(self.steps.get(name, 0.0) + took, 1)
            line = f"Timing: {self.label + ': ' if self.label else ''}{name} took {took:.1f} s"
            log.info(line)
            if self.echo:
                print(line)

    def total(self) -> float:
        return round(self._now() - self.started, 1)

    def as_dict(self) -> dict[str, float]:
        return dict(self.steps, total=self.total())

    def summary(self) -> str:
        parts = ", ".join(f"{name} {seconds:.1f} s" for name, seconds in self.steps.items())
        line = f"Timing total {self.total():.1f} s" + (f": {parts}" if parts else "")
        log.info(line)
        return line
