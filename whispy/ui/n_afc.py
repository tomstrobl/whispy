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
        self._screen_setting = self._ui_cfg.get("screen")
        self._resolve_config()

        # trial choices and selection state
        self._choices = self._prepare_choices()
        self._selected: Optional[Any] = None
        self._selected_button: Optional[QPushButton] = None
        self._rt: Optional[float] = None
        self._choice_buttons: List[QPushButton] = []
        # Choice buttons the participant has played at least once (gates
        # submit). Tracked per button, not per stimulus id, so duplicated
        # intervals (e.g. two standards in an odd-one-out trial) must all be
        # heard.
        self._listened: set = set()
        # With `test.single_replay: true` each interval plays at most twice:
        # the first (mandatory) listen plus one replay. Counted per button,
        # like `_listened`, so duplicated stimulus ids are limited per interval.
        self._single_replay = bool(self._test_cfg.get("single_replay", False))
        self._play_counts: Dict[QPushButton, int] = {}
        # With `test.autoplay: true` every trial starts by playing all
        # intervals once in button order (so after Submit the next trial's
        # stimuli play by themselves). The run-through counts as the mandatory
        # first listen (and as the first play for `single_replay`); any
        # click/keypress interrupts it and hands control to the participant.
        self._autoplay = bool(self._test_cfg.get("autoplay", False))
        self._autoplay_gap = max(0.0, float(self._test_cfg.get("autoplay_gap", 0.3)))
        self._autoplay_index = 0
        self._autoplay_button: Optional[QPushButton] = None
        self._autoplay_timer = QTimer(self)
        self._autoplay_timer.setSingleShot(True)
        self._autoplay_timer.timeout.connect(self._on_autoplay_timeout)
        self._listen_info_window: Optional[InfoWindow] = None
        # Whether this instance has an app-level key event filter installed.
        # Tracked so it is installed/removed exactly once per trial (see
        # ``_install_key_handling`` / ``_remove_key_handling``).
        self._key_filter_installed = False

        # In non-debug standalone mode, block the native close button.
        if parent is None and not self._debug:
            self.disable_close_button()

        # Resolve the target window size BEFORE building the UI so buttons and
        # fonts can scale to it (otherwise they look lost on large/fullscreen
        # displays). When reusing a parent host this still resolves the
        # configured size (e.g. fullscreen -> screen size), so every trial
        # scales the same way.
        window_size = self._ui_cfg.get("window_size", [1000, 600])
        self._window_width, self._window_height, self._fullscreen = self._resolve_window_size(
            window_size, fallback=(1000, 600), minimum_size=(400, 300))

        self._build_ui()

        # Keyboard support: number keys play an interval, Enter submits. The
        # filter belongs to THIS instance so it always acts on the current
        # trial's choices/state, even though a staircase reuses one host window
        # across trials (each trial is a fresh NAFC swapped into the host).
        self._install_key_handling()

        # Present the host window. When reusing a parent host the central widget
        # is swapped in place (no new OS window), so a running experiment stays
        # e.g. fullscreen across trials.
        if parent is None:
            self._show_host_window(
                width=self._window_width, height=self._window_height,
                fullscreen=self._fullscreen,
                background_color=self._background_color)

        # start time for reaction time measurement
        self._start_time = time.time()

        # Kick off the automatic run-through once the trial is on screen (the
        # timer fires after Qt has processed the show/swap of the window).
        if self._autoplay:
            self._autoplay_timer.start(max(0, round(self._autoplay_gap * 1000)))

        if blocking:
            self.wait_until_closed()

    # ------------------------------------------------------------------ setup
    def _resolve_config(self) -> None:
        """Read all UI config values once into named attributes."""
        ui = self._ui_cfg
        self._fontcolor = str(ui.get("fontcolor", "#e8eaed"))
        self._background_color = str(ui.get("window_background_color", "#2b2b2b"))
        self._task_fontsize = max(1, int(ui.get("task_fontsize", 16)))
        # Smaller font for the keyboard hint below the buttons.
        # `hint_fontsize` is the shared explanatory-text size (same key as
        # ABX); `submit_hint_fontsize` overrides it for the hint specifically.
        self._hint_fontsize = max(1, int(ui.get("hint_fontsize", 11)))
        self._submit_hint_fontsize = max(1, int(
            ui.get("submit_hint_fontsize") or self._hint_fontsize))
        self._task_spacing = int(ui.get("task_spacing", 12))
        self._button_size = int(ui.get("button_size", 56))
        self._button_fontsize = max(1, int(ui.get("button_fontsize", 14)))
        self._submit_button_fontsize = max(1, int(
            ui.get("submit_button_fontsize") or self._button_fontsize))
        # Extra multiplier on top of the automatic window-size scaling, so the
        # button size can be dialed up/down without changing the base sizes.
        self._button_scale = max(0.0, float(ui.get("button_scale", 1.0)))
        # Size of the content area (task + buttons + submit) as a percentage
        # [x%, y%] of the window, centered. Same `content_area_size` key and
        # behavior as every other test; 100 uses the maximally available size.
        self._content_area_size = ui.get("content_area_size", [100, 100])
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
        self._submit_hint = str(ui.get("submit_hint", "Press a number key (or click) to listen, select one, then press Enter to submit."))
        self._submit_button_text = str(ui.get("submit_button_text", "Submit choice"))
        # Trial progress indicator ("Trial X of Y"): shown when enabled AND the
        # screen dict carries a `progress` entry (injected by e.g. Staircase).
        self._show_progress = bool(ui.get("show_progress", False))
        self._progress_text = str(ui.get("progress_text", "Trial {current} of {total}"))
        self._progress_fontsize = max(1, int(
            ui.get("progress_fontsize") or self._hint_fontsize))
        self._progress_bar_color = str(ui.get("progress_bar_color", "#5cb874"))
        self._progress_trough_color = str(
            ui.get("progress_bar_background_color", "#dbe2f1"))

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
        """Resolve the on-screen task prompt for this trial.

        A ``task`` given directly in the ``screen`` dict carries the trial's
        prompt inline (e.g. from a single experiment config). When absent, a
        generic default is shown.
        """
        inline_task = self.screen.get("task")
        if inline_task:
            return str(inline_task)
        return "N-AFC task"

    def _scale_factor(self) -> float:
        """Factor for scaling buttons/fonts with the window size.

        ``1.0`` at the 600 px reference height (so the configured ``button_size``
        is unchanged for the default window) and grows proportionally with the
        window height, so controls don't look lost on large/fullscreen displays.
        Never shrinks below the configured sizes; ``button_scale`` tunes it.
        """
        reference_height = 600.0
        height = float(getattr(self, "_window_height", reference_height))
        return max(1.0, (height / reference_height) * self._button_scale)

    def _build_ui(self) -> None:
        """Build the central widget: task text, choice buttons, submit."""
        scale = self._scale_factor()
        button_size = round(self._button_size * scale)
        button_fontsize = max(1, round(self._button_fontsize * scale))
        submit_button_fontsize = max(1, round(self._submit_button_fontsize * scale))
        task_fontsize = max(1, round(self._task_fontsize * scale))
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

        # The stretches (here and below the submit button) center the choice
        # buttons + submit between the task text pinned on top and the footer
        # (hint + progress) pinned to the bottom.
        layout.addStretch(1)

        # choice buttons (labelled 1..n in the order shown to the participant)
        buttons_row = QWidget(self)
        br_layout = QHBoxLayout(buttons_row)
        br_layout.setContentsMargins(0, 12, 0, 12)
        br_layout.setSpacing(self._button_spacing)
        for idx, stim_id in enumerate(self._choices, start=1):
            btn = QPushButton(str(idx), self)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedSize(button_size, button_size)
            btn.setFont(QFont("Helvetica", button_fontsize))
            btn.clicked.connect(partial(self._on_choice_clicked, stim_id, btn))
            br_layout.addWidget(btn)
            self._choice_buttons.append(btn)
        self._apply_choice_button_styles()
        layout.addWidget(buttons_row, alignment=Qt.AlignmentFlag.AlignHCenter)

        # extra gap so the submit button sits clearly apart from the choice
        # buttons (on top of the general task_spacing)
        layout.addSpacing(self._task_spacing * 3)

        # submit button (disabled until a choice is selected)
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

        layout.addStretch(1)

        # Footer pinned to the bottom of the content area: the submit hint and
        # the trial progress ("Trial X of Y" text + bar) grouped tightly
        # together, clearly set apart from the controls above.
        footer = QWidget(content)
        footer_layout = QVBoxLayout(footer)
        footer_layout.setContentsMargins(0, 0, 0, 0)
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

        # Distribute the free window space around the content area 3:2 (the
        # block sits a little below the window center). The top share is a
        # fixed spacer so the content box's downward extension (progress_drop)
        # only moves its bottom edge, not the block itself.
        outer_layout.addSpacing(round(
            0.6 * max(0, self._window_height - 28 - area_h)))
        outer_layout.addWidget(content, alignment=Qt.AlignmentFlag.AlignHCenter)
        outer_layout.addStretch(1)
        self._host.setCentralWidget(container)

    # --------------------------------------------------------------- handlers
    def _on_choice_clicked(self, stim_id: Any, button: QPushButton, *_args: Any) -> None:
        """Select a choice and play its stimulus (final logging is on submit).

        The trailing ``*_args`` absorbs the ``checked`` boolean that Qt's
        ``clicked`` signal appends after the bound ``stim_id``/``button``.
        """
        # The participant took over: stop a running automatic run-through.
        self._cancel_autoplay()
        self._selected = stim_id
        self._selected_button = button
        self._listened.add(button)
        self._submit_button.setEnabled(True)
        self._apply_choice_button_styles()
        if self._debug:
            print(f"Selected: {stim_id!r} (type={type(stim_id).__name__})")
        # `single_replay` caps playback at two plays per interval (first listen
        # + one replay); further clicks/keys still select, but stay silent.
        if self._single_replay and self._play_counts.get(button, 0) >= 2:
            if self._debug:
                print(f"single_replay: no plays left for {stim_id!r}")
            return
        self._play_counts[button] = self._play_counts.get(button, 0) + 1
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

    # --------------------------------------------------------------- autoplay
    def _stimulus_duration(self, stim_id: Any) -> float:
        """Duration of a stimulus in seconds, for sequencing the autoplay.

        Read from the loaded ``SoundDevice`` signal; for other handlers (which
        expose no duration) a 1 s fallback keeps the run-through moving.
        """
        if isinstance(self.stimuli_handler, SoundDevice):
            stimuli = self.stimuli_handler.stimuli
            entry = stimuli.get(stim_id) or stimuli.get(str(stim_id))
            if entry is not None and "signal" in entry:
                signal = entry["signal"]
                return float(signal.n_samples) / float(signal.sampling_rate)
        return 1.0

    def _on_autoplay_timeout(self) -> None:
        """Play the next interval of the automatic run-through."""
        # Past the last interval: end the run-through.
        if self._autoplay_index >= len(self._choice_buttons):
            self._autoplay_button = None
            self._apply_choice_button_styles()
            # A looping handler would repeat the last interval forever.
            if isinstance(self.stimuli_handler, SoundDevice) and self.stimuli_handler.loop:
                try:
                    self.stimuli_handler.stop()
                except Exception:
                    pass
            # Reaction time is measured from when the participant can act on
            # what they heard, i.e. from the end of the run-through.
            self._start_time = time.time()
            return

        button = self._choice_buttons[self._autoplay_index]
        stim_id = self._choices[self._autoplay_index]
        self._autoplay_index += 1

        # An autoplayed interval counts as heard (gates submit) and as the
        # first play for `single_replay`.
        self._listened.add(button)
        self._play_counts[button] = self._play_counts.get(button, 0) + 1

        # Highlight the interval that is playing so the participant can map
        # what they hear to the buttons.
        self._autoplay_button = button
        self._apply_choice_button_styles()
        self._play_stimulus(stim_id)

        delay = self._stimulus_duration(stim_id) + self._autoplay_gap
        self._autoplay_timer.start(max(0, round(delay * 1000)))

    def _cancel_autoplay(self) -> None:
        """Stop the automatic run-through and clear its highlight (idempotent)."""
        self._autoplay_timer.stop()
        if self._autoplay_button is not None:
            self._autoplay_button = None
            self._apply_choice_button_styles()

    def _on_submit_clicked(self) -> None:
        """Finalize the currently selected choice and end the trial.

        Like the other whispy UIs, this only releases the blocking loop; the
        window stays open so the caller can present the next trial in the same
        window (no reload / fullscreen drop). The caller closes it explicitly
        via ``close()`` when the experiment is done.
        """
        if self._selected is None:
            return

        # Require the participant to have heard every interval at least once
        # (mirrors the MUSHRA "listen to each sound once" rule).
        if not self._debug and not self._all_listened():
            self._show_listen_hint()
            return

        # Reaction time is measured for the confirmed answer.
        self._rt = time.time() - self._start_time
        if self._debug:
            print(f"Submitted: {self._selected!r} (rt={self._rt:.3f}s)")

        self.unblock()

    def _all_listened(self) -> bool:
        """Whether every choice/interval has been played at least once."""
        return all(button in self._listened for button in self._choice_buttons)

    def _show_listen_hint(self) -> None:
        """Pop up a non-blocking reminder to listen to every interval first."""
        self._listen_info_window = InfoWindow(
            info_text="You have to listen to each interval at least once.",
            fontsize=self._task_fontsize,
            fontcolor=self._fontcolor,
            blocking=False,
        )

    # --------------------------------------------------------------- keyboard
    def _install_key_handling(self) -> None:
        """Route key presses to this trial via an app-level event filter.

        An application filter (rather than overriding ``keyPressEvent``) is used
        because a staircase reuses a single host window across trials: key
        events would otherwise be delivered to the first instance that owns the
        host, not the current trial. The filter sees every key press regardless
        of which widget has focus, and is removed again when the trial ends.
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
        """Handle number/Enter keys; defer everything else to Qt."""
        if event.type() == QEvent.Type.KeyPress and self._handle_key_press(event):
            return True
        return super().eventFilter(obj, event)

    def _handle_key_press(self, event: QEvent) -> bool:
        """Play interval ``1..n`` for number keys, submit on Enter/Return.

        Returns ``True`` when the key was consumed so Qt does not also act on
        it (e.g. activating a focused button).
        """
        key = event.key()

        # Enter / Return submit, reusing the click path so the same guards
        # apply (a selection must exist and every interval must be heard).
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._on_submit_clicked()
            return True

        # Number keys 1..9 (main row and keypad share these key codes) select
        # and play the interval shown with that label, exactly like a click.
        if Qt.Key.Key_1 <= key <= Qt.Key.Key_9:
            index = key - Qt.Key.Key_1
            if 0 <= index < len(self._choice_buttons):
                self._on_choice_clicked(self._choices[index], self._choice_buttons[index])
                return True

        return False

    def unblock(self) -> None:  # type: ignore[override]
        """Remove key handling for this trial, then release the blocking loop."""
        self._cancel_autoplay()
        self._remove_key_handling()
        super().unblock()

    def closeEvent(self, event: Any) -> None:  # type: ignore[override]
        """Ensure the key filter is removed when the window actually closes."""
        if self._allow_close:
            self._cancel_autoplay()
            self._remove_key_handling()
        super().closeEvent(event)

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
            elif btn is self._autoplay_button:
                # Currently autoplaying: shown in the hover color so the
                # participant can tell which interval they are hearing.
                btn.setStyleSheet(
                    f"QPushButton {{ background-color: {self._button_hover_bg};"
                    f" color: {self._button_fg};"
                    f" border: 1px solid {self._button_border};"
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