from __future__ import annotations

from typing import Optional

from whispy.utils import read_config

from pythonosc.udp_client import SimpleUDPClient

from .stimuli import StimuliHandler


class OSCHandler(StimuliHandler):
    """Send OSC (Open Sound Control) messages instead of playing audio.

    A drop-in ``StimuliHandler`` that maps each ``play(stimulus)`` call to
    sending one configured OSC message (address + optional arguments) over
    UDP. Sends only — there is no OSC server/receiving side. Config-driven
    like ``SoundDevice``, so a listening test can switch between audio
    playback and OSC control via a single config key (see
    :func:`whispy.interfaces.build_stimuli_handler`).

    Parameters
    ----------
    stimuli : str or dict
        A config containing an ``OSCHandler:`` block — either a path to the
        YAML file or an already-loaded dict (e.g. a combined experiment
        config). The block maps each stimulus id to ``{address: ...,
        args: [...]}`` (``args`` optional, defaults to no arguments) under a
        nested ``stimuli:`` key, plus optional ``ip``/``port``/
        ``stop_address``/``stop_args`` connection settings. Required.
    ip : str, optional
        OSC target host. Overrides the config's ``ip:``; falls back to
        ``"127.0.0.1"`` if neither is set.
    port : int, optional
        OSC target port. Overrides the config's ``port:``; falls back to
        ``9000`` if neither is set.

    Raises
    ------
    ValueError
        If ``stimuli`` is ``None``, if the config has no ``OSCHandler:``
        block, or if a stimulus entry has no ``address``.

    Examples
    --------
    .. code-block:: yaml

        OSCHandler:
          ip: "127.0.0.1"
          port: 9000
          stop_address: "/whispy/stop"
          stimuli:
            stim_1:
              address: "/whispy/play"
              args: [1]
            stim_2:
              address: "/whispy/play"
              args: [2]
    """

    def __init__(
            self, stimuli=None, ip: Optional[str] = None,
            port: Optional[int] = None):

        if stimuli is None:
            raise ValueError(
                "OSCHandler needs a stimuli config: pass stimuli=<path or "
                "dict> containing an `OSCHandler:` block (e.g. your combined "
                "experiment config).")

        cfg = read_config(stimuli)

        if 'OSCHandler' not in cfg:
            raise ValueError("Stimuli are not defined for OSCHandler")

        cfg = cfg["OSCHandler"]

        self._ip = str(ip if ip is not None else cfg.get("ip", "127.0.0.1"))
        self._port = int(port if port is not None else cfg.get("port", 9000))
        self._stop_address = cfg.get("stop_address")
        self._stop_args = list(cfg.get("stop_args", []))

        # per-stimulus OSC address (+ optional args), mirroring SoundDevice's
        # per-stimulus `file:` mapping
        self.stimuli = cfg.get("stimuli", {})
        for stim_id, entry in self.stimuli.items():
            if not isinstance(entry, dict) or "address" not in entry:
                raise ValueError(
                    f"OSCHandler stimulus {stim_id!r} needs an `address:`")

        self._client = SimpleUDPClient(self._ip, self._port)

    def play(self, stimulus: str) -> None:
        """
        Send the OSC message configured for ``stimulus``.

        Parameters
        ----------
        stimulus : str
            The name of the stimulus as defined under ``OSCHandler.stimuli``
            in the stimuli configuration.
        """
        entry = self.stimuli[stimulus]
        self._send(entry["address"], entry.get("args", []))

    def stop(self, stimulus: str | None = None) -> None:
        """
        Send the configured stop message, if any.

        Parameters
        ----------
        stimulus : str, optional
            Ignored by this backend (mirrors ``SoundDevice.stop``, which also
            stops all playback at once regardless of which stimulus is
            passed); accepted so all handlers share the same call signature.
        """
        # NOTE: `stop_address` is optional - an OSC trigger message often has
        # no natural "stop" counterpart, so a config without one is a no-op
        # rather than an error.
        if self._stop_address is not None:
            self._send(self._stop_address, self._stop_args)

    def _send(self, address: str, args: list) -> None:
        self._client.send_message(address, list(args))
