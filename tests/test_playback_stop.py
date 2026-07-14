"""Offscreen tests: stimulus playback stops when a trial ends.

Every test UI must call ``stimuli_handler.stop()`` when the answer is
submitted (``unblock()``) and when its window actually closes, so no
stimulus from a finished trial keeps playing into the next screen or past
the end of the experiment.
"""
import pytest

import whispy
from whispy.ui import ABX, DragAndDropMUSHRA, ExperimentHost, NAFC, ScaleTest
from whispy.utils import read_config


@pytest.fixture
def host(pump):
    h = ExperimentHost()
    pump()
    yield h
    if h.isVisible():
        h.close()
        pump()


def test_abx_submit_stops_playback(host, pump, configs, stub_handler_cls,
                                   abx_screen):
    handler = stub_handler_cls(["ref", "proc"])
    abx = ABX(screen=abx_screen, stimuli_handler=handler,
              abx_config=str(configs / "abx.yml"), blocking=False, parent=host)
    pump()
    for label in ("A", "B", "X"):
        abx._on_play_clicked(label)
    abx._on_answer_clicked("A")

    before = handler.stops
    abx._on_submit_clicked()
    pump()
    assert handler.stops > before


def test_nafc_submit_stops_playback(host, pump, configs, stub_handler_cls,
                                    nafc_screen):
    handler = stub_handler_cls(["ref", "proc", "proc2"])
    nafc = NAFC(screen=nafc_screen, stimuli_handler=handler,
                n_afc_config=str(configs / "staircase_n_afc.yml"),
                blocking=False, parent=host)
    pump()
    nafc._on_choice_clicked("ref", nafc._choice_buttons[0])
    nafc._listened = set(nafc._choice_buttons)  # mark all intervals as heard

    before = handler.stops
    nafc._on_submit_clicked()
    pump()
    assert handler.stops > before


def test_scale_test_submit_stops_playback(host, pump, configs,
                                          stub_handler_cls):
    cfg = read_config(str(configs / "scale_testing.yml"))
    ids = list(cfg["SoundDevice"].keys())
    handler = stub_handler_cls(ids)
    scale = ScaleTest(screen={"stimulus": ids[0], "task": "t", "block": 0,
                              "section": 0, "trial_id": 1, "block_name": "b",
                              "section_name": "s"},
                      stimuli_handler=handler,
                      scale_test_config=str(configs / "scale_testing.yml"),
                      blocking=False, debug=True, parent=host)
    pump()

    before = handler.stops
    scale._on_submit_clicked()  # debug=True bypasses completeness checks
    pump()
    assert handler.stops > before


def test_mushra_continue_stops_playback(host, pump, configs,
                                        stub_handler_cls):
    cfg = read_config(str(configs / "drag_and_drop_mushra.yml"))
    screen = list(whispy.ExperimentScheduler(experiment=cfg["experiment"]))[0]
    handler = stub_handler_cls([screen["reference"]] + list(screen["test"]))
    mushra = DragAndDropMUSHRA(screen=screen, stimuli_handler=handler,
                               drag_and_drop_mushra=cfg,
                               blocking=False, debug=True, parent=host)
    pump()

    before = handler.stops
    mushra._on_continue_clicked()  # debug=True bypasses the listen-to-all rule
    pump()
    assert handler.stops > before


def test_raising_stop_never_blocks_trial_end(host, pump, configs,
                                             stub_handler_cls, abx_screen):
    handler = stub_handler_cls(["ref", "proc"], fail_stop=True)
    abx = ABX(screen=abx_screen, stimuli_handler=handler,
              abx_config=str(configs / "abx.yml"), blocking=False, parent=host)
    pump()
    for label in ("A", "B", "X"):
        abx._on_play_clicked(label)
    abx._on_answer_clicked("B")

    abx._on_submit_clicked()  # must not raise despite handler.stop() raising
    pump()
    assert len(abx.get_results()) == 1


def test_closing_standalone_window_stops_playback(pump, configs,
                                                  stub_handler_cls,
                                                  abx_screen):
    handler = stub_handler_cls(["ref", "proc"])
    abx = ABX(screen=abx_screen, stimuli_handler=handler,
              abx_config=str(configs / "abx.yml"), blocking=False)
    pump()

    before = handler.stops
    abx.close()
    pump()
    assert handler.stops > before
