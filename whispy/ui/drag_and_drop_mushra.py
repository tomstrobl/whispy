from __future__ import annotations

from .base import _BaseUIWindow
from .info_window import InfoWindow
from whispy.interfaces import StimuliHandler, SoundDevice
from whispy.utils import read_config
from whispy.utils._utils import format_markdown

import pandas
import os
from dataclasses import dataclass
from typing import Dict, List, Optional

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QGraphicsLineItem,
    QGraphicsObject,
    QGraphicsScene,
    QGraphicsView,
    QLabel,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

# Directory containing this file.
# Required for loading the default configs
FILEPATH = os.path.dirname(os.path.abspath(__file__))

class DragAndDropMUSHRA(_BaseUIWindow):

    def __init__(
        self,
        *,
        screen: Optional[Dict] = None,
        stimuli_handler: Optional[StimuliHandler] = None,
        attributes: Optional[str] = None,
        drag_and_drop_mushra: Optional[str] = None,
        blocking: Optional[bool] = True,
        debug: Optional[bool] = False,
        parent: Optional[QMainWindow] = None,
    ) -> None:
        super().__init__(blocking=bool(blocking), debug=bool(debug), parent=parent)

        # initialize experimental parameters ----------------------------------
        # initialize rating screen if it was not passed
        if screen is None:
            screen = {
                "block": 0,
                "section": 0,
                "reference": 1,
                "test": [2, 3],
                "block_changed": True,
                "section_changed": False,
                "attribute": "difference",
                "block_name": "Block 1",
                "section_name": "Section 1"}

        self.screen = screen

        # initialize default audio handler if it was not passed
        if stimuli_handler is None:
            stimuli_handler = SoundDevice()

        self.stimuli_handler: StimuliHandler = stimuli_handler

        # initialize attributes if they were not passed
        if attributes is None:
            attributes = os.path.join(
                FILEPATH, "..", "..", "configs", "attributes.yml")

        attributes = read_config(attributes)

        # read GUI config (use default if not provided)
        if drag_and_drop_mushra is None:
            drag_and_drop_mushra = os.path.join(
                FILEPATH, "..", "..", "configs", "drag_and_drop_mushra.yml")

        drag_and_drop_mushra = read_config(drag_and_drop_mushra)

        # parse config data to get parameters for current task ----------------
        # current attribute and rating scale
        task = attributes[screen["attribute"]]["task"]
        description = attributes[screen["attribute"]]["description"]
        neutral_value = attributes[screen["attribute"]]["neutral_value"]
        values = attributes[screen["attribute"]]["values"]
        labels = attributes[screen["attribute"]]["labels"]

        # number of conditions
        num_buttons = len(screen["test"])
        reference = screen["reference"] is not None

        # initialize QT parameters --------------------------------------------
        # set global parameters
        # In non-debug mode, window close actions are blocked until Continue.
        if parent is None and not self._debug:
            self.disable_close_button()

        # set window size
        window_size = drag_and_drop_mushra["window_size"]
        window_width, window_height, fullscreen = self._resolve_window_size(
            window_size,
            fallback=(1000, 700),
        )
        if fullscreen:
            # Shallow-copy the config so the caller's dict is not mutated.
            drag_and_drop_mushra = dict(drag_and_drop_mushra)
            drag_and_drop_mushra["window_size"] = [window_width, window_height]

        self._continue_info_window: Optional[InfoWindow] = None

        container = QWidget()
        container.setStyleSheet(
            f"background-color: {drag_and_drop_mushra['window_background_color']};"
        )
        layout = QVBoxLayout(container)
        layout.setContentsMargins(22, 22, 22, 22)

        # initialize main rating window ---------------------------------------
        self.drag_area = _MainWindow(
            num_buttons=num_buttons,
            reference=reference,
            task=task,
            description=description,
            neutral_value=neutral_value,
            values=values,
            labels=labels,
            drag_and_drop_mushra=drag_and_drop_mushra,
            parent=container,
        )
        layout.addWidget(self.drag_area)

        self._host.setCentralWidget(container)

        self.drag_area.tilePressed.connect(self._on_tile_pressed)
        self.drag_area.tileReleased.connect(self._on_tile_released)
        self.drag_area.tileClicked.connect(self._on_tile_clicked)
        self.drag_area.tileActivated.connect(self._on_tile_activated)
        self.drag_area.tileDeactivated.connect(self._on_tile_deactivated)
        self.drag_area.stopClicked.connect(self._on_stop_clicked)

        if parent is None:
            # show window in front of all other windows
            self._show_host_window(
                width=window_width,
                height=window_height,
                fullscreen=fullscreen,
            )

        self.drag_area.continueClicked.connect(self._on_continue_clicked)
        # Block code execution outside this class until Continue is clicked
        if blocking:
            self.wait_until_closed()

    def _on_tile_pressed(self, tile_name: str, pos: QPointF) -> None:
        if self._debug:
            print(f"pressed: {tile_name} at ({pos.x():.2f}, {pos.y()})")

    def _on_tile_released(self, tile_name: str, pos: QPointF) -> None:
        if self._debug:
            print(f"released: {tile_name} at ({pos.x():.2f}, {pos.y()})")

    def _on_tile_clicked(self, tile_name: str, pos: QPointF) -> None:
        if self._debug:
            print(f"clicked: {tile_name} at ({pos.x():.2f}, {pos.y()})")

    def _on_tile_activated(self, tile_name: str) -> None:
        stimulus_name = self._get_stimulus_name(tile_name)
        self.stimuli_handler.play(stimulus_name)
        if self._debug:
            print(f"activated: {tile_name}, playing: {stimulus_name}")

    def _on_tile_deactivated(self, tile_name: str) -> None:
        stimulus_name = self._get_stimulus_name(tile_name)
        self.stimuli_handler.stop(stimulus_name)
        if self._debug:
            print(f"deactivated: {tile_name}, stopped: {stimulus_name}")

    def _on_stop_clicked(self) -> None:
        if self._debug:
            print("Stop clicked")

    def _get_stimulus_name(self, tile_name):
        if tile_name == "R":
            stimulus_name = self.screen["reference"]
        else:
            stimulus_name = self.screen["test"][int(tile_name) - 1]

        return stimulus_name

    def _on_continue_clicked(self) -> None:
        if self.drag_area.view.all_tiles_activated_once() or self._debug:

            self.drag_area.view.deactivate_active_button()

            # Quit the blocking loop so the caller regains control.
            # The window stays open; caller must call .close() explicitly.
            self.unblock()
            return

        self._continue_info_window = InfoWindow(
            info_text="You have to listen to each sound at least once.",
            fontsize=self.drag_area._fontsize,
            fontcolor=self.drag_area._fontcolor,
            blocking=False,
        )

    def get_results(
            self,
            results: Optional[pandas.DataFrame] = None
            ) -> Dict[str, Dict[str, float | bool]]:

        # ratings coded by the names of the GUI buttons/tiles
        ratings_raw = self.drag_area.view.get_values()
        # decode to stimulus names
        ratings = {}
        for tile_name, rating in ratings_raw.items():
            ratings[self._get_stimulus_name(tile_name)] = rating


        if results is None:
            # create empty dataframe with columns from the screen metadata
            results = pandas.DataFrame(
                columns=list(self.screen.keys()) + ['rating'])

        # fill data frame in long format (one row per test condition)
        for t in self.screen["test"]:
            row = dict(self.screen)
            row["test"] = t
            row["rating"] = ratings[t]
            results.loc[len(results)] = row

        return results

