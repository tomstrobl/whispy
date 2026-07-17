from __future__ import annotations

from typing import Optional, Union

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget

from whispy.utils import load_design

from .base import _BaseUIWindow


class ExperimentHost(_BaseUIWindow):
    """Persistent window hosting every screen of one experiment.

    Open the host once at the start of a full experiment and pass it as
    ``parent=`` to every UI shown afterwards (``InfoWindow``,
    ``Questionnaire``, ``DragAndDropMUSHRA``, ``NAFC``, ``ABX``,
    ``ScaleTest``). Each UI then swaps its content into this window instead
    of opening (and closing) an OS window of its own, so the participant
    never sees the desktop between two screens. Call ``close()`` once after
    the last screen.

    Parameters
    ----------
    design : str or dict, optional
        Overrides for the global theme (``configs/design.yml``) — a YAML
        path or an already-loaded dict, merged the same way every UI merges
        its design. The host uses the ``window_background_color``,
        ``window_size`` and ``screen`` keys.
    debug : bool, optional
        If ``False`` (the default), the native close button is disabled and
        the window can only be closed by calling ``close()``.
    """

    def __init__(
        self,
        *,
        design: Optional[Union[str, dict]] = None,
        debug: bool = False,
    ) -> None:
        super().__init__(blocking=False, debug=bool(debug))

        cfg = load_design(design)
        self._screen_setting = cfg.get("screen")
        background_color = str(cfg.get("window_background_color", "#2b2b2b"))

        self.setWindowTitle("")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        if not debug:
            self.disable_close_button()

        # Blank, theme-colored content shown until the first UI swaps its
        # own central widget in.
        placeholder = QWidget()
        placeholder.setStyleSheet(f"background-color: {background_color};")
        self.setCentralWidget(placeholder)

        width, height, fullscreen = self._resolve_window_size(
            cfg.get("window_size", "fullscreen"),
            fallback=(1000, 700),
            minimum_size=(400, 300),
        )
        self._show_host_window(
            width=width,
            height=height,
            fullscreen=fullscreen,
            background_color=background_color,
        )
