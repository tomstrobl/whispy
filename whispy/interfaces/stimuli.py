from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from whispy.utils import read_config

import pyfar as pf
import numpy as np
import sounddevice as sd
import os


class StimuliHandler(ABC):
    """Abstract base class for all StimuliHandler."""
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
        stimulus : str
            The name of the stimulus as defined in the stimuli configuration
        """
        # NOTE: `stimulus` is not required here to stop the playback. But
        #       it might be required by other handlers that must share the same
        #       call signature.
        sd.stop()
