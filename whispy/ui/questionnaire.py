from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Optional

import pandas
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QDoubleValidator, QFont, QFontMetrics
from PyQt6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from whispy.utils import read_config
from whispy.utils._utils import format_markdown

from .base import _BaseUIWindow
from .info_window import InfoWindow

# Directory containing this file.
# Required for loading the default questionnaire config.
FILEPATH = os.path.dirname(os.path.abspath(__file__))


@dataclass
class _QuestionEntry:
    section: str
    widget: _BaseQuestionWidget


class Questionnaire(_BaseUIWindow):
    """Config-driven questionnaire UI.

    Parameters
    ----------
    questionnaire : str or None, optional
        Path to the questionnaire YAML file. If ``None``, the default
        ``configs/questionnaire.yml`` file is used.
    blocking : bool, optional
        If ``True``, block execution until the window is closed.
    debug : bool, optional
        If ``False``, the window close button is disabled and the questionnaire
        can only be closed via Continue after all required answers are
        provided.
    """

    def __init__(self,
                 *,
                 questionnaire: Optional[str] = None,
                 blocking: Optional[bool] = True,
                 debug: Optional[bool] = False,
                 parent: Optional[QMainWindow] = None) -> None:
        super().__init__(blocking=bool(blocking), debug=bool(debug), parent=parent)

        if questionnaire is None:
            questionnaire = os.path.join(
                FILEPATH, "..", "..", "configs", "questionnaire.yml")

        cfg = read_config(questionnaire)
        if not isinstance(cfg, dict):
            raise ValueError("Questionnaire config must be a mapping.")

        self._ui_cfg = cfg.get("ui", {})
        self._questionnaire_cfg = cfg.get("questionnaire", [])
        if not isinstance(self._questionnaire_cfg, list):
            raise ValueError("The 'questionnaire' key must be a list.")

        self._continue_info_window: Optional[InfoWindow] = None

        if parent is None:
            self.setWindowTitle("")
            if not debug:
                self.disable_close_button()

        container = QWidget()
        container.setStyleSheet(
            f"background-color: {self._ui_cfg['window_background_color']};"
        )
        layout = QVBoxLayout(container)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        self.main = _QuestionnaireMain(self._questionnaire_cfg, self._ui_cfg, parent=container)
        self.main.continueClicked.connect(self._on_continue_clicked)
        layout.addWidget(self.main, alignment=Qt.AlignmentFlag.AlignHCenter)

        self._host.setCentralWidget(container)

        window_width, window_height, fullscreen = self._apply_window_size()
        if parent is None:
            self._show_host_window(
                width=window_width,
                height=window_height,
                fullscreen=fullscreen,
            )

        if blocking:
            self.wait_until_closed()

    def _apply_window_size(self) -> tuple[int, int, bool]:
        window_size = self._ui_cfg["window_size"]
        width, height, fullscreen = self._resolve_window_size(
            window_size,
            fallback=(1000, 700),
            minimum_size=(400, 300),
        )
        self._apply_questionnaire_size(width, height)
        return width, height, fullscreen

    def _apply_questionnaire_size(self, window_width: int, window_height: int) -> None:
        questionnaire_size = self._ui_cfg["questionnaire_size"]
        if not isinstance(questionnaire_size, list) or len(questionnaire_size) != 2:
            return

        x_pct = max(0.0, min(100.0, float(questionnaire_size[0]))) / 100.0
        y_pct = max(0.0, min(100.0, float(questionnaire_size[1]))) / 100.0

        min_w, min_h = 320, 240
        max_w = max(min_w, int(window_width) - 28)
        max_h = max(min_h, int(window_height) - 28)

        target_w = max(min_w, min(max_w, int(window_width * x_pct)))
        target_h = max(min_h, min(max_h, int(window_height * y_pct)))
        self.main.setFixedSize(target_w, target_h)

    def _on_continue_clicked(self) -> None:

        # check if questionnaire is complete
        missing = self.main.get_missing_required_labels()

        if missing and not self._debug:
            font_size = max(1, int(self._ui_cfg["question_fontsize"]))
            font_color = str(self._ui_cfg["fontcolor"])
            preview = "\n".join(f"- {label}" for label in missing[:8])
            if len(missing) > 8:
                preview += f"\n- ... and {len(missing) - 8} more"
            self._continue_info_window = InfoWindow(
                info_text=(
                    "Please answer all required questions before continuing.\n"
                    f"Missing answers:\n{preview}"
                ),
                fontsize=font_size,
                fontcolor=font_color,
                blocking=False,
            )
            return

        # Quit the blocking loop so the caller regains control.
        # The window stays open; caller must call .close() explicitly.
        self.unblock()

    def get_results(self) -> pandas.DataFrame:
        """Return the questionnaire responses as a data frame.

        Returns
        -------
        pandas.DataFrame
            A data frame with one row per question containing the section,
            question identifier, prompt, type, required flag, and answer.
        """
        return self.main.collect_results()

