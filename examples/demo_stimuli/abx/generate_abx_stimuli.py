#%% Generate stimuli for the ABX discrimination demo
#
# An ABX trial presents two stimuli (A and B) plus X, a copy of one of them, and
# the participant decides whether X matches A or B. Discrimination is easy when
# A and B are obviously different and hard when they are nearly identical.
#
# This makes two pairs of band-emphasised noise that differ only in the *center
# frequency* of a spectral bump, level-matched so loudness is not a cue:
#   - easy_a / easy_b : far apart in frequency  -> obviously different
#   - hard_a / hard_b : close in frequency      -> subtle difference
# These match configs/abx.yml. Run this script from inside the
# examples/demo_stimuli/abx/ directory to (re)create the WAVs next to it.
#
# This is intentionally separate from the other example stimulus generators.
import pyfar as pf
import numpy as np

# Each pair is (id, center_frequency_in_Hz). Both members of a pair share the
# same noise token, so they differ only in the frequency of the spectral bump.
pairs = {
    "easy": [("easy_a", 600.0), ("easy_b", 2400.0)],   # far apart -> easy
    "hard": [("hard_a", 1000.0), ("hard_b", 1060.0)],  # close -> hard
}

# Shared peak amplitude for every stimulus. Level-matching ensures the stimuli
# differ only in frequency, and the value stays below 1 so nothing clips
# (SoundDevice rejects stimuli with |sample| >= 1).
target_amplitude = 0.7

# Bell (peaking) filter shape applied to the noise to create the spectral bump.
bell_gain_db = 12.0
bell_quality = 4.0

# Shared noise token (same underlying signal for every stimulus).
signal = pf.signals.pulsed_noise(22050, 1, 90, 1, seed=42)
signal = pf.dsp.pad_zeros(signal, 22050)

for pair_name, members in pairs.items():
    for stim_id, frequency in members:
        stimulus = pf.dsp.filter.bell(signal, frequency, bell_gain_db, bell_quality)
        # Normalise each stimulus to the same peak so only frequency varies.
        stimulus = pf.dsp.normalize(stimulus) * target_amplitude
        peak = float(np.max(np.abs(stimulus.time)))
        assert peak < 1, (
            f"{stim_id} clips (peak={peak:.3f}); lower target_amplitude")
        pf.io.write_audio(stimulus, f"{stim_id}.wav")
        print(f"wrote {stim_id}.wav  ({frequency:.0f} Hz, {pair_name} pair, peak={peak:.3f})")
