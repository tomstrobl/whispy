"""Offscreen tests for the shared ExperimentHost window.

The full-experiment notebooks open one ``ExperimentHost`` and pass it as
``parent=`` to every UI, which swaps its content into that window instead of
opening its own — so participants never see the desktop between screens.
These tests drive that whole chain headlessly.
"""
import pytest

import whispy
from whispy.ui import (
    ABX, DragAndDropMUSHRA, ExperimentHost, InfoWindow, NAFC, Questionnaire,
    ScaleTest,
)
from whispy.ui.base import resolve_screen
from whispy.utils import read_config


@pytest.fixture
def host(pump):
    h = ExperimentHost()
    pump()
    yield h
    if h.isVisible():
        h.close()
        pump()


def test_host_opens_visible_and_sized(host):
    assert host.isVisible()
    assert host.width() > 400 and host.height() > 300


def test_host_close_actually_closes(host, pump):
    host.close()
    pump()
    assert not host.isVisible()


def test_full_experiment_chain_shares_one_window(
        host, pump, configs, stub_handler_cls):
    """welcome → consent → ABX → NAFC → ScaleTest → MUSHRA → thanks,
    all inside one OS window that never closes in between."""
    win_id = int(host.effectiveWinId())

    # --- welcome ---------------------------------------------------------
    welcome = read_config(str(configs / "welcome.yml"))["ui"]
    info = InfoWindow(welcome["message"], parent=host, blocking=False)
    pump()
    assert host.centralWidget() is not None
    info.continue_button.click()
    pump()
    assert host.isVisible()

    # --- consent questionnaire ---------------------------------------------
    consent = Questionnaire(
        questionnaire=str(configs / "questionnaires" / "questionnaire_consent.yml"),
        blocking=False, debug=True, parent=host)
    pump()
    assert host.isVisible()
    assert len(consent.get_results()) > 0
    consent.main.continueClicked.emit()  # debug=True skips required answers
    pump()
    assert host.isVisible()

    # --- one ABX trial --------------------------------------------------------
    abx = ABX(screen={"a": "ref", "b": "proc", "x": "ref", "task": "t",
                      "block": 0, "section": 0, "trial_id": 1,
                      "block_name": "b", "section_name": "s"},
              stimuli_handler=stub_handler_cls(["ref", "proc"]),
              abx_config=str(configs / "abx.yml"), blocking=False, parent=host)
    pump()
    for label in ("A", "B", "X"):
        abx._on_play_clicked(label)
        pump()
    abx._on_answer_clicked("A")
    abx._on_submit_clicked()
    pump()
    assert host.isVisible()
    assert len(abx.get_results()) == 1

    # --- one N-AFC trial ---------------------------------------------------------
    nafc = NAFC(screen={"test": ["ref", "proc", "proc2"], "correct": "proc",
                        "task": "t", "block": 0, "section": 0, "trial_id": 1,
                        "block_name": "b", "section_name": "s"},
                stimuli_handler=stub_handler_cls(["ref", "proc", "proc2"]),
                n_afc_config=str(configs / "staircase_n_afc.yml"),
                blocking=False, parent=host)
    pump()
    nafc._on_choice_clicked("ref", nafc._choice_buttons[0])
    nafc._listened = set(nafc._choice_buttons)
    pump()
    nafc._on_submit_clicked()
    pump()
    assert host.isVisible()
    assert len(nafc.get_results()) == 1

    # --- one ScaleTest screen -------------------------------------------------------
    scale_cfg = read_config(str(configs / "scale_testing.yml"))
    stim_ids = list(scale_cfg["SoundDevice"].keys())
    scale = ScaleTest(screen={"stimulus": stim_ids[0],
                              "task": scale_cfg["trial"]["task"],
                              "block": 0, "section": 0, "trial_id": 1,
                              "block_name": "b", "section_name": "s"},
                      stimuli_handler=stub_handler_cls(stim_ids),
                      scale_test_config=str(configs / "scale_testing.yml"),
                      blocking=False, debug=True, parent=host)
    pump()
    assert host.isVisible()
    scale._on_submit_clicked()  # debug=True bypasses completeness checks
    pump()

    # --- one MUSHRA screen ---------------------------------------------------------
    mushra_cfg = read_config(str(configs / "drag_and_drop_mushra.yml"))
    screen = list(whispy.ExperimentScheduler(
        experiment=mushra_cfg["experiment"]))[0]
    ids = [screen["reference"]] + list(screen["test"])
    mushra = DragAndDropMUSHRA(screen=screen,
                               stimuli_handler=stub_handler_cls(ids),
                               drag_and_drop_mushra=mushra_cfg,
                               blocking=False, debug=True, parent=host)
    pump()
    assert host.isVisible()
    mushra._on_continue_clicked()  # debug=True bypasses the listen-to-all rule
    pump()

    # --- thanks --------------------------------------------------------------------
    thanks = read_config(str(configs / "thanks.yml"))["ui"]
    info2 = InfoWindow(thanks["message"], parent=host, blocking=False)
    pump()
    info2.continue_button.click()
    pump()

    assert host.isVisible()
    assert int(host.effectiveWinId()) == win_id  # same OS window throughout

    host.close()
    pump()
    assert not host.isVisible()


def test_resolve_screen_is_failsafe(pump):
    """Invalid screen settings must fall back to the primary screen."""
    from PyQt6.QtWidgets import QApplication

    primary = QApplication.primaryScreen()
    for setting in (None, "", "primary", "no such monitor", 99, -1, True, 3.5):
        assert resolve_screen(setting) is not None
    assert resolve_screen("no such monitor") is primary
    assert resolve_screen(99) is primary