class _MainWindow(QWidget):
    tilePressed = pyqtSignal(str, QPointF)
    tileReleased = pyqtSignal(str, QPointF)
    tileClicked = pyqtSignal(str, QPointF)
    tileActivated = pyqtSignal(str)
    tileDeactivated = pyqtSignal(str)
    stopClicked = pyqtSignal()
    continueClicked = pyqtSignal()

    def __init__(
        self,
        num_buttons: int = 5,
        reference: bool = True,
        task: str = "Rate the\n**Tone colour bright-dark**\n",
        description: str = "some text",
        neutral_value: float = 0,
        values: Optional[List[float]] = None,
        labels: Optional[List[Optional[str]]] = None,
        drag_and_drop_mushra: Optional[Dict] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        if drag_and_drop_mushra is None:
            raise ValueError("drag_and_drop_mushra config is required")

        task_fontsize = drag_and_drop_mushra["task_fontsize"]
        task_spacing = drag_and_drop_mushra["task_spacing"]
        fontsize = drag_and_drop_mushra["fontsize"]
        button_fontsize = drag_and_drop_mushra["button_fontsize"]
        fontcolor = drag_and_drop_mushra["fontcolor"]

        self._description = description
        self._fontsize = max(1, int(fontsize))
        self._fontcolor = fontcolor
        self._info_window: Optional[InfoWindow] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addStretch(1)

        task_row_widget = QWidget(self)
        task_row = QHBoxLayout(task_row_widget)
        task_row.setContentsMargins(0, 0, 0, 0)
        task_row.setSpacing(8)

        self.task_label = QLabel(format_markdown(task), self)
        self.task_label.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
        self.task_label.setWordWrap(True)
        self.task_label.setTextFormat(Qt.TextFormat.MarkdownText)
        self.task_label.setStyleSheet(
            f"color: {fontcolor}; font-size: {max(1, int(task_fontsize))}pt;"
        )

        self.info_button = QPushButton("ℹ️", self)
        self.info_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.info_button.setFlat(True)
        self.info_button.setFixedWidth(32)
        self.info_button.setStyleSheet("QPushButton { border: none; background-color: transparent; }")
        self.info_button.clicked.connect(self._on_info_button_clicked)

        self._left_info_placeholder = QWidget(self)
        self._left_info_placeholder.setFixedWidth(32)

        task_row.addWidget(self._left_info_placeholder, 0, Qt.AlignmentFlag.AlignTop)
        task_row.addWidget(self.task_label, 1)
        task_row.addWidget(self.info_button, 0, Qt.AlignmentFlag.AlignTop)
        layout.addWidget(task_row_widget, alignment=Qt.AlignmentFlag.AlignHCenter)
        if task_spacing > 0:
            layout.addSpacing(task_spacing)

        self.labels_row = _RatingAreaLabels(
            fontsize=fontsize,
            fontcolor=fontcolor,
            parent=self,
        )
        layout.addWidget(self.labels_row, alignment=Qt.AlignmentFlag.AlignHCenter)

        self.view = _RatingArea(
            num_buttons=num_buttons,
            reference=reference,
            neutral_value=neutral_value,
            values=values,
            labels=labels,
            drag_and_drop_mushra=drag_and_drop_mushra,
            parent=self,
        )
        layout.addWidget(self.view, alignment=Qt.AlignmentFlag.AlignHCenter)

        task_row_widget.setFixedWidth(self.view.minimumWidth())
        self.labels_row.setFixedWidth(self.view.minimumWidth())
        self.view.lineLayoutChanged.connect(self.labels_row.set_layout)
        self.view._draw_value_lines()

        controls_widget = QWidget(self)
        controls_layout = QHBoxLayout(controls_widget)
        controls_layout.setContentsMargins(0, 8, 0, 0)
        controls_layout.setSpacing(8)
        controls_layout.addStretch(1)

        self.stop_button = QPushButton("Stop", self)
        self.continue_button = QPushButton("Continue", self)

        self._setup_control_button(self.stop_button, button_fontsize)
        self._setup_control_button(self.continue_button, button_fontsize)

        self.stop_button.clicked.connect(self._on_stop_button_clicked)
        self.continue_button.clicked.connect(self.continueClicked)

        controls_layout.addWidget(self.stop_button)
        controls_layout.addWidget(self.continue_button)
        controls_widget.setFixedWidth(self.view.minimumWidth())
        layout.addWidget(controls_widget, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch(1)

        self.view.tilePressed.connect(self.tilePressed)
        self.view.tileReleased.connect(self.tileReleased)
        self.view.tileClicked.connect(self.tileClicked)
        self.view.tileActivated.connect(self.tileActivated)
        self.view.tileDeactivated.connect(self.tileDeactivated)

    def _on_info_button_clicked(self) -> None:
        self._info_window = InfoWindow(
            info_text=self._description,
            fontsize=self._fontsize,
            fontcolor=self._fontcolor,
            blocking=False,
        )

    def _on_stop_button_clicked(self) -> None:
        self.view.deactivate_active_button()
        self.stopClicked.emit()

    @staticmethod
    def _setup_control_button(button: QPushButton, button_fontsize: int) -> None:
        font_size = max(1, int(button_fontsize))
        font = QFont("Helvetica", font_size, QFont.Weight.Normal)
        button.setFont(font)
        # Use the widget's style-aware size hint, then add a small safety margin.
        hint = button.sizeHint()
        width = hint.width() + max(6, int(font_size * 0.5))
        height = hint.height() + max(4, int(font_size * 0.3))
        button.setFixedSize(width, height)


class _RatingArea(QGraphicsView):
    tilePressed = pyqtSignal(str, QPointF)
    tileReleased = pyqtSignal(str, QPointF)
    tileClicked = pyqtSignal(str, QPointF)
    tileActivated = pyqtSignal(str)
    tileDeactivated = pyqtSignal(str)
    lineLayoutChanged = pyqtSignal(list, list, list)

    def __init__(
        self,
        num_buttons: int = 5,
        reference: bool = True,
        neutral_value: float = 0,
        values: Optional[List[float]] = None,
        labels: Optional[List[Optional[str]]] = None,
        drag_and_drop_mushra: Optional[Dict] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)

        if drag_and_drop_mushra is None:
            raise ValueError("drag_and_drop_mushra config is required")

        button_size = drag_and_drop_mushra["button_size"]
        button_fontsize = drag_and_drop_mushra["button_fontsize"]
        button_spacing = drag_and_drop_mushra["button_spacing"]
        rating_area_background_color = drag_and_drop_mushra["rating_area_background_color"]
        window_background_color = drag_and_drop_mushra["window_background_color"]
        edge_color = drag_and_drop_mushra["edge_color"]
        button_color_initial = drag_and_drop_mushra["button_color_initial"]
        button_color_clicked = drag_and_drop_mushra["button_color_clicked"]
        button_color_active = drag_and_drop_mushra["button_color_active"]
        button_fontcolor = drag_and_drop_mushra["button_fontcolor"]
        autoplay_reference = drag_and_drop_mushra["autoplay_reference"]
        autoplay_delay = drag_and_drop_mushra["autoplay_delay"]
        window_size = drag_and_drop_mushra["window_size"]
        rating_area_size = drag_and_drop_mushra["rating_area_size"]

        self._num_buttons = max(1, num_buttons)
        self._reference = bool(reference)
        self._button_size = max(8.0, float(button_size))
        self._button_fontsize = max(1, int(button_fontsize))
        self._button_spacing = max(0.0, float(button_spacing))
        self._rating_area_background_color = rating_area_background_color
        self._window_background_color = window_background_color
        self._edge_color = edge_color
        self._button_color_initial = button_color_initial
        self._button_color_clicked = button_color_clicked
        self._button_color_active = button_color_active
        self._button_fontcolor = button_fontcolor
        self._autoplay_reference = autoplay_reference
        self._autoplay_delay_ms = max(0, int(float(autoplay_delay) * 1000))
        self._neutral_value = float(neutral_value)
        self._neutral_tile_name = "R"
        self._active_tile_name: Optional[str] = None
        self._reference_activation_enabled = False
        self._activated_once: set[str] = set()
        self._values = self._normalize_values(values)
        self._labels = self._normalize_labels(labels)

        self.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.TextAntialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
        )
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._scene.setSceneRect(0, 0, 980, 220)

        self._tiles: Dict[str, _DraggableTile] = {}
        self._lane_lines: List[QGraphicsLineItem] = []
        self._startup_layout_applied = False
        self._user_positioned_tiles = False
        self._autoplay_timer = QTimer(self)
        self._autoplay_timer.setSingleShot(True)
        self._autoplay_timer.timeout.connect(self._on_autoplay_timer_timeout)

        self._button_area_width: float = 0.0

        # Apply rating_area_size as a percentage of the window dimensions.
        # Width  bounds: [200 px, window_width  - 44 px (container margins)]
        # Height bounds: [80 px,  window_height - 200 px (margins + other widgets)]
        _win_w = int(window_size[0])
        _win_h = int(window_size[1])
        _min_w, _max_w = 200, max(200, _win_w - 44)
        _min_h, _max_h = 80,  max(80,  _win_h - 200)
        _x_pct = max(0.0, min(100.0, float(rating_area_size[0]))) / 100.0
        _y_pct = max(0.0, min(100.0, float(rating_area_size[1]))) / 100.0
        self.setFixedWidth( max(_min_w, min(_max_w, int(_win_w * _x_pct))))
        self.setFixedHeight(max(_min_h, min(_max_h, int(_win_h * _y_pct))))

        self._sync_scene_to_viewport()
        self._build_tiles()

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        painter.fillRect(rect, QColor(self._window_background_color))
        scene_rect = self._scene.sceneRect()
        left, right = self._line_anchor_domain(scene_rect.width())
        rating_rect = QRectF(left, scene_rect.top(), right - left, scene_rect.height())
        clipped = rating_rect.intersected(rect)
        if not clipped.isEmpty():
            painter.fillRect(clipped, QColor(self._rating_area_background_color))

    def resizeEvent(self, event) -> None:
        relative_x: Dict[str, float] = {}
        preserve_relative_positions = self._startup_layout_applied and self._user_positioned_tiles
        if preserve_relative_positions:
            relative_x = self._capture_relative_x_positions()

        super().resizeEvent(event)
        self._sync_scene_to_viewport()

        if preserve_relative_positions:
            self._restore_relative_x_positions(relative_x)
        else:
            self._apply_startup_layout()
            self._startup_layout_applied = True

        self._position_neutral_tile()
        self._clamp_tiles_to_scene()

    def _draw_value_lines(self) -> None:
        rect = self._scene.sceneRect()
        positions = self._scaled_line_positions(rect.width())

        for line_item in self._lane_lines:
            self._scene.removeItem(line_item)
        self._lane_lines.clear()

        for x in positions:
            pen = QPen(QColor(self._edge_color), 2)
            line = self._scene.addLine(x, rect.top(), x, rect.bottom(), pen)
            line.setZValue(0)
            self._lane_lines.append(line)

        numeric_labels = [f"{v:g}" for v in self._values]
        self.lineLayoutChanged.emit(positions, self._labels, numeric_labels)

    def _build_tiles(self) -> None:
        specs = self._default_specs(self._num_buttons)

        for spec in specs:
            tile = _DraggableTile(
                spec.name,
                size=self._button_size,
                color=self._button_color_clicked,
                initial_color=self._button_color_initial,
                active_color=self._button_color_active,
                edge_color=self._edge_color,
                font_color=self._button_fontcolor,
                font_size=self._button_fontsize,
                switch_style_on_first_click=True,
            )
            tile.setPos(spec.x, spec.y)
            tile.setCursor(Qt.CursorShape.OpenHandCursor)

            tile.pressed.connect(self._on_tile_pressed)
            tile.clicked.connect(self._on_tile_clicked)
            tile.released.connect(self._on_tile_released)
            tile.doubleClicked.connect(self._on_tile_double_clicked)

            self._scene.addItem(tile)
            self._tiles[spec.name] = tile

        if self._reference:
            neutral_tile = _DraggableTile(
                self._neutral_tile_name,
                size=self._button_size,
                color="#d9dde3",
                initial_color="#d9dde3",
                active_color=self._button_color_active,
                edge_color=self._edge_color,
                font_color=self._button_fontcolor,
                font_size=self._button_fontsize,
                movable=False,
                switch_style_on_first_click=False,
            )
            neutral_tile.setZValue(1)
            neutral_tile.setCursor(Qt.CursorShape.ArrowCursor)
            neutral_tile.pressed.connect(self._on_tile_pressed)
            neutral_tile.clicked.connect(self._on_tile_clicked)
            neutral_tile.released.connect(self._on_tile_released)
            self._scene.addItem(neutral_tile)
            self._tiles[self._neutral_tile_name] = neutral_tile
            self._position_neutral_tile()

    def _apply_startup_layout(self) -> None:
        specs = self._default_specs(self._num_buttons)
        for spec in specs:
            tile = self._tiles.get(spec.name)
            if tile is not None:
                tile.setPos(spec.x, spec.y)

    def _on_tile_pressed(self, name: str, pos: QPointF) -> None:
        self._autoplay_timer.stop()
        if self._reference and name != self._neutral_tile_name:
            self._reference_activation_enabled = True
        self._set_active_tile(name, allow_reference_fallback=False)
        self.tilePressed.emit(name, self._map_pos_to_value_space(pos))

    def _on_tile_clicked(self, name: str, pos: QPointF) -> None:
        self.tileClicked.emit(name, self._map_pos_to_value_space(pos))

    def _on_tile_released(self, name: str, pos: QPointF) -> None:
        if name != self._neutral_tile_name:
            self._user_positioned_tiles = True

            tile = self._tiles.get(name)
            if tile is not None:
                rect = self._scene.sceneRect()
                left, _ = self._line_anchor_domain(rect.width())
                min_x = left - self._button_size / 2
                tile._min_x = min_x
                if tile.x() < min_x:
                    tile.setX(min_x)
                pos = tile.scenePos()

        if self._active_tile_name == name:
            self._set_active_tile(None, allow_reference_fallback=False)

        if self._reference and name != self._neutral_tile_name and self._autoplay_reference:
            self._schedule_reference_autoplay()

        self.tileReleased.emit(name, self._map_pos_to_value_space(pos))

    def _on_tile_double_clicked(self, name: str, pos: QPointF) -> None:
        if name == self._neutral_tile_name:
            return

        tile = self._tiles.get(name)
        if tile is None:
            return

        rect = self._scene.sceneRect()
        center_x = self._value_to_center_x(self._neutral_value, rect.width())
        tile_x = center_x - tile.boundingRect().width() / 2
        tile.setX(tile_x)
        self._user_positioned_tiles = True
        self._clamp_tiles_to_scene()

    def deactivate_active_button(self) -> None:
        self._autoplay_timer.stop()
        self._set_active_tile(None, allow_reference_fallback=False)

    def all_tiles_activated_once(self) -> bool:
        return set(self._tiles.keys()).issubset(self._activated_once)

    def _schedule_reference_autoplay(self) -> None:
        if not self._reference_activation_enabled:
            return

        if self._autoplay_delay_ms == 0:
            self._on_autoplay_timer_timeout()
            return

        self._autoplay_timer.start(self._autoplay_delay_ms)

    def _on_autoplay_timer_timeout(self) -> None:
        if not self._autoplay_reference or not self._reference:
            return

        if self._active_tile_name is None and self._reference_activation_enabled:
            self._set_active_tile(self._neutral_tile_name, allow_reference_fallback=False)

    def _set_active_tile(self, name: Optional[str], allow_reference_fallback: bool) -> None:
        previous_name = self._active_tile_name
        target_name = name
        if (
            target_name is None
            and allow_reference_fallback
            and self._reference
            and self._reference_activation_enabled
        ):
            target_name = self._neutral_tile_name

        if previous_name == target_name:
            return

        if previous_name is not None:
            current_tile = self._tiles.get(previous_name)
            if current_tile is not None:
                current_tile.set_active(False)
            self.tileDeactivated.emit(previous_name)
            self._active_tile_name = None

        if target_name is None:
            return

        target_tile = self._tiles.get(target_name)
        if target_tile is None:
            return

        target_tile.set_active(True)
        self._active_tile_name = target_name
        self._activated_once.add(target_name)
        self.tileActivated.emit(target_name)

    def _update_button_area_width(self) -> None:
        """Recompute the width reserved for the button staging columns."""
        rect = self._scene.sceneRect()
        step = self._button_size + self._button_spacing
        max_y = rect.height() - self._button_size
        rows_per_column = max(1, int(max(0.0, max_y) / step) + 1)
        num_columns = -(-self._num_buttons // rows_per_column)  # ceil division
        self._button_area_width = num_columns * step

    def _sync_scene_to_viewport(self) -> None:
        viewport_size = self.viewport().size()
        width = max(1.0, float(viewport_size.width()))
        height = max(1.0, float(viewport_size.height()))
        self._scene.setSceneRect(0, 0, width, height)
        self._update_button_area_width()
        self._draw_value_lines()

    def _normalize_values(self, values: Optional[List[float]]) -> List[float]:
        if values is None:
            # Default keeps a useful left-to-right scale with one line per button.
            return [float(i) for i in range(self._num_buttons)]

        if len(values) == 0:
            raise ValueError("values must contain at least one number")

        normalized = [float(v) for v in values]
        for prev, curr in zip(normalized, normalized[1:]):
            if curr <= prev:
                raise ValueError("values must be strictly increasing")
        return normalized

    def _normalize_labels(self, labels: Optional[List[Optional[str]]]) -> List[str]:
        if labels is None:
            return ["" for _ in self._values]

        if len(labels) != len(self._values):
            raise ValueError("labels must have the same length as values")

        normalized_labels: List[str] = []
        for item in labels:
            if item is None:
                normalized_labels.append("")
                continue

            normalized_labels.append(str(item))
        return normalized_labels

    def _scaled_line_positions(self, area_width: float) -> List[float]:
        left, right = self._line_anchor_domain(area_width)

        if len(self._values) == 1:
            return [left]

        min_v = self._values[0]
        max_v = self._values[-1]
        span = max_v - min_v

        if span <= 0:
            return [left for _ in self._values]

        return [
            left + ((v - min_v) / span) * (right - left)
            for v in self._values
        ]

    def _line_anchor_domain(self, area_width: float) -> tuple[float, float]:
        left = self._button_area_width + self._button_size / 2
        right = max(left, area_width - self._button_size / 2)
        return left, right

    def _value_to_center_x(self, value: float, area_width: float) -> float:
        left, right = self._line_anchor_domain(area_width)
        if len(self._values) == 1:
            return left

        min_v = self._values[0]
        max_v = self._values[-1]
        span = max_v - min_v
        if span <= 0:
            return left

        ratio = (value - min_v) / span
        ratio = min(max(ratio, 0.0), 1.0)
        return left + ratio * (right - left)

    def _position_neutral_tile(self) -> None:
        neutral_tile = self._tiles.get(self._neutral_tile_name)
        if neutral_tile is None:
            return

        rect = self._scene.sceneRect()
        center_x = self._value_to_center_x(self._neutral_value, rect.width())
        tile_w = neutral_tile.boundingRect().width()
        tile_h = neutral_tile.boundingRect().height()
        tile_x = center_x - tile_w / 2
        tile_y = rect.height() / 2 - tile_h / 2
        neutral_tile.setPos(tile_x, tile_y)

    def _map_pos_to_value_space(self, pos: QPointF) -> QPointF:
        rect = self._scene.sceneRect()
        left, right = self._line_anchor_domain(rect.width())
        span_px = max(1e-9, right - left)

        center_x = pos.x() + self._button_size / 2
        ratio = (center_x - left) / span_px
        ratio = min(max(ratio, 0.0), 1.0)

        if len(self._values) == 1:
            value_x = self._values[0]
        else:
            min_v = self._values[0]
            max_v = self._values[-1]
            value_x = min_v + ratio * (max_v - min_v)

        return QPointF(value_x, pos.y())

    def get_values(self) -> Dict:
        values = {}
        for name, tile in self._tiles.items():
            if name == self._neutral_tile_name:
                continue
            value_pos = self._map_pos_to_value_space(tile.scenePos())
            values[name] = float(value_pos.x())
        return values

    def _capture_relative_x_positions(self) -> Dict[str, float]:
        rect = self._scene.sceneRect()
        left, right = self._line_anchor_domain(rect.width())
        span = max(1e-9, right - left)

        relative_x: Dict[str, float] = {}
        for name, tile in self._tiles.items():
            if name == self._neutral_tile_name:
                continue
            center_x = tile.x() + tile.boundingRect().width() / 2
            ratio = (center_x - left) / span
            relative_x[name] = min(max(ratio, 0.0), 1.0)
        return relative_x

    def _restore_relative_x_positions(self, relative_x: Dict[str, float]) -> None:
        rect = self._scene.sceneRect()
        left, right = self._line_anchor_domain(rect.width())
        span = max(0.0, right - left)

        for name, ratio in relative_x.items():
            tile = self._tiles.get(name)
            if tile is None:
                continue
            center_x = left + ratio * span
            tile_x = center_x - tile.boundingRect().width() / 2
            tile.setX(tile_x)

    def _clamp_tiles_to_scene(self) -> None:
        bounds = self._scene.sceneRect()
        for tile in self._tiles.values():
            tile_rect = tile.boundingRect()
            max_x = bounds.right() - tile_rect.width()
            max_y = bounds.bottom() - tile_rect.height()
            clamped_x = min(max(tile.x(), bounds.left()), max_x)
            clamped_y = min(max(tile.y(), bounds.top()), max_y)
            tile.setPos(clamped_x, clamped_y)

    def _default_specs(self, count: int) -> List[_DraggableTileSpec]:
        rect = self._scene.sceneRect()
        step = self._button_size + self._button_spacing
        max_y = rect.height() - self._button_size
        rows_per_column = max(1, int(max(0.0, max_y) / step) + 1)

        specs: List[_DraggableTileSpec] = []
        for idx in range(count):
            col = idx // rows_per_column
            row = idx % rows_per_column
            x = col * step
            y = row * step
            specs.append(_DraggableTileSpec(name=str(idx + 1), x=x, y=y))
        return specs


class _RatingAreaLabels(QWidget):
    def __init__(
        self,
        fontsize: int = 9,
        fontcolor: str = "#e8eaed",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._positions: List[float] = []
        self._upper_labels: List[str] = []
        self._lower_labels: List[str] = []
        self._fontsize = max(1, int(fontsize))
        self._fontcolor = QColor(fontcolor)
        self.setMinimumHeight(48)
        self.setMaximumHeight(56)

    def set_layout(self, positions: List[float], upper_labels: List[str], lower_labels: List[str]) -> None:
        self._positions = positions
        self._upper_labels = upper_labels
        self._lower_labels = lower_labels
        self.update()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        upper_font = QFont("Helvetica", self._fontsize, QFont.Weight.DemiBold)
        lower_font = QFont("Helvetica", self._fontsize)

        top_y = 16
        bottom_y = 35

        for idx, x in enumerate(self._positions):
            if idx < len(self._upper_labels):
                upper_text = self._upper_labels[idx]
            else:
                upper_text = ""

            if idx < len(self._lower_labels):
                lower_text = self._lower_labels[idx]
            else:
                lower_text = ""

            painter.setPen(self._fontcolor)
            painter.setFont(upper_font)
            upper_width = painter.fontMetrics().horizontalAdvance(upper_text)
            upper_x = int(x - upper_width / 2)
            upper_x = min(max(upper_x, 0), max(0, self.width() - upper_width))
            painter.drawText(upper_x, top_y, upper_text)

            painter.setPen(self._fontcolor)
            painter.setFont(lower_font)
            lower_width = painter.fontMetrics().horizontalAdvance(lower_text)
            lower_x = int(x - lower_width / 2)
            lower_x = min(max(lower_x, 0), max(0, self.width() - lower_width))
            painter.drawText(lower_x, bottom_y, lower_text)


@dataclass
class _DraggableTileSpec:
    name: str
    x: float
    y: float


class _DraggableTile(QGraphicsObject):
    pressed = pyqtSignal(str, QPointF)
    released = pyqtSignal(str, QPointF)
    clicked = pyqtSignal(str, QPointF)
    doubleClicked = pyqtSignal(str, QPointF)

    def __init__(
        self,
        name: str,
        size: float = 56,
        color: str = "#d9dde3",
        initial_color: str = "#ffffff",
        active_color: str = "#a5d6a7",
        edge_color: str = "#c8cdd4",
        font_color: str = "#444a55",
        font_size: int = 17,
        movable: bool = True,
        switch_style_on_first_click: bool = False,
        parent: Optional[QGraphicsObject] = None,
    ) -> None:
        super().__init__(parent)
        self.name = name
        self._rect = QRectF(0, 0, size, size)
        self._clicked_color = QColor(color)
        self._initial_color = QColor(initial_color)
        self._active_color = QColor(active_color)
        self._edge_color = QColor(edge_color)
        self._font_color = QColor(font_color)
        self._font_size = max(1, int(font_size))
        self._movable = movable
        self._switch_style_on_first_click = switch_style_on_first_click
        self._was_clicked = False
        self._is_active = False
        self._drag_offset = QPointF(0, 0)
        self._moved_since_press = False
        self._min_x: float = 0.0

        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)
        self.setFlag(QGraphicsObject.GraphicsItemFlag.ItemIsFocusable, True)
        self.setZValue(10)

    def boundingRect(self) -> QRectF:
        return self._rect

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        use_initial_style = self._switch_style_on_first_click and not self._was_clicked
        border = QPen(self._edge_color, 1.2)
        if use_initial_style and not self._is_active:
            border.setStyle(Qt.PenStyle.DotLine)
        painter.setPen(border)
        if self._is_active:
            fill = self._active_color
        else:
            fill = self._initial_color if use_initial_style else self._clicked_color
        painter.setBrush(fill)
        painter.drawRoundedRect(self._rect, 14, 14)

        center_line = QPen(self._edge_color, 1.2)
        if use_initial_style and not self._is_active:
            center_line.setStyle(Qt.PenStyle.DotLine)
        painter.setPen(center_line)
        center_x = self._rect.center().x()
        font = QFont("Helvetica", self._font_size, QFont.Weight.DemiBold)
        painter.setFont(font)
        text_rect = painter.fontMetrics().boundingRect(
            self._rect.toRect(),
            int(Qt.AlignmentFlag.AlignCenter),
            self.name,
        )
        gap_margin = max(3.0, self._rect.height() * 0.06)
        upper_end = max(self._rect.top(), text_rect.top() - gap_margin)
        lower_start = min(self._rect.bottom(), text_rect.bottom() + gap_margin)
        painter.drawLine(
            QPointF(center_x, self._rect.top()),
            QPointF(center_x, upper_end),
        )
        painter.drawLine(
            QPointF(center_x, self._rect.bottom()),
            QPointF(center_x, lower_start),
        )

        painter.setPen(self._font_color)
        painter.drawText(self._rect, Qt.AlignmentFlag.AlignCenter, self.name)

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            event.ignore()
            return

        self._moved_since_press = False
        self._drag_offset = event.pos()
        self.setCursor(Qt.CursorShape.ClosedHandCursor)
        self.pressed.emit(self.name, self.scenePos())
        event.accept()

    def mouseMoveEvent(self, event) -> None:
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            event.ignore()
            return

        self._moved_since_press = True
        if not self._movable:
            event.accept()
            return

        next_scene_pos = event.scenePos() - self._drag_offset
        self._move_within_scene(next_scene_pos)
        event.accept()

    def mouseReleaseEvent(self, event) -> None:
        self.setCursor(Qt.CursorShape.OpenHandCursor)

        if self._switch_style_on_first_click and not self._was_clicked:
            self._was_clicked = True
            self.update()

        if not self._moved_since_press:
            # Treat press+release without drag as click.
            self.clicked.emit(self.name, self.scenePos())

        self.released.emit(self.name, self.scenePos())
        event.accept()

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            event.ignore()
            return

        self.doubleClicked.emit(self.name, self.scenePos())
        event.accept()

    def set_active(self, is_active: bool) -> None:
        if self._is_active == is_active:
            return
        self._is_active = is_active
        self.update()

    def _move_within_scene(self, new_pos: QPointF) -> None:
        scene = self.scene()
        if scene is None:
            self.setPos(new_pos)
            return

        bounds = scene.sceneRect()
        max_x = bounds.right() - self._rect.width()
        max_y = bounds.bottom() - self._rect.height()

        clamped_x = min(max(new_pos.x(), max(bounds.left(), self._min_x)), max_x)
        clamped_y = min(max(new_pos.y(), bounds.top()), max_y)
        self.setPos(clamped_x, clamped_y)
