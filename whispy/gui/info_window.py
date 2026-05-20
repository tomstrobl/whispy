from __future__ import annotations

import math
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QTextDocument
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget


class InfoWindow(QWidget):

    def __init__(
        self,
        info_text: str,
        fontsize: int,
        fontcolor: str,
        minimum_width: int=320,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("")
        self._fontsize = max(1, int(fontsize))
        self._minimum_width = max(1, int(minimum_width))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        self.info_label = QLabel(self._format_markdown(info_text), self)
        self.info_label.setTextFormat(Qt.TextFormat.MarkdownText)
        self.info_label.setWordWrap(False)
        self.info_label.setFont(QFont("Helvetica", self._fontsize))
        self.info_label.setStyleSheet(f"color: {QColor(fontcolor).name()};")

        layout.addWidget(self.info_label)

        controls_layout = QHBoxLayout()
        controls_layout.addStretch(1)

        self.continue_button = QPushButton("Continue", self)
        self._setup_control_button(self.continue_button, self._fontsize)
        self.continue_button.clicked.connect(self.close)

        controls_layout.addWidget(self.continue_button)
        layout.addLayout(controls_layout)

        self._resize_to_content()

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

        margins = self.layout().contentsMargins()
        spacing = self.layout().spacing()
        button_width = self.continue_button.width()
        button_height = self.continue_button.height()

        width = max(text_width, button_width) + margins.left() + margins.right() + 8
        height = text_height + button_height + margins.top() + margins.bottom() + spacing + 8
        self.setFixedSize(max(self._minimum_width, width), max(30, height))

    @staticmethod
    def _setup_control_button(button: QPushButton, button_fontsize: int) -> None:
        font_size = max(1, int(button_fontsize))
        font = QFont("Helvetica", font_size, QFont.Weight.Normal)
        button.setFont(font)
        hint = button.sizeHint()
        width = hint.width() + max(6, int(font_size * 0.5))
        height = hint.height() + max(4, int(font_size * 0.3))
        button.setFixedSize(width, height)
