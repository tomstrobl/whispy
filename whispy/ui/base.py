from __future__ import annotations

import sys
from typing import Optional

from PyQt6.QtCore import QEventLoop, Qt, QTimer
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import QApplication, QMainWindow


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
        # Avoid passing notebook/kernel arguments through to Qt.
        _qapp = QApplication(sys.argv[:1])
        app = _qapp

    _enable_qt_gui_in_ipython()
    return app


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

    @staticmethod
    def _is_fullscreen_window_size(window_size: object) -> bool:
        """Return whether the config value requests fullscreen mode."""
        return isinstance(window_size, str) and window_size.strip().lower() == "fullscreen"

    @staticmethod
    def _primary_screen_size() -> tuple[int, int]:
        """Return the primary screen's available width and height."""
        geometry = QApplication.primaryScreen().availableGeometry()
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
            width, height = self._primary_screen_size()
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

    def _show_host_window(
        self,
        *,
        width: Optional[int] = None,
        height: Optional[int] = None,
        fullscreen: bool = False,
    ) -> None:
        """Show and activate the host window using the resolved presentation mode."""
        if width is not None and height is not None:
            self._host.resize(width, height)

        if fullscreen:
            self._host.showFullScreen()
        else:
            self._host.show()

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
