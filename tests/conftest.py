"""Shared fixtures for the whispy test suite.

The Qt tests run headlessly: ``QT_QPA_PLATFORM=offscreen`` is set *before*
anything imports Qt, so no display is needed. Audio is never touched — the
UIs are exercised with :class:`StubHandler`, which only records ``play`` /
``stop`` calls — so no sound device is needed either.
"""
import os
from pathlib import Path

# Must happen before the first Qt import (pytest loads conftest first).
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication

from whispy.interfaces import StimuliHandler

REPO = Path(__file__).resolve().parents[1]
CONFIGS = REPO / "configs"


class StubHandler(StimuliHandler):
    """A stimuli handler that records calls instead of making sound."""

    def __init__(self, ids, fail_stop=False):
        self.stimuli = {i: {} for i in ids}
        self.loop = False
        self.plays = []
        self.stops = 0
        self._fail_stop = fail_stop

    def play(self, stimulus):
        self.plays.append(stimulus)

    def stop(self, stimulus=None):
        self.stops += 1
        if self._fail_stop:
            raise RuntimeError("stop failed (simulated)")


@pytest.fixture
def stub_handler_cls():
    """The StubHandler class (tests instantiate it with their stimulus ids)."""
    return StubHandler


@pytest.fixture
def configs():
    """Path to the repo's ``configs/`` directory."""
    return CONFIGS


@pytest.fixture
def pump():
    """Process pending Qt events (the offscreen loop never runs by itself)."""

    def _pump():
        QApplication.processEvents()

    return _pump


@pytest.fixture
def abx_screen():
    """A minimal ABX screen dict (mirrors the notebooks' build_screen)."""
    return {
        "a": "ref", "b": "proc", "x": "ref", "task": "Which matches X?",
        "block": 0, "section": 0, "trial_id": 1,
        "block_name": "ABX", "section_name": "pair",
        "progress": {"current": 1, "total": 2},
    }


@pytest.fixture
def nafc_screen():
    """A minimal N-AFC screen dict (the Staircase's build_screen contract)."""
    return {
        "test": ["ref", "proc", "proc2"], "correct": "proc",
        "task": "Pick the odd one out.", "block": 0, "section": 0,
        "trial_id": 1, "block_name": "staircase", "section_name": "trial",
    }
