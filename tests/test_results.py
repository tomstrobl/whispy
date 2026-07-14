"""Tests for results naming, saving, and crash-safe autosaving (no GUI)."""
from pathlib import Path

import pandas as pd
import pytest

from whispy.utils import ResultsAutosaver, participant_id_from_consent, save_results


@pytest.fixture
def df():
    return pd.DataFrame({"trial_id": [1, 2], "selected": ["A", "B"]})


# ------------------------------------------------------------- save_results
def test_save_results_with_participant_id(tmp_path, df):
    path = save_results(df, "abx", results_dir=tmp_path, participant_id="HPo1")
    assert path.exists()
    assert path.name.startswith("abx_HPo1_")
    assert len(pd.read_csv(path)) == 2


def test_save_results_fallback_number_iterates(tmp_path, df):
    first = save_results(df, "abx", results_dir=tmp_path)
    second = save_results(df, "abx", results_dir=tmp_path)
    assert first.name.startswith("abx_0001_")
    assert second.name.startswith("abx_0002_")


def test_save_results_sanitizes_participant_id(tmp_path, df):
    path = save_results(df, "abx", results_dir=tmp_path, participant_id="a/b c")
    assert "/" not in path.name.replace(str(tmp_path), "")
    assert path.exists()


def test_save_results_never_overwrites(tmp_path, df):
    paths = {save_results(df, "abx", results_dir=tmp_path,
                          participant_id="HPo1").name for _ in range(3)}
    assert len(paths) == 3


# --------------------------------------------------------- ResultsAutosaver
def test_autosaver_reserves_path_at_construction(tmp_path):
    saver = ResultsAutosaver("abx", results_dir=tmp_path, participant_id="HPo1")
    assert saver.path.exists()
    assert saver.path.name.startswith("abx_HPo1_")


def test_autosaver_rewrites_atomically(tmp_path, df):
    saver = ResultsAutosaver("abx", results_dir=tmp_path)
    saver.save(df.iloc[:1])
    assert len(pd.read_csv(saver.path)) == 1

    path = saver.save(df)
    back = pd.read_csv(saver.path)
    assert path == saver.path
    assert list(back["selected"]) == ["A", "B"]
    assert not list(Path(tmp_path).glob("*.tmp"))


def test_autosaver_ignores_empty_results(tmp_path, df):
    saver = ResultsAutosaver("abx", results_dir=tmp_path)
    saver.save(df)
    saver.save(None)
    saver.save(pd.DataFrame())
    assert len(pd.read_csv(saver.path)) == 2


def test_autosaver_new_run_new_file(tmp_path, df):
    first = ResultsAutosaver("abx", results_dir=tmp_path, participant_id="HPo1")
    first.save(df)
    second = ResultsAutosaver("abx", results_dir=tmp_path, participant_id="HPo1")
    assert second.path != first.path
    assert len(pd.read_csv(first.path)) == 2  # earlier run untouched


def test_autosaver_fallback_number(tmp_path):
    saver = ResultsAutosaver("abx", results_dir=tmp_path)
    assert saver.path.name.startswith("abx_0001_")


# ------------------------------------------- participant_id_from_consent
def test_participant_id_from_consent():
    results = pd.DataFrame({
        "question": ["consent", "pid_1", "pid_2", "pid_3", "pid_4"],
        "answer": ["yes", "H", "P", "o", "1"],
    })
    assert participant_id_from_consent(results) == "HPo1"


def test_participant_id_missing_fields_returns_none():
    results = pd.DataFrame({"question": ["pid_1"], "answer": ["H"]})
    assert participant_id_from_consent(results) is None


def test_participant_id_blank_answer_returns_none():
    results = pd.DataFrame({
        "question": ["pid_1", "pid_2", "pid_3", "pid_4"],
        "answer": ["H", "", "o", "1"],
    })
    assert participant_id_from_consent(results) is None
