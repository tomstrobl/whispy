from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from whispy.utils import read_config

import pyfar as pf
import numpy as np
import sounddevice as sd
import os

from pythonosc.udp_client import SimpleUDPClient


class StimuliHandler(ABC):
    """Abstract base class for all stimulus handlers (playback backends)."""
    @abstractmethod
    def play(self, stimulus: str) -> None:
        """Play a configured stimulus.

        Parameters
        ----------
        stimulus : str
            Stimulus identifier as defined in the handler configuration.
        """
        raise NotImplementedError

    @abstractmethod
    def stop(self, stimulus: Optional[str] = None) -> None:
        """Stop playback.

        Parameters
        ----------
        stimulus : str or None, optional
            Optional stimulus identifier for handlers that require it.
        """
        raise NotImplementedError


class SoundDevice(StimuliHandler):

    def __init__(self, stimuli=None, base_dir=None, loop=True):
        """Initialize the sounddevice backend and load configured stimuli.

        Parameters
        ----------
        stimuli : str or dict
            A config containing a ``SoundDevice:`` block (mapping each stimulus
            id to ``{file: ...}``) — either a path to the YAML file or an
            already-loaded dict (e.g. a combined experiment config). Required.
        base_dir : str
            Base directory holding the audio files referenced under
            ``SoundDevice:``. Required.
        loop : bool, optional
            If ``True``, playback loops continuously.

        Raises
        ------
        ValueError
            If ``stimuli`` or ``base_dir`` is ``None``, if the config has no
            ``SoundDevice:`` block, or if loaded stimuli clip (maximum absolute
            value equals 1) or do not share the same sampling rate.
        """

        # load config file
        if stimuli is None:
            raise ValueError(
                "SoundDevice needs a stimuli config: pass stimuli=<path or "
                "dict> containing a `SoundDevice:` block (e.g. your combined "
                "experiment config).")

        self.stimuli = read_config(stimuli)

        if 'SoundDevice' not in self.stimuli:
            raise ValueError("Stimuli are not defined for SoundDevice")

        self.stimuli = self.stimuli["SoundDevice"]

        # base directory holding the audio files referenced under SoundDevice:
        if base_dir is None:
            raise ValueError(
                "SoundDevice needs base_dir: the folder holding the WAVs "
                "referenced under `SoundDevice:`.")

        # load and check audio files
        self.sampling_rate = None

        for s_id in self.stimuli.keys():

            # load file
            file = self.stimuli[s_id]["file"]
            signal = pf.io.read_audio(os.path.join(
                base_dir, file))

            # check for clipping
            if np.max(np.abs(signal.time)) >= 1:
                raise ValueError((
                    f'detected clipping in {file} '
                    '(maximum absolute amplitude equals 1)'))

            # check for equal sampling rate
            if self.sampling_rate is None:
                self.sampling_rate = signal.sampling_rate
            elif signal.sampling_rate != self.sampling_rate:
                raise ValueError(
                    "All stimuli must have the same sampling rate")

            self.stimuli[s_id]["signal"] = signal

        # sounddevice settings
        sd.default.samplerate = self.sampling_rate
        self.loop = loop

    def play(self, stimulus: str) -> None:
        """
        Play stimulus.

        Parameters
        ----------
        stimulus : str
            The name of the stimulus as defined in the stimuli configuration
        """
        sd.stop()
        sd.play(self.stimuli[stimulus]['signal'].time.T, loop=self.loop)

    def stop(self, stimulus: str | None = None) -> None:
        """
        Stop playback.

        Parameters
        ----------
        stimulus : str, optional
            Ignored by this backend (sounddevice stops all playback at once);
            accepted so all handlers share the same call signature.
        """
        # NOTE: `stimulus` is not required here to stop the playback. But
        #       it might be required by other handlers that must share the same
        #       call signature.
        sd.stop()


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

        if not isinstance(cfg, dict) or 'OSCHandler' not in cfg:
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
