"""Tests for the Staircase run loop and its after_trial hook (no GUI)."""
import random

import pandas as pd
import pytest

import whispy
from whispy.utils import ResultsAutosaver, read_config


@pytest.fixture
def staircase_setup(configs):
    """Levels, build_screen and kwargs exactly as the notebooks derive them."""
    cfg = read_config(str(configs / "staircase_n_afc.yml"))
    trial = cfg["trial"]
    levels = trial["levels"]
    n_intervals = int(cfg["test"]["n_choices"])

    def build_screen(level):
        return {
            "test": [trial["standard"]] * (n_intervals - 1) + [level],
            "correct": level,
            "task": trial["task"],
            "block": 0,
            "section": 0,
            "block_name": trial.get("block_name", "Staircase"),
            "section_name": trial.get("section_name", "N-AFC"),
        }

    kwargs = dict(cfg["staircase"])
    if kwargs.get("start_index", 0) < 0:  # allow -1 = easiest (last) level
        kwargs["start_index"] += len(levels)
    return levels, build_screen, kwargs


def make_observer(seed=0, p_correct=0.7):
    rng = random.Random(seed)

    def run_trial(screen):
        return rng.random() < p_correct

    return run_trial


def test_run_completes_and_logs_history(staircase_setup):
    levels, build_screen, kwargs = staircase_setup
    staircase = whispy.Staircase(levels, build_screen=build_screen, **kwargs)
    results = staircase.run(make_observer())
    assert isinstance(results, pd.DataFrame)
    assert len(results) > 0
    assert staircase.finished


def test_after_trial_called_once_per_trial_with_growing_history(staircase_setup):
    levels, build_screen, kwargs = staircase_setup
    staircase = whispy.Staircase(levels, build_screen=build_screen, **kwargs)
    seen = []
    results = staircase.run(make_observer(),
                            after_trial=lambda df: seen.append(len(df)))
    assert seen == list(range(1, len(results) + 1))


def test_after_trial_autosave_matches_final_history(staircase_setup, tmp_path):
    levels, build_screen, kwargs = staircase_setup
    staircase = whispy.Staircase(levels, build_screen=build_screen, **kwargs)
    saver = ResultsAutosaver("staircase_n_afc", results_dir=tmp_path)
    results = staircase.run(make_observer(), after_trial=saver.save)
    on_disk = pd.read_csv(saver.path)
    assert len(on_disk) == len(results)
