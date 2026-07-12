from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Sequence
import time

import pandas


# Mapping from internal step direction to a human-readable label used in the
# results table. -1 lowers the level (harder), +1 raises it (easier).
_STEP_LABEL = {-1: "down", 0: "", 1: "up"}


class Staircase:
    """Adaptive transformed up/down staircase for N-AFC tasks.

    The staircase tracks an index into an ordered list of stimulus ``levels``
    (assumed to run from least to most discriminable, e.g. soundfiles of
    increasing intensity). After each trial the level is adjusted with a
    transformed up/down rule (Levitt, 1971):

    - step **down** (toward a *lower*, harder level) after ``n_down``
      consecutive correct responses,
    - step **up** (toward a *higher*, easier level) after ``n_up`` consecutive
      incorrect responses.

    The default ``n_up=1`` / ``n_down=2`` ("1-up/2-down") converges on the
    stimulus level yielding ~70.7% correct. The run ends as soon as either
    ``max_reversals`` reversals or ``max_trials`` trials have occurred,
    whichever comes first.

    The class is intentionally free of any GUI/audio dependency so it can be
    unit tested without a display. Drive it with :meth:`run` or the explicit
    :attr:`finished` / :meth:`next_screen` / :meth:`update` loop and present
    each trial with :class:`whispy.ui.NAFC`.

    Parameters
    ----------
    levels : sequence
        Ordered stimulus levels from least to most discriminable. Each element
        is passed unchanged to ``build_screen``. If the elements are numeric,
        :meth:`threshold` reports the threshold in their units; otherwise it
        reports the mean reversal *index*.
    build_screen : callable, optional
        Callback mapping the current level value to an :class:`NAFC` ``screen``
        dict, i.e. ``build_screen(level) -> dict``. Required for
        :meth:`next_screen` and :meth:`run`; if ``None`` you must build the
        screen yourself from :attr:`current_level`.
    n_up : int, optional
        Number of consecutive incorrect responses that trigger a step up
        (easier). The default is ``1``.
    n_down : int, optional
        Number of consecutive correct responses that trigger a step down
        (harder). The default is ``2``.
    step : int, optional
        Number of levels moved per step. The default is ``1``.
    big_step : int, optional
        Optional larger step size used during the first
        ``reversals_for_big_step`` reversals. The default is ``None``.
    reversals_for_big_step : int, optional
        Number of reversals for which ``big_step`` is used before falling back
        to ``step``. The default is ``0``.
    start_index : int, optional
        Index into ``levels`` of the first trial. The default is ``0``.
    max_reversals : int, optional
        Stop after this many reversals. The default is ``8``.
    max_trials : int, optional
        Stop after this many trials. The default is ``60``.
    reversals_for_threshold : int, optional
        Number of final reversals averaged by :meth:`threshold`. The default is
        ``6``.

    Examples
    --------
    .. code-block:: python

        import whispy

        files = [1, 2, 3, 4]  # stimulus ids of increasing intensity

        def build_screen(level):
            # one target interval among two standards (stimulus id 1)
            return {"test": [1, 1, level], "correct": level,
                    "attribute": "difference"}

        staircase = whispy.Staircase(files, build_screen=build_screen,
                                     n_up=1, n_down=2)

        def run_trial(screen):
            naf = whispy.ui.NAFC(screen=screen)
            return bool(naf.get_results()["correct_bool"].iloc[0])

        results = staircase.run(run_trial)
        print(staircase.threshold())
    """

    def __init__(
        self,
        levels: Sequence[Any],
        *,
        build_screen: Optional[Callable[[Any], Dict[str, Any]]] = None,
        n_up: int = 1,
        n_down: int = 2,
        step: int = 1,
        big_step: Optional[int] = None,
        reversals_for_big_step: int = 0,
        start_index: int = 0,
        max_reversals: int = 8,
        max_trials: int = 60,
        reversals_for_threshold: int = 6,
    ) -> None:
        self._levels = list(levels)
        if not self._levels:
            raise ValueError("levels must contain at least one element")

        if not 0 <= int(start_index) < len(self._levels):
            raise ValueError("start_index must be a valid index into levels")

        if int(n_up) < 1 or int(n_down) < 1:
            raise ValueError("n_up and n_down must be >= 1")
        if int(step) < 1:
            raise ValueError("step must be >= 1")
        if big_step is not None and int(big_step) < 1:
            raise ValueError("big_step must be >= 1")
        if int(reversals_for_big_step) < 0:
            raise ValueError("reversals_for_big_step must be >= 0")
        if int(max_reversals) < 1 or int(max_trials) < 1:
            raise ValueError("max_reversals and max_trials must be >= 1")
        if int(reversals_for_threshold) < 1:
            raise ValueError("reversals_for_threshold must be >= 1")

        self._build_screen = build_screen
        self._n_up = int(n_up)
        self._n_down = int(n_down)
        self._step = int(step)
        self._big_step = None if big_step is None else int(big_step)
        self._reversals_for_big_step = int(reversals_for_big_step)
        self._max_reversals = int(max_reversals)
        self._max_trials = int(max_trials)
        self._reversals_for_threshold = int(reversals_for_threshold)

        # mutable run state
        self._index = int(start_index)
        self._consec_correct = 0
        self._consec_incorrect = 0
        self._last_step_dir = 0  # -1 down, +1 up, 0 none yet
        self._trial = 0
        self._finished = False
        self._history: List[Dict[str, Any]] = []
        self._reversals: List[Dict[str, Any]] = []

    # --------------------------------------------------------------- state
    @property
    def finished(self) -> bool:
        """Whether the stopping criterion has been reached."""
        return self._finished

    @property
    def current_index(self) -> int:
        """Index into ``levels`` of the level to present next."""
        return self._index

    @property
    def current_level(self) -> Any:
        """Level value to present next (``levels[current_index]``)."""
        return self._levels[self._index]

    @property
    def n_reversals(self) -> int:
        """Number of reversals recorded so far."""
        return len(self._reversals)

    def next_screen(self) -> Dict[str, Any]:
        """Build the ``screen`` dict for the current level.

        A ``progress`` entry (``{"current": trial number, "total":
        max_trials}``) is added so the UI can show a trial-progress bar.
        ``total`` is the upper bound: a run that converges via
        ``max_reversals`` stops earlier. A ``progress`` already set by
        ``build_screen`` is kept untouched.

        Returns
        -------
        dict
            The result of ``build_screen(current_level)``.

        Raises
        ------
        ValueError
            If no ``build_screen`` callback was provided.
        RuntimeError
            If the staircase has already finished.
        """
        self._start_time = time.time()
        if self._build_screen is None:
            raise ValueError(
                "No build_screen callback was provided; build the screen "
                "yourself from `current_level`.")
        if self._finished:
            raise RuntimeError("staircase has finished; no further trials")
        screen = self._build_screen(self.current_level)
        if isinstance(screen, dict):
            screen.setdefault(
                "progress",
                {"current": self._trial + 1, "total": self._max_trials})
        return screen

    # --------------------------------------------------------------- driving
    def update(self, correct: bool) -> None:
        """Record the response for the current trial and advance the level.

        Parameters
        ----------
        correct : bool
            Whether the participant's response on the current trial was
            correct.

        Raises
        ------
        RuntimeError
            If the staircase has already finished.
        """
        if self._finished:
            raise RuntimeError("staircase has finished; cannot update further")
        self._rt = time.time() - self._start_time

        correct = bool(correct)
        self._trial += 1
        presented_index = self._index

        # transformed up/down counters
        if correct:
            self._consec_correct += 1
            self._consec_incorrect = 0
        else:
            self._consec_incorrect += 1
            self._consec_correct = 0

        # decide whether (and which way) to step
        step_dir = 0
        if self._consec_correct >= self._n_down:
            step_dir = -1  # down = lower intensity = harder
            self._consec_correct = 0
        elif self._consec_incorrect >= self._n_up:
            step_dir = +1  # up = higher intensity = easier
            self._consec_incorrect = 0

        # a reversal is a change of direction relative to the last actual step
        is_reversal = (
            step_dir != 0
            and self._last_step_dir != 0
            and step_dir != self._last_step_dir
        )
        if is_reversal:
            self._reversals.append({
                "trial": self._trial,
                "index": presented_index,
                "level": self._levels[presented_index],
            })

        self._history.append({
            "trial": self._trial,
            "level_index": presented_index,
            "level": self._levels[presented_index],
            "correct": correct,
            "step": _STEP_LABEL[step_dir],
            "reversal": is_reversal,
            "rt": self._rt,
        })

        # apply the step, clamped to the available level range
        if step_dir != 0:
            if (
                self._big_step is not None
                and self._reversals_for_big_step > 0
                and len(self._reversals) < self._reversals_for_big_step
            ):
                step_size = self._big_step
            else:
                step_size = self._step

            self._index = max(
                0, min(len(self._levels) - 1, self._index + step_dir * step_size))
            self._last_step_dir = step_dir

        # stop on whichever criterion is reached first
        if (len(self._reversals) >= self._max_reversals
                or self._trial >= self._max_trials):
            self._finished = True

    def run(self, run_trial: Callable[[Dict[str, Any]], bool]) -> pandas.DataFrame:
        """Run the staircase to completion using a trial callback.

        Parameters
        ----------
        run_trial : callable
            Function called once per trial as ``run_trial(screen) -> bool``,
            where ``screen`` is produced by ``build_screen`` and the return
            value is whether the response was correct.

        Returns
        -------
        pandas.DataFrame
            The trial history, as returned by :meth:`get_results`.
        """
        while not self._finished:
            screen = self.next_screen()
            correct = run_trial(screen)
            self.update(correct)
        return self.get_results()

    # --------------------------------------------------------------- results
    def reversal_levels(self) -> List[Any]:
        """Return the stimulus level at each reversal, in order."""
        return [r["level"] for r in self._reversals]

    def threshold(self) -> Optional[float]:
        """Estimate the threshold from the final reversals.

        Returns
        -------
        float or None
            The mean stimulus level over the last ``reversals_for_threshold``
            reversals when the levels are numeric, otherwise the mean reversal
            *index*. ``None`` if no reversals have occurred yet.
        """
        if not self._reversals:
            return None

        used = self._reversals[-self._reversals_for_threshold:]
        levels = [r["level"] for r in used]
        numeric = all(
            isinstance(v, (int, float)) and not isinstance(v, bool) for v in levels)
        if numeric:
            return sum(levels) / len(levels)
        indices = [r["index"] for r in used]
        return sum(indices) / len(indices)

    def get_results(self) -> pandas.DataFrame:
        """Return the per-trial history as a data frame.

        Returns
        -------
        pandas.DataFrame
            One row per trial with columns ``trial``, ``level_index``,
            ``level``, ``correct``, ``step`` (``"up"``/``"down"``/``""``), and
            ``reversal``, and ``rt``.
        """
        columns = ["trial", "level_index", "level", "correct", "step", "reversal", "rt"]
        return pandas.DataFrame(self._history, columns=columns)
