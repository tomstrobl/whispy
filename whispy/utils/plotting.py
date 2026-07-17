from __future__ import annotations

import textwrap
from datetime import datetime
from pathlib import Path
from statistics import NormalDist
from typing import Optional, Union

import matplotlib.pyplot as plt
import pandas as pd


class Plotting:
    """Collection of plotting helpers for staircase, ABX, and MUSHRA results.

    Every ``plot_*`` method accepts either a results ``DataFrame`` or a path
    to a results CSV (loaded via :meth:`read_results`). By default a method
    creates its own figure, saves it as a PNG into ``<results_dir>/plots/``
    (pass ``save=False`` to skip) and shows it, returning the saved path.
    Passing an existing ``ax=`` instead composes into the caller's figure:
    the method only draws and returns ``None`` — saving/showing is then the
    caller's job.
    """

    def read_results(
        self,
        results: Union[str, Path, pd.DataFrame],  # CSV path, Path object, or an already-loaded DataFrame
        kind: Optional[str] = None,               # experiment family ("staircase", "abx", "mushra"); auto-detected from columns if None
    ) -> pd.DataFrame:
        """Load CSV results or normalize an existing DataFrame for plotting."""
        if isinstance(results, pd.DataFrame):
            plot_df = results.copy()  # never mutate the caller's DataFrame
        else:
            path = Path(results)
            if not path.exists():
                raise FileNotFoundError(f"results file not found: {path}")
            plot_df = pd.read_csv(path)

        if kind is None:
            kind = self._infer_result_kind(plot_df)  # guess the experiment type from the columns present

        kind = str(kind).lower()
        if kind in {"staircase", "staircase_n_afc", "n_afc", "nafc"}:
            # normalize column-name variants so downstream plot functions can rely on fixed names
            if "correct_bool" not in plot_df.columns and "correct" in plot_df.columns:
                plot_df["correct_bool"] = plot_df["correct"].fillna(False).astype(bool)
            if "trial" not in plot_df.columns and "trial_id" in plot_df.columns:
                plot_df["trial"] = plot_df["trial_id"]
            return plot_df

        if kind in {"abx", "abx_discrimination"}:
            if "correct_bool" not in plot_df.columns and "correct" in plot_df.columns:
                plot_df["correct_bool"] = plot_df["correct"].fillna(False).astype(bool)
            return plot_df

        if kind in {"mushra", "drag_and_drop_mushra", "drag_and_drop"}:
            if "rt" in plot_df.columns:
                plot_df["rt"] = pd.to_numeric(plot_df["rt"], errors="coerce")  # force numeric, invalid entries -> NaN
            if "block" not in plot_df.columns and "block_name" in plot_df.columns:
                plot_df["block"] = plot_df["block_name"]
            if "stimulus" not in plot_df.columns:
                if "reference" in plot_df.columns and "test" in plot_df.columns:
                    # build a human-readable stimulus label out of the reference/test pair
                    plot_df["stimulus"] = plot_df[["reference", "test"]].astype(str).agg(
                        lambda s: f"{s['reference']} / {s['test']}", axis=1
                    )
            return plot_df

        return plot_df  # unrecognized kind: hand the DataFrame back unmodified

    def _infer_result_kind(self, results: pd.DataFrame) -> str:  # results: raw DataFrame to inspect
        """Infer the experiment family from the available columns."""
        columns = set(results.columns)
        if {"trial", "level", "correct", "reversal"}.issubset(columns):
            return "staircase"
        if {"correct_bool", "rt"}.issubset(columns) and {"a", "b", "x"}.issubset(columns):
            return "abx"
        if "rating" in columns or "stimulus" in columns or {"reference", "test"}.issubset(columns):
            return "mushra"
        return "generic"

    def save_plot(
        self,
        fig=None,                                    # figure to save; defaults to the current active figure (plt.gcf())
        name: str = "plot",                          # filename stem; a timestamp is appended so repeated runs don't overwrite each other
        results_dir: str = 'results',                # base directory; the PNG is written to "<results_dir>/plots/"
        dpi: int = 300,                              # resolution of the saved PNG
    ) -> Optional[Path]:
        """Save a figure as ``<results_dir>/plots/<name>_<timestamp>.png``."""
        if fig is None:
            fig = plt.gcf()
        if results_dir is None:
            results_dir = 'results'
        if name is None:
            name = 'plot'

        folder = Path(results_dir) / "plots"
        folder.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")  # keeps every saved plot uniquely named
        path = folder / f"{name}_{timestamp}.png"
        fig.savefig(path, dpi=dpi) 
        return path

    def _finish(
        self,
        fig,
        created_fig: bool,
        save: bool,
        results_dir: Optional[Union[str, Path]],
        name: str,
    ) -> Optional[Path]:
        """Save/show a figure this method created; leave a caller's ax alone."""
        if not created_fig:
            return None
        path = self.save_plot(fig=fig, results_dir=results_dir, name=name) if save else None
        plt.show()
        return path

    def _finish(
        self,
        fig,
        created_fig: bool,
        save: bool,
        results_dir: Optional[Union[str, Path]],
        name: str,
    ) -> Optional[Path]:
        """Save/show a figure this method created; leave a caller's ax alone."""
        if not created_fig:
            return None
        path = self.save_plot(fig=fig, results_dir=results_dir, name=name) if save else None
        plt.show()
        return path

    def _add_caption(
        self,
        ax=None,                          # axis to attach the caption to (used to find the parent figure if fig is not given)
        fig=None,                         # figure to attach the caption to directly; takes priority over ax
        caption_text: Optional[str] = None,  # the caption string itself; nothing is drawn if this is falsy
        wrap_width: int = 100,            # max characters per line before wrapping; keeps a long caption from widening the saved figure
    ) -> None:
        """Add an explanatory caption below the current figure when requested.

        The caption is wrapped onto multiple lines instead of being drawn as one long
        line, so it never becomes wider than the figure itself -- otherwise
        bbox_inches="tight" (used in save_plot) would expand the saved PNG to fit the
        full unwrapped text, making captioned plots wider than uncaptioned ones.
        """
        if not caption_text:
            return
        target_fig = fig or (ax.figure if ax is not None else plt.gcf())
        if target_fig is None:
            return

        wrapped_text = textwrap.fill(caption_text, width=wrap_width)
        n_lines = wrapped_text.count("\n") + 1
        # grow the bottom margin with the number of wrapped lines so longer captions
        # still have room, but cap it so the plot area never shrinks too much
        bottom_margin = min(0.12 + 0.045 * n_lines, 0.4)
        target_fig.subplots_adjust(bottom=bottom_margin)
        target_fig.text(
            0.5,
            0.01,
            wrapped_text,
            ha="center",
            va="bottom",
            fontsize=9,
            style="italic",
            color="0.35",
        )

    def _resolve_reference_value(
        self,
        group: pd.DataFrame,                                  # the (already-filtered) rows to search for an explicit reference/neutral value
        reference_value: Optional[float] = None,              # explicit override; used as-is if provided, skipping all lookups below
        config_path: Optional[Union[str, Path]] = None,       # optional YAML config to fall back on if no value is found in the data
        group_label: Optional[str] = None,                    # attribute name used to look up "attributes.<name>.neutral_value" in the config
    ) -> Optional[float]:
        """Try to recover a reference/neutral rating for a grouped DataFrame.

        Checks, in order: an explicit ``reference_value``, a value column in
        the results, and the ``neutral_value`` of the attribute in a config
        file. Returns ``None`` when nothing is configured so callers skip the
        reference line instead of drawing a misleading one at 0.
        """
        if reference_value is not None:
            return float(reference_value)

        for column in ("neutral_value", "reference_value", "reference_rating"):
            if column in group.columns:
                values = pd.to_numeric(group[column], errors="coerce").dropna()
                if not values.empty:
                    return float(values.iloc[0])

        if config_path is not None:
            try:
                from yaml import safe_load

                path = Path(config_path)
                if path.exists():
                    config = safe_load(path.read_text(encoding="utf-8"))
                    if isinstance(config, dict):
                        attribute_name = None
                        if group_label is not None and str(group_label).strip():
                            attribute_name = str(group_label)
                        elif "attribute" in group.columns:
                            attribute_values = group["attribute"].dropna()
                            if not attribute_values.empty:
                                attribute_name = str(attribute_values.iloc[0])

                        if attribute_name is not None:
                            attributes = config.get("attributes", {})
                            if isinstance(attributes, dict):
                                attr_config = attributes.get(attribute_name)
                                if isinstance(attr_config, dict):
                                    neutral_value = attr_config.get("neutral_value")
                                    if neutral_value is not None:
                                        return float(neutral_value)
            except Exception:
                pass  # config missing/unreadable/malformed -> fall through to the default below

        return None

    # ------------------------------------------------------ shared drawing
    def _plot_rt_by_correctness_boxplot(
        self,
        plot_df: pd.DataFrame,
        correctness_col: str,
        title: str,
        default_name: str,
        ax,
        results_dir: Optional[Union[str, Path]],
        plot_name: Optional[str],
        save: bool,
        caption_bool: Optional[bool] = True,
    ) -> Optional[Path]:
        """Boxplot reaction times split by response correctness (shared)."""
        if correctness_col not in plot_df.columns or "rt" not in plot_df.columns:
            raise ValueError(
                f"results must contain '{correctness_col}' and 'rt' columns")

        created_fig = ax is None
        if created_fig:
            _, ax = plt.subplots(figsize=(10, 6))

        correct_mask = plot_df[correctness_col].fillna(False).astype(bool)
        values = []
        labels = []
        colors = []
        for correct in (True, False):
            subset = plot_df.loc[correct_mask == correct, "rt"].dropna()
            if not subset.empty:
                values.append(subset)
                labels.append("correct" if correct else "incorrect")
                colors.append("#2ca02c" if correct else "#d62728")
        if not values:
            raise ValueError("results contain no reaction times to plot")

        box = ax.boxplot(values, tick_labels=labels, patch_artist=True)
        for patch, color in zip(box["boxes"], colors):
            patch.set_facecolor(color)
            patch.set_alpha(0.6)
        for median in box["medians"]:
            median.set_color("black")
        ax.set_ylabel("RT (s)")
        ax.set_title(title)
        ax.grid(axis="y", linestyle="--", alpha=0.3)
        ax.figure.tight_layout()
        if caption_bool:
            self._add_caption(
                ax=ax,
                caption_text=(
                    "Boxplot reaction times split by response correctness."
                ),
            )
        return self._finish(ax.figure, created_fig, save, results_dir,
                            plot_name or default_name)

    def _plot_rolling_correctness_rt(
        self,
        plot_df: pd.DataFrame,
        correctness_col: str,
        window: int,
        title: str,
        default_name: str,
        ax,
        results_dir: Optional[Union[str, Path]],
        plot_name: Optional[str],
        save: bool,
        caption_bool: Optional[bool] = True,
    ) -> Optional[Path]:
        """Plot rolling correctness and RT over trial order (shared)."""
        if correctness_col not in plot_df.columns or "rt" not in plot_df.columns:
            raise ValueError(
                f"results must contain '{correctness_col}' and 'rt' columns")

        created_fig = ax is None
        if created_fig:
            _, ax = plt.subplots(figsize=(10, 6))

        plot_df = plot_df.reset_index(drop=True)
        correctness = plot_df[correctness_col].fillna(False).astype(int)
        rt = pd.to_numeric(plot_df["rt"], errors="coerce")

        correctness_series = correctness.rolling(window=window, min_periods=1).mean()
        rt_series = rt.rolling(window=window, min_periods=1).mean()

        x = range(1, len(plot_df) + 1)
        ax.plot(x, correctness_series, label="Rolling accuracy")
        ax2 = ax.twinx()
        ax2.plot(x, rt_series, color="tab:red", label="Rolling RT")

        ax.set_xlabel("Trial")
        ax.set_ylabel("Rolling accuracy")
        ax2.set_ylabel("Rolling RT (s)")
        ax.set_title(title)
        ax.set_ylim(0, 1)
        ax.grid(axis="y", linestyle="--", alpha=0.3)
        lines1, labels1 = ax.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax.legend(lines1 + lines2, labels1 + labels2, loc="best")
        ax.figure.tight_layout()
        if caption_bool:
            self._add_caption(
                ax=ax,
                caption_text=(
                    f"Rolling average (window = {window} trials) reaction time "
                    "across the staircase's trial order."
                ),
            )
        return self._finish(ax.figure, created_fig, save, results_dir,
                            plot_name or default_name)

    # ------------------------------------------------------ staircase plots
    def plot_staircase(
        self,
        results: Union[str, Path, pd.DataFrame],                 # staircase trial-level results; needs "trial", "level", and optionally "reversal" columns
        threshold: Optional[float] = None,                     # estimated threshold; drawn as a dashed horizontal line if given
        title: Optional[str] = None,                           # optional custom plot title (overrides no title, not the caption)
        results_dir: Optional[Union[str, Path]] = None,        # base directory to save into (see save_plot)
        plot_name: Optional[str] = None,                       # filename stem for the saved PNG
        caption_bool: bool = True,                             # if True, adds an explanatory caption below the plot
        ax=None,
        save: bool = True,
    ) -> Optional[Path]:
        """Plot a staircase trace with reversal markers and a threshold line."""
        plot_df = self.read_results(results, kind="staircase")
        if "trial" not in plot_df.columns or "level" not in plot_df.columns:
            raise ValueError("results must contain 'trial' and 'level' columns")

        created_fig = ax is None
        if created_fig:
            _, ax = plt.subplots(figsize=(10, 6))

        ax.plot(plot_df["trial"], plot_df["level"], label="Staircase")

        if "reversal" in plot_df.columns:
            reversal_mask = plot_df["reversal"].fillna(False).astype(bool)
            if reversal_mask.any():
                ax.scatter(
                    plot_df.loc[reversal_mask, "trial"],
                    plot_df.loc[reversal_mask, "level"],
                    color="red",
                    zorder=3,
                    label="Reversal",
                )

        if threshold is not None:
            ax.axhline(
                threshold,
                color="tab:orange",
                linestyle="--",
                linewidth=1.5,
                label=f"Estimated threshold ({threshold:.2f})",
            )

        ax.set_xlabel("trial")
        ax.set_ylabel("level")
        if title:
            ax.set_title(title)
        else: 
            ax.set_title("Staircase")
        ax.legend()
        ax.figure.tight_layout()
        if caption_bool:
            self._add_caption(
                ax=plt.gca(),
                caption_text=(
                    "Stimulus level presented on each trial. Red dots mark reversals "
                    "(points where the staircase direction switches from up to down or vice versa); "
                    "the dashed line, if shown, is the threshold estimated from the stable reversals."
                ),
            )
        return self._finish(ax.figure, created_fig, save, results_dir,
                            plot_name or "staircase")

    def plot_staircase_rt_boxplot(
        self,
        results: Union[str, Path, pd.DataFrame],
        correctness_col: str = "correct",
        ax=None,
        results_dir: Optional[Union[str, Path]] = None,
        plot_name: Optional[str] = None,
        caption_bool: Optional[bool] = True,
        save: bool = True,
    ) -> Optional[Path]:
        """Boxplot staircase reaction times by response correctness."""
        plot_df = self.read_results(results, kind="staircase")
        return self._plot_rt_by_correctness_boxplot(
            plot_df, correctness_col, "Staircase RT by correctness",
            "staircase_rt_boxplot", ax, results_dir, plot_name, save, caption_bool)

    def plot_staircase_correctness_rt_over_trials(
        self,
        results: Union[str, Path, pd.DataFrame],
        window: int = 10,
        ax=None,
        results_dir: Optional[Union[str, Path]] = None,
        plot_name: Optional[str] = None,
        caption_bool: Optional[bool] = True,
        save: bool = True,
    ) -> Optional[Path]:
        """Plot rolling correctness and RT over staircase trials."""
        plot_df = self.read_results(results, kind="staircase")
        return self._plot_rolling_correctness_rt(
            plot_df, "correct", window, "Staircase correctness and RT over trials",
            "staircase_correctness_rt_over_trials", ax, results_dir, plot_name, save,
            caption_bool)

    # ------------------------------------------------------------ ABX plots
    def plot_abx_accuracy_by_section(
        self,
        results: Union[str, Path, pd.DataFrame],                                 # ABX trial-level results; needs "correct_bool" and the grouping columns below
        group_col: str = "section_name",                       # column defining the finer-grained grouping (e.g. easy/hard section)
        condition_col: str = "block_name",                     # column defining the coarser condition/block; combined with group_col for the x-axis label
        ci: float = 0.95,                                      # confidence level for the error bars (0.95 -> z=1.96, anything else -> z=1.645)
        ax=None,                                               # existing axis to draw into; a new figure/axis is created if None
        results_dir: Optional[Union[str, Path]] = None,        # base directory to save into (see save_plot)
        plot_name: Optional[str] = None,                       # filename stem for the saved PNG
        caption_bool: bool = True,                             # if True, adds an explanatory caption below the plot
        chance: Optional[float] = 0.5,
        save: bool = True,
    ) -> Optional[Path]:
        """Plot ABX accuracy per section/condition with Wilson confidence
        intervals and the chance level (``chance=None`` hides the line)."""
        plot_df = self.read_results(results, kind="abx")
        if "correct_bool" not in plot_df.columns:
            raise ValueError("results must contain a 'correct_bool' column")

        created_fig = ax is None
        if created_fig:
            _, ax = plt.subplots(figsize=(10, 6))

        plot_df["correct_bool"] = plot_df["correct_bool"].fillna(False).astype(int)
        if condition_col in plot_df.columns:
            plot_df["group_label"] = (plot_df[condition_col].astype(str)
                                      + " / " + plot_df[group_col].astype(str))
        else:
            plot_df["group_label"] = plot_df[group_col].astype(str)

        summary = []
        for label, group in plot_df.groupby("group_label", dropna=False):
            n = len(group)
            p = float(group["correct_bool"].mean())
            lower, upper = self._binomial_ci_bounds(p, n, ci)
            summary.append({"label": label, "accuracy": p, "n": n,
                            "err_low": max(0.0, p - lower),
                            "err_high": max(0.0, upper - p)})

        summary_df = pd.DataFrame(summary)
        x = range(len(summary_df))
        colors = plt.cm.Set2.colors[: len(summary_df)]
        ax.bar(
            x,
            summary_df["accuracy"],
            yerr=[summary_df["err_low"], summary_df["err_high"]],
            capsize=6,
            color=colors,
            alpha=0.85,
        )
        if chance is not None:
            ax.axhline(chance, color="0.35", linestyle=":", linewidth=1.4,
                       label=f"Chance ({chance:.0%})")
            ax.legend(loc="lower right")
        ax.set_xticks(list(x))
        ax.set_xticklabels(summary_df["label"], ha="right")
        ax.set_ylabel("Accuracy")
        ax.set_ylim(0, 1)
        ax.set_title("ABX accuracy by section/condition")
        ax.grid(axis="y", linestyle="--", alpha=0.3)
        plt.tight_layout()
        if caption_bool:
            self._add_caption(
                ax=ax,
                caption_text=(
                    f"Proportion of correct responses per condition, with error bars showing the "
                    f"{int(ci * 100)}% confidence interval (Wilson score interval bounds for a binomial proportion)."
                ),
            )
        return self._finish(ax.figure, created_fig, save, results_dir,
                            plot_name or "abx_accuracy_by_section")

    def plot_abx_rt_boxplot(
        self,
        results: Union[str, Path, pd.DataFrame],               # ABX trial-level results; needs correctness_col and "rt"
        correctness_col: str = "correct_bool",                 # column of correct/incorrect booleans to split the boxplot by
        ax=None,                                               # existing axis to draw into; a new figure/axis is created if None
        results_dir: Optional[Union[str, Path]] = None,        # base directory to save into (see save_plot)
        plot_name: Optional[str] = None,                       # filename stem for the saved PNG
        caption_bool: Optional[bool] = True,                             # if True, adds an explanatory caption below the plot
        save: bool = True,
    ) -> Optional[Path]:
        """Boxplot ABX reaction times by response correctness."""
        plot_df = self.read_results(results, kind="abx")
        return self._plot_rt_by_correctness_boxplot(
            plot_df, correctness_col, "ABX RT by correctness",
            "abx_rt_boxplot", ax, results_dir, plot_name, save, 
            caption_bool)

    def plot_abx_correctness_rt_over_trials(
        self,
        results: Union[str, Path, pd.DataFrame],                # ABX trial-level results, in presentation order; needs "correct_bool" and "rt"
        window: int = 10,                                       # size of the rolling window (in trials) used to smooth both series
        ax=None,                                                # existing axis to draw into; a new figure/axis is created if None
        results_dir: Optional[Union[str, Path]] = None,         # base directory to save into (see save_plot)
        plot_name: Optional[str] = None,                        # filename stem for the saved PNG
        save: bool = True,
        caption_bool: Optional[bool] = True,                              # if True, adds an explanatory caption below the plot
    ) -> Optional[Path]:
        """Plot rolling correctness and RT over trial order."""
        plot_df = self.read_results(results, kind="abx")
        return self._plot_rolling_correctness_rt(
            plot_df, "correct_bool", window, "ABX correctness and RT over trials",
            "abx_correctness_rt_over_trials", ax, results_dir, plot_name,
              save, caption_bool)

    # --------------------------------------------------------- MUSHRA plots
    def plot_mushra_rt_boxplot(
        self,
        results: Union[str, Path, pd.DataFrame],             # MUSHRA trial-level results or a path/DataFrame accepted by read_results
        block_col: Optional[str] = None,                       # column to split boxes by; falls back to "block"/"block_name", or a single "all" group
        ax=None,                                               # existing axis to draw into; a new figure/axis is created if None
        results_dir: Optional[Union[str, Path]] = None,        # base directory to save into (see save_plot)
        plot_name: Optional[str] = None,                       # filename stem for the saved PNG
        caption_bool: bool = True,                             # if True, adds an explanatory caption below the plot
        save: bool = True,
    ) -> Optional[Path]:
        """Boxplot MUSHRA reaction times by block."""
        plot_df = self.read_results(results, kind="mushra")
        if "rt" not in plot_df.columns:
            raise ValueError("results must contain an 'rt' column")

        created_fig = ax is None
        if created_fig:
            _, ax = plt.subplots(figsize=(10, 6))

        if block_col is None:
            if "block" in plot_df.columns:
                block_col = "block"
            elif "block_name" in plot_df.columns:
                block_col = "block_name"
            else:
                plot_df["block"] = "all"  # no block info available: treat everything as one group
                block_col = "block"

        values = []
        labels = []
        colors = []
        for block_value, group in plot_df.groupby(block_col, dropna=False):
            subset = group["rt"].dropna()
            if not subset.empty:
                values.append(subset)
                labels.append(str(block_value))
                colors.append(plt.cm.Set2.colors[len(colors) % len(plt.cm.Set2.colors)])
        if not values:
            raise ValueError("results contain no reaction times to plot")

        box = ax.boxplot(values, tick_labels=labels, patch_artist=True, showfliers=False)
        for patch, color in zip(box["boxes"], colors):
            patch.set_facecolor(color)
            patch.set_alpha(0.6)
        for median in box["medians"]:
            median.set_color("black")
        ax.set_ylabel("RT (s)")
        ax.set_title("MUSHRA RT by block")
        ax.grid(axis="y", linestyle="--", alpha=0.3)
        plt.tight_layout()
        if caption_bool:
            self._add_caption(
                ax=ax,
                caption_text=(
                    "Reaction time distribution per block. The box spans the interquartile range (IQR) "
                    "with the median line; whiskers extend to 1.5x IQR. Outlier markers are suppressed "
                    "here, so extreme individual trials are folded into the whisker range."
                ),
            )
        return self._finish(ax.figure, created_fig, save, results_dir,
                            plot_name or "mushra_rt_boxplot")

    def plot_mushra_rt_over_trials(
        self,
        results: pd.DataFrame,                                 # MUSHRA trial-level results or a path/DataFrame accepted by read_results
        window: int = 10,                                      # size of the rolling window (in trials) used to smooth the RT series
        ax=None,                                               # existing axis to draw into; a new figure/axis is created if None
        results_dir: Optional[Union[str, Path]] = None,        # base directory to save into (see save_plot)
        plot_name: Optional[str] = None,                       # filename stem for the saved PNG
        caption_bool: bool = True,                             # if True, adds an explanatory caption below the plot
        save: bool = True,
    ) -> Optional[Path]:
        """Plot rolling MUSHRA reaction times over the trial order."""
        plot_df = self.read_results(results, kind="mushra")
        if "rt" not in plot_df.columns:
            raise ValueError("results must contain an 'rt' column")

        created_fig = ax is None
        if created_fig:
            _, ax = plt.subplots(figsize=(10, 6))

        plot_df = plot_df.reset_index(drop=True)
        plot_df["rt"] = pd.to_numeric(plot_df["rt"], errors="coerce")
        x_values = plot_df["trial_id"] if "trial_id" in plot_df.columns else range(1, len(plot_df) + 1)
        rt_series = plot_df["rt"].rolling(window=window, min_periods=1).mean()

        ax.plot(x_values, rt_series, label="Rolling RT", color="tab:red")
        ax.set_xlabel("Trial")
        ax.set_ylabel("Rolling RT (s)")
        ax.set_title("MUSHRA RT over trials")
        ax.grid(axis="y", linestyle="--", alpha=0.3)
        ax.legend(loc="best")
        plt.tight_layout()
        if caption_bool:
            self._add_caption(
                ax=ax,
                caption_text=f"Rolling average (window = {window} trials) of MUSHRA reaction times across trial order.",
            )
        return self._finish(ax.figure, created_fig, save, results_dir,
                            plot_name or "mushra_rt_over_trials")

    def _prepare_mushra_ratings(
        self,
        results: Union[str, Path, pd.DataFrame],
        stimulus_col: Optional[str],
        rating_col: str,
        attribute_col: Optional[str],
    ) -> tuple[pd.DataFrame, str, str]:
        """Normalize MUSHRA ratings and resolve stimulus/attribute columns."""
        plot_df = self.read_results(results, kind="mushra")
        if rating_col not in plot_df.columns:
            raise ValueError("results must contain a rating column")

        plot_df[rating_col] = pd.to_numeric(plot_df[rating_col], errors="coerce")
        plot_df = plot_df.dropna(subset=[rating_col])

        if stimulus_col is None:
            if "stimulus" in plot_df.columns:
                stimulus_col = "stimulus"
            elif "test" in plot_df.columns:
                plot_df["stimulus"] = plot_df["test"].astype(str)
                stimulus_col = "stimulus"
            else:
                raise ValueError(
                    "results must contain a stimulus column or reference/test columns")

        if attribute_col is None:
            if "attribute" in plot_df.columns:
                attribute_col = "attribute"
            elif "attribute_name" in plot_df.columns:
                attribute_col = "attribute_name"
            else:
                plot_df["attribute"] = "all"  # no attribute info available: treat everything as one group
                attribute_col = "attribute"

        return plot_df, stimulus_col, attribute_col

    def plot_mushra_mean_ratings(
        self,
        results: Union[str, Path, pd.DataFrame],
        stimulus_col: Optional[str] = None,
        rating_col: str = "rating",
        attribute_col: Optional[str] = None,
        ax=None,
        results_dir: Optional[Union[str, Path]] = None,
        plot_name: Optional[str] = None,
        caption_bool: Optional[bool] = True,
        reference_value: Optional[float] = None,
        config_path: Optional[Union[str, Path]] = None,
        save: bool = True,
    ) -> Optional[Path]:
        """Plot attribute-wise MUSHRA means and the underlying trial ratings."""
        plot_df, stimulus_col, attribute_col = self._prepare_mushra_ratings(
            results, stimulus_col, rating_col, attribute_col)

        created_fig = ax is None
        if created_fig:
            _, ax = plt.subplots(figsize=(10, 6))

        attribute_groups = [
            (str(attribute_value), group)
            for attribute_value, group in plot_df.groupby(attribute_col, dropna=False)
        ]
        if not attribute_groups:
            return None

        # One shared x-axis across all stimuli keeps the attribute lines comparable.
        all_stimuli = sorted({str(stimulus)
                              for _, group in attribute_groups
                              for stimulus in group[stimulus_col].astype(str).unique()})
        x_positions = {stimulus: idx for idx, stimulus in enumerate(all_stimuli)}
        colors = plt.cm.Set2.colors

        for idx, (attribute_label, group) in enumerate(attribute_groups):
            color = colors[idx % len(colors)]
            stimuli = sorted(group[stimulus_col].astype(str).unique())
            if not stimuli:
                continue

            x = [x_positions[stimulus] for stimulus in stimuli]
            means = [float(group.loc[group[stimulus_col].astype(str) == stimulus, rating_col].mean())
                     for stimulus in stimuli]

            # Individual trial ratings are shown as semi-transparent dots.
            for stimulus in stimuli:
                subset = group.loc[group[stimulus_col].astype(str) == stimulus, rating_col]
                jitter = 0.02 * (idx % 2) - 0.01
                ax.scatter([x_positions[stimulus] + jitter] * len(subset), subset,
                           color=color, alpha=0.45, s=25)

            # One line per attribute, with the attribute mean per stimulus.
            ax.plot(x, means, color=color, linewidth=1.6, marker='o', label=attribute_label)
            ax.scatter(x, means, color=color, s=70, zorder=3)

            reference_line_value = self._resolve_reference_value(
                group,
                reference_value=reference_value,
                config_path=config_path,
                group_label=attribute_label,
            )
            if reference_line_value is not None:
                ax.axhline(
                    reference_line_value,
                    color=color,
                    linestyle="--",
                    linewidth=1.2,
                    alpha=0.7,
                    label=f"Reference ({attribute_label})",
                )

        ax.set_xticks(list(range(len(all_stimuli))))
        ax.set_xticklabels(all_stimuli, ha="right")
        ax.set_ylabel("Rating")
        ax.set_xlabel("Test stimulus")
        ax.set_title("MUSHRA mean ratings by attribute")
        ax.grid(axis="y", linestyle="--", alpha=0.3)
        plt.tight_layout()
        if ax.get_legend_handles_labels()[0]:
            ax.legend(title="Attribute")
        if caption_bool:
            self._add_caption(
                ax=ax,
                caption_text=(
                    "Mean rating per test stimulus, one line per attribute; small dots are the underlying "
                    "individual trial ratings. Dashed lines show each attribute's reference rating."
                ),
            )
        return self._finish(ax.figure, created_fig, save, results_dir,
                            plot_name or "mushra_mean_ratings")

    def plot_mushra_summary_distribution(
        self,
        results: Union[str, Path, pd.DataFrame],
        stimulus_col: Optional[str] = None,
        rating_col: str = "rating",
        attribute_col: Optional[str] = None,
        ax=None,
        results_dir: Optional[Union[str, Path]] = None,
        plot_name: Optional[str] = None,
        caption_bool: Optional[bool] = False,
        reference_value: Optional[float] = None,
        config_path: Optional[Union[str, Path]] = None,
        save: bool = True,
    ) -> Optional[Path]:
        """Plot a classic MUSHRA summary plot with one subplot per attribute."""
        plot_df, stimulus_col, attribute_col = self._prepare_mushra_ratings(
            results, stimulus_col, rating_col, attribute_col)

        attribute_groups = [
            (str(attribute_value), group)
            for attribute_value, group in plot_df.groupby(attribute_col, dropna=False)
        ]
        if not attribute_groups:
            return None

        created_fig = ax is None
        if created_fig:
            # One subplot per attribute; scale the height so many attributes
            # do not end up cramped into a fixed-size figure.
            fig, axes = plt.subplots(
                len(attribute_groups), 1,
                figsize=(10, max(5, 4 * len(attribute_groups))), squeeze=False)
            axes = axes.flatten()
        else:
            fig = ax.figure
            axes = [ax]

        # Plot one boxplot per attribute in its own subplot.
        for axis, (attribute_label, group) in zip(axes, attribute_groups):
            stimuli = sorted(group[stimulus_col].astype(str).unique())
            values = [
                group.loc[group[stimulus_col].astype(str) == stimulus, rating_col].dropna().tolist()
                for stimulus in stimuli
            ]
            box = axis.boxplot(values, tick_labels=stimuli, patch_artist=True)
            for patch in box["boxes"]:
                patch.set_alpha(0.7)

            for i, stimulus in enumerate(stimuli, start=1):
                subset = group.loc[group[stimulus_col].astype(str) == stimulus, rating_col].dropna()
                if subset.empty:
                    continue
                jitter = 0.02 * (i % 2) - 0.01
                axis.scatter([i + jitter] * len(subset), subset,
                             color="0.25", alpha=0.45, s=25)

            reference_line_value = self._resolve_reference_value(
                group,
                reference_value=reference_value,
                config_path=config_path,
                group_label=attribute_label,
            )
            if reference_line_value is not None:
                axis.axhline(
                    reference_line_value,
                    color="tab:orange",
                    linestyle="--",
                    linewidth=1.2,
                    alpha=0.7,
                    label=f"Reference ({attribute_label})",
                )

            axis.set_ylabel("Rating")
            axis.set_xlabel("Test stimulus")
            axis.set_title(f"MUSHRA rating distribution (Attribute: {attribute_label})")
            axis.grid(axis="y", linestyle="--", alpha=0.3)
            if axis.get_legend_handles_labels()[0]:
                axis.legend()

        if created_fig:
            fig.tight_layout()
        if caption_bool:
            self._add_caption(
                fig=fig,
                caption_text="Boxplots per test stimulus. The dashed line shows the reference rating. There is a subplot for every attribute",
            )
        return self._finish(fig, created_fig, save, results_dir,
                            plot_name or "mushra_summary_distribution")

    def _binomial_ci_bounds(self, p: float, n: int, ci: float = 0.95) -> tuple[float, float]:
        """Wilson score interval bounds for a binomial proportion.

        Unlike the normal approximation, the interval stays meaningful for
        small ``n`` and for ``p`` at 0 or 1 (a participant scoring 100%
        correct gets a CI reaching below 1 instead of a zero-width one).
        """
        if n <= 0:
            return 0.0, 1.0
        z = NormalDist().inv_cdf(0.5 + float(ci) / 2)
        denom = 1 + z * z / n
        center = (p + z * z / (2 * n)) / denom
        half = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / denom
        return max(0.0, center - half), min(1.0, center + half)
