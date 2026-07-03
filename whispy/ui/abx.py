from __future__ import annotations

import os
import random
import time
from functools import partial
from typing import Any, Dict, List, Optional

from PyQt6.QtCore import QEvent, Qt, QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication,
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
from whispy.utils._utils import format_markdown

from .base import _BaseUIWindow, build_progress_widget
from .info_window import InfoWindow

# Directory containing this file. Required for default configs
FILEPATH = os.path.dirname(os.path.abspath(__file__))


class ABX(_BaseUIWindow):
    """Classic ABX discrimination UI.

    The participant hears three intervals: ``A``, ``B`` and ``X``. ``X`` is a
    copy of either ``A`` or ``B`` (chosen at random unless given) and the
    participant decides whether ``X`` matches ``A`` or ``B``.

    Notes
    -----
    - Mirrors :class:`whispy.ui.NAFC`: config-driven via ``configs/abx.yml``,
      uses a :class:`~whispy.interfaces.StimuliHandler` to play stimuli by id,
      reuses a single host window across trials (``parent=``), supports keyboard
      control, and scales its controls with the window size.

    Parameters
    ----------
    screen : dict, optional
        Trial description. Must carry ``a`` and ``b`` (stimulus ids of the
        pair). May carry ``x`` (the id played as X, must equal ``a`` or ``b``);
        if absent, X is drawn at random. Optional metadata: ``task``, ``block``,
        ``section``, ``trial_id``, ``block_name``, ``section_name``.
    stimuli_handler : StimuliHandler, optional
        Handler used to play stimuli. If ``None``, ``SoundDevice()`` is used.
    abx_config : str or dict, optional
        The ABX config — a YAML path or an already-loaded dict (its ``ui:``
        and ``test:`` blocks are used). If ``None``, ``configs/abx.yml`` from
        the package is used.
    blocking : bool, optional
        If ``True``, block until the trial is submitted.
    debug : bool, optional
        If ``True``, the window close button is enabled and debug prints are
        emitted (and the listen/answer gates are relaxed).
    parent : QMainWindow, optional
        If provided, reuse that UI's host window instead of opening a new one
        (keeps a running experiment in the same window across trials).
    """

    def __init__(
        self,
        *,
        screen: Optional[Dict[str, Any]] = None,
        stimuli_handler: Optional[StimuliHandler] = None,
        abx_config: Optional[str] = None,
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
                "a": 1,
                "b": 2,
                "trial_id": 0,
                "block_name": "Block 1",
                "section_name": "Section 1",
            }
        self.screen = screen

        # stimuli handler
        self.stimuli_handler = stimuli_handler if stimuli_handler is not None else SoundDevice()

        # load UI/test config and resolve all settings once
        if abx_config is None:
            abx_config = os.path.join(FILEPATH, "..", "..", "configs", "abx.yml")
        cfg = read_config(abx_config)
        cfg = cfg if isinstance(cfg, dict) else {}
        # The global theme from configs/design.yml is the base; the per-UI
        # `ui:` block only overrides wording, window size, or individual colors.
        self._ui_cfg = load_design(cfg.get("ui"))
        self._test_cfg = cfg.get("test", {})
        self._screen_setting = self._ui_cfg.get("screen")
        self._resolve_config()

        # Resolve the A/B/X assignment for this trial.
        self._a, self._b, self._x, self._correct = self._prepare_trial()

        # selection / playback state
        self._selected_answer: Optional[str] = None        # "A" or "B"
        self._selected_answer_button: Optional[QPushButton] = None
        self._rt: Optional[float] = None
        # playback buttons keyed by label ("A"/"B"/"X"); answer buttons by "A"/"B".
        self._playback_buttons: Dict[str, QPushButton] = {}
        self._answer_buttons: Dict[str, QPushButton] = {}
        # Interval labels the participant has played at least once (gates submit).
        self._played: set = set()
        # Label of the interval currently playing (highlighted green) and the
        # timer that reverts it to normal once the stimulus finishes.
        self._playing_label: Optional[str] = None
        self._play_timer: Optional[QTimer] = None
        self._listen_info_window: Optional[InfoWindow] = None
        # Whether this instance has an app-level key event filter installed.
        self._key_filter_installed = False

        # In non-debug standalone mode, block the native close button.
        if parent is None and not self._debug:
            self.disable_close_button()

        # Resolve the target window size BEFORE building the UI so buttons and
        # fonts can scale to it (see NAFC for the same pattern).
        window_size = self._ui_cfg.get("window_size", [1000, 600])
        self._window_width, self._window_height, self._fullscreen = self._resolve_window_size(
            window_size, fallback=(1000, 600), minimum_size=(400, 300))

        self._build_ui()
        self._install_key_handling()

        if parent is None:
            self._show_host_window(
                width=self._window_width, height=self._window_height,
                fullscreen=self._fullscreen,
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
        # Smaller font for the explanatory texts around the controls (the
        # listen/answer labels and the submit hint). `hint_fontsize` sets all
        # three at once; each can be overridden individually.
        self._hint_fontsize = max(1, int(ui.get("hint_fontsize", 11)))
        self._listen_label_fontsize = max(1, int(
            ui.get("listen_label_fontsize") or self._hint_fontsize))
        self._answer_label_fontsize = max(1, int(
            ui.get("answer_label_fontsize") or self._hint_fontsize))
        self._submit_hint_fontsize = max(1, int(
            ui.get("submit_hint_fontsize") or self._hint_fontsize))
        self._task_spacing = int(ui.get("task_spacing", 12))
        # Gap (px) between the submit button and the hint below it. Defaults
        # to task_spacing (the layout's base item spacing), which is also the
        # effective minimum.
        self._submit_hint_spacing = int(
            ui.get("submit_hint_spacing", self._task_spacing))
        # Share (0..1) of the free vertical window space placed ABOVE the
        # content area: 0 = flush at the top, 0.5 = centered, 1 = at the
        # bottom. Values outside 0..1 are clamped.
        self._content_top_share = min(1.0, max(0.0, float(
            ui.get("content_top_share", 0.6))))
        self._button_size = int(ui.get("button_size", 56))
        self._button_fontsize = max(1, int(ui.get("button_fontsize", 14)))
        self._submit_button_fontsize = max(1, int(
            ui.get("submit_button_fontsize") or self._button_fontsize))
        self._button_spacing = int(ui.get("button_spacing", 8))
        # Extra horizontal gap (px) between the A/B pair and the X button in
        # the playback row, on top of button_spacing; X is the reference, so
        # it is set apart visually. Scales with the window like the buttons.
        self._x_button_gap = max(0, int(ui.get("x_button_gap", 32)))
        self._button_scale = max(0.0, float(ui.get("button_scale", 1.0)))
        # Size of the content area (prompt + button rows + submit) as a
        # percentage [x%, y%] of the window, centered. Same `content_area_size`
        # key and behavior as every other test; 100 uses the max available size.
        self._content_area_size = ui.get("content_area_size", [100, 100])
        self._button_bg = str(ui.get("button_background_color", "#ffffff"))
        self._button_fg = str(ui.get("button_text_color", "#2b3550"))
        self._button_border = str(ui.get("button_border_color", "#b9c4dd"))
        self._button_hover_bg = str(ui.get("button_hover_background_color", "#dbe2f1"))
        self._button_selected_bg = str(ui.get("button_selected_background_color", "#5cb874"))
        self._button_selected_fg = str(ui.get("button_selected_text_color", "#ffffff"))
        self._button_disabled_bg = str(ui.get("button_disabled_background_color", "#eef1f7"))
        self._button_disabled_fg = str(ui.get("button_disabled_text_color", "#9aa3b2"))
        self._button_radius = str(ui.get("button_border_radius", "8px"))
        # ABX-specific wording.
        self._listen_label_text = str(ui.get("listen_label", "Listen:"))
        self._answer_label_text = str(ui.get("answer_label", "Your answer — X is the same as:"))
        self._submit_hint = str(ui.get(
            "submit_hint",
            "Play A, B and X (keys A/B/X), choose with ←/→, then press Enter to submit."))
        self._submit_button_text = str(ui.get("submit_button_text", "Submit choice"))
        # Trial progress indicator ("Trial X of Y"): shown when enabled AND the
        # screen dict carries a `progress` entry (set by the notebook's trial
        # loop). Same keys and widget as every other test.
        self._show_progress = bool(ui.get("show_progress", False))
        self._progress_text = str(ui.get("progress_text", "Trial {current} of {total}"))
        self._progress_fontsize = max(1, int(
            ui.get("progress_fontsize") or self._hint_fontsize))
        self._progress_bar_color = str(ui.get("progress_bar_color", "#5cb874"))
        self._progress_trough_color = str(
            ui.get("progress_bar_background_color", "#dbe2f1"))

    def _prepare_trial(self) -> tuple[Any, Any, Any, str]:
        """Resolve the per-trial A/B/X stimulus ids and the correct answer.

        ``test.shuffle_ab`` randomizes which stimulus of the pair is presented
        as A vs B (the answer is unaffected since it depends only on what X is).
        X is taken from the screen if given, otherwise drawn at random from the
        pair. The correct answer is ``"A"`` when X equals the A stimulus.
        """
        a = self.screen.get("a")
        b = self.screen.get("b")
        if bool(self._test_cfg.get("shuffle_ab", True)) and random.random() < 0.5:
            a, b = b, a

        x = self.screen.get("x")
        if x is None:
            x = random.choice([a, b])

        correct = "A" if x == a else "B"
        return a, b, x, correct

    # -------------------------------------------------------------- build UI
    def _scale_factor(self) -> float:
        """Factor for scaling buttons/fonts with the window size.

        ``1.0`` at the 600 px reference height and grows with the window height,
        so controls don't look lost on large/fullscreen displays. Never shrinks
        below the configured sizes; ``button_scale`` tunes it. (Same rule as
        :class:`whispy.ui.NAFC`.)
        """
        reference_height = 600.0
        height = float(getattr(self, "_window_height", reference_height))
        return max(1.0, (height / reference_height) * self._button_scale)

    def _build_ui(self) -> None:
        """Build the central widget: prompt, playback row, answer row, submit."""
        scale = self._scale_factor()
        button_size = round(self._button_size * scale)
        button_fontsize = max(1, round(self._button_fontsize * scale))
        submit_button_fontsize = max(1, round(self._submit_button_fontsize * scale))
        task_fontsize = max(1, round(self._task_fontsize * scale))
        listen_label_fontsize = max(1, round(self._listen_label_fontsize * scale))
        answer_label_fontsize = max(1, round(self._answer_label_fontsize * scale))
        submit_hint_fontsize = max(1, round(self._submit_hint_fontsize * scale))

        container = QWidget(self)
        container.setStyleSheet(f"background-color: {self._background_color};")
        outer_layout = QVBoxLayout(container)
        outer_layout.setContentsMargins(14, 14, 14, 14)

        # The actual content lives in a fixed-size widget sized to a percentage
        # of the window (`content_area_size`) and centered, exactly like the
        # MUSHRA rating area, so the layout scales the same way across tests.
        content = QWidget(container)
        area_w, area_h = self._resolve_area_size(
            (self._window_width, self._window_height),
            self._content_area_size,
            min_size=(300, 200),
            reserved=(28, 28),
        )
        # The content box is extended a little past the configured height so
        # the progress bar (flush at its bottom edge) sits a bit lower; the
        # footer spacing below compensates, so the hint and everything above
        # it keep their position.
        progress_drop = min(24, max(0, self._window_height - 28 - area_h))
        content.setFixedSize(area_w, area_h + progress_drop)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(self._task_spacing)

        # small offset so the task text sits a little below the top edge
        layout.addSpacing(self._task_spacing)

        # task prompt (markdown, like every other whispy prompt), pinned to
        # the top of the content area. The fixed
        # full-content width makes the word-wrapped height computable, so the
        # text is never clipped when the stretches compact the layout.
        task_label = QLabel(format_markdown(self._resolve_task_text()), self)
        task_label.setTextFormat(Qt.TextFormat.MarkdownText)
        task_label.setWordWrap(True)
        task_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        task_label.setStyleSheet(f"color: {self._fontcolor};")
        task_label.setFont(QFont("Helvetica", task_fontsize))
        task_label.setFixedWidth(area_w)
        layout.addWidget(task_label, alignment=Qt.AlignmentFlag.AlignHCenter)

        # The stretches (here and below the answer row) center the play/
        # answer controls between the task text pinned on top and the
        # submit button + footer (hint + progress) pinned to the bottom.
        layout.addStretch(1)

        # playback row: A, B, X (play only, not an answer)
        listen_label = QLabel(format_markdown(self._listen_label_text), self)
        listen_label.setTextFormat(Qt.TextFormat.MarkdownText)
        listen_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        listen_label.setStyleSheet(f"color: {self._fontcolor};")
        listen_label.setFont(QFont("Helvetica", listen_label_fontsize))
        layout.addWidget(listen_label, alignment=Qt.AlignmentFlag.AlignHCenter)

        play_row = QWidget(self)
        play_layout = QHBoxLayout(play_row)
        play_layout.setContentsMargins(0, 6, 0, 6)
        play_layout.setSpacing(self._button_spacing)
        for label in ("A", "B", "X"):
            if label == "X":
                # Extra gap before X: it is the reference, not part of the
                # A/B pair, so set it apart visually.
                play_layout.addSpacing(round(self._x_button_gap * scale))
            btn = QPushButton(label, self)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedSize(button_size, button_size)
            btn.setFont(QFont("Helvetica", button_fontsize))
            btn.clicked.connect(partial(self._on_play_clicked, label))
            play_layout.addWidget(btn)
            self._playback_buttons[label] = btn
        layout.addWidget(play_row, alignment=Qt.AlignmentFlag.AlignHCenter)

        # extra gap so the A/B/X playback buttons sit clearly apart from the
        # answer section below
        layout.addSpacing(self._task_spacing * 2)

        # answer row: X is the same as A or B
        answer_label = QLabel(format_markdown(self._answer_label_text), self)
        answer_label.setTextFormat(Qt.TextFormat.MarkdownText)
        answer_label.setWordWrap(True)
        answer_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        answer_label.setStyleSheet(f"color: {self._fontcolor};")
        answer_label.setFont(QFont("Helvetica", answer_label_fontsize))
        # Fixed full-content width (like the task label) so the word-wrapped
        # height is computable and the text is never clipped.
        answer_label.setFixedWidth(area_w)
        layout.addWidget(answer_label, alignment=Qt.AlignmentFlag.AlignHCenter)

        answer_row = QWidget(self)
        answer_layout = QHBoxLayout(answer_row)
        answer_layout.setContentsMargins(0, 6, 0, 6)
        answer_layout.setSpacing(self._button_spacing)
        for label in ("A", "B"):
            btn = QPushButton(label, self)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedSize(button_size, button_size)
            btn.setFont(QFont("Helvetica", button_fontsize))
            btn.clicked.connect(partial(self._on_answer_clicked, label))
            answer_layout.addWidget(btn)
            self._answer_buttons[label] = btn
        layout.addWidget(answer_row, alignment=Qt.AlignmentFlag.AlignHCenter)
        self._apply_playback_button_styles()
        self._apply_answer_button_styles()

        layout.addStretch(1)

        # submit button (disabled until an answer is selected), pinned to the
        # bottom of the content area, right above the hint
        self._submit_button = QPushButton(self._submit_button_text, self)
        self._submit_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._submit_button.setFont(QFont("Helvetica", submit_button_fontsize))
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

        # Footer pinned to the bottom of the content area: the submit hint and
        # the trial progress ("Trial X of Y" text + bar) grouped tightly
        # together, clearly set apart from the controls above.
        footer = QWidget(content)
        footer_layout = QVBoxLayout(footer)
        # The top margin tops up the layout's base task_spacing to the
        # configured submit-button-to-hint gap (submit_hint_spacing).
        footer_layout.setContentsMargins(
            0, max(0, self._submit_hint_spacing - self._task_spacing), 0, 0)
        # 16 px hint-to-bar gap plus the extra drop of the bar (see
        # progress_drop above), so the hint itself does not move down
        footer_layout.setSpacing(16 + progress_drop)

        # submit hint (markdown), spanning the full content-area width (text
        # centered) so it wraps into as few lines as possible
        submit_label = QLabel(format_markdown(self._submit_hint), self)
        submit_label.setTextFormat(Qt.TextFormat.MarkdownText)
        submit_label.setWordWrap(True)
        submit_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        submit_label.setStyleSheet(f"color: {self._fontcolor};")
        submit_label.setFont(QFont("Helvetica", submit_hint_fontsize))
        submit_label.setFixedWidth(area_w)
        footer_layout.addWidget(submit_label, alignment=Qt.AlignmentFlag.AlignHCenter)

        # trial progress ("Trial X of Y"), when enabled and the screen carries
        # progress info
        progress_widget = None
        if self._show_progress:
            progress_widget = build_progress_widget(
                self.screen.get("progress"),
                text_template=self._progress_text,
                fontsize=max(1, round(self._progress_fontsize * scale)),
                fontcolor=self._fontcolor,
                bar_color=self._progress_bar_color,
                trough_color=self._progress_trough_color,
                parent=footer,
            )
        if progress_widget is not None:
            progress_widget.setFixedWidth(min(area_w, round(300 * scale)))
            footer_layout.addWidget(
                progress_widget, alignment=Qt.AlignmentFlag.AlignHCenter)
        else:
            # no bar: fill the extended bottom so the hint stays in place
            footer_layout.addSpacing(progress_drop)

        layout.addWidget(footer, alignment=Qt.AlignmentFlag.AlignHCenter)

        # Distribute the free window space around the content area according
        # to content_top_share (default 0.6, so the block sits a little below
        # the window center). The top share is a fixed spacer so the content
        # box's downward extension (progress_drop) only moves its bottom edge,
        # not the block itself.
        outer_layout.addSpacing(round(
            self._content_top_share * max(0, self._window_height - 28 - area_h)))
        outer_layout.addWidget(content, alignment=Qt.AlignmentFlag.AlignHCenter)
        outer_layout.addStretch(1)
        self._host.setCentralWidget(container)

    def _resolve_task_text(self) -> str:
        """Resolve the on-screen task prompt. A ``task`` on the screen wins."""
        inline_task = self.screen.get("task")
        if inline_task:
            return str(inline_task)
        return "Is **X** the same as **A** or **B**?"

    # --------------------------------------------------------------- handlers
    def _on_play_clicked(self, label: str, *_args: Any) -> None:
        """Play the stimulus behind a playback button.

        The button is highlighted green while it plays and reverts to normal
        once the stimulus finishes (mirrors the active highlight in NAFC). The
        label is also recorded so the submit gate can require every interval to
        have been heard.
        """
        self._played.add(label)
        stim_id = {"A": self._a, "B": self._b, "X": self._x}[label]
        if self._debug:
            print(f"Play {label}: {stim_id!r}")
        self._play_stimulus(stim_id)

        # Highlight only the interval that is currently playing.
        self._playing_label = label
        self._apply_playback_button_styles()
        self._schedule_play_revert(label, stim_id)

    def _schedule_play_revert(self, label: str, stim_id: Any) -> None:
        """Revert ``label`` to normal once its stimulus has finished playing.

        Uses the stimulus duration when the handler exposes it; otherwise leaves
        the highlight until another interval is played or the trial ends.
        """
        if self._play_timer is None:
            self._play_timer = QTimer(self)
            self._play_timer.setSingleShot(True)
            self._play_timer.timeout.connect(self._clear_playing_highlight)
        else:
            self._play_timer.stop()

        duration = self._stimulus_duration(stim_id)
        if duration is not None:
            self._play_timer.start(max(1, int(duration * 1000)))

    def _clear_playing_highlight(self) -> None:
        """Drop the currently-playing highlight and restyle the buttons."""
        self._playing_label = None
        self._apply_playback_button_styles()

    def _stimulus_duration(self, stim_id: Any) -> Optional[float]:
        """Best-effort stimulus duration in seconds (None if unknown)."""
        stimuli = getattr(self.stimuli_handler, "stimuli", None)
        if not isinstance(stimuli, dict):
            return None
        spec = stimuli.get(stim_id, stimuli.get(str(stim_id)))
        signal = spec.get("signal") if isinstance(spec, dict) else None
        sampling_rate = (getattr(self.stimuli_handler, "sampling_rate", None)
                         or getattr(signal, "sampling_rate", None))
        if signal is None or not sampling_rate:
            return None
        try:
            return signal.time.shape[-1] / float(sampling_rate)
        except Exception:
            return None

    def _on_answer_clicked(self, answer: str, *_args: Any) -> None:
        """Select ``A`` or ``B`` as the answer (logged on submit)."""
        self._selected_answer = answer
        self._selected_answer_button = self._answer_buttons[answer]
        self._submit_button.setEnabled(True)
        self._apply_answer_button_styles()
        if self._debug:
            print(f"Answer: {answer}")

    def _play_stimulus(self, stim_id: Any) -> None:
        """Play a stimulus, retrying with a string key for ``SoundDevice``.

        Playback errors never propagate, so a misconfigured stimulus can never
        block the participant from finishing the trial.
        """
        try:
            self.stimuli_handler.play(stim_id)
            return
        except Exception as exc:
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
        """Finalize the answer and end the trial (window stays open)."""
        if self._selected_answer is None:
            return

        # Require every interval to have been heard at least once.
        if not self._debug and not self._all_played():
            self._show_listen_hint()
            return

        self._rt = time.time() - self._start_time
        if self._debug:
            print(f"Submitted: {self._selected_answer} "
                  f"(correct={self._correct}, rt={self._rt:.3f}s)")
        self.unblock()

    def _all_played(self) -> bool:
        """Whether A, B and X have each been played at least once."""
        return {"A", "B", "X"}.issubset(self._played)

    def _show_listen_hint(self) -> None:
        """Pop up a non-blocking reminder to listen to every interval first."""
        self._listen_info_window = InfoWindow(
            info_text="You have to listen to A, B and X at least once.",
            fontsize=self._task_fontsize,
            fontcolor=self._fontcolor,
            blocking=False,
        )

    # --------------------------------------------------------------- keyboard
    def _install_key_handling(self) -> None:
        """Route key presses to this trial via an app-level event filter.

        Matches :class:`whispy.ui.NAFC`: an application-level filter is used so
        the current trial (not the shared host's first instance) handles keys.
        """
        app = QApplication.instance()
        if app is not None and not self._key_filter_installed:
            app.installEventFilter(self)
            self._key_filter_installed = True

    def _remove_key_handling(self) -> None:
        """Stop intercepting key presses for this trial (idempotent)."""
        app = QApplication.instance()
        if app is not None and self._key_filter_installed:
            app.removeEventFilter(self)
        self._key_filter_installed = False

    def eventFilter(self, obj: Any, event: QEvent) -> bool:  # type: ignore[override]
        """Handle ABX keys; defer everything else to Qt."""
        if event.type() == QEvent.Type.KeyPress and self._handle_key_press(event):
            return True
        return super().eventFilter(obj, event)

    def _handle_key_press(self, event: QEvent) -> bool:
        """A/B/X (or 1/2/3) play an interval; ←/→ answer; Enter submits."""
        key = event.key()

        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._on_submit_clicked()
            return True

        # Play intervals: letters A/B/X or numbers 1/2/3.
        play_key = {
            Qt.Key.Key_A: "A", Qt.Key.Key_B: "B", Qt.Key.Key_X: "X",
            Qt.Key.Key_1: "A", Qt.Key.Key_2: "B", Qt.Key.Key_3: "X",
        }.get(key)
        if play_key is not None:
            self._on_play_clicked(play_key)
            return True

        # Answer with the arrow keys (A = left, B = right).
        if key == Qt.Key.Key_Left:
            self._on_answer_clicked("A")
            return True
        if key == Qt.Key.Key_Right:
            self._on_answer_clicked("B")
            return True

        return False

    def unblock(self) -> None:  # type: ignore[override]
        """Remove key handling for this trial, then release the blocking loop."""
        self._stop_play_timer()
        self._remove_key_handling()
        super().unblock()

    def closeEvent(self, event: Any) -> None:  # type: ignore[override]
        """Ensure the key filter is removed when the window actually closes."""
        if self._allow_close:
            self._stop_play_timer()
            self._remove_key_handling()
        super().closeEvent(event)

    def _stop_play_timer(self) -> None:
        """Stop the pending revert timer so it can't restyle deleted widgets
        after the trial's central widget has been swapped out."""
        if self._play_timer is not None:
            self._play_timer.stop()

    # ----------------------------------------------------------------- styles
    def _apply_playback_button_styles(self) -> None:
        """Style playback buttons; the one currently playing is filled green
        (like the active tile in NAFC), the rest are normal."""
        for label, btn in self._playback_buttons.items():
            if label == self._playing_label:
                # Playing: filled green, no border, no hover change.
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

    def _apply_answer_button_styles(self) -> None:
        """Style answer buttons; the selected one is filled with the accent."""
        for btn in self._answer_buttons.values():
            if btn is self._selected_answer_button:
                btn.setStyleSheet(
                    f"QPushButton {{ background-color: {self._button_selected_bg};"
                    f" color: {self._button_selected_fg}; border: none;"
                    f" border-radius: {self._button_radius}; }}"
                )
            else:
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
        - a, b, x : stimulus ids presented as A, B and X
        - correct : ``"A"`` or ``"B"`` (which answer was right)
        - selected : ``"A"``/``"B"`` chosen by the participant (or None)
        - correct_bool : whether the answer was correct
        - rt : reaction time in seconds (float or None)
        """
        row = {
            k: self.screen.get(k)
            for k in ["block", "section", "trial_id", "block_name", "section_name"]
        }
        row.update(
            {
                "a": self._a,
                "b": self._b,
                "x": self._x,
                "correct": self._correct,
                "selected": self._selected_answer,
                "correct_bool": None if self._selected_answer is None
                else (self._selected_answer == self._correct),
                "rt": float(self._rt) if self._rt is not None else None,
            }
        )
        return pd.DataFrame([row])
