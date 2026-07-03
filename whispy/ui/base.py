from __future__ import annotations

import sys
import os
from typing import Optional

from PyQt6.QtCore import QEventLoop, Qt, QTimer
from PyQt6.QtGui import QCloseEvent, QCursor, QFont, QScreen
from PyQt6.QtWidgets import (
    QApplication,
    QLabel,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from whispy.utils import load_design


# Module-level QApplication reference kept alive for the process lifetime so
# repeated widget construction in notebooks does not leave Qt without an app.
_qapp: Optional[QApplication] = None


def _enable_qt_gui_in_ipython() -> None:
    """Enable Qt6 integration when running inside an IPython kernel."""
    try:
        from IPython import get_ipython

        ip = get_ipython()

        if ip is None:
            return

        ip.enable_gui("qt6")
        # Minimal deterministic wait: let Qt event loop tick once
        loop = QEventLoop()
        QTimer.singleShot(200, loop.quit)
        loop.exec()

    except Exception:
        pass


def ensure_qapplication() -> QApplication:
    """Return a QApplication instance, creating one when required."""
    global _qapp

    app = QApplication.instance()
    if app is None:
        force_software_gl = os.environ.get("WHISPY_FORCE_SOFTWARE_GL", "0") == "1"
        if force_software_gl:
            QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseSoftwareOpenGL, True)
        # Avoid passing notebook/kernel arguments through to Qt.
        _qapp = QApplication(sys.argv[:1])
        app = _qapp

        _enable_qt_gui_in_ipython()

    return app


def resolve_screen(setting: object = None) -> QScreen:
    """Resolve a config-driven screen setting into a ``QScreen``.

    ``setting`` may be:

    - ``None`` / ``"primary"``: the OS primary screen (the default).
    - ``"cursor"`` / ``"mouse"``: the screen currently containing the mouse
      pointer (useful to open the test wherever the experimenter is working).
    - an integer index into ``QApplication.screens()`` (``0``, ``1``, ...).
    - a string naming a screen (exact match first, then substring,
      case-insensitive), e.g. ``"DELL U2720Q"``.

    This is a failsafe resolver: any unknown, out-of-range, or otherwise
    invalid value falls back to the primary screen instead of raising, so a
    misconfigured ``screen:`` key can never prevent an experiment window from
    opening.
    """
    ensure_qapplication()
    primary = QApplication.primaryScreen()
    screens = QApplication.screens()

    if setting is None or isinstance(setting, bool) or not screens:
        return primary

    if isinstance(setting, str):
        name = setting.strip()
        lowered = name.lower()
        if lowered in ("", "primary", "default"):
            return primary
        if lowered in ("cursor", "mouse", "current"):
            return QApplication.screenAt(QCursor.pos()) or primary
        try:
            setting = int(name)
        except ValueError:
            for screen in screens:
                if screen.name().lower() == lowered:
                    return screen
            for screen in screens:
                if lowered in screen.name().lower():
                    return screen
            return primary

    if isinstance(setting, int):
        if 0 <= setting < len(screens):
            return screens[setting]
        return primary

    return primary


def style_qpushbutton(
    button: QPushButton, button_fontsize: int,
    button_fontcolor: str, button_background_color: str,
    button_border_radius: str = "8px",
    button_hover_background_color: Optional[str] = None,
    button_border_color: Optional[str] = None) -> None:
    font_size = max(1, int(button_fontsize))
    font = QFont("Helvetica", font_size, QFont.Weight.Normal)
    button.setFont(font)
    button.setCursor(Qt.CursorShape.PointingHandCursor)

    border = f"1px solid {button_border_color}" if button_border_color else "none"
    sheet = (
        f"QPushButton {{"
        f" background-color: {button_background_color};"
        f" color: {button_fontcolor};"
        f" border: {border};"
        f" border-radius: {button_border_radius};"
        f" padding: 6px 16px; }}"
    )
    if button_hover_background_color:
        sheet += (
            f"QPushButton:hover {{"
            f" background-color: {button_hover_background_color}; }}"
        )
    # Apply the stylesheet (incl. padding/border) BEFORE measuring, so the size
    # hint accounts for it and the label is never clipped.
    button.setStyleSheet(sheet)
    # Use the widget's style-aware size hint, then add a small safety margin.
    hint = button.sizeHint()
    width = hint.width() + max(6, int(font_size * 0.5))
    height = hint.height() + max(4, int(font_size * 0.3))
    button.setFixedSize(width, height)


