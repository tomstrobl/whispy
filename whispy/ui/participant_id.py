from __future__ import annotations

import os
import re
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from whispy.utils import load_design, read_config
from whispy.utils._utils import format_markdown

from .base import _BaseUIWindow, style_qpushbutton
from .info_window import InfoWindow

# Directory containing this file.
# Required for loading the default participant_id config.
FILEPATH = os.path.dirname(os.path.abspath(__file__))


class ParticipantID(_BaseUIWindow):
    """Prompt once for a participant ID before the experiment starts.

    A single text field is shown by default. If the config defines a ``fields:``
    list, one labeled text field is shown per entry and the id is the answers
    joined by ``separator`` — e.g. first letters of names plus a birthday digit
    build an anonymous code. The id is returned by :meth:`get_id` so it can be
    stored alongside the experiment results (e.g.
    ``results.insert(0, "participant_id", participant_id)``). Like the other
    whispy UIs the look is inherited from ``configs/design.yml`` and may be
    overridden under the ``ui:`` block of ``configs/participant_id.yml``.

    Parameters
    ----------
    participant_id_config : str or None, optional
        Path to the config YAML. If ``None``, the default
        ``configs/participant_id.yml`` is used.
    blocking : bool, optional
        If ``True``, block until a valid id is submitted.
    debug : bool, optional
        If ``False``, the native close button is disabled and the window can
        only be left by submitting a valid id (empty / malformed ids are
        rejected). If ``True`` validation is skipped.
    parent : QMainWindow, optional
        If provided, reuse the host window instead of creating a new one.
    """

    def __init__(
        self,
        *,
        participant_id_config: Optional[str] = None,
        blocking: bool = True,
        debug: bool = False,
        parent: Optional[QMainWindow] = None,
    ) -> None:
        super().__init__(blocking=bool(blocking), debug=bool(debug), parent=parent)

        if participant_id_config is None:
            participant_id_config = os.path.join(
                FILEPATH, "..", "..", "configs", "participant_id.yml")
        cfg = read_config(participant_id_config)
        cfg = cfg if isinstance(cfg, dict) else {}
        # The global theme from configs/design.yml is the base; the per-UI
        # `ui:` block only overrides wording, window size, or individual colors.
        self._ui_cfg = load_design(cfg.get("ui"))
        self._screen_setting = self._ui_cfg.get("screen")

        self._participant_id: Optional[str] = None
        self._info_window: Optional[InfoWindow] = None
        self._resolve_config()

        if parent is None:
            self.setWindowTitle("")
            if not self._debug:
                self.disable_close_button()

        window_size = self._ui_cfg.get("window_size", [640, 320])
        self._window_width, self._window_height, self._fullscreen = self._resolve_window_size(
            window_size, fallback=(640, 320), minimum_size=(360, 200))

        self._build_ui()

        if parent is None:
            # Grow the window to fit the content if the configured size is too
            # small, and stop it being resized smaller than the content (which
            # would clip the prompt / submit button).
            if not self._fullscreen:
                min_w, min_h = self._content_min_size
                self._window_width = max(self._window_width, min_w)
                self._window_height = max(self._window_height, min_h)
                self._host.setMinimumSize(min_w, min_h)
            self._show_host_window(
                width=self._window_width, height=self._window_height,
                fullscreen=self._fullscreen,
                background_color=self._background_color)

        if blocking:
            self.wait_until_closed()

    # ------------------------------------------------------------------ setup
    def _resolve_config(self) -> None:
        """Read all UI config values once into named attributes."""
        ui = self._ui_cfg
        self._fontcolor = str(ui.get("fontcolor", "#2b2f38"))
        self._background_color = str(ui.get("window_background_color", "#eef1f7"))
        self._response_color = str(ui.get("response_boxes_color", "#ffffff"))
        self._input_text_color = str(ui.get("button_text_color", "#2b3550"))
        self._prompt = str(ui.get("prompt", "Please enter the participant ID:"))
        self._placeholder = str(ui.get("placeholder", ""))
        self._submit_button_text = str(ui.get("submit_button_text", "Start"))
        # Optional regex the id must fully match; empty accepts any non-empty id.
        self._pattern = str(ui.get("pattern", "") or "")
        self._invalid_hint = str(ui.get(
            "invalid_hint", "Please enter a valid participant ID."))
        self._task_fontsize = max(1, int(ui.get("task_fontsize", 16)))
        # Optional multi-part id: a list of ``{prompt, placeholder, pattern}``.
        # When given, one labeled text field is shown per entry and the id is the
        # answers joined by ``separator`` (so e.g. first letters + a digit build
        # an anonymous code). Without it, a single field is shown using the
        # top-level ``prompt``/``placeholder``/``pattern``.
        fields = ui.get("fields")
        self._fields = fields if isinstance(fields, list) and fields else None
        self._separator = str(ui.get("separator", ""))

    def _build_ui(self) -> None:
        """Build the central widget: prompt, text field, submit button.

        The widgets are added directly to the window-filling layout (with top /
        bottom stretches to center them vertically). A word-wrapped label nested
        in a centered, size-hint-constrained widget is computed for the wrong
        width by Qt and gets clipped, so we avoid that nesting here — the same
        pattern the NAFC/ABX prompts use.
        """
        container = QWidget(self)
        container.setStyleSheet(f"background-color: {self._background_color};")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        layout.addStretch(1)

        # Heading (the top-level prompt). Bold when it sits above several fields.
        heading = QLabel(format_markdown(self._prompt), container)
        heading.setTextFormat(Qt.TextFormat.MarkdownText)
        heading.setWordWrap(True)
        heading.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        heading.setStyleSheet(f"color: {self._fontcolor};")
        heading.setFont(QFont("Helvetica", self._task_fontsize,
                              QFont.Weight.Bold if self._fields else QFont.Weight.Normal))
        # Fills the full width, so word-wrap height is measured correctly.
        layout.addWidget(heading)

        # One text field per id part (multi-field), or a single field.
        self._inputs: list[QLineEdit] = []
        if self._fields:
            field_fontsize = max(1, self._task_fontsize - 2)
            for field in self._fields:
                fp = field.get("prompt") if isinstance(field, dict) else None
                if fp:
                    fl = QLabel(format_markdown(str(fp)), container)
                    fl.setTextFormat(Qt.TextFormat.MarkdownText)
                    fl.setWordWrap(True)
                    fl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
                    fl.setStyleSheet(f"color: {self._fontcolor};")
                    fl.setFont(QFont("Helvetica", field_fontsize))
                    layout.addWidget(fl)
                placeholder = field.get("placeholder", "") if isinstance(field, dict) else ""
                inp = self._make_input(str(placeholder))
                layout.addWidget(inp, alignment=Qt.AlignmentFlag.AlignHCenter)
                self._inputs.append(inp)
        else:
            inp = self._make_input(self._placeholder)
            layout.addWidget(inp, alignment=Qt.AlignmentFlag.AlignHCenter)
            self._inputs.append(inp)

        # Enter moves to the next field, and submits from the last one.
        for earlier, later in zip(self._inputs, self._inputs[1:]):
            earlier.returnPressed.connect(later.setFocus)
        self._inputs[-1].returnPressed.connect(self._on_submit_clicked)

        self._submit_button = QPushButton(self._submit_button_text, container)
        style_qpushbutton(
            self._submit_button, self._task_fontsize,
            self._ui_cfg.get("button_text_color", "#2b3550"),
            self._ui_cfg.get("button_background_color", "#ffffff"),
            self._ui_cfg.get("button_border_radius", "8px"),
            self._ui_cfg.get("button_hover_background_color"),
            self._ui_cfg.get("button_border_color"),
        )
        self._submit_button.clicked.connect(self._on_submit_clicked)
        layout.addWidget(self._submit_button, alignment=Qt.AlignmentFlag.AlignHCenter)

        layout.addStretch(1)

        self._host.setCentralWidget(container)
        self._inputs[0].setFocus()

        # Remember the size the content needs (incl. margins) so the window can
        # be grown to fit it. Without this a small configured window clips the
        # prompt and submit button on high-DPI screens or with large fonts.
        container.adjustSize()
        hint = container.sizeHint()
        self._content_min_size = (hint.width(), hint.height())

    def _make_input(self, placeholder: str) -> QLineEdit:
        """Create a styled, fixed-width text field for one id part."""
        inp = QLineEdit(self)
        if placeholder:
            inp.setPlaceholderText(placeholder)
        inp.setStyleSheet(
            f"QLineEdit {{ background-color: {self._response_color};"
            f" color: {self._input_text_color}; border: 1px solid {self._fontcolor};"
            f" border-radius: 6px; padding: 6px 8px; }}"
        )
        inp.setFont(QFont("Helvetica", self._task_fontsize))
        inp.setFixedWidth(280)
        return inp

    # --------------------------------------------------------------- handlers
    def _on_submit_clicked(self) -> None:
        """Validate every field and finish, or show a hint if invalid."""
        parts = [inp.text().strip() for inp in self._inputs]

        if not self._debug:
            # every field is required
            if any(part == "" for part in parts):
                self._show_invalid_hint()
                return
            # optional per-field pattern (multi-field) or overall pattern (single)
            if self._fields:
                for field, part in zip(self._fields, parts):
                    pat = str(field.get("pattern", "") or "") if isinstance(field, dict) else ""
                    if pat and re.fullmatch(pat, part) is None:
                        self._show_invalid_hint()
                        return
            elif self._pattern and re.fullmatch(self._pattern, parts[0]) is None:
                self._show_invalid_hint()
                return

        self._participant_id = self._separator.join(parts)

        # Standalone window: close it so the simple `ParticipantID().get_id()`
        # usage leaves no lingering window. When a host is reused, just unblock.
        if self._host is self:
            self.close()
        else:
            self.unblock()

    def _show_invalid_hint(self) -> None:
        """Pop up a non-blocking reminder to enter a valid id."""
        self._info_window = InfoWindow(
            info_text=self._invalid_hint,
            fontsize=self._task_fontsize,
            fontcolor=self._fontcolor,
            blocking=False,
        )

    def get_id(self) -> Optional[str]:
        """Return the submitted participant id (``None`` if none was entered)."""
        return self._participant_id
