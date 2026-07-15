"""Headless smoke tests for whispy.utils.Plotting.

Rendered with the Agg backend, so no display is needed. Each ``plot_*``
method is exercised on synthetic results shaped like the real ones; the key
assertions are "does not raise" plus the save/compose contract (PNG written
by default, nothing written for ``save=False`` or a caller-provided ``ax``).
"""
import random

import matplotlib

matplotlib.use("Agg", force=True)

import matplotlib.pyplot as mpl_plt
import pandas as pd
import pytest

from whispy.utils import Plotting

# plt.show() on the Agg backend warns about the non-interactive backend.
pytestmark = pytest.mark.filterwarnings(
    "ignore:.*non-interactive.*:UserWarning")


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    mpl_plt.close("all")


@pytest.fixture
def plotting():
    return Plotting()


@pytest.fixture
def abx_results():
    rng = random.Random(0)
    rows = []
    for i in range(12):
        rows.append({
            "block": 0, "section": i % 2, "trial_id": i + 1,
            "block_name": "ABX", "section_name": f"pair{i % 2 + 1}",
            "a": "ref", "b": "proc", "x": "ref",
            "correct": "A" if i % 2 else "B",
            "selected": "A",
            "correct_bool": rng.random() < 0.8,
            "rt": 0.5 + rng.random(),
        })
    return pd.DataFrame(rows)


@pytest.fixture
def staircase_results():
    rng = random.Random(1)
    rows = []
    for i in range(10):
        rows.append({
            "trial": i + 1, "level_index": i % 4, "level": 10 * (i % 4 + 1),
            "correct": rng.random() < 0.7, "step": "down",
            "reversal": i in (3, 7), "rt": 0.4 + rng.random(),
        })
    return pd.DataFrame(rows)


@pytest.fixture
def mushra_results():
    rng = random.Random(2)
    rows = []
    for attribute in ("roughness", "brightness"):
        for stimulus in ("cond_a", "cond_b", "cond_c"):
            for trial in range(4):
                rows.append({
                    "block": 0, "section": 0, "block_name": "quality",
                    "section_name": "s1", "attribute": attribute,
                    "reference": "ref", "test": stimulus,
                    "stimulus": stimulus, "trial_id": trial + 1,
                    "rating": rng.uniform(0, 100), "rt": 1 + rng.random(),
                })
    return pd.DataFrame(rows)


def _saved_pngs(results_dir):
    return list((results_dir / "plots").glob("*.png"))


# ------------------------------------------------------------- smoke: ABX
def test_abx_plots_save_pngs(plotting, abx_results, tmp_path):
    paths = [
        plotting.plot_abx_accuracy_by_section(abx_results, results_dir=tmp_path),
        plotting.plot_abx_rt_boxplot(abx_results, results_dir=tmp_path),
        plotting.plot_abx_correctness_rt_over_trials(abx_results, results_dir=tmp_path),
    ]
    assert all(p is not None and p.exists() for p in paths)
    assert len(_saved_pngs(tmp_path)) == 3


def test_abx_accuracy_handles_perfect_score(plotting, abx_results, tmp_path):
    perfect = abx_results.assign(correct_bool=True)
    path = plotting.plot_abx_accuracy_by_section(perfect, results_dir=tmp_path)
    assert path.exists()


# ------------------------------------------------------- smoke: staircase
def test_staircase_plots_save_pngs(plotting, staircase_results, tmp_path):
    paths = [
        plotting.plot_staircase(staircase_results, threshold=25.0,
                                results_dir=tmp_path),
        plotting.plot_staircase_rt_boxplot(staircase_results,
                                           results_dir=tmp_path),
        plotting.plot_staircase_correctness_rt_over_trials(
            staircase_results, results_dir=tmp_path),
    ]
    assert all(p is not None and p.exists() for p in paths)


def test_staircase_plot_without_reversal_column(plotting, staircase_results,
                                                tmp_path):
    no_reversal = staircase_results.drop(columns=["reversal"])
    path = plotting.plot_staircase(no_reversal, results_dir=tmp_path)
    assert path.exists()


# --------------------------------------------------------- smoke: MUSHRA
def test_mushra_plots_save_pngs(plotting, mushra_results, tmp_path):
    paths = [
        plotting.plot_mushra_mean_ratings(mushra_results, results_dir=tmp_path),
        plotting.plot_mushra_summary_distribution(mushra_results,
                                                  results_dir=tmp_path),
        plotting.plot_mushra_rt_boxplot(mushra_results, results_dir=tmp_path),
        plotting.plot_mushra_rt_over_trials(mushra_results, results_dir=tmp_path),
    ]
    assert all(p is not None and p.exists() for p in paths)


def test_mushra_summary_scales_height_with_attributes(plotting, mushra_results,
                                                      tmp_path):
    plotting.plot_mushra_summary_distribution(mushra_results,
                                              results_dir=tmp_path)
    fig_two = mpl_plt.gcf()
    assert fig_two.get_size_inches()[1] >= 8  # two attributes → taller figure


# --------------------------------------------------- save/compose contract
def test_save_false_writes_nothing(plotting, abx_results, tmp_path):
    path = plotting.plot_abx_rt_boxplot(abx_results, results_dir=tmp_path,
                                        save=False)
    assert path is None
    assert not (tmp_path / "plots").exists()


def test_caller_ax_is_composed_not_saved(plotting, abx_results, tmp_path):
    _, ax = mpl_plt.subplots()
    path = plotting.plot_abx_rt_boxplot(abx_results, ax=ax,
                                        results_dir=tmp_path)
    assert path is None
    assert not (tmp_path / "plots").exists()
    assert ax.get_title() == "ABX RT by correctness"  # it did draw


# ------------------------------------------------------------ read_results
def test_plots_accept_csv_paths(plotting, staircase_results, tmp_path):
    csv = tmp_path / "staircase.csv"
    staircase_results.to_csv(csv, index=False)
    path = plotting.plot_staircase(csv, results_dir=tmp_path)
    assert path.exists()


def test_read_results_aliases_trial_id(plotting, staircase_results):
    renamed = staircase_results.rename(columns={"trial": "trial_id"})
    normalized = plotting.read_results(renamed, kind="staircase")
    assert "trial" in normalized.columns


# ------------------------------------------------------------- statistics
def test_wilson_ci_is_not_degenerate_at_perfect_score(plotting):
    lower, upper = plotting._binomial_ci_bounds(1.0, 4)
    assert upper == pytest.approx(1.0)
    assert 0.0 < lower < 0.99  # normal approximation would give lower == 1.0


def test_wilson_ci_contains_p_and_respects_ci_level(plotting):
    lower, upper = plotting._binomial_ci_bounds(0.7, 20, ci=0.95)
    assert lower < 0.7 < upper
    lower99, upper99 = plotting._binomial_ci_bounds(0.7, 20, ci=0.99)
    assert lower99 < lower and upper99 > upper  # wider at higher confidence


# --------------------------------------------------------- reference line
def test_reference_value_is_none_when_unconfigured(plotting, mushra_results):
    assert plotting._resolve_reference_value(mushra_results) is None


def test_reference_value_explicit_wins(plotting, mushra_results):
    value = plotting._resolve_reference_value(mushra_results,
                                              reference_value=50)
    assert value == 50.0