def build_progress_widget(
    progress: object,
    *,
    text_template: str = "Trial {current} of {total}",
    fontsize: int = 11,
    fontcolor: str = "#2b2f38",
    bar_color: str = "#5cb874",
    trough_color: str = "#dbe2f1",
    parent: Optional[QWidget] = None,
) -> Optional[QWidget]:
    """Build the trial-progress indicator shared by every listening test.

    ``progress`` is the ``progress`` entry of a ``screen`` dict — either a
    ``{"current": ..., "total": ...}`` mapping or a ``(current, total)`` pair —
    telling the participant how far into the trial list they are. Returns a
    small widget (a centered text label over a slim filled bar) or ``None``
    when ``progress`` is missing/unusable, so callers can simply skip it.

    ``text_template`` is formatted with ``current``, ``total`` and
    ``remaining`` (``total - current``); a broken template falls back to the
    default wording instead of raising mid-experiment.
    """
    try:
        if isinstance(progress, dict):
            current = int(progress["current"])
            total = int(progress["total"])
        else:
            current = int(progress[0])  # type: ignore[index]
            total = int(progress[1])  # type: ignore[index]
    except Exception:
        return None
    if total < 1:
        return None
    current = max(1, min(current, total))

    try:
        text = str(text_template).format(
            current=current, total=total, remaining=total - current)
    except Exception:
        text = f"Trial {current} of {total}"

    widget = QWidget(parent)
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(20)

    label = QLabel(text, widget)
    label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
    label.setStyleSheet(f"color: {fontcolor}; background-color: transparent;")
    label.setFont(QFont("Helvetica", max(1, int(fontsize))))
    layout.addWidget(label)

    bar = QProgressBar(widget)
    bar.setRange(0, total)
    bar.setValue(current)
    bar.setTextVisible(False)
    bar.setFixedHeight(8)
    bar.setStyleSheet(
        f"QProgressBar {{ background-color: {trough_color}; border: none;"
        f" border-radius: 4px; }}"
        f"QProgressBar::chunk {{ background-color: {bar_color};"
        f" border-radius: 4px; }}"
    )
    layout.addWidget(bar)

    return widget


