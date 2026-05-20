import pyfar as pf
import sounddevice as sd

class SounddeviceHandler:
    def __init___(stimuli):

        # load and check audio files
        sampling_rate = None

        for stimulus in stimuli.keys():

            signal = pf.io.read_audio(stimuli[stimulus]["file"])

            if sampling_rate is None:
                sampling_rate = signal.sampling_rate
            elif signal.sampling_rate != sampling_rate:
                raise ValueError(
                    "All stimuli must have the same sampling rate")

            stimuli[stimulus]["signal"] = signal
