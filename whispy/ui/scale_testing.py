from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from functools import partial
from typing import Any, Dict, List, Optional

from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QColor, QFont, QPainter
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSlider,
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


@dataclass
class _QuestionSpec:
    """One rating scale shown below the play button (parsed from the config).

    ``interaction`` is ``"buttons"`` (one selectable button per integer step of
    ``scale_range``, Likert-style), ``"slider"`` (a continuous horizontal
    slider over the range) or ``"bipolar_slider"`` (a slider for a
    negative-to-positive range with the zero marked in the middle and no
    directional fill). ``labels`` is optional wording: two entries are
    endpoint labels (left/right of the scale); for buttons, one entry per step
    puts a small label under each button instead; a bipolar slider takes an
    optional THIRD entry as ``[left, center, right]`` (the center label sits
    under the zero tick).
    """
    qid: str
    prompt: str
    scale_type: str
    interaction: str
    minimum: int
    maximum: int
    labels: List[str] = field(default_factory=list)

    @property
    def values(self) -> List[int]:
        return list(range(self.minimum, self.maximum + 1))


class _ZeroTickBox(QWidget):
    """Hosts a bipolar slider and paints a thin zero tick behind its center.

    The tick is drawn in this container's ``paintEvent`` (i.e. underneath the
    slider child), so the groove crosses it and the handle covers it when it
    sits at zero.
    """

    def __init__(
        self,
        slider: QSlider,
        color: str,
        center_label: Optional[QLabel] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._slider = slider
        self._color = QColor(color)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addWidget(slider)
        if center_label is not None:
            layout.addWidget(center_label, alignment=Qt.AlignmentFlag.AlignHCenter)

    def paintEvent(self, event: Any) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.fillRect(
            self._slider.x() + self._slider.width() // 2 - 1,
            self._slider.y(), 2, self._slider.height(), self._color)
        painter.end()
        super().paintEvent(event)


class ScaleTest(_BaseUIWindow):
    """Rating-scale UI: one stimulus, several configurable scales below it.

    The participant plays a single stimulus (one play button) and rates it on
    every question stacked below — each question renders either a row of
    Likert-style buttons or a slider, as configured. Submitting requires the
    stimulus to have been played and every question to be answered.

    Notes
    -----
    - Mirrors :class:`whispy.ui.NAFC`: config-driven via
      ``configs/scale_testing.yml``, uses a
      :class:`~whispy.interfaces.StimuliHandler` to play stimuli by id, reuses
      a single host window across trials (``parent=``), supports keyboard
      control, and scales its controls with the window size.
    - Results are long-form like :class:`whispy.ui.DragAndDropMUSHRA`: one row
      per question per stimulus, accumulated across screens via
      ``get_results(results)``.

    Parameters
    ----------
    screen : dict, optional
        Trial description. Must carry ``stimulus`` (the stimulus id to rate).
        Optional metadata: ``task``, ``block``, ``section``, ``trial_id``,
        ``block_name``, ``section_name``, ``progress``, ``questions`` (a list
        of question dicts to use for this stimulus, overriding the config's
        global questions list).
    stimuli_handler : StimuliHandler, optional
        Handler used to play stimuli. If ``None``, ``SoundDevice()`` is used.
    scale_test_config : str or dict, optional
        The scale-testing config — a YAML path or an already-loaded dict (its
        ``ui:`` and ``questions:`` blocks are used). If ``None``,
        ``configs/scale_testing.yml`` from the package is used.
    blocking : bool, optional
        If ``True``, block until the trial is submitted.
    debug : bool, optional
        If ``True``, the window close button is enabled, debug prints are
        emitted and the listen/answer gates are relaxed.
    parent : QMainWindow, optional
        If provided, reuse that UI's host window instead of opening a new one
        (keeps a running experiment in the same window across trials).
    """

    def __init__(
        self,
        *,
        screen: Optional[Dict[str, Any]] = None,
        stimuli_handler: Optional[StimuliHandler] = None,
        scale_test_config: Optional[str] = None,
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
                "stimulus": 1,
                "trial_id": 0,
                "block_name": "Block 1",
                "section_name": "Section 1",
            }
        self.screen = screen
        self._stimulus = self.screen.get("stimulus")

        # stimuli handler
        self.stimuli_handler = stimuli_handler if stimuli_handler is not None else SoundDevice()

        # load UI config and resolve all settings once
        if scale_test_config is None:
            scale_test_config = os.path.join(
                FILEPATH, "..", "..", "configs", "scale_testing.yml")
        cfg = read_config(scale_test_config)
        cfg = cfg if isinstance(cfg, dict) else {}
        # The global theme from configs/design.yml is the base; the per-UI
        # `ui:` block only overrides wording, window size, or individual colors.
        self._ui_cfg = load_design(cfg.get("ui"))
        self._screen_setting = self._ui_cfg.get("screen")
        self._resolve_config()
        # Parse questions: prioritize per-stimulus questions passed on the screen,
        # fall back to the config's global questions list.
        screen_questions = self.screen.get("questions")
        if screen_questions is not None:
            self._questions = self._parse_questions(screen_questions)
        else:
            self._questions = self._parse_questions(cfg.get("questions"))

        # answer / playback state
        self._answers: Dict[str, Optional[int]] = {q.qid: None for q in self._questions}
        # per-question button rows: qid -> list of (value, button)
        self._scale_buttons: Dict[str, List[tuple]] = {}
        self._sliders: Dict[str, QSlider] = {}
        self._played = False
        self._rt: Optional[float] = None
        self._hint_info_window: Optional[InfoWindow] = None
        # Whether this instance has an app-level key event filter installed.
        self._key_filter_installed = False

        # In non-debug standalone mode, block the native close button.
        if parent is None and not self._debug:
            self.disable_close_button()

        # Resolve the target window size BEFORE building the UI so buttons and
        # fonts can scale to it (same rule as NAFC/ABX).
        window_size = self._ui_cfg.get("window_size", [1000, 700])
        self._window_width, self._window_height, self._fullscreen = self._resolve_window_size(
            window_size, fallback=(1000, 700), minimum_size=(400, 300))

        self._build_ui()

        # Keyboard support: Space/P plays the stimulus, Enter submits. The
        # filter belongs to THIS instance so it always acts on the current
        # trial's state even when one host window is reused across trials.
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
        self._question_fontsize = max(1, int(ui.get("question_fontsize", 13)))
        # Small font for the scale wording (endpoint/per-step labels).
        self._scale_label_fontsize = max(1, int(ui.get("scale_label_fontsize", 10)))
        # Smaller font for the keyboard hint below the submit button.
        self._hint_fontsize = max(1, int(ui.get("hint_fontsize", 11)))
        self._submit_hint_fontsize = max(1, int(
            ui.get("submit_hint_fontsize") or self._hint_fontsize))
        self._task_spacing = int(ui.get("task_spacing", 12))
        # Extra vertical gap (px) between stacked questions.
        self._question_spacing = int(ui.get("question_spacing", 18))
        # Gap (px) between a question's prompt text and its scale (the answer
        # widget row) below.
        self._prompt_scale_spacing = int(ui.get("prompt_scale_spacing", 6))
        # Maximum height of the scrollable questions area as a percentage of
        # the WINDOW height. The area never grows beyond the questions'
        # natural height; this caps it further, so past the cap the questions
        # scroll. 100 (the default) = no extra cap.
        self._questions_area_height = max(5.0, min(100.0, float(
            ui.get("questions_area_height", 100))))
        # How the question PROMPTS sit inside the content area: "left" or
        # "center" (anything else falls back to "center"). The scale rows
        # (buttons/slider) below them are always centered.
        self._question_alignment = str(
            ui.get("question_alignment", "center")).strip().lower()
        # Thin horizontal line between the stacked questions; its color
        # defaults to the shared button-border tone from the palette.
        self._show_question_separator = bool(
            ui.get("show_question_separator", False))
        self._question_separator_color = str(ui.get(
            "question_separator_color",
            ui.get("button_border_color", "#b9c4dd")))
        # Gap (px) between the submit button and the hint below it. Defaults
        # to task_spacing (the layout's base item spacing), which is also the
        # effective minimum.
        self._submit_hint_spacing = int(
            ui.get("submit_hint_spacing", self._task_spacing))
        # Gap (px) between the task text and the play button below it. Same
        # rule: defaults to task_spacing, which is also the effective minimum.
        self._play_button_spacing = int(
            ui.get("play_button_spacing", self._task_spacing))
        # Share (0..1) of the free vertical window space placed ABOVE the
        # content area: 0 = flush at the top, 0.5 = centered, 1 = at the
        # bottom. Values outside 0..1 are clamped.
        self._content_top_share = min(1.0, max(0.0, float(
            ui.get("content_top_share", 0.6))))
        # Side length of one Likert-style scale button (smaller than the NAFC
        # interval buttons; there can be many per row).
        self._scale_button_size = int(ui.get("scale_button_size", 40))
        self._button_fontsize = max(1, int(ui.get("button_fontsize", 14)))
        self._submit_button_fontsize = max(1, int(
            ui.get("submit_button_fontsize") or self._button_fontsize))
        self._play_button_text = str(ui.get("play_button_text", "► Play"))
        self._play_button_fontsize = max(1, int(
            ui.get("play_button_fontsize") or self._button_fontsize))
        # Extra multiplier on top of the automatic window-size scaling.
        self._button_scale = max(0.0, float(ui.get("button_scale", 1.0)))
        # Size of the content area (task + play button + questions + submit)
        # as a percentage [x%, y%] of the window, centered. Same key/behavior
        # as every other test.
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
        # Slider look, driven from the shared palette by default so the theme
        # stays in design.yml; individually overridable here.
        self._slider_groove_color = str(ui.get(
            "slider_groove_color",
            ui.get("progress_bar_background_color", "#dbe2f1")))
        self._slider_fill_color = str(ui.get(
            "slider_fill_color", ui.get("progress_bar_color", "#5cb874")))
        self._slider_handle_color = str(ui.get(
            "slider_handle_color", self._button_selected_bg))
        # Zero tick of bipolar sliders; the border tone is visible against
        # the (lighter) groove.
        self._slider_tick_color = str(ui.get(
            "slider_tick_color", self._button_border))
        self._submit_hint = str(ui.get(
            "submit_hint",
            "Press Space (or click Play) to listen, rate every scale, then press Enter to submit."))
        self._submit_button_text = str(ui.get("submit_button_text", "Submit ratings"))
        # Trial progress indicator ("Trial X of Y"): shown when enabled AND
        # the screen dict carries a `progress` entry.
        self._show_progress = bool(ui.get("show_progress", False))
        self._progress_text = str(ui.get("progress_text", "Trial {current} of {total}"))
        self._progress_fontsize = max(1, int(
            ui.get("progress_fontsize") or self._hint_fontsize))
        self._progress_bar_color = str(ui.get("progress_bar_color", "#5cb874"))
        self._progress_trough_color = str(
            ui.get("progress_bar_background_color", "#dbe2f1"))

    def _parse_questions(self, raw: Any) -> List[_QuestionSpec]:
        """Parse the config's ``questions:`` list into failsafe specs.

        Every entry is tolerated: missing keys fall back to a 5-point button
        scale, a broken ``scale_range`` to ``[1, 5]``, an unknown
        ``interaction_method`` to ``"buttons"`` — so a misconfigured question
        can never prevent the experiment window from opening.
        """
        specs: List[_QuestionSpec] = []
        for index, question in enumerate(raw or [], start=1):
            if not isinstance(question, dict):
                continue
            interaction = str(question.get("interaction_method", "buttons")).lower()
            if interaction not in ("buttons", "slider", "bipolar_slider"):
                interaction = "buttons"
            default_range = [-5, 5] if interaction == "bipolar_slider" else [1, 5]
            scale_range = question.get("scale_range", default_range)
            try:
                minimum, maximum = int(scale_range[0]), int(scale_range[1])
            except (TypeError, ValueError, IndexError):
                minimum, maximum = default_range
            if maximum < minimum:
                minimum, maximum = maximum, minimum
            if maximum == minimum:
                minimum, maximum = default_range
            labels = question.get("labels") or []
            if not isinstance(labels, list):
                labels = []
            default_scale_type = {
                "buttons": "likert",
                "slider": "continuous",
                "bipolar_slider": "bipolar",
            }[interaction]
            specs.append(_QuestionSpec(
                qid=str(question.get("id", f"q{index}")),
                prompt=str(question.get("prompt", f"Question {index}")),
                scale_type=str(question.get("scale_type", default_scale_type)),
                interaction=interaction,
                minimum=minimum,
                maximum=maximum,
                labels=[str(label) for label in labels],
            ))
        if not specs:
            # Failsafe default so the window never opens without any scale.
            specs.append(_QuestionSpec(
                qid="q1", prompt="Rate the stimulus", scale_type="likert",
                interaction="buttons", minimum=1, maximum=5))
        return specs

    def _resolve_task_text(self) -> str:
        """Resolve the on-screen task prompt. A ``task`` on the screen wins."""
        inline_task = self.screen.get("task")
        if inline_task:
            return str(inline_task)
        return "Listen to the sound and rate it on every scale."

    def _scale_factor(self) -> float:
        """Factor for scaling buttons/fonts with the window size.

        ``1.0`` at the 600 px reference height and growing proportionally with
        the window height; never shrinks below the configured sizes.
        ``button_scale`` tunes it. (Same rule as :class:`whispy.ui.NAFC`.)
        """
        reference_height = 600.0
        height = float(getattr(self, "_window_height", reference_height))
        return max(1.0, (height / reference_height) * self._button_scale)

    # --------------------------------------------------------------------- UI
    def _build_ui(self) -> None:
        """Build the central widget: task, play button, questions, submit."""
        scale = self._scale_factor()
        task_fontsize = max(1, round(self._task_fontsize * scale))
        play_button_fontsize = max(1, round(self._play_button_fontsize * scale))
        submit_button_fontsize = max(1, round(self._submit_button_fontsize * scale))
        submit_hint_fontsize = max(1, round(self._submit_hint_fontsize * scale))

        container = QWidget(self)
        container.setStyleSheet(f"background-color: {self._background_color};")
        outer_layout = QVBoxLayout(container)
        outer_layout.setContentsMargins(14, 14, 14, 14)

        # The actual content lives in a fixed-size widget sized to a percentage
        # of the window (`content_area_size`) and centered, exactly like the
        # other listening tests.
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

        # task prompt (markdown), pinned to the top of the content area. The
        # fixed full-content width makes the word-wrapped height computable,
        # so the text is never clipped when the stretches compact the layout.
        task_label = QLabel(format_markdown(self._resolve_task_text()), self)
        task_label.setTextFormat(Qt.TextFormat.MarkdownText)
        task_label.setWordWrap(True)
        task_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        task_label.setStyleSheet(f"color: {self._fontcolor};")
        task_label.setFont(QFont("Helvetica", task_fontsize))
        task_label.setFixedWidth(area_w)
        layout.addWidget(task_label, alignment=Qt.AlignmentFlag.AlignHCenter)

        # play button for the single stimulus of this screen, pinned to the
        # top right below the task text. The spacer tops up the layout's base
        # task_spacing to the configured play_button_spacing (only added when
        # needed: even a zero-height spacer would widen the gap by one extra
        # base spacing).
        extra_play_spacing = self._play_button_spacing - self._task_spacing
        if extra_play_spacing > 0:
            layout.addSpacing(extra_play_spacing)
        self._play_button = QPushButton(self._play_button_text, self)
        self._play_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._play_button.setFont(QFont("Helvetica", play_button_fontsize))
        self._play_button.setStyleSheet(
            f"QPushButton {{ background-color: {self._button_bg}; color: {self._button_fg};"
            f" border: 1px solid {self._button_border}; border-radius: {self._button_radius};"
            f" padding: 10px 32px; }}"
            f"QPushButton:hover {{ background-color: {self._button_hover_bg}; }}"
        )
        self._play_button.clicked.connect(self._on_play_clicked)
        layout.addWidget(self._play_button, alignment=Qt.AlignmentFlag.AlignHCenter)

        # The stretches (here and below the questions) center the question
        # stack between the task text + play button pinned on top and the
        # submit button + footer (hint + progress) pinned to the bottom.
        layout.addStretch(1)

        # The questions, stacked vertically in config order (optionally
        # separated by a thin line) inside a scroll area: when they fit, the
        # area takes exactly their natural height (no bar, nothing moves);
        # when there are too many, it shrinks with the layout and a scrollbar
        # appears on the right. The question column is built slightly narrower
        # than the content area so the bar never steals width from it.
        inner_w = area_w - 14
        questions_widget = QWidget()
        questions_layout = QVBoxLayout(questions_widget)
        questions_layout.setContentsMargins(0, 0, 0, 0)
        questions_layout.setSpacing(self._task_spacing)
        for spec in self._questions:
            questions_layout.addWidget(
                self._build_question(spec, inner_w, scale),
                alignment=Qt.AlignmentFlag.AlignHCenter)
            if spec is not self._questions[-1]:
                if self._show_question_separator:
                    separator = QWidget(questions_widget)
                    separator.setFixedSize(inner_w, 1)
                    separator.setStyleSheet(
                        f"background-color: {self._question_separator_color};")
                    questions_layout.addSpacing(self._question_spacing // 2)
                    questions_layout.addWidget(
                        separator, alignment=Qt.AlignmentFlag.AlignHCenter)
                    questions_layout.addSpacing(self._question_spacing // 2)
                else:
                    questions_layout.addSpacing(self._question_spacing)

        scroll = QScrollArea(content)
        scroll.setWidget(questions_widget)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        # transparent, so the window background shows through
        scroll.viewport().setAutoFillBackground(False)
        questions_widget.setAutoFillBackground(False)
        scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            f"QScrollBar:vertical {{ background: {self._progress_trough_color};"
            f" width: 8px; border-radius: 4px; margin: 0; }}"
            f"QScrollBar::handle:vertical {{ background: {self._button_border};"
            f" border-radius: 4px; min-height: 30px; }}"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical"
            " { height: 0; }"
            "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical"
            " { background: transparent; }"
        )
        # Grows to at most the questions' natural height (the big stretch
        # factor claims free space before the surrounding stretches), capped
        # at questions_area_height percent of the window height, and can
        # shrink further when the window is too small — whenever the questions
        # exceed the resulting height, the bar shows.
        natural_height = questions_widget.sizeHint().height()
        height_cap = round(
            self._window_height * self._questions_area_height / 100)
        scroll.setMaximumHeight(min(natural_height, height_cap))
        scroll.setMinimumHeight(min(120, natural_height, height_cap))
        layout.addWidget(scroll, 100)

        layout.addStretch(1)

        # submit button (disabled until every question is answered), pinned to
        # the bottom of the content area, right above the hint
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

        # submit hint (markdown), spanning the full content-area width
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

    def _build_question(self, spec: _QuestionSpec, area_w: int, scale: float) -> QWidget:
        """Build one stacked question: prompt label + scale widget below."""
        question_fontsize = max(1, round(self._question_fontsize * scale))

        widget = QWidget(self)
        q_layout = QVBoxLayout(widget)
        q_layout.setContentsMargins(0, 0, 0, 0)
        # gap between the prompt and the scale row (prompt_scale_spacing)
        q_layout.setSpacing(max(0, self._prompt_scale_spacing))

        # `question_alignment` moves the prompt TEXT (left or centered); the
        # scale row below it is always centered in the content area.
        prompt = QLabel(format_markdown(spec.prompt), widget)
        prompt.setTextFormat(Qt.TextFormat.MarkdownText)
        prompt.setWordWrap(True)
        prompt.setAlignment(Qt.AlignmentFlag.AlignLeft
                            if self._question_alignment == "left"
                            else Qt.AlignmentFlag.AlignCenter)
        prompt.setStyleSheet(f"color: {self._fontcolor};")
        prompt.setFont(QFont("Helvetica", question_fontsize))
        # Fixed full-content width (like the task label) so the word-wrapped
        # height is computable and the text is never clipped.
        prompt.setFixedWidth(area_w)
        q_layout.addWidget(prompt, alignment=Qt.AlignmentFlag.AlignHCenter)

        if spec.interaction in ("slider", "bipolar_slider"):
            row = self._build_slider_row(spec, area_w, scale)
        else:
            row = self._build_button_row(spec, area_w, scale)
        q_layout.addWidget(row, alignment=Qt.AlignmentFlag.AlignHCenter)
        return widget

    def _build_button_row(self, spec: _QuestionSpec, area_w: int, scale: float) -> QWidget:
        """One selectable button per integer step, with optional labels."""
        button_size = round(self._scale_button_size * scale)
        button_fontsize = max(1, round(self._button_fontsize * scale))
        label_fontsize = max(1, round(self._scale_label_fontsize * scale))
        values = spec.values
        # One label per step goes under each button; exactly two labels (that
        # don't match the step count) are endpoints left/right of the row.
        per_step = len(spec.labels) == len(values)
        endpoints = not per_step and len(spec.labels) == 2

        row = QWidget(self)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(self._button_spacing)

        left_label = right_label = None
        if endpoints:
            left_label = self._make_scale_label(spec.labels[0], label_fontsize)
            right_label = self._make_scale_label(spec.labels[1], label_fontsize)

        # The whole row must fit the content width: shrink the buttons below
        # the configured size when many steps (and the endpoint labels) would
        # otherwise overflow the area — an overflowing row would get clipped.
        total_spacing = self._button_spacing * (len(values) - 1)
        reserved = 0
        if endpoints:
            reserved = (left_label.sizeHint().width()
                        + right_label.sizeHint().width()
                        + 4 * self._button_spacing)
        available = max(3 * len(values), area_w - reserved)
        button_size = max(16, min(
            button_size, (available - total_spacing) // len(values)))

        # With per-step labels every button sits in a cell of ONE uniform
        # width (the widest wording), so the buttons are equally spaced no
        # matter how long the individual labels are. The width is capped at an
        # equal share of the content area so the row always fits; longer
        # wording word-wraps inside its cell instead of widening it.
        step_labels: List[QLabel] = []
        cell_width = button_size
        if per_step:
            step_labels = [
                self._make_scale_label(text, label_fontsize)
                for text in spec.labels]
            cell_width = max(
                [button_size] + [lbl.sizeHint().width() for lbl in step_labels])
            cell_width = min(cell_width, max(
                button_size, (area_w - total_spacing) // len(values)))
            for lbl in step_labels:
                lbl.setWordWrap(True)
                lbl.setFixedWidth(cell_width)

        if endpoints:
            row_layout.addWidget(left_label)
            row_layout.addSpacing(self._button_spacing)

        buttons: List[tuple] = []
        for step_index, value in enumerate(values):
            btn = QPushButton(str(value), row)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedSize(button_size, button_size)
            btn.setFont(QFont("Helvetica", button_fontsize))
            btn.clicked.connect(partial(self._on_scale_button_clicked, spec, value))
            buttons.append((value, btn))
            if per_step:
                # button with its wording underneath, centered in the cell
                cell = QWidget(row)
                cell.setFixedWidth(cell_width)
                cell_layout = QVBoxLayout(cell)
                cell_layout.setContentsMargins(0, 0, 0, 0)
                cell_layout.setSpacing(2)
                cell_layout.addWidget(btn, alignment=Qt.AlignmentFlag.AlignHCenter)
                cell_layout.addWidget(
                    step_labels[step_index],
                    alignment=Qt.AlignmentFlag.AlignHCenter)
                row_layout.addWidget(cell)
            else:
                row_layout.addWidget(btn)

        if endpoints:
            row_layout.addSpacing(self._button_spacing)
            row_layout.addWidget(right_label)

        self._scale_buttons[spec.qid] = buttons
        self._apply_scale_button_styles(spec.qid)
        return row

    def _build_slider_row(self, spec: _QuestionSpec, area_w: int, scale: float) -> QWidget:
        """A horizontal slider over the range, with optional endpoint labels.

        For ``bipolar_slider`` questions the directional fill is dropped (a
        left-anchored fill reads wrong on a negative-to-positive scale) and a
        thin zero tick marks the center; three ``labels`` are then
        ``[left, center, right]``, the center one sitting under the tick.
        """
        label_fontsize = max(1, round(self._scale_label_fontsize * scale))
        bipolar = spec.interaction == "bipolar_slider"

        left_text = center_text = right_text = None
        if bipolar and len(spec.labels) >= 3:
            left_text, center_text, right_text = spec.labels[:3]
        elif len(spec.labels) >= 2:
            left_text, right_text = spec.labels[0], spec.labels[1]
        elif len(spec.labels) == 1:
            left_text = spec.labels[0]

        row = QWidget(self)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(self._button_spacing * 2)

        left_label = (self._make_scale_label(left_text, label_fontsize)
                      if left_text is not None else None)
        right_label = (self._make_scale_label(right_text, label_fontsize)
                       if right_text is not None else None)
        if left_label is not None:
            row_layout.addWidget(left_label)

        slider = QSlider(Qt.Orientation.Horizontal, row)
        slider.setRange(spec.minimum, spec.maximum)
        # Start centered; the initial value does NOT count as an answer — the
        # participant must touch the slider (see the signal connections below).
        slider.setValue(spec.minimum + (spec.maximum - spec.minimum) // 2)
        # The row (endpoint labels + slider) must fit the content width, so
        # the slider takes at most what the measured labels leave over.
        reserved = sum(
            lbl.sizeHint().width() + self._button_spacing * 2
            for lbl in (left_label, right_label) if lbl is not None)
        slider.setFixedWidth(max(120, min(area_w - reserved, round(420 * scale))))
        handle_size = round(18 * scale)
        groove_height = max(4, round(6 * scale))
        # No fill for bipolar scales: the sub-page keeps the groove color.
        fill_color = self._slider_groove_color if bipolar else self._slider_fill_color
        slider.setStyleSheet(
            f"QSlider::groove:horizontal {{ height: {groove_height}px;"
            f" background: {self._slider_groove_color};"
            f" border-radius: {groove_height // 2}px; }}"
            f"QSlider::sub-page:horizontal {{ background: {fill_color};"
            f" border-radius: {groove_height // 2}px; }}"
            f"QSlider::handle:horizontal {{ background: {self._slider_handle_color};"
            f" width: {handle_size}px;"
            f" margin: -{(handle_size - groove_height) // 2}px 0;"
            f" border-radius: {handle_size // 2}px; }}"
        )
        # Both signals mark the question as answered: valueChanged covers
        # dragging/keyboard/groove clicks, sliderPressed covers a click exactly
        # on the handle position (no value change). The initial setValue above
        # happens before these connections, so it never counts.
        slider.valueChanged.connect(partial(self._on_slider_changed, spec))
        slider.sliderPressed.connect(
            lambda spec=spec, slider=slider: self._on_slider_changed(spec, slider.value()))
        self._sliders[spec.qid] = slider

        if bipolar:
            center_label = (self._make_scale_label(center_text, label_fontsize)
                            if center_text is not None else None)
            row_layout.addWidget(_ZeroTickBox(
                slider, self._slider_tick_color, center_label, row))
        else:
            row_layout.addWidget(slider)

        if right_label is not None:
            row_layout.addWidget(right_label)

        return row

    def _make_scale_label(self, text: str, fontsize: int) -> QLabel:
        label = QLabel(str(text), self)
        label.setStyleSheet(f"color: {self._fontcolor};")
        label.setFont(QFont("Helvetica", fontsize))
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return label

    # --------------------------------------------------------------- handlers
    def _on_play_clicked(self, *_args: Any) -> None:
        """Play the stimulus of this screen (gates submit)."""
        self._played = True
        self._update_submit_enabled()
        if self._debug:
            print(f"Playing: {self._stimulus!r}")
        self._play_stimulus(self._stimulus)

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

    def _on_scale_button_clicked(self, spec: _QuestionSpec, value: int, *_args: Any) -> None:
        """Record a Likert-style answer and highlight the chosen button."""
        self._answers[spec.qid] = int(value)
        self._apply_scale_button_styles(spec.qid)
        self._update_submit_enabled()
        if self._debug:
            print(f"Answered {spec.qid}: {value}")

    def _on_slider_changed(self, spec: _QuestionSpec, value: int) -> None:
        """Record a slider answer (any interaction counts as answered)."""
        self._answers[spec.qid] = int(value)
        self._update_submit_enabled()

    def _update_submit_enabled(self) -> None:
        """Enable submit once the stimulus was played and all scales answered."""
        self._submit_button.setEnabled(self._debug or self._all_complete())

    def _all_complete(self) -> bool:
        return self._played and all(
            answer is not None for answer in self._answers.values())

    def _on_submit_clicked(self) -> None:
        """Finalize the ratings and end the trial.

        Like the other whispy UIs, this only releases the blocking loop; the
        window stays open so the caller can present the next trial in the same
        window. The caller closes it explicitly via ``close()`` when the
        experiment is done.
        """
        if not self._debug and not self._all_complete():
            self._show_complete_hint()
            return

        self._rt = time.time() - self._start_time
        if self._debug:
            print(f"Submitted: {self._answers} (rt={self._rt:.3f}s)")

        self.unblock()

    def _show_complete_hint(self) -> None:
        """Pop up a non-blocking reminder to listen and answer everything."""
        if not self._played:
            text = "You have to listen to the sound at least once."
        else:
            text = "Please answer every scale before submitting."
        self._hint_info_window = InfoWindow(
            info_text=text,
            fontsize=self._task_fontsize,
            fontcolor=self._fontcolor,
            blocking=False,
        )

    # --------------------------------------------------------------- keyboard
    def _install_key_handling(self) -> None:
        """Route key presses to this trial via an app-level event filter.

        Same pattern as NAFC/ABX: the filter belongs to this instance so key
        events act on the current trial even though one host window is reused
        across trials; it is removed again when the trial ends.
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
        """Handle Space/P/Enter keys; defer everything else to Qt."""
        if event.type() == QEvent.Type.KeyPress and self._handle_key_press(event):
            return True
        return super().eventFilter(obj, event)

    def _handle_key_press(self, event: QEvent) -> bool:
        """Space/P plays the stimulus, Enter submits.

        Returns ``True`` when the key was consumed so Qt does not also act on
        it (e.g. activating a focused button). Arrow keys are left to Qt so a
        focused slider keeps its native keyboard control.
        """
        key = event.key()

        # Enter / Return submit, reusing the click path so the same guards
        # apply (stimulus heard and every scale answered).
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._on_submit_clicked()
            return True

        if key in (Qt.Key.Key_Space, Qt.Key.Key_P):
            self._on_play_clicked()
            return True

        return False

    def unblock(self) -> None:  # type: ignore[override]
        """Stop playback and key handling for this trial, then release the loop."""
        self._stop_stimuli_playback()
        self._remove_key_handling()
        super().unblock()

    def closeEvent(self, event: Any) -> None:  # type: ignore[override]
        """Ensure the key filter is removed when the window actually closes."""
        if self._allow_close:
            self._remove_key_handling()
        super().closeEvent(event)

    def _apply_scale_button_styles(self, qid: str) -> None:
        """Apply default/selected color styles to one question's buttons."""
        selected_value = self._answers.get(qid)
        for value, btn in self._scale_buttons.get(qid, []):
            if selected_value is not None and value == selected_value:
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
    def get_results(self, results: Optional[pd.DataFrame] = None) -> pd.DataFrame:
        """Return the ratings in long form (one row per question).

        Columns:
        - block, section, trial_id, block_name, section_name
        - stimulus : the stimulus id rated on this screen
        - question, prompt : the question's id and wording
        - scale_type, interaction_method, scale_min, scale_max
        - answer : the chosen value (int, or None in debug when skipped)
        - rt : seconds from screen shown to submit (same for all rows)

        Pass the running DataFrame back in to accumulate results across
        screens (same pattern as ``DragAndDropMUSHRA.get_results``).
        """
        meta = {
            k: self.screen.get(k)
            for k in ["block", "section", "trial_id", "block_name", "section_name"]
        }
        columns = list(meta.keys()) + [
            "stimulus", "question", "prompt", "scale_type",
            "interaction_method", "scale_min", "scale_max", "answer", "rt"]

        if results is None:
            results = pd.DataFrame(columns=columns)

        rt = float(self._rt) if self._rt is not None else None
        for spec in self._questions:
            row = dict(meta)
            row.update({
                "stimulus": self._stimulus,
                "question": spec.qid,
                "prompt": spec.prompt,
                "scale_type": spec.scale_type,
                "interaction_method": spec.interaction,
                "scale_min": spec.minimum,
                "scale_max": spec.maximum,
                "answer": self._answers.get(spec.qid),
                "rt": rt,
            })
            results.loc[len(results)] = row

        return results