class _QuestionnaireMain(QWidget):
    continueClicked = pyqtSignal()

    def __init__(self, questionnaire_cfg: list[dict[str, Any]], ui_cfg: dict[str, Any], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        self._ui_cfg = ui_cfg
        self._entries: list[_QuestionEntry] = []

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(10)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)

        content = QWidget(scroll)
        form_layout = QVBoxLayout(content)
        form_layout.setContentsMargins(8, 8, 8, 8)
        form_layout.setSpacing(max(2, int(ui_cfg["question_spacing"])))

        section_font_size = max(1, int(ui_cfg["section_fontsize"]))
        question_font_size = max(1, int(ui_cfg["question_fontsize"]))
        font_color = QColor(str(ui_cfg["fontcolor"])).name()
        response_color = QColor(str(ui_cfg["response_boxes_color"])).name()
        enumerate_enabled = bool(ui_cfg["enumerate"]) if "enumerate" in ui_cfg else False

        section_font = QFont("Helvetica", section_font_size, QFont.Weight.Bold)

        for section_idx, section_cfg in enumerate(questionnaire_cfg, start=1):
            if not isinstance(section_cfg, dict):
                continue

            section_id = str(section_cfg.get("section", ""))
            section_prompt = str(section_cfg.get("prompt", section_id))
            section_label_text = f"{section_idx}. {section_prompt}" if enumerate_enabled else section_prompt
            questions = section_cfg.get("questions", [])
            if not isinstance(questions, list):
                continue

            section_label = QLabel(section_label_text, content)
            section_label.setFont(section_font)
            section_label.setWordWrap(True)
            section_label.setTextFormat(Qt.TextFormat.MarkdownText)
            section_label.setText(format_markdown(section_label_text))
            section_label.setStyleSheet(f"color: {font_color};")
            form_layout.addWidget(section_label)

            for question_idx, question_cfg in enumerate(questions, start=1):
                if not isinstance(question_cfg, dict):
                    continue

                question_cfg_for_widget = dict(question_cfg)
                prompt_text = str(question_cfg_for_widget.get("prompt", ""))
                if enumerate_enabled:
                    prompt_text = f"{section_idx}.{question_idx} {prompt_text}"
                question_cfg_for_widget["prompt"] = prompt_text

                widget = _create_question_widget(
                    question_cfg_for_widget,
                    ui_cfg,
                    question_font_size,
                    font_color,
                    response_color,
                    content,
                )
                form_layout.addWidget(widget)
                self._entries.append(_QuestionEntry(section=section_id, widget=widget))

            form_layout.addSpacing(max(0, int(ui_cfg["section_spacing"])))

        form_layout.addStretch(1)

        scroll.setWidget(content)
        root_layout.addWidget(scroll)

        controls = QHBoxLayout()
        controls.addStretch(1)
        self.continue_button = QPushButton("Continue", self)
        self.continue_button.clicked.connect(self.continueClicked)
        controls.addWidget(self.continue_button)
        root_layout.addLayout(controls)

    def get_missing_required_labels(self) -> list[str]:
        missing: list[str] = []
        for entry in self._entries:
            widget = entry.widget
            if widget.required and not widget.is_answered():
                missing.append(widget.prompt)
        return missing

    def collect_results(self) -> pandas.DataFrame:
        rows: list[dict[str, Any]] = []
        for entry in self._entries:
            rows.append(
                {
                    "section": entry.section,
                    "question": entry.widget.question_id,
                    "prompt": entry.widget.prompt,
                    "type": entry.widget.question_type,
                    "required": entry.widget.required,
                    "answer": entry.widget.get_answer(),
                }
            )
        return pandas.DataFrame(rows)


class _BaseQuestionWidget(QWidget):

    def __init__(
        self,
        question_cfg: dict[str, Any],
        ui_cfg: dict[str, Any],
        question_font_size: int,
        font_color: str,
        response_color: str,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)

        self._cfg = question_cfg
        self.question_id = str(question_cfg.get("question", ""))
        self.prompt = str(question_cfg.get("prompt", self.question_id))
        self.question_type = str(question_cfg.get("type", ""))
        self.required = bool(question_cfg.get("required", False))
        self._ui_cfg = ui_cfg
        self._font_color = font_color
        self._response_color = response_color

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.prompt_label = QLabel(self.prompt, self)
        self.prompt_label.setWordWrap(True)
        self.prompt_label.setTextFormat(Qt.TextFormat.MarkdownText)
        self.prompt_label.setText(format_markdown(self.prompt))
        self.prompt_label.setStyleSheet(f"color: {font_color};")
        self.prompt_label.setFont(QFont("Helvetica", question_font_size))
        layout.addWidget(self.prompt_label)

        self.input_row = QVBoxLayout()
        self.input_row.setContentsMargins(10, 0, 0, 0)
        self.input_row.setSpacing(4)
        layout.addLayout(self.input_row)

    def is_answered(self) -> bool:
        raise NotImplementedError

    def get_answer(self) -> Any:
        raise NotImplementedError


