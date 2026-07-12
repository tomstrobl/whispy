from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional, Union

import matplotlib.pyplot as plt
import pandas as pd


class Plotting:
    """Collection of plotting helpers for staircase, ABX, and MUSHRA results."""

    def read_results(
        self,
        results: Union[str, Path, pd.DataFrame],
        kind: Optional[str] = None,
    ) -> pd.DataFrame:
        """Load CSV results or normalize an existing DataFrame for plotting."""
        if isinstance(results, pd.DataFrame):
            plot_df = results.copy()
        else:
            path = Path(results)
            if not path.exists():
                raise FileNotFoundError(f"results file not found: {path}")
            plot_df = pd.read_csv(path)

        if kind is None:
            kind = self._infer_result_kind(plot_df)

        kind = str(kind).lower()
        if kind in {"staircase", "staircase_n_afc", "n_afc", "nafc"}:
            if "correct_bool" not in plot_df.columns and "correct" in plot_df.columns:
                plot_df = plot_df.copy()
                plot_df["correct_bool"] = plot_df["correct"].fillna(False).astype(bool)
            if "trial" not in plot_df.columns and "trial_id" in plot_df.columns:
                plot_df = plot_df.copy()
                plot_df["trial"] = plot_df["trial_id"]
            return plot_df

        if kind in {"abx", "abx_discrimination"}:
            if "correct_bool" not in plot_df.columns and "correct" in plot_df.columns:
                plot_df = plot_df.copy()
                plot_df["correct_bool"] = plot_df["correct"].fillna(False).astype(bool)
            return plot_df

        if kind in {"mushra", "drag_and_drop_mushra", "drag_and_drop"}:
            plot_df = plot_df.copy()
            if "rt" in plot_df.columns:
                plot_df["rt"] = pd.to_numeric(plot_df["rt"], errors="coerce")
            if "block" not in plot_df.columns and "block_name" in plot_df.columns:
                plot_df["block"] = plot_df["block_name"]
            if "stimulus" not in plot_df.columns:
                if "reference" in plot_df.columns and "test" in plot_df.columns:
                    plot_df["stimulus"] = plot_df[["reference", "test"]].astype(str).agg(
                        lambda s: f"{s['reference']} / {s['test']}", axis=1
                    )
            return plot_df

        return plot_df

    def _infer_result_kind(self, results: pd.DataFrame) -> str:
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
        fig=None,
        name: str = "plot",
        results_dir: str = 'results',
        dpi: int = 300,
    ) -> Optional[Path]:
        """Save the current figure to a plots folder inside results_dir when requested."""
        if fig is None:
            fig = plt.gcf()
        if results_dir is None:
            results_dir = 'results'
        if name is None:
            name = 'plot'

        folder = Path(results_dir) / "plots"
        folder.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = folder / f"{name}_{timestamp}.png"
        fig.savefig(path, dpi=dpi, bbox_inches="tight")
        return path

    def _add_caption(
        self,
        ax=None,
        fig=None,
        caption_text: Optional[str] = None,
    ) -> None:
        """Add a caption to the current figure when requested."""
        if not caption_text:
            return
        target_fig = fig or (ax.figure if ax is not None else plt.gcf())
        if target_fig is None:
            return
        target_fig.subplots_adjust(bottom=0.22)
        target_fig.text(
            0.5,
            0.01,
            caption_text,
            ha="center",
            va="bottom",
            fontsize=9,
            style="italic",
            color="0.35",
        )

    def _resolve_reference_value(
        self,
        group: pd.DataFrame,
        reference_value: Optional[float] = None,
        config_path: Optional[Union[str, Path]] = None,
        group_label: Optional[str] = None,
    ) -> Optional[float]:
        """Try to recover a reference/neutral rating from a grouped DataFrame or config."""
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
                pass

        return 0.0

    def plot_staircase(
        self,
        results: pd.DataFrame,
        threshold: Optional[float] = None,
        title: Optional[str] = None,
        results_dir: Optional[Union[str, Path]] = None,
        plot_name: Optional[str] = None,
    ) -> None:
        """Plot a staircase trace with reversal markers and a threshold line."""
        if not isinstance(results, pd.DataFrame):
            raise TypeError("results must be a pandas DataFrame")

        x = "trial"
        y = "level"
        plt.figure(figsize=(10, 6))
        plt.plot(results[x], results[y], label="Staircase")

        reversal_mask = results.get("reversal", False).fillna(False)
        if reversal_mask.any():
            plt.scatter(
                results.loc[reversal_mask, x],
                results.loc[reversal_mask, y],
                color="red",
                zorder=3,
                label="Reversal",
            )

        if threshold is not None:
            plt.axhline(
                threshold,
                color="tab:orange",
                linestyle="--",
                linewidth=1.5,
                label=f"Estimated threshold ({threshold:.2f})",
            )

        plt.xlabel(x)
        plt.ylabel(y)
        if title:
            plt.title(title)
        plt.legend()
        self.save_plot(results_dir=results_dir, name=plot_name or "staircase")
        plt.show()

    def plot_abx_accuracy_by_section(
        self,
        results: pd.DataFrame,
        group_col: str = "section_name",
        condition_col: str = "block_name",
        ci: float = 0.95,
        ax=None,
        results_dir: Optional[Union[str, Path]] = None,
        plot_name: Optional[str] = None,
    ) -> None:
        """Plot ABX accuracy per section/condition with confidence intervals."""
        if not isinstance(results, pd.DataFrame):
            raise TypeError("results must be a pandas DataFrame")
        if "correct_bool" not in results.columns:
            raise ValueError("results must contain a 'correct_bool' column")

        if ax is None:
            _, ax = plt.subplots(figsize=(10, 6))

        plot_df = results.copy()
        plot_df["correct_bool"] = plot_df["correct_bool"].fillna(False).astype(int)
        if condition_col in plot_df.columns:
            plot_df["group_label"] = plot_df[condition_col].astype(str) + " / " + plot_df[group_col].astype(str)
        else:
            plot_df["group_label"] = plot_df[group_col].astype(str)

        summary = []
        for label, group in plot_df.groupby("group_label", dropna=False):
            n = len(group)
            p = float(group["correct_bool"].mean())
            ci_half = self._binomial_ci(p, n, ci)
            summary.append({"label": label, "accuracy": p, "ci_half": ci_half, "n": n})

        summary_df = pd.DataFrame(summary)
        x = range(len(summary_df))
        colors = plt.cm.Set2.colors[: len(summary_df)]
        ax.bar(
            x,
            summary_df["accuracy"],
            yerr=summary_df["ci_half"],
            capsize=6,
            color=colors,
            alpha=0.85,
        )
        ax.set_xticks(list(x))
        ax.set_xticklabels(summary_df["label"], rotation=45, ha="right")
        ax.set_ylabel("Accuracy")
        ax.set_ylim(0, 1)
        ax.set_title("ABX accuracy by section/condition")
        ax.grid(axis="y", linestyle="--", alpha=0.3)
        self.save_plot(results_dir=results_dir, name=plot_name or "abx_accuracy_by_section")
        plt.show()

    def plot_abx_rt_boxplot(
        self,
        results: pd.DataFrame,
        correctness_col: str = "correct_bool",
        ax=None,
        results_dir: Optional[Union[str, Path]] = None,
        plot_name: Optional[str] = None,
    ) -> None:
        """Boxplot ABX reaction times by response correctness."""
        if not isinstance(results, pd.DataFrame):
            raise TypeError("results must be a pandas DataFrame")
        if correctness_col not in results.columns or "rt" not in results.columns:
            raise ValueError("results must contain 'correct_bool' and 'rt' columns")

        if ax is None:
            _, ax = plt.subplots(figsize=(10, 6))

        values = []
        labels = []
        colors = []
        for correct in [True, False]:
            subset = results.loc[results[correctness_col].fillna(False).astype(bool) == correct, "rt"]
            if not subset.empty:
                values.append(subset.dropna())
                labels.append("correct" if correct else "incorrect")
                colors.append("#2ca02c" if correct else "#d62728")

        box = ax.boxplot(values, labels=labels, patch_artist=True)
        for patch, color in zip(box["boxes"], colors):
            patch.set_facecolor(color)
            patch.set_alpha(0.6)
        for median in box["medians"]:
            median.set_color("black")
        ax.set_ylabel("RT (s)")
        ax.set_title("ABX RT by correctness")
        ax.grid(axis="y", linestyle="--", alpha=0.3)
        self.save_plot(results_dir=results_dir, name=plot_name or "abx_rt_boxplot")
        plt.show()

    def plot_abx_correctness_rt_over_trials(
        self,
        results: pd.DataFrame,
        window: int = 10,
        ax=None,
        results_dir: Optional[Union[str, Path]] = None,
        plot_name: Optional[str] = None,
    ) -> None:
        """Plot rolling correctness and RT over trial order."""
        if not isinstance(results, pd.DataFrame):
            raise TypeError("results must be a pandas DataFrame")
        if "correct_bool" not in results.columns or "rt" not in results.columns:
            raise ValueError("results must contain 'correct_bool' and 'rt' columns")

        if ax is None:
            _, ax = plt.subplots(figsize=(10, 6))

        plot_df = results.copy()
        plot_df = plot_df.reset_index(drop=True)
        plot_df["correct_bool"] = plot_df["correct_bool"].fillna(False).astype(int)
        plot_df["rt"] = pd.to_numeric(plot_df["rt"], errors="coerce")

        correctness_series = plot_df["correct_bool"].rolling(window=window, min_periods=1).mean()
        rt_series = plot_df["rt"].rolling(window=window, min_periods=1).mean()

        ax.plot(range(1, len(plot_df) + 1), correctness_series, label="Rolling accuracy")
        ax2 = ax.twinx()
        ax2.plot(range(1, len(plot_df) + 1), rt_series, color="tab:red", label="Rolling RT")

        ax.set_xlabel("Trial")
        ax.set_ylabel("Rolling accuracy")
        ax2.set_ylabel("Rolling RT (s)")
        ax.set_title("ABX correctness and RT over trials")
        ax.set_ylim(0, 1)
        ax.grid(axis="y", linestyle="--", alpha=0.3)
        lines1, labels1 = ax.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax.legend(lines1 + lines2, labels1 + labels2, loc="best")
        self.save_plot(results_dir=results_dir, name=plot_name or "abx_correctness_rt_over_trials")
        plt.show()

    def plot_staircase_rt_boxplot(
        self,
        results: pd.DataFrame,
        correctness_col: str = "correct",
        ax=None,
        results_dir: Optional[Union[str, Path]] = None,
        plot_name: Optional[str] = None,
    ) -> None:
        """Boxplot staircase reaction times by response correctness."""
        if not isinstance(results, pd.DataFrame):
            raise TypeError("results must be a pandas DataFrame")
        if correctness_col not in results.columns or "rt" not in results.columns:
            raise ValueError("results must contain 'correctness' and 'rt' columns")

        if ax is None:
            _, ax = plt.subplots(figsize=(10, 6))

        values = []
        labels = []
        colors = []
        for correct in [True, False]:
            subset = results.loc[results[correctness_col].fillna(False).astype(bool) == correct, "rt"]
            if not subset.empty:
                values.append(subset.dropna())
                labels.append("correct" if correct else "incorrect")
                colors.append("#2ca02c" if correct else "#d62728")

        box = ax.boxplot(values, labels=labels, patch_artist=True)
        for patch, color in zip(box["boxes"], colors):
            patch.set_facecolor(color)
            patch.set_alpha(0.6)
        for median in box["medians"]:
            median.set_color("black")
        ax.set_ylabel("RT (s)")
        ax.set_title("Staircase RT by correctness")
        ax.grid(axis="y", linestyle="--", alpha=0.3)
        self.save_plot(results_dir=results_dir, name=plot_name or "staircase_rt_boxplot")
        plt.show()

    def plot_staircase_correctness_rt_over_trials(
        self,
        results: pd.DataFrame,
        window: int = 10,
        ax=None,
        results_dir: Optional[Union[str, Path]] = None,
        plot_name: Optional[str] = None,
    ) -> None:
        """Plot rolling correctness and RT over staircase trials."""
        if not isinstance(results, pd.DataFrame):
            raise TypeError("results must be a pandas DataFrame")
        if "correct" not in results.columns or "rt" not in results.columns:
            raise ValueError("results must contain 'correct' and 'rt' columns")

        if ax is None:
            _, ax = plt.subplots(figsize=(10, 6))

        plot_df = results.copy()
        plot_df = plot_df.reset_index(drop=True)
        plot_df["correct"] = plot_df["correct"].fillna(False).astype(int)
        plot_df["rt"] = pd.to_numeric(plot_df["rt"], errors="coerce")

        correctness_series = plot_df["correct"].rolling(window=window, min_periods=1).mean()
        rt_series = plot_df["rt"].rolling(window=window, min_periods=1).mean()

        ax.plot(range(1, len(plot_df) + 1), correctness_series, label="Rolling accuracy")
        ax2 = ax.twinx()
        ax2.plot(range(1, len(plot_df) + 1), rt_series, color="tab:red", label="Rolling RT")

        ax.set_xlabel("Trial")
        ax.set_ylabel("Rolling accuracy")
        ax2.set_ylabel("Rolling RT (s)")
        ax.set_title("Staircase correctness and RT over trials")
        ax.set_ylim(0, 1)
        ax.grid(axis="y", linestyle="--", alpha=0.3)
        lines1, labels1 = ax.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax.legend(lines1 + lines2, labels1 + labels2, loc="best")
        self.save_plot(results_dir=results_dir, name=plot_name or "staircase_correctness_rt_over_trials")
        plt.show()

    def plot_mushra_rt_boxplot(
        self,
        results: pd.DataFrame,
        block_col: Optional[str] = None,
        ax=None,
        results_dir: Optional[Union[str, Path]] = None,
        plot_name: Optional[str] = None,
    ) -> None:
        """Boxplot MUSHRA reaction times by block."""
        plot_df = self.read_results(results, kind="mushra")
        if "rt" not in plot_df.columns:
            raise ValueError("results must contain an 'rt' column")

        if ax is None:
            _, ax = plt.subplots(figsize=(10, 6))

        if block_col is None:
            if "block" in plot_df.columns:
                block_col = "block"
            elif "block_name" in plot_df.columns:
                block_col = "block_name"
            else:
                plot_df["block"] = "all"
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

        box = ax.boxplot(values, labels=labels, patch_artist=True, showfliers=False)
        for patch, color in zip(box["boxes"], colors):
            patch.set_facecolor(color)
            patch.set_alpha(0.6)
        for median in box["medians"]:
            median.set_color("black")
        ax.set_ylabel("RT (s)")
        ax.set_title("MUSHRA RT by block")
        ax.grid(axis="y", linestyle="--", alpha=0.3)
        self.save_plot(results_dir=results_dir, name=plot_name or "mushra_rt_boxplot")
        plt.show()

    def plot_mushra_rt_over_trials(
        self,
        results: pd.DataFrame,
        window: int = 10,
        ax=None,
        results_dir: Optional[Union[str, Path]] = None,
        plot_name: Optional[str] = None,
    ) -> None:
        """Plot rolling MUSHRA reaction times over the trial order."""
        plot_df = self.read_results(results, kind="mushra")
        if "rt" not in plot_df.columns:
            raise ValueError("results must contain an 'rt' column")

        if ax is None:
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
        self.save_plot(results_dir=results_dir, name=plot_name or "mushra_rt_over_trials")
        plt.show()

    def plot_mushra_mean_ratings(
        self,
        results: pd.DataFrame,
        stimulus_col: Optional[str] = None,
        rating_col: str = "rating",
        attribute_col: Optional[str] = None,
        ax=None,
        results_dir: Optional[Union[str, Path]] = None,
        plot_name: Optional[str] = None,
        caption_bool: bool = False,
        reference_value: Optional[float] = None,
        config_path: Optional[Union[str, Path]] = None,
    ) -> None:
        """Plot block-wise MUSHRA means and the underlying trial-level ratings."""
        if not isinstance(results, pd.DataFrame):
            raise TypeError("results must be a pandas DataFrame")
        if rating_col not in results.columns:
            raise ValueError("results must contain a rating column")

        if ax is None:
            _, ax = plt.subplots(figsize=(10, 6))

        plot_df = results.copy()
        plot_df[rating_col] = pd.to_numeric(plot_df[rating_col], errors="coerce")
        plot_df = plot_df.dropna(subset=[rating_col])

        if stimulus_col is None:
            if "stimulus" in plot_df.columns:
                stimulus_col = "stimulus"
            elif "test" in plot_df.columns and "reference" in plot_df.columns:
                plot_df["stimulus"] = plot_df[["reference", "test"]].astype(str).agg(lambda s: f"{s['test']}", axis=1)
                stimulus_col = "stimulus"
            else:
                raise ValueError("results must contain a stimulus column or reference/test columns")

        if attribute_col is None:
            if "attribute" in plot_df.columns:
                attribute_col = "attribute"
            elif "attribute_name" in plot_df.columns:
                attribute_col = "attribute_name"
            else:
                plot_df["attribute"] = "all"
                attribute_col = "attribute"

        # Group the data by attribute and draw one line per attribute.
        attribute_groups = []
        for attribute_value, group in plot_df.groupby(attribute_col, dropna=False):
            attribute_groups.append((str(attribute_value), group))

        if not attribute_groups:
            return

        # Use one shared x-axis across all stimuli so the attribute-wise lines remain comparable.
        all_stimuli = sorted({str(stimulus) for _, group in attribute_groups for stimulus in group[stimulus_col].astype(str).unique()})
        x_positions = {stimulus: idx for idx, stimulus in enumerate(all_stimuli)}
        colors = plt.cm.Set2.colors

        for idx, (attribute_label, group) in enumerate(attribute_groups):
            color = colors[idx % len(colors)]
            stimuli = sorted(group[stimulus_col].astype(str).unique())
            if not stimuli:
                continue

            x = [x_positions[stimulus] for stimulus in stimuli]
            means = [float(group.loc[group[stimulus_col].astype(str) == stimulus, rating_col].mean()) for stimulus in stimuli]

            # Individual trial ratings are shown as semi-transparent dots.
            for stimulus in stimuli:
                subset = group.loc[group[stimulus_col].astype(str) == stimulus, rating_col]
                jitter = 0.02 * (idx % 2) - 0.01
                ax.scatter([x_positions[stimulus] + jitter] * len(subset), subset, color=color, alpha=0.45, s=25)

            # One line per attribute, with the attribute mean per stimulus.
            ax.plot(x, means, color=color, linewidth=1.6, marker='o', label=attribute_label)
            ax.scatter(x, means, color=color, s=70, zorder=3)

            reference_line_value = self._resolve_reference_value(
                group,
                reference_value=reference_value,
                config_path=config_path,
                group_label=attribute_label,
            )
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
        handles, labels = ax.get_legend_handles_labels()
        if handles and labels:
            ax.legend(title="Attribute")
        else:
            ax.legend(title="Attribute")
        if caption_bool:
            self._add_caption(
                ax=ax,
                caption_text="Mean ratings per test stimulus and grouped by attribute. The dashed line shows the reference rating.",
            )
        self.save_plot(results_dir=results_dir, name=plot_name or "mushra_mean_ratings")
        plt.show()

    def plot_mushra_summary_distribution(
        self,
        results: pd.DataFrame,
        stimulus_col: Optional[str] = None,
        rating_col: str = "rating",
        attribute_col: Optional[str] = None,
        ax=None,
        results_dir: Optional[Union[str, Path]] = None,
        plot_name: Optional[str] = None,
        caption_bool: bool = False,
        reference_value: Optional[float] = None,
        config_path: Optional[Union[str, Path]] = None,
    ) -> None:
        """Plot a classic MUSHRA summary plot with one subplot per block."""
        if not isinstance(results, pd.DataFrame):
            raise TypeError("results must be a pandas DataFrame")
        if rating_col not in results.columns:
            raise ValueError("results must contain a rating column")

        plot_df = results.copy()
        plot_df[rating_col] = pd.to_numeric(plot_df[rating_col], errors="coerce")
        plot_df = plot_df.dropna(subset=[rating_col])

        if stimulus_col is None:
            if "stimulus" in plot_df.columns:
                stimulus_col = "stimulus"
            elif "test" in plot_df.columns and "reference" in plot_df.columns:
                plot_df["stimulus"] = plot_df[["reference", "test"]].astype(str).agg(lambda s: f"{s['test']}", axis=1)
                stimulus_col = "stimulus"
            else:
                raise ValueError("results must contain a stimulus column or reference/test columns")

        if attribute_col is None:
            if "attribute" in plot_df.columns:
                attribute_col = "attribute"
            elif "attribute_name" in plot_df.columns:
                attribute_col = "attribute_name"
            else:
                plot_df["attribute"] = "all"
                attribute_col = "attribute"

        attribute_groups = [(str(attribute_value), group) for attribute_value, group in plot_df.groupby(attribute_col, dropna=False)]
        if not attribute_groups:
            return

        if ax is None:
            fig, axes = plt.subplots(len(attribute_groups), 1, figsize=(10, 6), squeeze=False)
            axes = axes.flatten()
        else:
            fig = None
            axes = [ax]

        # Plot one boxplot per attribute in its own subplot.
        for axis, (attribute_label, group) in zip(axes, attribute_groups):
            values = [
                group.loc[group[stimulus_col].astype(str) == stimulus, rating_col].dropna().tolist()
                for stimulus in sorted(group[stimulus_col].astype(str).unique())
            ]
            labels = [str(stimulus) for stimulus in sorted(group[stimulus_col].astype(str).unique())]
            box = axis.boxplot(values, labels=labels, patch_artist=True)
            for patch in box["boxes"]:
                patch.set_alpha(0.7)

            for i, stimulus in enumerate(sorted(group[stimulus_col].astype(str).unique()), start=1):
                subset = group.loc[group[stimulus_col].astype(str) == stimulus, rating_col].dropna()
                if subset.empty:
                    continue
                jitter = 0.02 * (i % 2) - 0.01
                axis.scatter([i + jitter] * len(subset), subset, color="0.25", alpha=0.45, s=25)

            reference_line_value = self._resolve_reference_value(
                group,
                reference_value=reference_value,
                config_path=config_path,
                group_label=attribute_label,
            )
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
        
        plt.legend()
        if fig is not None:
           # fig.tight_layout(rect=(0, 0.05, 1, 1))
            if caption_bool:
                self._add_caption(
                    fig=fig,
                    caption_text="Boxplots per test stimulus. The dashed line shows the reference rating. There is a subplot for every attribute",
                )
        else:
            if caption_bool:
                self._add_caption(
                    ax=ax,
                    caption_text="Boxplots per test stimulus. The dashed line shows the reference rating. There is a subplot for every attribute",
                )
        self.save_plot(fig=fig ,results_dir=results_dir, name=plot_name or "mushra_summary_distribution")
        plt.show()

    def _binomial_ci(self, p: float, n: int, ci: float = 0.95) -> float:
        """Approximate binomial confidence interval half-width."""
        if n <= 0:
            return 0.0
        z = 1.96 if ci >= 0.95 else 1.645
        se = (p * (1 - p) / n) ** 0.5
        return z * se
