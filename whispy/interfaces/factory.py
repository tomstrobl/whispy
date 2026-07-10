from __future__ import annotations

from typing import Optional

from whispy.utils import read_config

from .stimuli_handlers import StimuliHandler, SoundDevice, OSCHandler


def build_stimuli_handler(
        stimuli, base_dir: Optional[str] = None, *,
        loop: bool = True, ip: Optional[str] = None,
        port: Optional[int] = None) -> StimuliHandler:
    """Build the ``StimuliHandler`` selected by the config's ``output:`` key.

    Reads ``output:`` from ``stimuli`` (``"sounddevice"`` [default] or
    ``"osc"``) and constructs the matching handler, so a listening test can
    switch between audio playback and OSC messages by changing a single
    config key instead of any Python code.

    Parameters
    ----------
    stimuli : str or dict
        The combined config (path or already-loaded dict) containing the
        ``output:`` key plus the ``SoundDevice:`` and/or ``OSCHandler:``
        block matching the selected backend.
    base_dir : str, optional
        Folder holding the WAVs referenced under ``SoundDevice:``. Required
        when ``output: sounddevice`` (see ``SoundDevice``); ignored for
        ``output: osc``.
    loop : bool, optional
        Forwarded to ``SoundDevice``; ignored for ``output: osc``.
    ip, port : optional
        Forwarded to ``OSCHandler``, overriding its config; ignored for
        ``output: sounddevice``.

    Returns
    -------
    StimuliHandler
        A ``SoundDevice`` or ``OSCHandler`` instance.

    Raises
    ------
    ValueError
        If ``output:`` is set to anything other than ``"sounddevice"`` or
        ``"osc"``.

    Examples
    --------
    .. code-block:: python

        import whispy

        # `output: osc` in config_path switches to OSC instead of audio;
        # every UI class (NAFC, ABX, ...) takes the handler unchanged.
        handler = whispy.interfaces.build_stimuli_handler(
            config_path, stimuli_dir, loop=False)
    """
    cfg = read_config(stimuli)
    output = str(cfg.get("output", "sounddevice")).strip().lower() \
        if isinstance(cfg, dict) else "sounddevice"

    if output == "sounddevice":
        return SoundDevice(stimuli=cfg, base_dir=base_dir, loop=loop)

    if output == "osc":
        kwargs = {}
        if ip is not None:
            kwargs["ip"] = ip
        if port is not None:
            kwargs["port"] = port
        return OSCHandler(stimuli=cfg, **kwargs)

    raise ValueError(
        f"Unknown output backend {output!r}: expected 'sounddevice' or 'osc'")