class _TextQuestionWidget(_BaseQuestionWidget):

    def __init__(
        self,
        question_cfg: dict[str, Any],
        ui_cfg: dict[str, Any],
        question_font_size: int,
        font_color: str,
        response_color: str,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(question_cfg, ui_cfg, question_font_size, font_color, response_color, parent)

        self.input = QLineEdit(self)
        self.input.setStyleSheet(
            f"background-color: {response_color}; color: {font_color}; border: 1px solid {font_color};"
        )
        self.input.setFixedWidth(_char_width(self.input.font(), int(ui_cfg["width_text_response"])))
        self.input_row.addWidget(self.input)

    def is_answered(self) -> bool:
        return bool(self.input.text().strip())

    def get_answer(self) -> str:
        return self.input.text().strip()


class _TextBoxQuestionWidget(_BaseQuestionWidget):

    def __init__(
        self,
        question_cfg: dict[str, Any],
        ui_cfg: dict[str, Any],
        question_font_size: int,
        font_color: str,
        response_color: str,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(question_cfg, ui_cfg, question_font_size, font_color, response_color, parent)

        self.input = QPlainTextEdit(self)
        self.input.setStyleSheet(
            f"background-color: {response_color}; color: {font_color}; border: 1px solid {font_color};"
        )
        self.input.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        self.input.setFixedWidth(_char_width(self.input.font(), int(ui_cfg["width_text_response"])))
        lines = max(1, int(ui_cfg["text_box_number_of_lines"]))
        line_height = QFontMetrics(self.input.font()).lineSpacing()
        self.input.setFixedHeight(int(line_height * lines + 16))
        self.input_row.addWidget(self.input)

    def is_answered(self) -> bool:
        return bool(self.input.toPlainText().strip())

    def get_answer(self) -> str:
        return self.input.toPlainText().strip()


class _NumericQuestionWidget(_BaseQuestionWidget):

    def __init__(
        self,
        question_cfg: dict[str, Any],
        ui_cfg: dict[str, Any],
        question_font_size: int,
        font_color: str,
        response_color: str,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(question_cfg, ui_cfg, question_font_size, font_color, response_color, parent)

        self.input = QLineEdit(self)
        self.input.setStyleSheet(
            f"background-color: {response_color}; color: {font_color}; border: 1px solid {font_color};"
        )
        validator = QDoubleValidator(self)
        validator.setNotation(QDoubleValidator.Notation.StandardNotation)
        self.input.setValidator(validator)
        self.input.setFixedWidth(_char_width(self.input.font(), int(ui_cfg["width_numeric_response"])))
        self.input_row.addWidget(self.input)

    def _parse_numeric(self) -> Optional[float]:
        text = self.input.text().strip().replace(",", ".")
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None

    def is_answered(self) -> bool:
        return self._parse_numeric() is not None

    def get_answer(self) -> Optional[float]:
        return self._parse_numeric()


class _SingleChoiceQuestionWidget(_BaseQuestionWidget):

    def __init__(
        self,
        question_cfg: dict[str, Any],
        ui_cfg: dict[str, Any],
        question_font_size: int,
        font_color: str,
        response_color: str,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(question_cfg, ui_cfg, question_font_size, font_color, response_color, parent)

        options = question_cfg.get("options", [])
        if not isinstance(options, list):
            options = []

        self._group = QButtonGroup(self)
        self._buttons: list[QRadioButton] = []
        indicator_size = 14
        for idx, option in enumerate(options):
            text = _as_option_text(option)
            button = QRadioButton(text, self)
            button.setStyleSheet(
                f"color: {font_color};"
                f"QRadioButton::indicator {{ background-color: {response_color}; border: 1px solid {font_color}; width: {indicator_size}px; height: {indicator_size}px; }}"
                f"QRadioButton::indicator:checked {{ background-color: {response_color}; border: 2px solid {font_color}; }}"
            )
            button.setFont(QFont("Helvetica", question_font_size))
            button.setMinimumHeight(max(button.sizeHint().height(), indicator_size + 8))
            self._group.addButton(button, idx)
            self._buttons.append(button)
            self.input_row.addWidget(button)

        self._other_cfg = question_cfg.get("other_question", None)
        self._other_widget: Optional[_BaseQuestionWidget] = None
        if isinstance(self._other_cfg, dict):
            other_prompt = str(self._other_cfg.get("prompt", "Please specify"))
            other_type = str(self._other_cfg.get("type", "text"))
            other_cfg = {
                "question": f"{self.question_id}__other",
                "prompt": other_prompt,
                "type": other_type,
                "required": True,
            }
            self._other_widget = _create_question_widget(
                other_cfg,
                ui_cfg,
                question_font_size,
                font_color,
                response_color,
                self,
            )
            self._other_widget.hide()
            self.input_row.addWidget(self._other_widget)
            self._group.buttonClicked.connect(self._update_other_visibility)

    def _selected_text(self) -> Optional[str]:
        checked = self._group.checkedButton()
        if checked is None:
            return None
        return checked.text()

    def _update_other_visibility(self) -> None:
        if self._other_widget is None or not isinstance(self._other_cfg, dict):
            return

        bind_value = _as_option_text(self._other_cfg.get("other_question_value", ""))
        selected = self._selected_text()
        self._other_widget.setVisible(selected == bind_value)

    def is_answered(self) -> bool:
        selected = self._selected_text()
        if not selected:
            return False

        if self._other_widget is None or not isinstance(self._other_cfg, dict):
            return True

        bind_value = _as_option_text(self._other_cfg.get("other_question_value", ""))
        if selected != bind_value:
            return True

        return self._other_widget.is_answered()

    def get_answer(self) -> Any:
        selected = self._selected_text()
        if selected is None:
            return None

        if self._other_widget is None or not isinstance(self._other_cfg, dict):
            return selected

        bind_value = _as_option_text(self._other_cfg.get("other_question_value", ""))
        if selected != bind_value:
            return selected

        other_answer = self._other_widget.get_answer()
        if _has_value(other_answer):
            return other_answer

        return selected


class _MultipleChoiceQuestionWidget(_BaseQuestionWidget):

    def __init__(
        self,
        question_cfg: dict[str, Any],
        ui_cfg: dict[str, Any],
        question_font_size: int,
        font_color: str,
        response_color: str,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(question_cfg, ui_cfg, question_font_size, font_color, response_color, parent)

        options = question_cfg.get("options", [])
        if not isinstance(options, list):
            options = []

        self._checks: list[QCheckBox] = []
        for option in options:
            text = _as_option_text(option)
            checkbox = QCheckBox(text, self)
            checkbox.setStyleSheet(
                f"color: {font_color};"
                f"QCheckBox::indicator {{ background-color: {response_color}; border: 1px solid {font_color}; }}"
                f"QCheckBox::indicator:checked {{ background-color: {response_color}; border: 2px solid {font_color}; }}"
            )
            checkbox.setFont(QFont("Helvetica", question_font_size))
            self._checks.append(checkbox)
            self.input_row.addWidget(checkbox)

    def is_answered(self) -> bool:
        return any(chk.isChecked() for chk in self._checks)

    def get_answer(self) -> list[str]:
        return [chk.text() for chk in self._checks if chk.isChecked()]


def _create_question_widget(
    question_cfg: dict[str, Any],
    ui_cfg: dict[str, Any],
    question_font_size: int,
    font_color: str,
    response_color: str,
    parent: Optional[QWidget] = None,
) -> _BaseQuestionWidget:
    qtype = str(question_cfg.get("type", "")).strip().lower()

    if qtype == "text":
        return _TextQuestionWidget(question_cfg, ui_cfg, question_font_size, font_color, response_color, parent)
    if qtype == "text_box":
        return _TextBoxQuestionWidget(question_cfg, ui_cfg, question_font_size, font_color, response_color, parent)
    if qtype == "single_choice":
        return _SingleChoiceQuestionWidget(question_cfg, ui_cfg, question_font_size, font_color, response_color, parent)
    if qtype == "multiple_choice":
        return _MultipleChoiceQuestionWidget(question_cfg, ui_cfg, question_font_size, font_color, response_color, parent)
    if qtype == "numeric":
        return _NumericQuestionWidget(question_cfg, ui_cfg, question_font_size, font_color, response_color, parent)

    raise ValueError(f"Unsupported question type: {qtype}")


def _char_width(font: QFont, n_chars: int) -> int:
    metrics = QFontMetrics(font)
    width = metrics.averageCharWidth() * max(1, int(n_chars))
    return max(80, width + 16)


def _as_option_text(value: Any) -> str:
    # PyYAML can parse bare yes/no into booleans; map them back to text labels.
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return len(value) > 0
    return True
