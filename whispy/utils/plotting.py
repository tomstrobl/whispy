from __future__ import annotations

from typing import Optional

import matplotlib.pyplot as plt
import pandas as pd


class Plotting:
    """Collection of plotting helpers for staircase, ABX, and MUSHRA results."""

    def plot_staircase(
        self,
        results: pd.DataFrame,
        title: Optional[str] = None,
        reversals_for_threshold: int = 6,
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

        threshold = self._estimate_threshold_level(
            results,
            reversals_for_threshold=reversals_for_threshold,
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
        plt.show()

    def plot_abx_accuracy_by_section(
        self,
        results: pd.DataFrame,
        group_col: str = "section_name",
        condition_col: str = "block_name",
        ci: float = 0.95,
        ax=None,
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
        plt.show()

    def plot_abx_rt_boxplot(
        self,
        results: pd.DataFrame,
        correctness_col: str = "correct_bool",
        ax=None,
    ) -> None:
        """Boxplot ABX reaction times by response correctness."""
        if not isinstance(results, pd.DataFrame):
            raise TypeError("results must be a pandas DataFrame")
        if correctness_col not in results.columns or "rt" not in results.columns:
            raise ValueError("results must contain 'correct_bool' and 'rt' columns")

        if ax is None:
            _, ax = plt.subplots(figsize=(8, 5))

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
        plt.show()

    def plot_abx_correctness_rt_over_trials(
        self,
        results: pd.DataFrame,
        window: int = 10,
        ax=None,
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
        plt.show()

    def plot_mushra_mean_ratings(
        self,
        results: pd.DataFrame,
        stimulus_col: Optional[str] = None,
        rating_col: str = "rating",
        block_col: Optional[str] = None,
        ax=None,
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
                plot_df["stimulus"] = plot_df[["reference", "test"]].astype(str).agg(lambda s: f"{s['reference']} / {s['test']}", axis=1)
                stimulus_col = "stimulus"
            else:
                raise ValueError("results must contain a stimulus column or reference/test columns")

        if block_col is None:
            if "block" in plot_df.columns:
                block_col = "block"
            elif "block_name" in plot_df.columns:
                block_col = "block_name"
            else:
                plot_df["block"] = "all"
                block_col = "block"

        # Group the data by block and draw one line per block.
        block_groups = []
        for block_value, group in plot_df.groupby(block_col, dropna=False):
            block_groups.append((str(block_value), group))

        if not block_groups:
            return

        # Use one shared x-axis across all stimuli so the block-wise lines remain comparable.
        all_stimuli = sorted({str(stimulus) for _, group in block_groups for stimulus in group[stimulus_col].astype(str).unique()})
        x_positions = {stimulus: idx for idx, stimulus in enumerate(all_stimuli)}
        colors = plt.cm.Set2.colors

        for idx, (block_label, group) in enumerate(block_groups):
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

            # One line per block, with the block mean per stimulus.
            ax.plot(x, means, color=color, linewidth=1.6, marker='o', label=block_label)
            ax.scatter(x, means, color=color, s=70, zorder=3)

        ax.set_xticks(list(range(len(all_stimuli))))
        ax.set_xticklabels(all_stimuli, rotation=45, ha="right")
        ax.set_ylabel("Rating")
        ax.set_title("MUSHRA mean ratings by block")
        ax.grid(axis="y", linestyle="--", alpha=0.3)
        ax.legend(title="Block")
        plt.show()

    def plot_mushra_summary_distribution(
        self,
        results: pd.DataFrame,
        stimulus_col: Optional[str] = None,
        rating_col: str = "rating",
        block_col: Optional[str] = None,
        ax=None,
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
                plot_df["stimulus"] = plot_df[["reference", "test"]].astype(str).agg(lambda s: f"{s['reference']} / {s['test']}", axis=1)
                stimulus_col = "stimulus"
            else:
                raise ValueError("results must contain a stimulus column or reference/test columns")

        if block_col is None:
            if "block" in plot_df.columns:
                block_col = "block"
            elif "block_name" in plot_df.columns:
                block_col = "block_name"
            else:
                plot_df["block"] = "all"
                block_col = "block"

        block_groups = [(str(block_value), group) for block_value, group in plot_df.groupby(block_col, dropna=False)]
        if not block_groups:
            return

        if ax is None:
            fig, axes = plt.subplots(len(block_groups), 1, figsize=(10, 4 * len(block_groups)), squeeze=False)
            axes = axes.flatten()
        else:
            fig = None
            axes = [ax]

        # Plot one boxplot per block in its own subplot.
        for axis, (block_label, group) in zip(axes, block_groups):
            values = [
                group.loc[group[stimulus_col].astype(str) == stimulus, rating_col].dropna().tolist()
                for stimulus in sorted(group[stimulus_col].astype(str).unique())
            ]
            labels = [str(stimulus) for stimulus in sorted(group[stimulus_col].astype(str).unique())]
            box = axis.boxplot(values, labels=labels, patch_artist=True)
            for patch in box["boxes"]:
                patch.set_alpha(0.7)
            axis.set_ylabel("Rating")
            axis.set_title(f"MUSHRA rating distribution — {block_label}")
            axis.grid(axis="y", linestyle="--", alpha=0.3)

        if fig is not None:
            fig.tight_layout()
        plt.show()

    def _estimate_threshold_level(
        self,
        results: pd.DataFrame,
        reversals_for_threshold: int = 6,
    ) -> Optional[float]:
        """Estimate the staircase threshold from the final reversal levels."""
        if not isinstance(results, pd.DataFrame):
            return None
        if "reversal" not in results.columns or "level" not in results.columns:
            return None

        reversal_levels = results.loc[results["reversal"].fillna(False), "level"]
        if reversal_levels.empty:
            return None

        used = reversal_levels.iloc[-max(1, int(reversals_for_threshold)):]
        return float(used.mean())

    def _binomial_ci(self, p: float, n: int, ci: float = 0.95) -> float:
        """Approximate binomial confidence interval half-width."""
        if n <= 0:
            return 0.0
        z = 1.96 if ci >= 0.95 else 1.645
        se = (p * (1 - p) / n) ** 0.5
        return z * se
