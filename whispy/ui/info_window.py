from __future__ import annotations

from whispy.utils import load_design
from whispy.utils._utils import format_markdown
from .base import _BaseUIWindow, style_qpushbutton

import math
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QCloseEvent, QColor, QFont, QTextDocument
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QMainWindow, QPushButton, QScrollArea, QVBoxLayout, QWidget

# Module-level registry of top-level InfoWindows that are not stored by the user.
# This keeps them alive so they don't get garbage collected before the user closes them.
_orphaned_windows: list[InfoWindow] = []

_SCREEN_MARGIN_FACTOR = 0.9
_SCROLL_WIDTH_MARGIN_FACTOR = 1.1
_PERSISTENT_SCROLLBAR_STYLE = """
QScrollBar:vertical {
    background: rgba(255, 255, 255, 0.15);
    width: 6px;
    margin: 0px;
    border-radius: 6px;
}
QScrollBar::handle:vertical {
    background: rgba(255, 255, 255, 0.70);
    width: 6px;
    min-height: 24px;
    border-radius: 6px;
}
QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {
    height: 0px;
}
QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical {
    background: transparent;
}
"""


class InfoWindow(_BaseUIWindow):
    """
    Display a popup window to render markdown text.

    Parameters
    ----------
    info_text : str
        Markdown text to display.
    fontsize : int, optional
        Font size for the text and button.
    fontcolor : str, optional
        Text color.
    background_color : str, optional
        Window background color. Like ``fontsize``/``fontcolor`` it falls
        back to the global theme (``configs/design.yml``).
    fullscreen : bool, optional
        If ``True``, show the window fullscreen on the target screen (the
        ``screen:`` setting of ``configs/design.yml``).
    minimum_width : int, optional
        Minimum width for the content block in pixel.
    center : bool, optional
        If ``True``, center the text horizontally inside the window.
    blocking : bool, optional
        If True, block until Continue is clicked.
    debug : bool, optional
        If False, the window close button is disabled and Continue is the
        only way to close the window.
    parent : QMainWindow, optional
        If provided, reuse the host window instead of creating a new one.
        The host's central widget is replaced with this UI's content.
        The OS window is not opened or resized. Call ``close()`` on any UI
        instance sharing the host to close the window.
    """

    def __init__(
        self,
        info_text: str,
        *,
        fontsize: Optional[int] = None,
        fontcolor: Optional[str] = None,
        background_color: Optional[str] = None,
        fullscreen: bool = False,
        minimum_width: int=320,
        center: bool = True,
        blocking: bool = True,
        debug: bool = False,
        parent: Optional[QMainWindow] = None,
    ) -> None:
        super().__init__(blocking=blocking, debug=debug, parent=parent)

        # Fall back to the global theme so standalone info screens match the
        # other listening-test UIs. Explicit args still win.
        design = load_design()
        if fontsize is None:
            fontsize = int(design.get("fontsize", 12))
        if fontcolor is None:
            fontcolor = str(design.get("fontcolor", "#FFFFFF"))
        if background_color is None:
            background_color = str(design.get("window_background_color", "#2b2b2b"))
        self._screen_setting = design.get("screen")
        self._fullscreen = fullscreen
        self._center = center
        self._fontsize = max(1, int(fontsize))
        self._minimum_width = max(1, int(minimum_width))
        self._formatted_text = format_markdown(info_text)

        if parent is None:
            self.setWindowTitle("")
            self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
            if not debug:
                self.disable_close_button()

        self._content_widget = QWidget()
        self._content_widget.setStyleSheet(
            f"background-color: {background_color};"
        )
        content_layout = QVBoxLayout(self._content_widget)
        content_layout.setContentsMargins(10, 10, 10, 10)
        content_layout.setSpacing(10)

        self._scroll_area = QScrollArea(self._content_widget)
        self._scroll_area.setWidgetResizable(False)
        self._scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll_area.verticalScrollBar().setStyleSheet(_PERSISTENT_SCROLLBAR_STYLE)

        self.info_label = QLabel(self._formatted_text)
        self.info_label.setTextFormat(Qt.TextFormat.MarkdownText)
        self.info_label.setWordWrap(False)
        self.info_label.setFont(QFont("Helvetica", self._fontsize))
        self.info_label.setStyleSheet(f"color: {QColor(fontcolor).name()};")
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self._scroll_area.setWidget(self.info_label)

        if self._center:
            content_layout.addWidget(self._scroll_area, 0, Qt.AlignmentFlag.AlignHCenter)
        else:
            content_layout.addWidget(self._scroll_area)

        controls_layout = QHBoxLayout()
        controls_layout.addStretch(1)

        self.continue_button = QPushButton("Continue")
        style_qpushbutton(
            self.continue_button, fontsize,
            design.get("button_text_color", "#2b3550"),
            design.get("button_background_color", "#ffffff"),
            design.get("button_border_radius", "8px"),
            design.get("button_hover_background_color"),
            design.get("button_border_color"),
        )
        self.continue_button.clicked.connect(self._on_continue_clicked)

        controls_layout.addWidget(self.continue_button)
        content_layout.addLayout(controls_layout)

        # Wrap the content widget so we can center it vertically in the host.
        outer = QWidget()
        outer_layout = QVBoxLayout(outer)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)
        if self._center:
            outer_layout.addStretch(1)
            outer_layout.addWidget(self._content_widget, 0, Qt.AlignmentFlag.AlignHCenter)
            outer_layout.addStretch(1)
        else:
            outer_layout.addWidget(
                self._content_widget,
                0,
                Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft,
            )

        self._host.setCentralWidget(outer)
        self._resize_to_content()

        if parent is None:
            if self._fullscreen:
                width, height = self._target_screen_size()
                self._show_host_window(
                    width=width, height=height, fullscreen=True,
                    background_color=background_color)
            else:
                self._show_host_window()
                self._center_on_screen()
            # Keep top-level windows alive even if the caller does not store them.
            _orphaned_windows.append(self)

        if blocking:
            self.wait_until_closed()

    def _resize_to_content(self) -> None:
        screen_geometry = self._target_screen().availableGeometry()
        max_width = max(self._minimum_width, math.floor(screen_geometry.width() * _SCREEN_MARGIN_FACTOR))
        max_height = max(30, math.floor(screen_geometry.height() * _SCREEN_MARGIN_FACTOR))

        text_width, text_height = self._measure_markdown(self._formatted_text)

        content_layout = self._content_widget.layout()
        margins = content_layout.contentsMargins()
        spacing = content_layout.spacing()
        button_width = self.continue_button.width()
        button_height = self.continue_button.height()

        width_padding = margins.left() + margins.right() + 8
        controls_height = button_height + margins.top() + margins.bottom() + spacing + 8
        min_content_width = max(self._minimum_width, button_width + width_padding)
        available_text_width = max(1, max_width - width_padding)
        available_text_height = max(1, max_height - controls_height)

        target_text_width = math.ceil(text_width * _SCROLL_WIDTH_MARGIN_FACTOR)
        visible_text_width = min(target_text_width, available_text_width)
        visible_text_height = min(text_height, available_text_height)
        width = max(min_content_width, visible_text_width + width_padding)
        height = visible_text_height + controls_height
        needs_vertical_scroll = text_height > available_text_height

        self.info_label.setFixedSize(max(1, text_width), max(1, text_height))
        self._scroll_area.setFixedSize(max(1, visible_text_width), max(1, visible_text_height))

        self._content_widget.setFixedSize(width, height)
        self._scroll_area.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOn if needs_vertical_scroll else Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        if not self._fullscreen and self._host is self:
            self._host.adjustSize()

    def _center_on_screen(self) -> None:
        # Re-center with the now-accurate frame geometry, staying on the
        # target screen (a popup shown over a running test stays on the
        # test's screen, see _BaseUIWindow._target_screen()).
        self._move_host_to_screen(self._target_screen())

    def _measure_markdown(self, markdown_text: str) -> tuple[int, int]:
        doc = QTextDocument()
        doc.setDefaultFont(self.info_label.font())
        doc.setMarkdown(markdown_text)
        doc.adjustSize()

        self.info_label.adjustSize()
        label_hint = self.info_label.sizeHint()

        text_width = max(math.ceil(doc.idealWidth()), label_hint.width())
        text_height = max(math.ceil(doc.size().height()), label_hint.height())
        return max(1, text_width), max(1, text_height)

    def _on_continue_clicked(self) -> None:
        # Standalone popup (owns its window): close it on Continue so it does
        # not linger. closeEvent also quits any blocking loop, so a blocking
        # caller still returns after the participant clicks Continue.
        if self._host is self:
            self._allow_close = True
            QMainWindow.close(self)
            return
        # Reused host: just unblock the caller; the shared window stays open and
        # is managed by whoever owns the host.
        self.unblock()

    def closeEvent(self, event: QCloseEvent) -> None:
        # Remove from orphaned windows registry if present
        if self in _orphaned_windows:
            _orphaned_windows.remove(self)
        super().closeEvent(event)
