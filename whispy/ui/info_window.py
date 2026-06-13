from __future__ import annotations

import math
import sys
from typing import Optional

from PyQt6.QtCore import QEventLoop, Qt
from PyQt6.QtGui import QCloseEvent, QColor, QFont, QTextDocument
from PyQt6.QtWidgets import QApplication, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget


# Module-level QApplication reference — kept alive for the process lifetime so
# that constructing and destroying InfoWindow instances multiple times (e.g.
# in a notebook) never leaves Qt without an application instance.
_qapp: Optional[QApplication] = None

# Module-level registry of top-level InfoWindows that are not stored by the user.
# This keeps them alive so they don't get garbage collected before the user closes them.
_orphaned_windows: list[InfoWindow] = []


class InfoWindow(QWidget):
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
    fullscreen : bool, optional
        If ``True``, show the window fullscreen using the primary screen
        geometry.
    minimum_width : int, optional
        Minimum width for the content block in pixel.
    center : bool, optional
        If ``True``, center the entire text and continue button in the window.
    blocking : bool, optional
        If True, block until the window is closed.
    debug : bool, optional
        If False, the window close button is disabled and Continue is the
        only way to close the window.
    """

    def __init__(
        self,
        info_text: str,
        *,
        fontsize: int = 12,
        fontcolor: str = "#FFFFFF",
        background_color: Optional[str] = None,
        fullscreen: bool = False,
        minimum_width: int=320,
        center: bool = True,
        blocking: bool = True,
        debug: bool = False,
    ) -> None:
        # QApplication must exist before any QWidget is constructed.
        # sys.argv[:1] avoids passing Jupyter/IPython kernel arguments to Qt.
        global _qapp
        if QApplication.instance() is None:
            _qapp = QApplication(sys.argv[:1])

        # When running inside an IPython kernel (e.g. VS Code interactive
        # window) enable Qt6 GUI integration so the event loop is active.
        try:
            from IPython import get_ipython
            ip = get_ipython()
            if ip is not None:
                ip.enable_gui('qt6')
        except Exception:
            pass

        super().__init__()
        self.setWindowTitle("")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self._debug = debug
        self._allow_close = bool(debug)
        self._fullscreen = fullscreen
        self._center = center
        self._fontsize = max(1, int(fontsize))
        self._minimum_width = max(1, int(minimum_width))
        self._wait_loop: Optional[QEventLoop] = None

        if not self._debug:
            self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._content_widget = QWidget(self)
        self._content_widget.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        effective_background = background_color or "#94b1ff"
        self.setStyleSheet(f"background-color: {effective_background};")
        self._content_widget.setStyleSheet(
            f"background-color: {effective_background};"
        )

        content_layout = QVBoxLayout(self._content_widget)
        content_layout.setContentsMargins(10, 10, 10, 10)
        content_layout.setSpacing(10)

        self.info_label = QLabel(self._format_markdown(info_text), self._content_widget)
        self.info_label.setTextFormat(Qt.TextFormat.MarkdownText)
        self.info_label.setWordWrap(False)
        self.info_label.setFont(QFont("Helvetica", self._fontsize))
        self.info_label.setStyleSheet(f"color: {QColor(fontcolor).name()};")

        content_layout.addWidget(self.info_label)

        controls_layout = QHBoxLayout()
        controls_layout.addStretch(1)

        self.continue_button = QPushButton("Continue", self._content_widget)
        self._setup_control_button(self.continue_button, self._fontsize)
        self.continue_button.clicked.connect(self._on_continue_clicked)

        controls_layout.addWidget(self.continue_button)
        content_layout.addLayout(controls_layout)

        if self._center:
            layout.addStretch(1)
            layout.addWidget(self._content_widget, 0, Qt.AlignmentFlag.AlignHCenter)
            layout.addStretch(1)
        else:
            layout.addWidget(
                self._content_widget,
                0,
                Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft,
            )
            layout.setAlignment(self._content_widget, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        self._resize_to_content()
        if self._fullscreen:
            geo = QApplication.primaryScreen().availableGeometry()
            self.resize(geo.width(), geo.height())
            self.showFullScreen()
        else:
            self.show()
        self.raise_()
        self.activateWindow()

        # Keep top-level windows alive even if the caller does not store them.
        _orphaned_windows.append(self)

        if blocking:
            self.wait_until_closed()

    @staticmethod
    def _format_markdown(text: str) -> str:
        return text.replace("\n", "  \n")

    def _resize_to_content(self) -> None:
        doc = QTextDocument()
        doc.setDefaultFont(self.info_label.font())
        doc.setMarkdown(self.info_label.text())
        doc.adjustSize()

        # QLabel and QTextDocument can disagree slightly for markdown layout.
        # Use the larger size to avoid clipping text.
        self.info_label.adjustSize()
        label_hint = self.info_label.sizeHint()

        text_width = max(math.ceil(doc.idealWidth()), label_hint.width())
        text_height = max(math.ceil(doc.size().height()), label_hint.height())

        margins = self._content_widget.layout().contentsMargins()
        spacing = self._content_widget.layout().spacing()
        button_width = self.continue_button.width()
        button_height = self.continue_button.height()

        width = max(text_width, button_width) + margins.left() + margins.right() + 8
        height = text_height + button_height + margins.top() + margins.bottom() + spacing + 8
        self._content_widget.setFixedSize(max(self._minimum_width, width), max(30, height))

        if not self._fullscreen:
            self.adjustSize()

    def wait_until_closed(self) -> None:
        if not self.isVisible():
            return

        if self._wait_loop is None:
            self._wait_loop = QEventLoop(self)

        self._wait_loop.exec()

    def _on_continue_clicked(self) -> None:
        self._allow_close = True
        self.close()

    def closeEvent(self, event: QCloseEvent) -> None:
        if not self._allow_close:
            event.ignore()
            return
        if self._wait_loop is not None and self._wait_loop.isRunning():
            self._wait_loop.quit()
        # Remove from orphaned windows registry if present
        if self in _orphaned_windows:
            _orphaned_windows.remove(self)
        super().closeEvent(event)

    @staticmethod
    def _setup_control_button(button: QPushButton, button_fontsize: int) -> None:
        font_size = max(1, int(button_fontsize))
        font = QFont("Helvetica", font_size, QFont.Weight.Normal)
        button.setFont(font)
        hint = button.sizeHint()
        width = hint.width() + max(6, int(font_size * 0.5))
        height = hint.height() + max(4, int(font_size * 0.3))
        button.setFixedSize(width, height)
