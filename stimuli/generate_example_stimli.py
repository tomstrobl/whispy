#%% Generate example stimuli for demos
import pyfar as pf
import numpy as np

signal = pf.signals.pulsed_noise(22050, 1, 90, 1, seed=42)
signal = pf.dsp.pad_zeros(signal, 22050)
signal = pf.dsp.normalize(signal) * .5

for n, f in enumerate([200, 800, 1600]):
    stimulus = pf.dsp.filter.bell(signal, f, 6, 1)
    assert np.max(np.abs(stimulus.time)) < 1
    pf.io.write_audio(stimulus, f'stimulus_{n+1}.wav')
