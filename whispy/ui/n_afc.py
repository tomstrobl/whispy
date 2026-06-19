from __future__ import annotations

import os
import sys
import time
from typing import Dict, List, Optional, Any

from PyQt6.QtCore import QEventLoop, Qt
from PyQt6.QtGui import QCloseEvent, QFont
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QSizePolicy,
)

import pandas as pd

from .base import style_qpushbutton
from whispy.interfaces import StimuliHandler, SoundDevice
from whispy.utils import read_config



# Directory containing this file. Required for default configs
FILEPATH = os.path.dirname(os.path.abspath(__file__))

# Module-level QApplication reference like other UI modules
_qapp: Optional[QApplication] = None


class NAFC(QMainWindow):
    """Simple N-AFC (N-alternative forced choice) UI.

    Notes
    -----
    - Minimal, modular scaffold following the project's UI patterns.
    - Config-driven via `configs/n_afc.yml`.
    - Uses a `StimuliHandler` (default `SoundDevice`) to play stimuli by id.

    Parameters
    ----------
    screen : dict, optional
        Screen dict describing the trial (block/section/test/...). If not
        provided a minimal default is used for quick testing.
    stimuli_handler : StimuliHandler, optional
        Handler used to play stimuli. If None, `SoundDevice()` is used.
    n_afc_config : str, optional
        Path to the N-AFC YAML config. If None, `configs/n_afc.yml` from the
        package is used.
    blocking : bool, optional
        If True, block execution until the window closes (via `wait_until_closed`).
    debug : bool, optional
        If True, window close button is enabled and debug prints are emitted.
    """
    
    def __init__(
        self,
        *,
        screen: Optional[Dict[str, Any]] = None,
        stimuli_handler: Optional[StimuliHandler] = None,
        n_afc_config: Optional[str] = None,
        n_afc_ui: Optional[str] = None,
        blocking: bool = True,
        debug: bool = False,
    ) -> None:
        """Initialize the N-AFC window and trial state.

        Parameters
        ----------
        screen : dict or None, optional
            Trial description containing metadata and the ``test`` choices.
        stimuli_handler : StimuliHandler or None, optional
            Playback backend. If ``None``, ``SoundDevice`` is used.
        n_afc_config : str or None, optional
            Path to the N-AFC UI/test config file.
        blocking : bool, optional
            If ``True``, block until the window is closed.
        debug : bool, optional
            Enable debug logging and allow closing via window controls.
        """
        global _qapp
        if QApplication.instance() is None:
            _qapp = QApplication(sys.argv[:1])

        # enable Qt integration for IPython kernels (same pattern as other UIs)
        try:
            from IPython import get_ipython

            ip = get_ipython()
            if ip is not None:
                ip.enable_gui("qt6")
        except Exception:
            pass

        super().__init__()

        # default screen for quick tests
        if screen is None:
            screen = {
                "block": 0,
                "section": 0,
                "test": [1, 2, 3],
                "correct": 1,
                "trial_id": 0,
                "block_changed": True,
                "section_changed": True,
                "block_name": "Block 1",
                "section_name": "Section 1",
            }

        self.screen = screen
        self._debug = bool(debug)
        self._allow_close = bool(debug)
        self._wait_loop: Optional[QEventLoop] = None

        # stimuli handler
        if stimuli_handler is None:
            stimuli_handler = SoundDevice()
        self.stimuli_handler = stimuli_handler

        # load UI/test config
        if n_afc_config is None:
            n_afc_config = os.path.join(FILEPATH, "..", "..", "configs", "n_afc.yml")
        if n_afc_ui is None:
            n_afc_ui = os.path.join(FILEPATH, "..", "..", "configs", "design.yml")

        cfg = read_config(n_afc_config)
        cfg_ui = read_config(n_afc_ui)
        self.cfg_ui = cfg_ui

        # self._ui_cfg = cfg.get("ui", {}) if isinstance(cfg, dict) else {}
        self._test_cfg = cfg if isinstance(cfg, dict) else {}

        # window sizing
        window_size = self.cfg_ui["window_size"]
        fullscreen = isinstance(window_size, str) and window_size.strip().lower() == "fullscreen"
        if fullscreen:
            geo = QApplication.primaryScreen().availableGeometry()
            self.resize(geo.width(), geo.height())
            self.showFullScreen()
        else:
            try:
                w, h = int(window_size[0]), int(window_size[1])
            except Exception:
                w, h = 1000, 600
            self.resize(max(400, w), max(300, h))

        # UI elements
        container = QWidget(self)
        container.setStyleSheet(f"background-color: {cfg_ui['window_background_color']};")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(cfg_ui["task_spacing"])

        # task label (try to get from attributes if provided in screen)
        task_text = "N-AFC task"
        attr_name = self.screen.get("attribute", None)
        if attr_name is not None:
            # attempt to read attributes.yml like other UIs
            try:
                attributes = read_config(os.path.join(FILEPATH, "..", "..", "configs", "attributes.yml"))
                if attr_name in attributes:
                    task_text = attributes[attr_name].get("task", task_text)
            except Exception:
                pass
        
        font_color = cfg_ui["fontcolor"]
        task_label = QLabel(str(task_text).replace("\n", "  \n"), self)
        task_label.setWordWrap(True)
        task_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        task_label.setStyleSheet(f"color: {font_color};"
            "text-align: center;"
        )
        task_label.setFont(QFont("Helvetica", max(1, self.cfg_ui["fontsize"])))
        layout.addWidget(task_label, alignment=Qt.AlignmentFlag.AlignHCenter)

        # choices
        choices = list(self.screen.get("test", []))
        # allow overriding n_choices
        n_choices_cfg = self._test_cfg.get("n_choices", None)
        if n_choices_cfg is not None and len(choices) != int(n_choices_cfg):
            # do not enforce, just warn in debug
            if self._debug:
                print("warning: number of provided choices != test.n_choices")

        # Optionally shuffle choices per-trial
        if bool(self._test_cfg.get("shuffle_choices", True)):
            try:
                import random

                random.shuffle(choices)
            except Exception:
                pass

        self._choices = choices
        self._selected: Optional[Any] = None
        self._rt: Optional[float] = None
        self._selected_button: Optional[QPushButton] = None

        # creating buttons
        button_spacing = cfg_ui["button_spacing"]
        buttons_row = QWidget(self)
        br_layout = QHBoxLayout(buttons_row)
        br_layout.setContentsMargins(0, 12, 0, 12)
        br_layout.setSpacing(button_spacing)

        # choice button  design
        button_fontsize = cfg_ui["button_fontsize"]
        button_font_color = cfg_ui["button_fontcolor_initial"]
        button_color_initial = cfg_ui["button_color_initial"]
        button_border_raduis = cfg_ui["button_border_radius"]
        
        self._choice_buttons: List[QPushButton] = []
        for idx, stim_id in enumerate(self._choices, start=1):
            btn = QPushButton(str('Stimulus ' + str(idx)), self)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            style_qpushbutton(btn, button_fontsize, 
                              button_font_color, button_color_initial, button_border_raduis)
            btn.clicked.connect(self._make_choice_handler(stim_id, btn))
            br_layout.addWidget(btn)
            self._choice_buttons.append(btn)

        self._apply_choice_button_styles()

        layout.addWidget(buttons_row, alignment=Qt.AlignmentFlag.AlignHCenter)

        submit_label = QLabel(self.cfg_ui["submit_hint"], self)
        submit_label.setWordWrap(True)
        submit_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        submit_label.setStyleSheet(
            f"color: {font_color};"
            "text-align: center;"
        )
        submit_label.setFont(QFont("Helvetica", max(1, self.cfg_ui["fontsize"])))
        layout.addWidget(submit_label, alignment=Qt.AlignmentFlag.AlignHCenter)

        self._submit_button = QPushButton(str(self.cfg_ui["submit_button_text"]), self)
        self._submit_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._submit_button.setFont(QFont("Helvetica", max(1, self.cfg_ui["button_fontsize"])))
        self._submit_button.setEnabled(False)
        
        self._submit_button.clicked.connect(self._on_submit_clicked)
        layout.addWidget(self._submit_button, alignment=Qt.AlignmentFlag.AlignHCenter)
                
        self._apply_submit_button_styles()  

        self.setCentralWidget(container)

        # show window
        self.show()
        self.raise_()
        self.activateWindow()

        # start time for reaction time measurement
        self._start_time = time.time()

        if blocking:
            self.wait_until_closed()

    def _make_choice_handler(self, stim_id: Any, button: QPushButton):
        """Create a click handler for one choice button.

        Parameters
        ----------
        stim_id : Any
            Stimulus identifier represented by the button.
        button : QPushButton
            Button widget associated with the stimulus.

        Returns
        -------
        callable
            Slot function that updates selection state and triggers playback.
        """
        # Accept arbitrary args because Qt's clicked signal may pass a 'checked' boolean
        def handler(*_args) -> None:
            """Handle a choice click, including preview playback.

            Parameters
            ----------
            *_args : Any
                Optional Qt signal payload (ignored).
            """
            # Store current selection; final logging happens on submit.
            self._selected = stim_id
            self._selected_button = button
            self._submit_button.setEnabled(True)
            self._apply_submit_button_styles()
            self._apply_choice_button_styles()
            if self._debug:
                # log the value and its type to help debugging mismatched keys
                print(f"Selected: {repr(stim_id)} (type={type(stim_id).__name__})")

            # Try playback but don't let playback errors prevent closing the UI
            try:
                self.stimuli_handler.play(stim_id)
            except Exception as e:
                # Try common fallback: SoundDevice often uses string keys from YAML
                tried_fallback = False
                try:
                    if isinstance(self.stimuli_handler, SoundDevice):
                        tried_fallback = True
                        self.stimuli_handler.play(str(stim_id))
                except Exception as e2:
                    if self._debug:
                        if tried_fallback:
                            print(f"playback failed for {repr(stim_id)} (fallback tried): {e2}")
                        else:
                            print(f"playback failed for {repr(stim_id)}: {e}")
                else:
                    if self._debug:
                        print(f"playback succeeded for fallback key {repr(str(stim_id))}")

        return handler

    def _on_submit_clicked(self) -> None:
        """Finalize the currently selected choice and close the trial window."""
        if self._selected is None:
            return

        # Reaction time is measured for the confirmed answer.
        self._rt = time.time() - self._start_time
        if self._debug:
            print(f"Submitted: {repr(self._selected)} (rt={self._rt:.3f}s)")

        self._allow_close = True
        self.close()

    def _apply_submit_button_styles(self) -> None:
        """Apply submit button colors from the UI config."""
        default_button_color = self.cfg_ui["window_background_color"]
        default_fontcolor = self.cfg_ui["submit_button_text_color"]
        enabled_button_color = self.cfg_ui["button_color_clicked"]
        enabled_fontcolor = self.cfg_ui["button_fontcolor"]
        button_border_radius = self.cfg_ui["button_border_radius"]

        bg = enabled_button_color if self._submit_button.isEnabled() else default_button_color
        fg = enabled_fontcolor if self._submit_button.isEnabled() else default_fontcolor

        self._submit_button.setStyleSheet(
            f"background-color: {bg}; color: {fg}; border: 1px solid #d0d7de; border-radius: {button_border_radius}; padding: 6px 12px;"
        )

    def _apply_choice_button_styles(self) -> None:
        """Apply default/selected color styles to all choice buttons."""
        button_color_initial =  self.cfg_ui["button_color_initial"]
        button_fontcolor_initial = self.cfg_ui["button_fontcolor_initial"]
        button_color_clicked = self.cfg_ui["button_color_clicked"]
        button_fontcolor = self.cfg_ui["button_fontcolor"]
        button_border_radius = self.cfg_ui["button_border_radius"]
        hover_color = self.cfg_ui["button_hover_background_color"]

        for btn in self._choice_buttons:
            if btn is self._selected_button:
                btn.setStyleSheet(f"""
                QPushButton {{
                            background-color: {button_color_clicked}; 
                            color: {button_fontcolor};
                            }}
                            """)
            else:
                btn.setStyleSheet(f"""
                QPushButton {{
                            background-color: {button_color_initial};
                            color: {button_fontcolor_initial};
                            border-radius: {button_border_radius}
                            }}
                QPushButton:hover {{
                            background-color: {hover_color};
                            }}
                            """)
  
        

        btn.adjustSize()

    def get_results(self) -> pd.DataFrame:
        """Return a one-row DataFrame with trial result.

        Columns:
        - block, section, trial_id, block_name, section_name
        - choices : list of stimulus ids (order shown to participant)
        - correct : stimulus id marked as correct in screen (optional)
        - selected : stimulus id selected by participant (or None)
        - correct_bool : bool if correct info present
        - rt : reaction time in seconds (float or None)
        """
        row = {
            k: self.screen.get(k) for k in ["block", "section", "trial_id", "block_name", "section_name"]
        }
        row.update(
            {
                "choices": list(self._choices),
                "correct": self.screen.get("correct", None),
                "selected": self._selected,
                "correct_bool": None if self.screen.get("correct", None) is None else (self._selected == self.screen.get("correct", None)),
                "rt": float(self._rt) if self._rt is not None else None,
            }
        )

        df = pd.DataFrame([row])
        return df

    def wait_until_closed(self) -> None:
        """Block until the window has been closed."""
        if not self.isVisible():
            return
        if self._wait_loop is None:
            self._wait_loop = QEventLoop(self)
        self._wait_loop.exec()

    def closeEvent(self, event: QCloseEvent) -> None:
        """Handle close requests and release the internal wait loop.

        Parameters
        ----------
        event : QCloseEvent
            Close event emitted by Qt.
        """
        if not self._allow_close:
            event.ignore()
            return
        if self._wait_loop is not None and self._wait_loop.isRunning():
            self._wait_loop.quit()
        super().closeEvent(event)

