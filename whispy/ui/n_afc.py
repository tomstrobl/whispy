from __future__ import annotations

import os
import random
import time
from functools import partial
from typing import Any, Dict, List, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

import pandas as pd

from whispy.interfaces import StimuliHandler, SoundDevice
from whispy.utils import load_design, read_config

from .base import _BaseUIWindow

# Directory containing this file. Required for default configs
FILEPATH = os.path.dirname(os.path.abspath(__file__))


class NAFC(_BaseUIWindow):
    """Simple N-AFC (N-alternative forced choice) UI.

    Notes
    -----
    - Minimal, modular scaffold following the project's UI patterns.
    - Config-driven via ``configs/n_afc.yml``.
    - Uses a ``StimuliHandler`` (default ``SoundDevice``) to play stimuli by id.

    Parameters
    ----------
    screen : dict, optional
        Trial description containing metadata and the ``test`` choices. If not
        provided a minimal default is used for quick testing.
    stimuli_handler : StimuliHandler, optional
        Handler used to play stimuli. If ``None``, ``SoundDevice()`` is used.
    n_afc_config : str, optional
        Path to the N-AFC YAML config. If ``None``, ``configs/n_afc.yml`` from
        the package is used.
    blocking : bool, optional
        If ``True``, block until the trial is submitted (via
        ``wait_until_closed``).
    debug : bool, optional
        If ``True``, the window close button is enabled and debug prints are
        emitted.
    parent : QMainWindow, optional
        If provided, reuse that UI's host window instead of opening a new one:
        the host's central widget is swapped in place. This keeps a running
        experiment (e.g. a staircase) in the same window across trials so it
        does not flicker/reload or drop out of fullscreen. The OS window is not
        re-shown or resized; call ``close()`` on any instance sharing the host
        to close it.
    """

    def __init__(
        self,
        *,
        screen: Optional[Dict[str, Any]] = None,
        stimuli_handler: Optional[StimuliHandler] = None,
        n_afc_config: Optional[str] = None,
        blocking: bool = True,
        debug: bool = False,
        parent: Optional[QMainWindow] = None,
    ) -> None:
        super().__init__(blocking=bool(blocking), debug=bool(debug), parent=parent)

        # default screen for quick tests
        if screen is None:
            screen = {
                "block": 0,
                "section": 0,
                "test": [1, 2, 3],
                "correct": 1,
                "trial_id": 0,
                "block_changed": True,
                "section_changed": True,
                "block_name": "Block 1",
                "section_name": "Section 1",
            }

        self.screen = screen

        # stimuli handler
        self.stimuli_handler = stimuli_handler if stimuli_handler is not None else SoundDevice()

        # load UI/test config and resolve all settings once
        if n_afc_config is None:
            n_afc_config = os.path.join(FILEPATH, "..", "..", "configs", "n_afc.yml")
        cfg = read_config(n_afc_config)
        cfg = cfg if isinstance(cfg, dict) else {}
        # The global theme from configs/design.yml is the base; the per-UI
        # `ui:` block only overrides wording, window size, or individual colors.
        self._ui_cfg = load_design(cfg.get("ui"))
        self._test_cfg = cfg.get("test", {})
        self._resolve_config()

        # trial choices and selection state
        self._choices = self._prepare_choices()
        self._selected: Optional[Any] = None
        self._selected_button: Optional[QPushButton] = None
        self._rt: Optional[float] = None
        self._choice_buttons: List[QPushButton] = []

        # In non-debug standalone mode, block the native close button.
        if parent is None and not self._debug:
            self.disable_close_button()

        self._build_ui()

        # Resolve and present the host window. When reusing a parent host the
        # central widget is swapped in place (no new OS window), so a running
        # experiment stays e.g. fullscreen across trials.
        window_size = self._ui_cfg.get("window_size", [1000, 600])
        width, height, fullscreen = self._resolve_window_size(
            window_size, fallback=(1000, 600), minimum_size=(400, 300))
        if parent is None:
            self._show_host_window(
                width=width, height=height, fullscreen=fullscreen,
                background_color=self._background_color)

        # start time for reaction time measurement
        self._start_time = time.time()

        if blocking:
            self.wait_until_closed()

    # ------------------------------------------------------------------ setup
    def _resolve_config(self) -> None:
        """Read all UI config values once into named attributes."""
        ui = self._ui_cfg
        self._fontcolor = str(ui.get("fontcolor", "#e8eaed"))
        self._background_color = str(ui.get("window_background_color", "#2b2b2b"))
        self._task_fontsize = max(1, int(ui.get("task_fontsize", 16)))
        self._task_spacing = int(ui.get("task_spacing", 12))
        self._button_size = int(ui.get("button_size", 56))
        self._button_fontsize = max(1, int(ui.get("button_fontsize", 14)))
        self._button_spacing = int(ui.get("button_spacing", 8))
        self._button_bg = str(ui.get("button_background_color", "#ffffff"))
        self._button_fg = str(ui.get("button_text_color", "#2b3550"))
        self._button_border = str(ui.get("button_border_color", "#b9c4dd"))
        self._button_hover_bg = str(ui.get("button_hover_background_color", "#dbe2f1"))
        self._button_selected_bg = str(ui.get("button_selected_background_color", "#5cb874"))
        self._button_selected_fg = str(ui.get("button_selected_text_color", "#ffffff"))
        self._button_disabled_bg = str(ui.get("button_disabled_background_color", "#eef1f7"))
        self._button_disabled_fg = str(ui.get("button_disabled_text_color", "#9aa3b2"))
        self._button_radius = str(ui.get("button_border_radius", "8px"))
        self._submit_hint = str(ui.get("submit_hint", "Listen to a stimulus, select one, then submit."))
        self._submit_button_text = str(ui.get("submit_button_text", "Submit choice"))

    def _prepare_choices(self) -> List[Any]:
        """Return the per-trial choice ids, optionally shuffled."""
        choices = list(self.screen.get("test", []))

        n_choices = self._test_cfg.get("n_choices")
        if self._debug and n_choices is not None and len(choices) != int(n_choices):
            print("warning: number of provided choices != test.n_choices")

        if bool(self._test_cfg.get("shuffle_choices", True)):
            random.shuffle(choices)
        return choices

    def _resolve_task_text(self) -> str:
        """Look up the task prompt from ``attributes.yml`` for this trial."""
        attr_name = self.screen.get("attribute")
        if attr_name is None:
            return "N-AFC task"
        try:
            attributes = read_config(os.path.join(FILEPATH, "..", "..", "configs", "attributes.yml"))
        except Exception:
            return "N-AFC task"
        attr = attributes.get(attr_name) if isinstance(attributes, dict) else None
        if isinstance(attr, dict):
            return str(attr.get("task", "N-AFC task"))
        return "N-AFC task"

    def _build_ui(self) -> None:
        """Build the central widget: task text, choice buttons, submit."""
        container = QWidget(self)
        container.setStyleSheet(f"background-color: {self._background_color};")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(self._task_spacing)

        # task prompt
        task_label = QLabel(self._resolve_task_text().replace("\n", "  \n"), self)
        task_label.setWordWrap(True)
        task_label.setStyleSheet(f"color: {self._fontcolor};")
        task_label.setFont(QFont("Helvetica", self._task_fontsize))
        layout.addWidget(task_label, alignment=Qt.AlignmentFlag.AlignHCenter)

        # choice buttons (labelled 1..n in the order shown to the participant)
        buttons_row = QWidget(self)
        br_layout = QHBoxLayout(buttons_row)
        br_layout.setContentsMargins(0, 12, 0, 12)
        br_layout.setSpacing(self._button_spacing)
        for idx, stim_id in enumerate(self._choices, start=1):
            btn = QPushButton(str(idx), self)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedSize(self._button_size, self._button_size)
            btn.setFont(QFont("Helvetica", self._button_fontsize))
            btn.clicked.connect(partial(self._on_choice_clicked, stim_id, btn))
            br_layout.addWidget(btn)
            self._choice_buttons.append(btn)
        self._apply_choice_button_styles()
        layout.addWidget(buttons_row, alignment=Qt.AlignmentFlag.AlignHCenter)

        # submit hint
        submit_label = QLabel(self._submit_hint, self)
        submit_label.setWordWrap(True)
        submit_label.setStyleSheet(f"color: {self._fontcolor};")
        submit_label.setFont(QFont("Helvetica", max(1, self._task_fontsize - 1)))
        layout.addWidget(submit_label, alignment=Qt.AlignmentFlag.AlignHCenter)

        # submit button (disabled until a choice is selected)
        self._submit_button = QPushButton(self._submit_button_text, self)
        self._submit_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._submit_button.setFont(QFont("Helvetica", self._button_fontsize))
        self._submit_button.setStyleSheet(
            f"QPushButton {{ background-color: {self._button_bg}; color: {self._button_fg};"
            f" border: 1px solid {self._button_border}; border-radius: {self._button_radius};"
            f" padding: 6px 16px; }}"
            f"QPushButton:hover {{ background-color: {self._button_hover_bg}; }}"
            f"QPushButton:disabled {{ background-color: {self._button_disabled_bg};"
            f" color: {self._button_disabled_fg}; border-color: {self._button_disabled_bg}; }}"
        )
        self._submit_button.setEnabled(False)
        self._submit_button.clicked.connect(self._on_submit_clicked)
        layout.addWidget(self._submit_button, alignment=Qt.AlignmentFlag.AlignHCenter)

        self._host.setCentralWidget(container)

    # --------------------------------------------------------------- handlers
    def _on_choice_clicked(self, stim_id: Any, button: QPushButton, *_args: Any) -> None:
        """Select a choice and play its stimulus (final logging is on submit).

        The trailing ``*_args`` absorbs the ``checked`` boolean that Qt's
        ``clicked`` signal appends after the bound ``stim_id``/``button``.
        """
        self._selected = stim_id
        self._selected_button = button
        self._submit_button.setEnabled(True)
        self._apply_choice_button_styles()
        if self._debug:
            print(f"Selected: {stim_id!r} (type={type(stim_id).__name__})")
        self._play_stimulus(stim_id)

    def _play_stimulus(self, stim_id: Any) -> None:
        """Play a stimulus, retrying with a string key for ``SoundDevice``.

        Playback errors never propagate, so a misconfigured stimulus can never
        block the participant from finishing the trial.
        """
        try:
            self.stimuli_handler.play(stim_id)
            return
        except Exception as exc:
            # SoundDevice keys come from YAML and may be strings; retry as str.
            if not isinstance(self.stimuli_handler, SoundDevice):
                if self._debug:
                    print(f"playback failed for {stim_id!r}: {exc}")
                return

        try:
            self.stimuli_handler.play(str(stim_id))
        except Exception as exc:
            if self._debug:
                print(f"playback failed for {stim_id!r} (fallback tried): {exc}")

    def _on_submit_clicked(self) -> None:
        """Finalize the currently selected choice and end the trial.

        Like the other whispy UIs, this only releases the blocking loop; the
        window stays open so the caller can present the next trial in the same
        window (no reload / fullscreen drop). The caller closes it explicitly
        via ``close()`` when the experiment is done.
        """
        if self._selected is None:
            return

        # Reaction time is measured for the confirmed answer.
        self._rt = time.time() - self._start_time
        if self._debug:
            print(f"Submitted: {self._selected!r} (rt={self._rt:.3f}s)")

        self.unblock()

    def _apply_choice_button_styles(self) -> None:
        """Apply default/selected color styles to all choice buttons."""
        for btn in self._choice_buttons:
            if btn is self._selected_button:
                # Selected: filled green, no hover change.
                btn.setStyleSheet(
                    f"QPushButton {{ background-color: {self._button_selected_bg};"
                    f" color: {self._button_selected_fg}; border: none;"
                    f" border-radius: {self._button_radius}; }}"
                )
            else:
                # Resting: light, bordered, with a hover highlight.
                btn.setStyleSheet(
                    f"QPushButton {{ background-color: {self._button_bg};"
                    f" color: {self._button_fg};"
                    f" border: 1px solid {self._button_border};"
                    f" border-radius: {self._button_radius}; }}"
                    f"QPushButton:hover {{ background-color: {self._button_hover_bg}; }}"
                )

    # ---------------------------------------------------------------- results
    def get_results(self) -> pd.DataFrame:
        """Return a one-row DataFrame with the trial result.

        Columns:
        - block, section, trial_id, block_name, section_name
        - choices : list of stimulus ids (order shown to participant)
        - correct : stimulus id marked as correct in screen (optional)
        - selected : stimulus id selected by participant (or None)
        - correct_bool : bool if correct info present
        - rt : reaction time in seconds (float or None)
        """
        row = {
            k: self.screen.get(k) for k in ["block", "section", "trial_id", "block_name", "section_name"]
        }
        correct = self.screen.get("correct", None)
        row.update(
            {
                "choices": list(self._choices),
                "correct": correct,
                "selected": self._selected,
                "correct_bool": None if correct is None else (self._selected == correct),
                "rt": float(self._rt) if self._rt is not None else None,
            }
        )
        return pd.DataFrame([row])