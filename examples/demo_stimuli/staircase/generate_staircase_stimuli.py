#%% Generate stimuli for the frequency-discrimination staircase demo
#
# All stimuli are band-emphasised noise that differ only in the *center
# frequency* of a spectral bump, and are level-matched so loudness is not a cue.
#
# ``stimulus_1`` is the "standard" (reference) interval. ``stimulus_2..N`` are
# "target" levels whose bump frequency differs from the standard; the targets
# are ordered from the smallest frequency difference (hardest to tell apart)
# to the largest (easiest). This matches the adaptive staircase in
# examples/staircase_n_afc.ipynb (standard = 1, levels = [2, 3, 4, ...], which
# starts easy and shrinks the frequency difference as it steps down).
#
# This is intentionally separate from examples/demo_stimuli/mushra/generate_mushra_stimuli.py,
# which generates the (timbre) stimuli used by the MUSHRA demo. Run this script
# from inside the examples/demo_stimuli/staircase/ directory to (re)create the
# WAVs next to it.
import pyfar as pf
import numpy as np

# Center frequency of the spectral bump in the standard (stimulus_1), in Hz.
standard_frequency = 1000.0

# Frequency difference of each target from the standard, in Hz, ordered from
# hardest (smallest) to easiest (largest). One target stimulus per entry, so
# these become stimulus_2, stimulus_3, ... Add/adjust entries to change the
# number of levels or their spacing. More entries give the staircase finer
# resolution; the spacing here is roughly geometric so the steps feel evenly
# spaced perceptually.
target_differences = [
    25.0, 40.0, 60.0, 90.0, 130.0, 180.0, 250.0, 330.0, 430.0, 550.0, 700.0
]

# Shared peak amplitude for every stimulus. Level-matching the stimuli ensures
# they differ only in frequency, and the value stays below 1 so nothing clips
# (SoundDevice rejects stimuli with |sample| >= 1).
target_amplitude = 0.7

# Bell (peaking) filter shape applied to the noise to create the spectral bump.
bell_gain_db = 12.0
bell_quality = 4.0

# Shared noise token. Using the same underlying signal for every stimulus means
# they differ only in the bump frequency, which is what the staircase varies.
signal = pf.signals.pulsed_noise(22050, 1, 90, 1, seed=42)
signal = pf.dsp.pad_zeros(signal, 22050)

# stimulus_1 is the standard; the rest are targets offset from it.
frequencies = [standard_frequency] + [standard_frequency + d for d in target_differences]

for n, frequency in enumerate(frequencies):
    stimulus = pf.dsp.filter.bell(signal, frequency, bell_gain_db, bell_quality)
    # Normalise each stimulus to the same peak so only frequency varies.
    stimulus = pf.dsp.normalize(stimulus) * target_amplitude
    peak = float(np.max(np.abs(stimulus.time)))
    assert peak < 1, (
        f"stimulus_{n + 1} clips (peak={peak:.3f}); lower target_amplitude")
    pf.io.write_audio(stimulus, f'stimulus_{n + 1}.wav')
    role = "standard" if n == 0 else f"target +{frequencies[n] - standard_frequency:.0f} Hz"
    print(f"wrote stimulus_{n + 1}.wav  ({frequency:.0f} Hz, {role}, peak={peak:.3f})")