class _BaseUIWindow(QMainWindow):
    """Shared Qt host-window lifecycle for Whispy UI classes.

    This base class centralizes the behavior currently shared by the concrete
    UI windows: QApplication bootstrapping, reuse of a parent host window,
    blocking event-loop handling, and guarded close behavior.
    """

    def __init__(
        self,
        *,
        blocking: bool = True,
        debug: bool = False,
        parent: Optional["_BaseUIWindow"] = None,
    ) -> None:
        if parent is None:
            ensure_qapplication()

        super().__init__()
        self._host: QMainWindow = self if parent is None else parent._host
        self._active_child_loop: Optional[QEventLoop] = None
        self._wait_loop: Optional[QEventLoop] = None
        self._blocking = bool(blocking)
        self._debug = bool(debug)
        self._allow_close = bool(debug)
        # Which screen (monitor) this UI opens on. Concrete UIs overwrite this
        # with the `screen:` key of their merged design/config before showing;
        # ``None`` falls back to the global default from configs/design.yml
        # (and ultimately to the primary screen), see ``_target_screen()``.
        self._screen_setting: object = None

    @staticmethod
    def _is_fullscreen_window_size(window_size: object) -> bool:
        """Return whether the config value requests fullscreen mode."""
        return isinstance(window_size, str) and window_size.strip().lower() == "fullscreen"

    def _target_screen(self) -> QScreen:
        """Return the screen every window of this experiment should open on.

        A host window that is already visible stays on whichever screen it
        currently occupies (so trials reusing a shared host, and popups shown
        over it, never jump to another monitor). Otherwise the configured
        ``screen:`` setting is resolved, falling back to the global default
        from ``configs/design.yml`` and ultimately to the primary screen.
        """
        if self._host.isVisible():
            # Call QWidget.screen() unbound: test UIs (NAFC/ABX/MUSHRA) store
            # their trial dict as `self.screen`, shadowing the Qt method.
            screen = QWidget.screen(self._host)
            if screen is not None:
                return screen

        setting = self._screen_setting
        if setting is None:
            try:
                setting = load_design().get("screen")
            except Exception:
                setting = None
        return resolve_screen(setting)

    def _target_screen_size(self) -> tuple[int, int]:
        """Return the target screen's available width and height."""
        geometry = self._target_screen().availableGeometry()
        return geometry.width(), geometry.height()

    def _resolve_window_size(
        self,
        window_size: object,
        *,
        fallback: tuple[int, int],
        minimum_size: Optional[tuple[int, int]] = None,
    ) -> tuple[int, int, bool]:
        """Resolve config-driven window sizing into concrete dimensions."""
        if self._is_fullscreen_window_size(window_size):
            width, height = self._target_screen_size()
            return width, height, True

        width, height = fallback
        if isinstance(window_size, list) and len(window_size) == 2:
            try:
                width = int(window_size[0])
                height = int(window_size[1])
            except (TypeError, ValueError):
                width, height = fallback

        if minimum_size is not None:
            width = max(int(minimum_size[0]), width)
            height = max(int(minimum_size[1]), height)

        return width, height, False

    @staticmethod
    def _resolve_area_size(
        window_size: tuple[int, int],
        area_pct: object,
        *,
        min_size: tuple[int, int],
        reserved: tuple[int, int],
    ) -> tuple[int, int]:
        """Resolve an ``[x%, y%]``-of-window area size into clamped pixels.

        ``area_pct`` is an ``[x_percent, y_percent]`` pair (each clamped to
        0..100); the result is that percentage of the window dimensions. It is
        bounded below by ``min_size`` and above by the window size minus
        ``reserved`` (the space taken by margins / surrounding widgets), so the
        area never collapses or overflows the window. This is the single sizing
        rule shared by every listening test (MUSHRA's rating area and the
        N-AFC/ABX content areas).
        """
        win_w, win_h = int(window_size[0]), int(window_size[1])
        min_w, min_h = int(min_size[0]), int(min_size[1])
        max_w = max(min_w, win_w - int(reserved[0]))
        max_h = max(min_h, win_h - int(reserved[1]))
        try:
            x_pct = max(0.0, min(100.0, float(area_pct[0]))) / 100.0  # type: ignore[index]
            y_pct = max(0.0, min(100.0, float(area_pct[1]))) / 100.0  # type: ignore[index]
        except (TypeError, ValueError, IndexError):
            x_pct = y_pct = 1.0
        width = max(min_w, min(max_w, int(win_w * x_pct)))
        height = max(min_h, min(max_h, int(win_h * y_pct)))
        return width, height

    def _move_host_to_screen(self, screen: QScreen) -> None:
        """Associate the host window with ``screen`` and center it there.

        The top-left corner is clamped into the screen's available geometry so
        the window (and its title bar) always stays reachable, even when it is
        larger than the target screen.
        """
        host = self._host
        try:
            # Associate the widget with the screen so the native window is
            # created there (must happen before the first show to be reliable).
            host.setScreen(screen)
        except Exception:
            pass
        handle = host.windowHandle()
        if handle is not None and handle.screen() is not screen:
            try:
                handle.setScreen(screen)
            except Exception:
                pass

        available = screen.availableGeometry()
        frame = host.frameGeometry()
        frame.moveCenter(available.center())
        x = max(available.left(),
                min(frame.left(), available.right() - frame.width() + 1))
        y = max(available.top(),
                min(frame.top(), available.bottom() - frame.height() + 1))
        host.move(x, y)

    def _show_host_window(
        self,
        *,
        width: Optional[int] = None,
        height: Optional[int] = None,
        fullscreen: bool = False,
        background_color = None,
    ) -> None:
        """Show and activate the host window using the resolved presentation mode.

        The window is always placed on the configured target screen (see
        ``_target_screen()``) so every window of one experiment opens on the
        same monitor, instead of wherever the OS last remembered a window.
        """
        if width is not None and height is not None:
            self._host.resize(width, height)

        # Set window background color
        if background_color:
            self._host.setStyleSheet(f"background-color: {background_color};")

        screen = self._target_screen()
        # Place the window on the target screen while it is still hidden;
        # fullscreen then engages on that screen.
        self._move_host_to_screen(screen)

        if fullscreen:
            self._host.showFullScreen()
            # Failsafe: if the platform still put the fullscreen window on
            # another screen, reassign it via the native window handle (which
            # moves fullscreen windows in Qt 6). Never move() a fullscreen
            # window - that can drop it out of fullscreen on macOS.
            handle = self._host.windowHandle()
            if handle is not None and handle.screen() is not screen:
                try:
                    handle.setScreen(screen)
                except Exception:
                    pass
        else:
            self._host.show()
            # Failsafe: some window managers restore a remembered position on
            # another monitor during show; re-pin after the window exists.
            # (QWidget.screen() unbound: `self.screen` may be the trial dict.)
            if QWidget.screen(self._host) is not screen:
                self._move_host_to_screen(screen)

        self._host.raise_()
        self._host.activateWindow()

    def disable_close_button(self) -> None:
        """Hide the native close button for top-level windows."""
        if self._host is self:
            self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)

    def wait_until_closed(self) -> None:
        """Block until the shared host window is closed or explicitly unblocked."""
        if not self._host.isVisible():
            return

        if self._wait_loop is None:
            self._wait_loop = QEventLoop(self._host)

        self._host._active_child_loop = self._wait_loop
        self._wait_loop.exec()

    def unblock(self) -> None:
        """Quit the local blocking event loop if it is active."""
        if self._wait_loop is not None and self._wait_loop.isRunning():
            self._wait_loop.quit()

    def close(self) -> None:  # type: ignore[override]
        """Close the host OS window. Must be called explicitly by the caller."""
        self._host._allow_close = True
        QMainWindow.close(self._host)

    def closeEvent(self, event: QCloseEvent) -> None:
        """Guard closing and release any nested blocking loops."""
        if not self._allow_close:
            event.ignore()
            return

        if self._active_child_loop is not None and self._active_child_loop.isRunning():
            self._active_child_loop.quit()
        if self._wait_loop is not None and self._wait_loop.isRunning():
            self._wait_loop.quit()

        super().closeEvent(event)
